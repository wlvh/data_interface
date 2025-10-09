"""图表模板与编码契约模型。"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChartEncoding(BaseModel):
    """可视化编码通道的契约描述。"""

    model_config = ConfigDict(extra="forbid")

    channel: Literal[
        "x",
        "y",
        "color",
        "size",
        "theta",
        "radius",
        "row",
        "column",
        "tooltip",
        "detail",
    ] = Field(description="编码通道名称。")
    semantic_role: Literal[
        "dimension",
        "measure",
        "temporal",
        "identifier",
        "geo",
    ] = Field(description="该编码通道期望绑定的字段语义。")
    required: bool = Field(description="通道是否为模板必填。")
    allow_multiple: bool = Field(description="通道是否允许绑定多个字段。")
    aggregate: Optional[Literal["sum", "avg", "min", "max", "count", "median"]] = Field(
        default=None,
        description="默认聚合方式，仅对度量字段生效。",
    )
    description: Optional[str] = Field(
        default=None,
        description="通道的业务说明或使用建议。",
    )

    @model_validator(mode="after")
    def validate_measure_aggregate(cls, data: "ChartEncoding") -> "ChartEncoding":
        """校验聚合配置与语义角色的匹配关系。"""

        if data.aggregate is not None and data.semantic_role != "measure":
            raise ValueError("仅度量通道允许声明聚合方式。")
        if data.allow_multiple is False and data.required is False:
            # 非必填且仅允许单字段的场景提醒上层进行二次校验，避免误用。
            return data
        return data


class ChartTemplate(BaseModel):
    """图表模板契约。"""

    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(description="模板唯一标识。", min_length=1)
    version: str = Field(description="模板版本号。", min_length=1)
    name: str = Field(description="模板名称。", min_length=1)
    description: Optional[str] = Field(
        default=None,
        description="模板说明，用于提示合适的使用场景。",
    )
    mark: Literal[
        "bar",
        "line",
        "area",
        "point",
        "pie",
        "heatmap",
        "table",
        "boxplot",
    ] = Field(description="对应的可视化基础图元类型。")
    encodings: List[ChartEncoding] = Field(
        description="模板支持的编码通道集合。",
        min_items=1,
    )
    default_config: Dict[str, object] = Field(
        default_factory=dict,
        description="可直接传给渲染引擎的默认配置片段。",
    )
    supported_engines: List[Literal["vega-lite", "echarts"]] = Field(
        description="模板兼容的渲染引擎列表。",
        min_items=1,
    )

    @model_validator(mode="after")
    def validate_template(cls, data: "ChartTemplate") -> "ChartTemplate":
        """校验模板的基础约束。"""

        required_channels = [item.channel for item in data.encodings if item.required]
        if len(set(required_channels)) != len(required_channels):
            raise ValueError("模板中的必填编码通道不能重复。")
        return data

