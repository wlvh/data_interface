"""图表推荐结果契约，支撑推荐列表与“给我惊喜”体验。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from apps.backend.compat import ConfigDict, Field, model_validator

from apps.backend.contracts.chart_spec import ChartSpec
from apps.backend.contracts.metadata import VersionedContractModel


def _ensure_utc(timestamp: datetime, field_name: str) -> None:
    """确保时间戳包含 UTC 信息，避免回放时区错乱。"""

    if timestamp.tzinfo is None:
        raise ValueError(f"{field_name} 必须包含 UTC 时区信息。")
    if timestamp.tzinfo.utcoffset(timestamp) != timezone.utc.utcoffset(timestamp):
        raise ValueError(f"{field_name} 必须为 UTC 时间。")


class ChartRecommendationCandidate(VersionedContractModel):
    """单个图表推荐候选，包含 ChartSpec 与解释信息。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回候选契约 Schema 名称。"""

        return "chart_recommendation_candidate"

    candidate_id: str = Field(description="候选标识，便于前端引用。", min_length=1)
    chart_spec: ChartSpec = Field(description="推荐的图表规范。")
    confidence: float = Field(
        description="推荐置信度，范围 [0, 1]。",
        ge=0.0,
        le=1.0,
    )
    rationale: str = Field(description="推荐理由的摘要。", min_length=1)
    intent_tags: List[str] = Field(
        description="该推荐覆盖的分析意图标签，如 trend/comparison。",
        json_schema_extra={"minItems": 1},
    )
    coverage: Optional[str] = Field(
        default=None,
        description="可选的分析覆盖说明，例如字段覆盖率或新增角度。",
    )

    @model_validator(mode="after")
    def ensure_tags(self) -> "ChartRecommendationCandidate":
        """确保意图标签非空。"""

        if not self.intent_tags:
            raise ValueError("intent_tags 不可为空。")
        return self


class RecommendationList(VersionedContractModel):
    """一次推荐请求产出的候选集合。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回推荐列表契约 Schema 名称。"""

        return "recommendation_list"

    task_id: str = Field(description="关联的任务标识。", min_length=1)
    dataset_id: str = Field(description="推荐所基于的数据集 ID。", min_length=1)
    generated_at: datetime = Field(description="UTC 时间的生成时间。")
    recommendations: List[ChartRecommendationCandidate] = Field(
        description="候选集合，按置信度排序。",
        json_schema_extra={"minItems": 1},
    )
    surprise_pool: List[str] = Field(
        default_factory=list,
        description="可用于“给我惊喜”按钮的指令候选集合。",
    )

    @model_validator(mode="after")
    def ensure_payload(self) -> "RecommendationList":
        """校验推荐集合与时间戳合法性。"""

        _ensure_utc(timestamp=self.generated_at, field_name="generated_at")
        if not self.recommendations:
            raise ValueError("recommendations 至少需要一个候选。")
        return self
