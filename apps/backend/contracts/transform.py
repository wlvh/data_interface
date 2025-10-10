"""数据变换相关契约模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from apps.backend.compat import ConfigDict, Field, model_validator

from apps.backend.contracts.metadata import VersionedContractModel


def _ensure_utc(dt: datetime, field_name: str) -> None:
    """确保时间戳包含 UTC 时区信息。"""

    if dt.tzinfo is None:
        message = f"{field_name} 必须包含 UTC 时区。"
        raise ValueError(message)
    if dt.tzinfo.utcoffset(dt) != timezone.utc.utcoffset(dt):
        message = f"{field_name} 必须为 UTC 时间。"
        raise ValueError(message)


class TransformLog(VersionedContractModel):
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


class TableColumn(VersionedContractModel):
    """描述变换产出表的单列表结构。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回列契约的 Schema 名称。"""

        return "table_column"

    column_name: str = Field(description="列名称。", min_length=1)
    data_type: str = Field(description="列的数据类型描述，例如 integer、number。", min_length=1)
    semantic_role: str = Field(
        description="列的语义角色，用于下游建模，例如 measure、dimension。",
        min_length=1,
    )
    nullable: bool = Field(description="是否允许缺失值。")
    description: Optional[str] = Field(
        default=None,
        description="列的补充说明或业务含义。",
    )


class TableSample(VersionedContractModel):
    """表样本，提供可回放的示例行集合。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回表样本的 Schema 名称。"""

        return "table_sample"

    rows: List[Dict[str, str]] = Field(
        description="样本行集合，所有值序列化为字符串。",
        max_length=50,
        default_factory=list,
    )

    @model_validator(mode="after")
    def validate_rows(self) -> "TableSample":
        """保证样本集合内所有行具有相同的列集合。"""

        if not self.rows:
            return self
        reference = set(self.rows[0].keys())
        for row in self.rows[1:]:
            if set(row.keys()) != reference:
                raise ValueError("样本行必须共享一致的列集合。")
        return self


class PreparedTableStats(VersionedContractModel):
    """变换执行前的统计信息，用于限制与审计。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回统计契约名称。"""

        return "prepared_table_stats"

    row_count: int = Field(description="输入数据的行数估计。", ge=0)
    estimated_bytes: Optional[int] = Field(
        default=None,
        description="输入数据的估算体积（字节）。",
        ge=0,
    )
    distinct_row_count: Optional[int] = Field(
        default=None,
        description="唯一行数估计，用于去重评估。",
        ge=0,
    )


class PreparedTableLimits(VersionedContractModel):
    """执行前的限制条件，用于保障资源消耗。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回限制契约名称。"""

        return "prepared_table_limits"

    row_limit: Optional[int] = Field(
        default=None,
        description="单次执行允许处理的最大行数，None 表示无限制。",
        ge=1,
    )
    timeout_ms: Optional[int] = Field(
        default=None,
        description="执行允许的最长耗时（毫秒）。",
        ge=1,
    )
    sample_limit: Optional[int] = Field(
        default=None,
        description="采样用于回放的最大行数。",
        ge=1,
    )


class PreparedTable(VersionedContractModel):
    """变换执行前的准备上下文，描述输入与约束。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回 PreparedTable 契约名称。"""

        return "prepared_table"

    prepared_table_id: str = Field(description="准备阶段输出的唯一标识。", min_length=1)
    source_id: str = Field(description="源数据标识，用于追踪血缘。", min_length=1)
    transform_id: str = Field(description="计划中引用的变换 ID。", min_length=1)
    schema: List[TableColumn] = Field(
        description="输入数据的列结构。",
        json_schema_extra={"minItems": 1},
    )
    sample: TableSample = Field(description="输入数据的摘样结果。")
    stats: PreparedTableStats = Field(description="输入数据的统计特征。")
    limits: PreparedTableLimits = Field(description="执行约束条件。")

    @model_validator(mode="after")
    def ensure_schema(self) -> "PreparedTable":
        """确保 schema 与样本列集合一致。"""

        if not self.schema:
            raise ValueError("schema 至少需要一个字段。")
        schema_columns = {column.column_name for column in self.schema}
        if self.sample.rows:
            sample_columns = set(self.sample.rows[0].keys())
            if sample_columns != schema_columns:
                message = "sample.rows 的列集合必须与 schema 列集合一致。"
                raise ValueError(message)
        return self


class OutputMetrics(VersionedContractModel):
    """变换执行后的指标数据，用于 SLO 与审计。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回输出指标契约名称。"""

        return "output_metrics"

    duration_ms: int = Field(description="执行耗时（毫秒）。", ge=0)
    rows_in: int = Field(description="输入行数。", ge=0)
    rows_out: int = Field(description="输出行数。", ge=0)
    retry_count: int = Field(description="执行过程中触发的重试次数。", ge=0)
    row_limit_applied: bool = Field(description="是否命中行数限制。")
    abort_reason: Optional[str] = Field(
        default=None,
        description="若执行提前结束或失败，此处记录原因。",
    )


class OutputTable(VersionedContractModel):
    """数据变换输出的表格快照。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回输出表契约名称。"""

        return "output_table"

    output_table_id: str = Field(description="输出表唯一标识。", min_length=1)
    prepared_table_id: str = Field(description="关联的 PreparedTable 标识。", min_length=1)
    schema: List[TableColumn] = Field(
        description="输出表的列结构。",
        json_schema_extra={"minItems": 1},
    )
    preview: TableSample = Field(description="输出数据的样本视图。")
    metrics: OutputMetrics = Field(description="执行后的指标数据。")
    logs: List[TransformLog] = Field(
        description="执行过程中的日志集合。",
        default_factory=list,
    )
    generated_at: datetime = Field(description="输出表生成时间（UTC）。")

    @model_validator(mode="after")
    def validate_output(self) -> "OutputTable":
        """校验记录的合法性与时间戳。"""

        _ensure_utc(dt=self.generated_at, field_name="generated_at")
        if not self.schema:
            raise ValueError("schema 不能为空。")
        schema_columns = {column.column_name for column in self.schema}
        if self.preview.rows:
            preview_columns = set(self.preview.rows[0].keys())
            if preview_columns != schema_columns:
                raise ValueError("preview.rows 与 schema 列集合不一致。")
        if self.metrics.rows_out < 0:
            raise ValueError("rows_out 不能为负数。")
        return self
