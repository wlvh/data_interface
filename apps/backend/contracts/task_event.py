"""SSE 任务事件契约，确保回放与落盘格式一致。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Literal

from apps.backend.compat import ConfigDict, Field, model_validator

from apps.backend.contracts.metadata import VersionedContractModel


def _ensure_utc(dt: datetime, field_name: str) -> None:
    """校验给定时间戳为 UTC，避免回放时区错乱。"""

    if dt.tzinfo is None:
        message = f"{field_name} 必须包含 UTC 时区信息。"
        raise ValueError(message)
    if dt.tzinfo.utcoffset(dt) != timezone.utc.utcoffset(dt):
        message = f"{field_name} 必须为 UTC 时间。"
        raise ValueError(message)


class TaskEvent(VersionedContractModel):
    """标准化的 SSE 事件结构，支持断线重放。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回事件契约的 Schema 名称。"""

        return "task_event"

    type: Literal["started", "node_completed", "completed", "failed", "chart_replaced", "chart_reverted"] = Field(
        description="事件类型，覆盖任务全生命周期。"
    )
    ts: datetime = Field(description="事件生成时间（UTC）。")
    sse_seq: int = Field(description="SSE 推送序号，单调递增。", ge=0)
    payload: Dict[str, object] = Field(
        default_factory=dict,
        description="事件附带的结构化载荷。",
    )

    @model_validator(mode="after")
    def validate_timestamp(self) -> "TaskEvent":
        """校验时间戳为 UTC。"""

        _ensure_utc(dt=self.ts, field_name="ts")
        return self
