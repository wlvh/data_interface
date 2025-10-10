"""Trace 与 Span 契约模型，支撑任务级回放与指标采集。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from apps.backend.compat import ConfigDict, Field, model_validator

from apps.backend.contracts.metadata import ContractModel


def _ensure_utc(dt: datetime, field_name: str) -> None:
    """确保时间戳包含 UTC 时区。"""

    if dt.tzinfo is None:
        message = f"{field_name} 必须包含 UTC 时区。"
        raise ValueError(message)
    if dt.tzinfo.utcoffset(dt) != timezone.utc.utcoffset(dt):
        message = f"{field_name} 必须为 UTC 时间。"
        raise ValueError(message)


class SpanSLO(ContractModel):
    """定义单个节点的服务目标。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回 SLO 契约 Schema 名称。"""

        return "span_slo"

    max_duration_ms: int = Field(
        description="节点允许的最大耗时（毫秒）。",
        ge=0,
    )
    max_retries: int = Field(
        description="节点允许的最大重试次数。",
        ge=0,
    )
    failure_isolation_required: bool = Field(
        description="节点失败时是否必须防止级联影响。",
    )


class SpanMetrics(ContractModel):
    """节点执行的指标快照。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回 Span 指标 Schema 名称。"""

        return "span_metrics"

    duration_ms: int = Field(
        description="节点执行耗时（毫秒）。",
        ge=0,
    )
    retry_count: int = Field(
        description="节点已经发生的重试次数。",
        ge=0,
    )
    failure_category: Optional[str] = Field(
        default=None,
        description="失败原因分类，成功时为空。",
    )
    failure_isolation_ratio: float = Field(
        description="失败隔离比例，范围 [0, 1]。",
        ge=0.0,
        le=1.0,
    )


class TraceSpan(ContractModel):
    """Trace 树中的单个 Span。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回 Trace Span Schema 名称。"""

        return "trace_span"

    span_id: str = Field(description="Span 唯一标识。", min_length=1)
    parent_span_id: Optional[str] = Field(
        default=None,
        description="父 Span 标识，根节点为空。",
    )
    node_name: str = Field(description="状态图节点名称。", min_length=1)
    agent_name: str = Field(description="执行该节点的 Agent 名称。", min_length=1)
    status: Literal["success", "failed"] = Field(description="节点执行状态。")
    started_at: datetime = Field(description="Span 开始时间（UTC）。")
    completed_at: datetime = Field(description="Span 完成时间（UTC）。")
    metrics: SpanMetrics = Field(description="节点执行指标。")
    slo: SpanSLO = Field(description="节点目标值。")
    model_name: Optional[str] = Field(
        default=None,
        description="调用的模型名称，非模型节点为空。",
    )
    prompt_version: Optional[str] = Field(
        default=None,
        description="提示词版本标识，非模型节点为空。",
    )

    @model_validator(mode="after")
    def ensure_temporal_order(self) -> "TraceSpan":
        """验证时间顺序并强制 UTC。"""

        _ensure_utc(dt=self.started_at, field_name="started_at")
        _ensure_utc(dt=self.completed_at, field_name="completed_at")
        if self.completed_at < self.started_at:
            message = "completed_at 不能早于 started_at。"
            raise ValueError(message)
        return self


class TraceRecord(ContractModel):
    """任务级 Trace 记录。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回 Trace 记录 Schema 名称。"""

        return "trace_record"

    task_id: str = Field(description="任务标识。", min_length=1)
    dataset_id: str = Field(description="关联数据集 ID。", min_length=1)
    created_at: datetime = Field(description="Trace 创建时间（UTC）。")
    spans: List[TraceSpan] = Field(
        description="按执行顺序排列的 Span 列表。",
        json_schema_extra={"minItems": 1},
    )

    @model_validator(mode="after")
    def ensure_created_at(self) -> "TraceRecord":
        """校验创建时间为 UTC。"""

        _ensure_utc(dt=self.created_at, field_name="created_at")
        if not self.spans:
            raise ValueError("Trace 至少需要一个 Span。")
        return self
