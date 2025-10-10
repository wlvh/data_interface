"""规划契约模型，描述从意图到图表的完整计划结构。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional
from uuid import UUID, uuid4

from apps.backend.compat import ConfigDict, Field, model_validator

from apps.backend.contracts.metadata import VersionedContractModel


def _ensure_utc(dt: datetime, field_name: str) -> None:
    """确保时间戳携带 UTC 时区信息。"""

    if dt.tzinfo is None:
        message = f"{field_name} 必须包含 UTC 时区信息。"
        raise ValueError(message)
    if dt.tzinfo.utcoffset(dt) != timezone.utc.utcoffset(dt):
        message = f"{field_name} 必须为 UTC 时间。"
        raise ValueError(message)


class PlanAssumption(VersionedContractModel):
    """规划过程中显式声明的假设与约束。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回假设契约的 Schema 名称。"""

        return "plan_assumption"

    statement: str = Field(description="假设的文本描述。", min_length=1)
    confidence: float = Field(
        description="假设成立的置信度，范围 [0, 1]。",
        ge=0.0,
        le=1.0,
    )
    impact: Literal["low", "medium", "high"] = Field(description="假设失效对计划的影响等级。")


class FieldPlanItem(VersionedContractModel):
    """字段规划条目，描述字段角色与操作建议。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回字段规划契约名称。"""

        return "field_plan_item"

    field_name: str = Field(description="字段名称。", min_length=1)
    semantic_role: Literal["dimension", "measure", "temporal", "identifier"] = Field(
        description="字段在本计划中的语义角色。",
    )
    priority: int = Field(
        description="推荐优先级，数值越小越靠前。",
        ge=0,
    )
    rationale: str = Field(description="选择该字段的理由。", min_length=1)
    operations: List[str] = Field(
        default_factory=list,
        description="针对该字段的派生或变换建议。",
    )


class ChartChannelMapping(VersionedContractModel):
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


class ChartPlanItem(VersionedContractModel):
    """计划中的图表模板候选项。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回图表计划契约名称。"""

        return "chart_plan_item"

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
    encoding: List[ChartChannelMapping] = Field(
        description="字段到视觉通道的映射集合。",
        json_schema_extra={"minItems": 1},
    )
    layout_hint: Optional[str] = Field(
        default=None,
        description="对布局或联动的补充说明。",
    )

    @model_validator(mode="after")
    def ensure_encoding(self) -> "ChartPlanItem":
        """确保模板候选至少包含一个编码映射。"""

        if not self.encoding:
            raise ValueError("chart_plan_item 需要至少一个编码映射。")
        return self


class TransformDraft(VersionedContractModel):
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

        if values is None:
            values = {}
        if "transform_id" not in values or values["transform_id"] is None:
            values["transform_id"] = uuid4()
        return values


class ExplainOutline(VersionedContractModel):
    """解释 Agent 的提纲，用于指导 Markdown 产出。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回解释提纲契约名称。"""

        return "explain_outline"

    bullets: List[str] = Field(
        description="建议解释内容的要点列表。",
        json_schema_extra={"minItems": 1},
    )

    @model_validator(mode="after")
    def ensure_bullets(self) -> "ExplainOutline":
        """保证提纲不为空。"""

        if not self.bullets:
            raise ValueError("解释提纲必须至少包含一个要点。")
        return self


class Plan(VersionedContractModel):
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
    assumptions: List[PlanAssumption] = Field(
        description="规划过程显式依赖的假设集合。",
        json_schema_extra={"minItems": 1},
    )
    field_plan: List[FieldPlanItem] = Field(
        description="字段规划明细。",
        json_schema_extra={"minItems": 1},
    )
    chart_plan: List[ChartPlanItem] = Field(
        description="图表候选明细。",
        json_schema_extra={"minItems": 1},
    )
    transform_drafts: List[TransformDraft] = Field(
        description="需要执行的数据变换草案列表。",
        json_schema_extra={"minItems": 1},
    )
    explain_outline: ExplainOutline = Field(
        description="解释 Agent 参考的提纲。",
    )

    @model_validator(mode="before")
    @classmethod
    def populate_plan_id(cls, values: dict) -> dict:
        """在未显式提供 plan_id 时自动补充。"""

        if values is None:
            values = {}
        if "plan_id" not in values or values["plan_id"] is None:
            values["plan_id"] = uuid4()
        return values

    @model_validator(mode="after")
    def ensure_utc(self) -> "Plan":
        """确保生成时间遵守 UTC 约束。"""

        _ensure_utc(dt=self.generated_at, field_name="generated_at")
        if not self.assumptions:
            raise ValueError("assumptions 不能为空。")
        if not self.field_plan:
            raise ValueError("field_plan 不能为空。")
        if not self.chart_plan:
            raise ValueError("chart_plan 不能为空。")
        if not self.transform_drafts:
            raise ValueError("transform_drafts 不能为空。")
        return self
