"""数据扫描 Agent，实现字段画像与摘要生成。"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from math import log
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.backend.agents.base import Agent, AgentContext, AgentOutcome
from apps.backend.contracts.dataset_profile import DatasetProfile, DatasetSampling, DatasetSummary
from apps.backend.contracts.fields import FieldSchema, FieldStatistics, TemporalGranularity, ValueRange
from apps.backend.contracts.metadata import SCHEMA_VERSION
from apps.backend.contracts.trace import SpanSLO

_PD_MODULE: Optional[Any] = None


def _get_pandas() -> Any:
    """延迟加载 pandas，避免在不支持环境中提前导入。"""

    global _PD_MODULE
    if _PD_MODULE is None:
        import pandas as pd  # noqa: WPS433 - 延迟导入

        _PD_MODULE = pd
    return _PD_MODULE

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanPayload:
    """数据扫描所需的输入参数。"""

    dataset_id: str
    dataset_name: str
    dataset_version: str
    path: Path
    sample_limit: int


def _infer_data_type(series: Any) -> str:
    """根据 Pandas dtype 推断基础数据类型。"""

    pd = _get_pandas()
    dtype = series.dtype
    if pd.api.types.is_integer_dtype(dtype):
        return "integer"
    if pd.api.types.is_numeric_dtype(dtype):
        return "number"
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    return "string"


def _infer_semantic_type(column_name: str, data_type: str) -> str:
    """根据字段名与基础类型推断语义类型。"""

    lowered = column_name.lower()
    if any(keyword in lowered for keyword in {"date", "time", "at"}):
        return "temporal"
    if data_type in {"integer", "number"}:
        return "measure"
    if "id" in lowered:
        return "identifier"
    return "dimension"


def _build_value_range(series: Any, data_type: str) -> ValueRange | None:
    """根据字段类型构建值域描述。"""

    if data_type in {"integer", "number"}:
        minimum = float(series.min())
        maximum = float(series.max())
        return ValueRange(minimum=minimum, maximum=maximum)
    non_null = series.dropna()
    if non_null.empty:
        return None
    value_counts = non_null.value_counts()
    top_values = list(value_counts.index[:10])
    top_counts = list(value_counts.values[:10])
    categories = [str(item) for item in top_values]
    frequencies = [int(value) for value in top_counts]
    return ValueRange(categories=categories, top_k_frequencies=frequencies)


def _calculate_entropy(series: Any) -> float | None:
    """计算离散分布的信息熵。"""

    non_null = series.dropna()
    if non_null.empty:
        return None
    probabilities = non_null.value_counts(normalize=True)
    entropy = 0.0
    for probability in probabilities:
        entropy -= probability * log(probability, 2)
    return entropy


def _recommend_temporal_granularities(series: Any) -> List[TemporalGranularity]:
    """根据时间字段的频率推断合适的粒度候选。"""

    pd = _get_pandas()
    non_null = series.dropna()
    if non_null.empty:
        return ["day"]
    if not hasattr(pd, "to_datetime"):
        return ["day", "week", "month"]
    try:
        converted = pd.to_datetime(non_null)
    except Exception as error:  # noqa: BLE001 - 保持 fail fast，抛出显式错误
        message = "时间字段解析失败，无法推断时间粒度。"
        raise ValueError(message) from error
    if not hasattr(non_null, "sort_values") or not hasattr(non_null, "diff"):
        return ["day", "week", "month"]
    sorted_values = converted.sort_values()
    diffs = sorted_values.diff().dropna()
    if diffs.empty:
        return ["day"]
    min_diff = diffs.min()
    candidates: List[TemporalGranularity] = []
    if min_diff <= pd.Timedelta(minutes=1):
        candidates.extend(["minute", "hour", "day"])
    elif min_diff <= pd.Timedelta(hours=1):
        candidates.extend(["hour", "day", "week"])
    elif min_diff <= pd.Timedelta(days=1):
        candidates.extend(["day", "week", "month"])
    else:
        candidates.extend(["week", "month", "quarter", "year"])
    # 去重并保持顺序。
    seen: set[str] = set()
    ordered: List[TemporalGranularity] = []
    for item in candidates:
        if item not in seen:
            ordered.append(item)  # type: ignore[arg-type]
            seen.add(item)
    if not ordered:
        ordered.append("day")  # type: ignore[arg-type]
    return ordered


def _build_field_schema(series: Any, field_name: str, total_count: int) -> FieldSchema:
    """将单个字段转换为 FieldSchema。"""

    data_type = _infer_data_type(series=series)
    semantic_type = _infer_semantic_type(column_name=field_name, data_type=data_type)
    if semantic_type == "temporal" and data_type != "datetime":
        pd = _get_pandas()
        try:
            series = pd.to_datetime(series, utc=True)
        except Exception as error:  # noqa: BLE001 - 保持 fail fast
            message = f"字段 {field_name} 无法解析为 datetime。"
            raise ValueError(message) from error
        data_type = "datetime"
    missing_count = int(series.isna().sum())
    missing_ratio = missing_count / total_count if total_count > 0 else 0.0
    distinct_count = int(series.nunique(dropna=True))
    entropy = _calculate_entropy(series=series)
    statistics = FieldStatistics(
        total_count=total_count,
        missing_count=missing_count,
        distinct_count=distinct_count,
        missing_ratio=missing_ratio,
        entropy=entropy,
    )
    sample_values = []
    # 选取非空样本值用于展示。
    non_null = series.dropna()
    limit = 3 if semantic_type == "measure" else 5
    for value in non_null.head(limit):
        sample_values.append(str(value))
    nullable = missing_count > 0
    value_range = _build_value_range(series=series, data_type=data_type)
    temporal_candidates: List[TemporalGranularity] = []
    if semantic_type == "temporal":
        temporal_candidates = _recommend_temporal_granularities(series=series)
    field_schema = FieldSchema(
        name=field_name,
        path=[],
        data_type=data_type,
        semantic_type=semantic_type,
        nullable=nullable,
        sample_values=sample_values,
        value_range=value_range,
        statistics=statistics,
        temporal_granularity_candidates=temporal_candidates,
    )
    return field_schema


class DatasetScannerAgent(Agent):
    """读取数据源并生成画像的 Agent。"""

    name = "dataset_scanner"
    slo = SpanSLO(
        max_duration_ms=5000,
        max_retries=0,
        failure_isolation_required=True,
    )

    def run(self, context: AgentContext, payload: ScanPayload) -> AgentOutcome:
        """执行扫描，返回 DatasetProfile。

        Parameters
        ----------
        context: AgentContext
            任务上下文，包含 Trace 记录器。
        payload: ScanPayload
            扫描所需的参数集合。

        Returns
        -------
        AgentOutcome
            输出 DatasetProfile 并携带 Trace Span。
        """

        LOGGER.info(
            "开始数据扫描",
            extra={
                "task_id": context.task_id,
                "dataset_id": payload.dataset_id,
            },
        )
        span_id = context.trace_recorder.start_span(
            operation="data.scan",
            agent_name=self.name,
            slo=self.slo,
            parent_span_id=context.parent_span_id,
            model_name=None,
            prompt_version=None,
        )
        pd = _get_pandas()
        dataframe = pd.read_csv(payload.path)
        # 计算基础数据维度。
        row_count = int(dataframe.shape[0])
        field_names = list(dataframe.columns)
        field_schemas: List[FieldSchema] = []
        for column in field_names:
            series = dataframe[column]
            field_schema = _build_field_schema(
                series=series,
                field_name=column,
                total_count=row_count,
            )
            field_schemas.append(field_schema)
        sample_rows: List[Dict[str, str]] = []
        for _, row in dataframe.head(payload.sample_limit).iterrows():
            sample_row: Dict[str, str] = {}
            for column in field_names:
                sample_row[column] = str(row[column])
            sample_rows.append(sample_row)
        warnings: List[str] = []
        for field_schema in field_schemas:
            if field_schema.statistics.missing_ratio > 0.3:
                warning = f"{field_schema.name} 缺失率较高"
                warnings.append(warning)
        generated_at = context.clock.now()
        summary = DatasetSummary(
            dataset_id=payload.dataset_id,
            dataset_version=payload.dataset_version,
            generated_at=generated_at,
            row_count=row_count,
            sampling=DatasetSampling(
                strategy="head",
                size=payload.sample_limit,
                seed=0,
            ),
            fields=field_schemas,
            sample_rows=sample_rows,
            warnings=warnings,
        )
        hash_digest = hashlib.sha256(payload.path.read_bytes()).hexdigest()
        context.trace_recorder.update_span(
            span_id=span_id,
            rows_in=row_count,
            rows_out=row_count,
            dataset_hash=hash_digest,
            schema_version=SCHEMA_VERSION,
        )
        context.trace_recorder.record_event(
            span_id=span_id,
            event_type="sample",
            detail={
                "strategy": summary.sampling.strategy,
                "size": summary.sampling.size,
                "seed": summary.sampling.seed,
            },
        )
        profile = DatasetProfile(
            dataset_id=payload.dataset_id,
            dataset_version=payload.dataset_version,
            name=payload.dataset_name,
            created_at=generated_at,
            profiled_at=generated_at,
            row_count=row_count,
            hash_digest=hash_digest,
            summary=summary,
            profiling_notes=warnings,
        )
        trace_span = context.trace_recorder.finish_span(
            span_id=span_id,
            status="success",
            failure_category=None,
            failure_isolation_ratio=1.0,
            status_detail={
                "dataset_hash": hash_digest,
                "row_count": row_count,
            },
        )
        LOGGER.info(
            "数据扫描完成",
            extra={
                "task_id": context.task_id,
                "dataset_id": payload.dataset_id,
                "fields": len(field_schemas),
            },
        )
        return AgentOutcome(
            output=profile,
            span_id=span_id,
            trace_span=trace_span,
        )
