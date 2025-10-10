"""契约模型与 JSONSchema 的同步校验测试。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from apps.backend.contracts.chart_spec import ChartA11y, ChartLayout, ChartSpec
from apps.backend.contracts.chart_template import ChartEncoding, ChartTemplate
from apps.backend.contracts.dataset_profile import DatasetProfile, DatasetSampling, DatasetSummary
from apps.backend.contracts.encoding_patch import EncodingPatch, EncodingPatchOp
from apps.backend.contracts.explanation import ExplanationArtifact
from apps.backend.contracts.fields import FieldSchema, FieldStatistics, ValueRange
from apps.backend.contracts.plan import (
    ChartChannelMapping,
    ChartPlanItem,
    ExplainOutline,
    FieldPlanItem,
    Plan,
    PlanAssumption,
    TransformDraft,
)
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
from apps.backend.contracts.trace import SpanEvent, SpanMetrics, SpanSLO, TraceRecord, TraceSpan
from pydantic import ValidationError


def _load_schema(name: str) -> dict:
    """读取落盘的 JSONSchema。"""

    schema_path = Path("apps/backend/contracts/schema") / name
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _strip_documentation(payload: object) -> object:
    """剥离 Schema 中的描述性字段，聚焦结构一致性。"""

    if isinstance(payload, dict):
        filtered = {}
        for key, value in payload.items():
            if key in {"title", "description", "examples"}:
                continue
            filtered[key] = _strip_documentation(value)
        return filtered
    if isinstance(payload, list):
        return [_strip_documentation(item) for item in payload]
    return payload


def _normalize_schema(schema: dict) -> dict:
    """对 schema 进行排序，避免键顺序导致的断言失败。"""

    stripped = _strip_documentation(schema)
    return json.loads(json.dumps(stripped, sort_keys=True))


def test_field_schema_matches_json() -> None:
    """确保字段契约的 JSONSchema 与模型保持一致。"""

    generated = _normalize_schema(FieldSchema.model_json_schema())
    stored = _normalize_schema(_load_schema("fields.schema.json"))
    assert generated == stored


def test_dataset_profile_schema_matches_json() -> None:
    """确保数据集画像契约的 JSONSchema 与模型保持一致。"""

    generated = _normalize_schema(DatasetProfile.model_json_schema())
    stored = _normalize_schema(_load_schema("dataset_profile.schema.json"))
    assert generated == stored


def test_chart_template_schema_matches_json() -> None:
    """确保图表模板契约的 JSONSchema 与模型保持一致。"""

    generated = _normalize_schema(ChartTemplate.model_json_schema())
    stored = _normalize_schema(_load_schema("chart_template.schema.json"))
    assert generated == stored


def test_plan_schema_matches_json() -> None:
    """确保计划契约的 JSONSchema 与模型保持一致。"""

    generated = _normalize_schema(Plan.model_json_schema())
    stored = _normalize_schema(_load_schema("plan.schema.json"))
    assert generated == stored


def test_trace_schema_matches_json() -> None:
    """确保 Trace 契约的 JSONSchema 与模型保持一致。"""

    generated = _normalize_schema(TraceRecord.model_json_schema())
    stored = _normalize_schema(_load_schema("trace.schema.json"))
    assert generated == stored


def test_explanation_schema_matches_json() -> None:
    """确保解释契约的 JSONSchema 与模型保持一致。"""

    generated = _normalize_schema(ExplanationArtifact.model_json_schema())
    stored = _normalize_schema(_load_schema("explanation_artifact.json"))
    assert generated == stored


def test_prepared_table_schema_matches_json() -> None:
    """确保 PreparedTable 契约的 JSONSchema 与模型保持一致。"""

    generated = _normalize_schema(PreparedTable.model_json_schema())
    stored = _normalize_schema(_load_schema("prepared_table.json"))
    assert generated == stored


def test_output_table_schema_matches_json() -> None:
    """确保输出表契约的 JSONSchema 与模型保持一致。"""

    generated = _normalize_schema(OutputTable.model_json_schema())
    stored = _normalize_schema(_load_schema("output_table.json"))
    assert generated == stored


def test_chart_spec_schema_matches_json() -> None:
    """确保 ChartSpec 契约的 JSONSchema 与模型保持一致。"""

    generated = _normalize_schema(ChartSpec.model_json_schema())
    stored = _normalize_schema(_load_schema("chart_spec.json"))
    assert generated == stored


def test_transform_log_schema_matches_json() -> None:
    """确保变换日志契约的 JSONSchema 与模型保持一致。"""

    generated = _normalize_schema(TransformLog.model_json_schema())
    stored = _normalize_schema(_load_schema("transform_log.schema.json"))
    assert generated == stored


def test_encoding_patch_schema_matches_json() -> None:
    """确保编码补丁契约的 JSONSchema 与模型保持一致。"""

    generated = _normalize_schema(EncodingPatch.model_json_schema())
    stored = _normalize_schema(_load_schema("encoding_patch.json"))
    assert generated == stored


def _build_field_schema() -> FieldSchema:
    """构造用于测试的字段契约。"""

    statistics = FieldStatistics(
        total_count=100,
        missing_count=2,
        distinct_count=10,
        missing_ratio=0.02,
        entropy=1.5,
    )
    value_range = ValueRange(
        minimum=0.0,
        maximum=100.0,
    )
    return FieldSchema(
        name="weekly_sales",
        path=[],
        data_type="number",
        semantic_type="measure",
        nullable=True,
        description="周销售额",
        tags=["finance"],
        sample_values=["132.5", "98.0"],
        value_range=value_range,
        statistics=statistics,
        temporal_granularity_candidates=[],
    )


def test_field_schema_invalid_semantic_type() -> None:
    """非法语义类型应该触发校验失败。"""

    statistics = FieldStatistics(
        total_count=10,
        missing_count=0,
        distinct_count=5,
        missing_ratio=0.0,
    )
    with pytest.raises(ValidationError):
        FieldSchema(
            name="invalid",
            path=[],
            data_type="string",
            semantic_type="measure",  # 与 sample 限制冲突
            nullable=False,
            sample_values=["超过", "限制", "示例", "过多"],
            statistics=statistics,
            temporal_granularity_candidates=[],
        )


def test_dataset_profile_consistency_checks() -> None:
    """画像与摘要不一致时应触发错误。"""

    field_schema = _build_field_schema()
    summary = DatasetSummary(
        dataset_id="ds_1",
        dataset_version="v1",
        generated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        row_count=50,
        sampling=DatasetSampling(strategy="head", size=5, seed=0),
        fields=[field_schema],
        sample_rows=[{"weekly_sales": "100"}],
    )
    with pytest.raises(ValidationError):
        DatasetProfile(
            dataset_id="ds_1",
            dataset_version="v1",
            name="测试数据集",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            profiled_at=datetime(2023, 12, 31, tzinfo=timezone.utc),
            row_count=40,
            hash_digest="abcdef12",
            summary=summary,
        )


def test_dataset_summary_rejects_naive_datetime() -> None:
    """生成时间缺失 UTC 时区时应触发异常。"""

    statistics = FieldStatistics(
        total_count=10,
        missing_count=0,
        distinct_count=5,
        missing_ratio=0.0,
    )
    field_schema = FieldSchema(
        name="created_at",
        path=[],
        data_type="datetime",
        semantic_type="temporal",
        nullable=False,
        statistics=statistics,
        temporal_granularity_candidates=["day"],
    )
    with pytest.raises(ValidationError):
        DatasetSummary(
            dataset_id="ds", 
            dataset_version="v1",
            generated_at=datetime(2024, 1, 1),
            row_count=1,
            sampling=DatasetSampling(strategy="head", size=5, seed=0),
            fields=[field_schema],
        )


def test_field_statistics_ratio_validation() -> None:
    """缺失率与缺失数量不匹配时应抛出错误。"""

    with pytest.raises(ValidationError):
        FieldStatistics(
            total_count=10,
            missing_count=1,
            missing_ratio=0.5,
        )


def test_dataset_profile_requires_utc() -> None:
    """画像时间若缺失 UTC 时区则拒绝。"""

    field_schema = _build_field_schema()
    summary = DatasetSummary(
        dataset_id="ds_1",
        dataset_version="v1",
        generated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        row_count=50,
        sampling=DatasetSampling(strategy="head", size=5, seed=0),
        fields=[field_schema],
    )
    with pytest.raises(ValidationError):
        DatasetProfile(
            dataset_id="ds_1",
            dataset_version="v1",
            name="测试数据集",
            created_at=datetime(2024, 1, 1),
            profiled_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
            row_count=100,
            hash_digest="abcdef12",
            summary=summary,
        )


def test_chart_template_duplicate_channel_forbidden() -> None:
    """除 tooltip/detail 外的通道不允许重复。"""

    encoding_x = ChartEncoding(
        channel="x",
        semantic_role="dimension",
        required=True,
        allow_multiple=False,
    )
    encoding_y = ChartEncoding(
        channel="x",
        semantic_role="measure",
        required=False,
        allow_multiple=False,
    )
    with pytest.raises(ValidationError):
        ChartTemplate(
            template_id="tpl_duplicate",
            version="1.0.0",
            name="重复通道",
            mark="bar",
            encodings=[encoding_x, encoding_y],
            supported_engines=["vega-lite"],
        )


def test_chart_template_default_config_serializable() -> None:
    """默认配置不可序列化时需要立即失败。"""

    encoding = ChartEncoding(
        channel="x",
        semantic_role="dimension",
        required=True,
        allow_multiple=False,
    )
    with pytest.raises(ValidationError):
        ChartTemplate(
            template_id="tpl_bad_config",
            version="1.0.0",
            name="非法配置",
            mark="bar",
            encodings=[encoding],
            default_config={"bad": {1, 2}},
            supported_engines=["vega-lite"],
        )


def test_chart_template_required_channels_unique() -> None:
    """模板中重复的必填通道应触发异常。"""

    encoding = ChartEncoding(
        channel="x",
        semantic_role="dimension",
        required=True,
        allow_multiple=False,
    )
    with pytest.raises(ValidationError):
        ChartTemplate(
            template_id="tpl_bar",
            version="1.0.0",
            name="柱状图",
            mark="bar",
            encodings=[encoding, encoding],
            supported_engines=["vega-lite"],
        )


def test_dataset_profile_success() -> None:
    """构造一份合法的画像模型确保校验通过。"""

    field_schema = _build_field_schema()
    summary = DatasetSummary(
        dataset_id="ds_1",
        dataset_version="v1",
        generated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        row_count=50,
        sampling=DatasetSampling(strategy="head", size=5, seed=0),
        fields=[field_schema],
        sample_rows=[{"weekly_sales": "100"}],
        warnings=["缺失值较高"],
    )
    profile = DatasetProfile(
        dataset_id="ds_1",
        dataset_version="v1",
        name="测试数据集",
        created_at=datetime(2023, 12, 31, tzinfo=timezone.utc),
        profiled_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        row_count=100,
        hash_digest="abcdef12",
        summary=summary,
        profiling_notes=["扫描成功"],
    )
    assert profile.summary.dataset_id == "ds_1"
