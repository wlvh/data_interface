"""数据变换相关契约模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from apps.backend.compat import ConfigDict, Field, model_validator

from apps.backend.contracts.metadata import ContractModel


def _ensure_utc(dt: datetime, field_name: str) -> None:
    """确保时间戳包含 UTC 时区信息。"""

    if dt.tzinfo is None:
        message = f"{field_name} 必须包含 UTC 时区。"
        raise ValueError(message)
    if dt.tzinfo.utcoffset(dt) != timezone.utc.utcoffset(dt):
        message = f"{field_name} 必须为 UTC 时间。"
        raise ValueError(message)


class TransformLog(ContractModel):
    """变换执行过程中的日志记录。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回日志契约名称。"""

        return "transform_log"

    level: str = Field(description="日志级别。", min_length=1)
    message: str = Field(description="日志内容。", min_length=1)
    timestamp: datetime = Field(description="UTC 时间的日志时间戳。")

    @model_validator(mode="after")
    def validate_timestamp(self) -> "TransformLog":
        """校验日志时间戳为 UTC。"""

        _ensure_utc(dt=self.timestamp, field_name="timestamp")
        return self


class OutputTable(ContractModel):
    """数据变换输出的表格快照。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回输出表契约名称。"""

        return "output_table"

    table_id: str = Field(description="输出表的唯一标识。", min_length=1)
    source_plan_id: Optional[str] = Field(
        default=None,
        description="产生该表的计划 ID，如无可为空。",
    )
    row_count: int = Field(description="输出表的总记录数。", ge=0)
    columns: List[str] = Field(
        description="输出表的列名称列表，按顺序排列。",
        json_schema_extra={"minItems": 1},
    )
    sample_rows: List[Dict[str, str]] = Field(
        description="用于展示的样本行集合。",
        max_length=50,
        default_factory=list,
    )
    generated_at: datetime = Field(description="表格生成时间（UTC）。")
    logs: List[TransformLog] = Field(
        description="执行过程中的日志集合。",
        default_factory=list,
    )

    @model_validator(mode="after")
    def validate_rows(self) -> "OutputTable":
        """校验样本行字段数量与列信息一致，并确保时间戳为 UTC。"""

        _ensure_utc(dt=self.generated_at, field_name="generated_at")
        if not self.columns:
            raise ValueError("columns 不能为空。")
        for row in self.sample_rows:
            if set(row.keys()) != set(self.columns):
                message = "sample_rows 中的列集合必须与 columns 完全一致。"
                raise ValueError(message)
        return self
