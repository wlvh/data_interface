"""数据集概览与概要契约模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from apps.backend.compat import ConfigDict, Field, model_validator

from apps.backend.contracts.fields import FieldSchema
from apps.backend.contracts.metadata import VersionedContractModel


def _ensure_utc(dt: datetime, field_name: str) -> None:
    """校验给定的时间戳为 UTC 时区。"""

    if dt.tzinfo is None:
        raise ValueError(f"{field_name} 必须包含时区信息，并使用 UTC。")
    if dt.tzinfo.utcoffset(dt) != timezone.utc.utcoffset(dt):
        raise ValueError(f"{field_name} 必须为 UTC 时间。")


class DatasetSampling(VersionedContractModel):
    """描述摘要生成时采用的采样策略。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回采样契约的 Schema 名称。"""

        return "dataset_sampling"

    strategy: str = Field(
        description="采样策略名称，例如 head、random、stratified。",
        min_length=1,
    )
    size: int = Field(
        description="采样的目标行数。",
        ge=1,
    )
    seed: int = Field(
        description="采样所用的随机种子，固定后即可回放。",
    )


class DatasetSummary(VersionedContractModel):
    """面向 LLM 和前端的轻量级数据摘要。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回用于标识摘要契约的 Schema 名称。"""

        return "dataset_summary"

    dataset_id: str = Field(description="数据集的唯一标识。", min_length=1)
    dataset_version: str = Field(description="数据集版本号，用于缓存控制。", min_length=1)
    generated_at: datetime = Field(description="UTC 时间的摘要生成时间戳。")
    row_count: int = Field(description="摘要统计的记录数。", ge=0)
    sampling: DatasetSampling = Field(description="生成摘要时采用的采样策略。")
    fields: List[FieldSchema] = Field(
        description="字段契约集合，用于驱动图表与规划。",
        json_schema_extra={"minItems": 1},
    )
    sample_rows: List[Dict[str, str]] = Field(
        default_factory=list,
        description="用于上下文示例的样本行，所有值均序列化为字符串。",
        max_length=20,
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="扫描过程中产生的告警信息，按时间顺序排列。",
    )

    @model_validator(mode="after")
    def validate_fields(self) -> "DatasetSummary":
        """校验字段数量、示例行一致性以及 UTC 时间。"""

        _ensure_utc(dt=self.generated_at, field_name="generated_at")
        if not self.fields:
            raise ValueError("fields 至少需要一个字段。")
        field_names = [field.name for field in self.fields]
        for sample in self.sample_rows:
            if set(sample.keys()) != set(field_names):
                raise ValueError("sample_rows 中的列集合必须与字段列表完全一致。")
        return self


class DatasetProfile(VersionedContractModel):
    """完整的数据集画像契约。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回用于标识画像契约的 Schema 名称。"""

        return "dataset_profile"

    dataset_id: str = Field(description="数据集的唯一标识。", min_length=1)
    dataset_version: str = Field(description="数据集版本号。", min_length=1)
    name: str = Field(description="数据集名称。", min_length=1)
    description: Optional[str] = Field(
        default=None,
        description="数据集的业务描述。",
    )
    source: Optional[str] = Field(
        default=None,
        description="数据来源或上传渠道。",
    )
    created_at: datetime = Field(description="数据集创建时间（UTC）。")
    profiled_at: datetime = Field(description="画像生成时间（UTC）。")
    row_count: int = Field(description="全量记录数。", ge=0)
    total_bytes: Optional[int] = Field(
        default=None,
        description="原始数据集大小（字节）。",
        ge=0,
    )
    hash_digest: str = Field(
        description="用于缓存和重放的哈希摘要。",
        min_length=8,
    )
    summary: DatasetSummary = Field(description="轻量级摘要，用于传递给模型。")
    profiling_notes: List[str] = Field(
        default_factory=list,
        description="画像过程中人工或自动记录的备注。",
    )

    @model_validator(mode="after")
    def validate_profile(self) -> "DatasetProfile":
        """确保概要信息与摘要保持一致，并强制 UTC。"""

        _ensure_utc(dt=self.created_at, field_name="created_at")
        _ensure_utc(dt=self.profiled_at, field_name="profiled_at")
        if self.profiled_at < self.created_at:
            raise ValueError("profiled_at 不能早于 created_at。")
        if self.summary.dataset_id != self.dataset_id:
            raise ValueError("summary.dataset_id 必须与 dataset_id 相同。")
        if self.summary.dataset_version != self.dataset_version:
            raise ValueError("summary.dataset_version 必须与 dataset_version 相同。")
        if self.summary.row_count > self.row_count:
            raise ValueError("摘要的行数不能超过完整画像记录数。")
        return self
