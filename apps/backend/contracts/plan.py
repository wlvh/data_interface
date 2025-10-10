"""规划契约模型，描述从意图到图表的完整计划结构。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal
from uuid import UUID, uuid4

from apps.backend.compat import ConfigDict, Field, model_validator

from apps.backend.contracts.metadata import ContractModel


def _ensure_utc(dt: datetime, field_name: str) -> None:
    """确保时间戳携带 UTC 时区信息。

    Parameters
    ----------
    dt: datetime
        待校验的时间对象，必须包含 tzinfo。
    field_name: str
        字段名称，用于报错信息。
    """

    if dt.tzinfo is None:
        message = f"{field_name} 必须包含 UTC 时区信息。"
        raise ValueError(message)
    if dt.tzinfo.utcoffset(dt) != timezone.utc.utcoffset(dt):
        message = f"{field_name} 必须为 UTC 时间。"
        raise ValueError(message)


class FieldRecommendation(ContractModel):
    """字段推荐结果，明确字段角色与推荐理由。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回字段推荐契约的 Schema 名称。"""

        return "field_recommendation"

    field_name: str = Field(description="被推荐的字段名称。", min_length=1)
    semantic_role: Literal["dimension", "measure", "temporal", "identifier"] = Field(
        description="推荐的语义角色。",
    )
    priority: int = Field(
        description="推荐排序优先级，数值越小优先级越高。",
        ge=0,
    )
    reason: str = Field(
        description="推荐该字段的原因描述。",
        min_length=1,
    )


class ChartChannelMapping(ContractModel):
    """模板编码映射，描述字段如何绑定到视觉通道。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回编码映射契约名称。"""

        return "chart_channel_mapping"

    channel: str = Field(description="视觉通道名称，例如 x、y、color。", min_length=1)
    field_name: str = Field(description="绑定到该通道的字段。", min_length=1)
    aggregation: Literal["none", "sum", "avg", "count"] = Field(
        description="字段在该通道的聚合方式。",
    )


class ChartCandidate(ContractModel):
    """计划中的图表模板候选项。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回图表候选契约名称。"""

        return "chart_candidate"

    template_id: str = Field(description="引用的模板 ID。", min_length=1)
    engine: Literal["vega-lite", "echarts"] = Field(
        description="渲染引擎类型。",
    )
    confidence: float = Field(
        description="推荐置信度，范围 [0, 1]。",
        ge=0.0,
        le=1.0,
    )
    rationale: str = Field(description="推荐该模板的理由。", min_length=1)
    encodings: List[ChartChannelMapping] = Field(
        description="字段到视觉通道的映射集合。",
        json_schema_extra={"minItems": 1},
    )

    @model_validator(mode="after")
    def ensure_encodings(self) -> "ChartCandidate":
        """确保模板候选至少包含一个编码映射。"""

        if not self.encodings:
            raise ValueError("chart candidate 需要至少一个编码映射。")
        return self


class TransformDraft(ContractModel):
    """计划中的数据变换草案。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回变换草案契约名称。"""

        return "transform_draft"

    transform_id: UUID = Field(description="变换草案唯一标识。")
    language: Literal["python", "sql"] = Field(description="变换草案使用的语言。")
    code: str = Field(description="可执行的代码片段。", min_length=1)
    output_table: str = Field(description="预期输出表的标识。", min_length=1)
    intent_summary: str = Field(description="代码对应的业务意图说明。", min_length=1)

    @model_validator(mode="before")
    @classmethod
    def populate_transform_id(cls, values: dict) -> dict:
        """在缺少 transform_id 时自动补充 UUID。"""

        if "transform_id" not in values or values["transform_id"] is None:
            values["transform_id"] = uuid4()
        return values


class ExplanationOutline(ContractModel):
    """解释 Agent 的提纲，用于指导 Markdown 产出。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回解释提纲契约名称。"""

        return "explanation_outline"

    bullets: List[str] = Field(
        description="建议解释内容的要点列表。",
        json_schema_extra={"minItems": 1},
    )

    @model_validator(mode="after")
    def ensure_bullets(self) -> "ExplanationOutline":
        """保证提纲不为空。"""

        if not self.bullets:
            raise ValueError("解释提纲必须至少包含一个要点。")
        return self


class Plan(ContractModel):
    """统一的计划契约，连接意图与图表交付。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回计划契约的 Schema 名称。"""

        return "plan"

    plan_id: UUID = Field(description="计划唯一标识。")
    task_id: str = Field(description="所属任务 ID。", min_length=1)
    dataset_id: str = Field(description="计划关联的数据集 ID。", min_length=1)
    refined_goal: str = Field(description="模型澄清后的目标描述。", min_length=1)
    generated_at: datetime = Field(description="计划生成时间（UTC）。")
    field_recommendations: List[FieldRecommendation] = Field(
        description="推荐使用的字段集合。",
        json_schema_extra={"minItems": 1},
    )
    chart_candidates: List[ChartCandidate] = Field(
        description="图表模板候选集合。",
        json_schema_extra={"minItems": 1},
    )
    transform_drafts: List[TransformDraft] = Field(
        description="需要执行的数据变换草案列表。",
        json_schema_extra={"minItems": 1},
    )
    explanation_outline: ExplanationOutline = Field(
        description="解释 Agent 参考的提纲。",
    )

    @model_validator(mode="before")
    @classmethod
    def populate_plan_id(cls, values: dict) -> dict:
        """在未显式提供 plan_id 时自动补充。"""

        if "plan_id" not in values or values["plan_id"] is None:
            values["plan_id"] = uuid4()
        return values

    @model_validator(mode="after")
    def ensure_utc(self) -> "Plan":
        """确保生成时间遵守 UTC 约束。"""

        _ensure_utc(dt=self.generated_at, field_name="generated_at")
        if not self.field_recommendations:
            raise ValueError("field_recommendations 不能为空。")
        if not self.chart_candidates:
            raise ValueError("chart_candidates 不能为空。")
        if not self.transform_drafts:
            raise ValueError("transform_drafts 不能为空。")
        return self
