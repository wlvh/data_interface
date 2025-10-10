"""数据变换执行 Agent。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.backend.agents.base import Agent, AgentContext, AgentOutcome
from apps.backend.contracts.dataset_profile import DatasetProfile
from apps.backend.contracts.metadata import SCHEMA_VERSION
from apps.backend.contracts.plan import Plan, TransformDraft
from apps.backend.contracts.transform import (
    OutputMetrics,
    OutputTable,
    PreparedTable,
    PreparedTableLimits,
    PreparedTableStats,
    TableColumn,
    TableSample,
    TransformLog,
)
from apps.backend.contracts.trace import SpanSLO

LOGGER = logging.getLogger(__name__)

_PD_MODULE: Optional[Any] = None


def _get_pandas() -> Any:
    """延迟加载 pandas，避免在不支持环境中提前导入。"""

    global _PD_MODULE
    if _PD_MODULE is None:
        import pandas as pd  # noqa: WPS433 - 延迟导入

        _PD_MODULE = pd
    return _PD_MODULE


def _estimate_bytes(path: Path) -> Optional[int]:
    """返回输入文件的字节大小，若路径不存在则返回 None。"""

    try:
        return path.stat().st_size
    except FileNotFoundError:
        return None


def _infer_series_type(series: Any) -> str:
    """根据 pandas Series 推断字段类型。"""

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


@dataclass(frozen=True)
class TransformPayload:
    """变换执行所需输入。"""

    dataset_profile: DatasetProfile
    plan: Plan
    dataset_path: Path
    sample_limit: int


@dataclass(frozen=True)
class TransformArtifacts:
    """变换阶段产出的复合对象，包含准备表与输出表。"""

    prepared_table: PreparedTable
    output_table: OutputTable


def _ensure_transform_function(namespace: dict) -> callable:
    """保证提供的命名空间中存在 transform 函数。"""

    if "transform" not in namespace:
        message = "变换代码必须定义 transform 函数。"
        raise ValueError(message)
    transform = namespace["transform"]
    if not callable(transform):
        message = "transform 必须是可调用对象。"
        raise ValueError(message)
    return transform


class TransformExecutionAgent(Agent):
    """执行计划中的数据变换。"""

    name = "transform_executor"
    slo = SpanSLO(
        max_duration_ms=4000,
        max_retries=0,
        failure_isolation_required=True,
    )

    def run(self, context: AgentContext, payload: TransformPayload) -> AgentOutcome:
        """运行变换并返回准备表与输出表。"""

        span_id = context.trace_recorder.start_span(
            operation="transform.execute",
            agent_name=self.name,
            slo=self.slo,
            parent_span_id=None,
            model_name=None,
            prompt_version=None,
        )
        transform_draft = payload.plan.transform_drafts[0]
        if transform_draft.language != "python":
            message = f"暂不支持语言 {transform_draft.language}"
            raise ValueError(message)
        pd = _get_pandas()
        dataframe = pd.read_csv(payload.dataset_path)
        exec_started_at = context.clock.now()
        namespace: dict = {}
        logs: List[TransformLog] = []
        role_mapping = {item.field_name: item.semantic_role for item in payload.plan.field_plan}

        # 构建 PreparedTable，确保输入上下文可回放。
        prepared_columns: List[TableColumn] = []
        for column in dataframe.columns:
            series = dataframe[column]
            data_type = _infer_series_type(series=series)
            semantic_role = role_mapping.get(column, "dimension")
            isna_result = series.isna()
            if hasattr(isna_result, "sum"):
                nullable = bool(isna_result.sum())
            else:
                nullable = any(value is None for value in series)
            prepared_columns.append(
                TableColumn(
                    column_name=column,
                    data_type=data_type,
                    semantic_role=semantic_role,
                    nullable=nullable,
                    description=None,
                ),
            )
        prepared_sample_rows: List[Dict[str, str]] = []
        for _, row in dataframe.head(payload.sample_limit).iterrows():
            prepared_sample_rows.append({column: str(row[column]) for column in dataframe.columns})
        prepared_table = PreparedTable(
            prepared_table_id=f"prepared_{transform_draft.transform_id}",
            source_id=payload.dataset_profile.dataset_id,
            transform_id=str(transform_draft.transform_id),
            schema=prepared_columns,
            sample=TableSample(rows=prepared_sample_rows),
            stats=PreparedTableStats(
                row_count=int(dataframe.shape[0]),
                estimated_bytes=_estimate_bytes(payload.dataset_path),
                distinct_row_count=None,
            ),
            limits=PreparedTableLimits(
                row_limit=None,
                timeout_ms=self.slo.max_duration_ms,
                sample_limit=payload.sample_limit,
            ),
        )
        context.trace_recorder.update_span(
            span_id=span_id,
            rows_in=int(dataframe.shape[0]),
            dataset_hash=payload.dataset_profile.hash_digest,
            schema_version=SCHEMA_VERSION,
        )
        try:
            exec(transform_draft.code, {"pd": pd}, namespace)  # noqa: S102 - 受控代码来源
            transform_fn = _ensure_transform_function(namespace=namespace)
            result_df = transform_fn(df=dataframe)
        except Exception as error:  # noqa: BLE001 - 需要捕获以记录日志
            log_entry = TransformLog(
                level="error",
                message=str(error),
                timestamp=context.clock.now(),
            )
            logs.append(log_entry)
            context.trace_recorder.finish_span(
                span_id=span_id,
                status="failed",
                failure_category=error.__class__.__name__,
                failure_isolation_ratio=0.0,
            )
            raise
        if not isinstance(result_df, pd.DataFrame):
            message = "transform 函数必须返回 pandas.DataFrame。"
            raise ValueError(message)
        exec_completed_at = context.clock.now()
        sample_rows: List[Dict[str, str]] = []
        for _, row in result_df.head(payload.sample_limit).iterrows():
            sample_rows.append({column: str(row[column]) for column in result_df.columns})
        columns: List[TableColumn] = []
        for column in result_df.columns:
            series = result_df[column]
            data_type = _infer_series_type(series=series)
            semantic_role = role_mapping.get(column, "dimension")
            isna_result = series.isna()
            if hasattr(isna_result, "sum"):
                nullable = bool(isna_result.sum())
            else:
                nullable = any(value is None for value in series)
            columns.append(
                TableColumn(
                    column_name=column,
                    data_type=data_type,
                    semantic_role=semantic_role,
                    nullable=nullable,
                    description=None,
                ),
            )
        table_sample = TableSample(rows=sample_rows)
        metrics = OutputMetrics(
            duration_ms=int((exec_completed_at - exec_started_at).total_seconds() * 1000),
            rows_in=int(dataframe.shape[0]),
            rows_out=int(result_df.shape[0]),
            retry_count=0,
            row_limit_applied=bool(result_df.shape[0] > payload.sample_limit),
            abort_reason=None,
        )
        output_table = OutputTable(
            output_table_id="derived_main",
            prepared_table_id=prepared_table.prepared_table_id,
            schema=columns,
            preview=table_sample,
            metrics=metrics,
            logs=logs,
            generated_at=context.clock.now(),
        )
        context.trace_recorder.update_span(
            span_id=span_id,
            rows_out=int(result_df.shape[0]),
        )
        trace_span = context.trace_recorder.finish_span(
            span_id=span_id,
            status="success",
            failure_category=None,
            failure_isolation_ratio=1.0,
        )
        LOGGER.info(
            "数据变换完成",
            extra={
                "task_id": context.task_id,
                "dataset_id": context.dataset_id,
                "rows": output_table.metrics.rows_out,
            },
        )
        return AgentOutcome(
            output=TransformArtifacts(
                prepared_table=prepared_table,
                output_table=output_table,
            ),
            span_id=span_id,
            trace_span=trace_span,
        )
