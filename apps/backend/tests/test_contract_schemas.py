"""契约模型与 JSONSchema 的同步校验测试。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from apps.backend.contracts.chart_template import ChartEncoding, ChartTemplate
from apps.backend.contracts.dataset_profile import DatasetProfile, DatasetSummary
from apps.backend.contracts.fields import FieldSchema, FieldStatistics, ValueRange
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
        )


def test_dataset_profile_consistency_checks() -> None:
    """画像与摘要不一致时应触发错误。"""

    field_schema = _build_field_schema()
    summary = DatasetSummary(
        dataset_id="ds_1",
        dataset_version="v1",
        generated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        row_count=50,
        field_count=1,
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
            field_count=2,
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
    )
    with pytest.raises(ValidationError):
        DatasetSummary(
            dataset_id="ds", 
            dataset_version="v1",
            generated_at=datetime(2024, 1, 1),
            row_count=1,
            field_count=1,
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
        field_count=1,
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
            field_count=1,
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
        field_count=1,
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
        field_count=1,
        hash_digest="abcdef12",
        summary=summary,
        profiling_notes=["扫描成功"],
    )
    assert profile.summary.dataset_id == "ds_1"

