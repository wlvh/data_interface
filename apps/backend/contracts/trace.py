"""Trace 与 Span 契约模型，支撑任务级回放与指标采集。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from apps.backend.compat import ConfigDict, Field, model_validator

from apps.backend.contracts.metadata import VersionedContractModel


def _ensure_utc(dt: datetime, field_name: str) -> None:
    """确保时间戳包含 UTC 时区。"""

    if dt.tzinfo is None:
        message = f"{field_name} 必须包含 UTC 时区。"
        raise ValueError(message)
    if dt.tzinfo.utcoffset(dt) != timezone.utc.utcoffset(dt):
        message = f"{field_name} 必须为 UTC 时间。"
        raise ValueError(message)


class SpanSLO(VersionedContractModel):
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


class SpanEvent(VersionedContractModel):
    """Span 生命周期内的离散事件记录。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回 SpanEvent 契约名称。"""

        return "span_event"

    event_type: Literal[
        "start",
        "cache_hit",
        "retry",
        "abort",
        "fallback",
        "emit_partial",
        "success",
    ] = Field(description="事件类型。")
    timestamp: datetime = Field(description="事件发生时间（UTC）。")
    detail: Optional[str] = Field(
        default=None,
        description="事件附带的信息。",
    )

    @model_validator(mode="after")
    def ensure_utc(self) -> "SpanEvent":
        """强制事件时间为 UTC。"""

        _ensure_utc(dt=self.timestamp, field_name="timestamp")
        return self


class SpanMetrics(VersionedContractModel):
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
    rows_in: Optional[int] = Field(
        default=None,
        description="输入行数，缺失表示未记录。",
        ge=0,
    )
    rows_out: Optional[int] = Field(
        default=None,
        description="输出行数，缺失表示未记录。",
        ge=0,
    )


class TraceSpan(VersionedContractModel):
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
    operation: str = Field(
        description="状态图节点名称，建议遵循动词.名词格式，例如 data.scan。",
        min_length=1,
    )
    agent_name: str = Field(description="执行该节点的 Agent 名称。", min_length=1)
    status: Literal["success", "failed", "aborted"] = Field(description="节点执行状态。")
    started_at: datetime = Field(description="Span 开始时间（UTC）。")
    slo: SpanSLO = Field(description="节点目标值。")
    metrics: SpanMetrics = Field(description="节点执行指标。")
    model_name: Optional[str] = Field(
        default=None,
        description="调用的模型名称，非模型节点为空。",
    )
    prompt_version: Optional[str] = Field(
        default=None,
        description="提示词版本标识，非模型节点为空。",
    )
    dataset_hash: Optional[str] = Field(
        default=None,
        description="输入数据集的哈希摘要，用于回放一致性校验。",
    )
    schema_version: Optional[str] = Field(
        default=None,
        description="运行时契约 Schema 版本，便于迁移。",
    )
    abort_reason: Optional[str] = Field(
        default=None,
        description="若状态为 aborted，则记录终止原因。",
    )
    error_class: Optional[str] = Field(
        default=None,
        description="失败时的错误分类。",
    )
    fallback_path: Optional[str] = Field(
        default=None,
        description="触发后备策略时记录所走的分支。",
    )
    sse_seq: Optional[int] = Field(
        default=None,
        description="若通过 SSE 推送，该 Span 对应的序号。",
        ge=0,
    )
    events: List[SpanEvent] = Field(
        description="Span 生命周期内发生的事件集合。",
        default_factory=list,
    )

    @model_validator(mode="after")
    def ensure_temporal_order(self) -> "TraceSpan":
        """验证时间戳与事件顺序，并强制 UTC。"""

        _ensure_utc(dt=self.started_at, field_name="started_at")
        if "." not in self.operation:
            raise ValueError("operation 需包含语义分段，例如 data.scan。")
        if self.events:
            # 确保事件时间不早于开始时间
            earliest = min(event.timestamp for event in self.events)
            if earliest < self.started_at:
                raise ValueError("事件时间不能早于 started_at。")
        return self


class TraceRecord(VersionedContractModel):
    """任务级 Trace 记录。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回 Trace 记录 Schema 名称。"""

        return "trace_record"

    trace_id: str = Field(description="Trace 唯一标识。", min_length=1)
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
