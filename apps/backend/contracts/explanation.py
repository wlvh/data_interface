"""解释 Agent 契约，封装 Markdown 输出。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from apps.backend.compat import ConfigDict, Field, model_validator

from apps.backend.contracts.metadata import VersionedContractModel


def _ensure_utc(dt: datetime, field_name: str) -> None:
    """校验时间字段必须为 UTC。"""

    if dt.tzinfo is None:
        message = f"{field_name} 必须包含 UTC 时区。"
        raise ValueError(message)
    if dt.tzinfo.utcoffset(dt) != timezone.utc.utcoffset(dt):
        message = f"{field_name} 必须为 UTC 时间。"
        raise ValueError(message)


class ExplanationArtifact(VersionedContractModel):
    """解释 Agent 输出的结构化结果。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回契约名称。"""

        return "explanation_artifact"

    markdown: str = Field(description="面向用户展示的 Markdown 说明。", min_length=1)
    key_points: List[str] = Field(
        description="解释重点摘要列表。",
    )
    generated_at: datetime = Field(description="生成时间（UTC）。")

    @model_validator(mode="after")
    def ensure_utc(self) -> "ExplanationArtifact":
        """校验生成时间为 UTC。"""

        _ensure_utc(dt=self.generated_at, field_name="generated_at")
        if not self.key_points:
            raise ValueError("key_points 不能为空。")
        return self
