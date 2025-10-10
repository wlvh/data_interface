"""会话导出契约，封装可回放的数据与图表上下文。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from apps.backend.compat import ConfigDict, Field, model_validator

from apps.backend.contracts.chart_spec import ChartSpec
from apps.backend.contracts.dataset_profile import DatasetProfile
from apps.backend.contracts.encoding_patch import EncodingPatch
from apps.backend.contracts.metadata import VersionedContractModel
from apps.backend.contracts.plan import Plan
from apps.backend.contracts.recommendation import RecommendationList
from apps.backend.contracts.trace import TraceRecord
from apps.backend.contracts.transform import OutputTable, PreparedTable


def _ensure_utc(timestamp: datetime, field_name: str) -> None:
    """确保导出时间使用 UTC。"""

    if timestamp.tzinfo is None:
        raise ValueError(f"{field_name} 必须包含 UTC 时区信息。")
    if timestamp.tzinfo.utcoffset(timestamp) != timezone.utc.utcoffset(timestamp):
        raise ValueError(f"{field_name} 必须为 UTC 时间。")


class SessionBundle(VersionedContractModel):
    """封装一次分析会话的完整上下文，支持离线回放。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回会话包契约名称。"""

        return "session_bundle"

    bundle_id: str = Field(description="会话包唯一标识。", min_length=1)
    task_id: str = Field(description="关联的任务 ID。", min_length=1)
    mode: Literal["full", "read_only"] = Field(description="打包模式，full 表示包含所有资产。")
    generated_at: datetime = Field(description="包生成时间（UTC）。")
    dataset_profile: Optional[DatasetProfile] = Field(
        default=None,
        description="可选的数据集画像，用于离线回放。",
    )
    plan: Plan = Field(description="最终的分析计划。")
    prepared_table: PreparedTable = Field(description="清理后的 PreparedTable 快照。")
    output_table: OutputTable = Field(description="清理后的输出表快照。")
    chart_specs: List[ChartSpec] = Field(
        description="会话涉及的图表集合，首个元素为当前展示图。",
        json_schema_extra={"minItems": 1},
    )
    encoding_patches: List[EncodingPatch] = Field(
        default_factory=list,
        description="应用过的编码补丁历史。",
    )
    recommendations: Optional[RecommendationList] = Field(
        default=None,
        description="对应的推荐集合，便于恢复多视图。"
    )
    trace: TraceRecord = Field(description="Trace 记录，用于回放链路。")
    notes: List[str] = Field(
        default_factory=list,
        description="导出过程中的补充说明或降级原因。",
    )
    data_fingerprints: List[dict] = Field(
        default_factory=list,
        description="数据引用指纹列表，包含 dataset_id/version/hash 等信息。",
    )

    @model_validator(mode="after")
    def ensure_consistency(self) -> "SessionBundle":
        """校验时间戳为 UTC 且至少包含一个图表。"""

        _ensure_utc(timestamp=self.generated_at, field_name="generated_at")
        if not self.chart_specs:
            raise ValueError("chart_specs 至少需要一个 ChartSpec。")
        return self
