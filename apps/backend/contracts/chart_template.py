"""图表模板与编码契约模型。"""

from __future__ import annotations

import json
from typing import Dict, List, Literal, Optional

from apps.backend.compat import ConfigDict, Field, model_validator

from apps.backend.contracts.metadata import ContractModel


class ChartEncoding(ContractModel):
    """可视化编码通道的契约描述。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回编码契约的 Schema 名称。"""

        return "chart_encoding"

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
    def validate_measure_aggregate(self) -> "ChartEncoding":
        """校验聚合配置与语义角色的匹配关系。"""

        if self.aggregate is not None and self.semantic_role != "measure":
            raise ValueError("仅度量通道允许声明聚合方式。")
        if self.allow_multiple is False and self.required is False:
            # 非必填且仅允许单字段的场景提醒上层进行二次校验，避免误用。
            return self
        return self


class ChartTemplate(ContractModel):
    """图表模板契约。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回图表模板契约的 Schema 名称。"""

        return "chart_template"

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
        json_schema_extra={"minItems": 1},
    )
    default_config: Dict[str, object] = Field(
        default_factory=dict,
        description="可直接传给渲染引擎的默认配置片段。",
    )
    supported_engines: List[Literal["vega-lite", "echarts"]] = Field(
        description="模板兼容的渲染引擎列表。",
        json_schema_extra={"minItems": 1},
    )

    @model_validator(mode="after")
    def validate_template(self) -> "ChartTemplate":
        """校验模板的基础约束。"""

        if not self.encodings:
            raise ValueError("模板必须至少包含一个编码通道。")
        if not self.supported_engines:
            raise ValueError("supported_engines 至少需要一个渲染引擎。")
        required_channels = [item.channel for item in self.encodings if item.required]
        if len(set(required_channels)) != len(required_channels):
            raise ValueError("模板中的必填编码通道不能重复。")

        channel_counts: Dict[str, int] = {}
        for encoding in self.encodings:
            if encoding.channel in channel_counts:
                channel_counts[encoding.channel] = channel_counts[encoding.channel] + 1
            else:
                channel_counts[encoding.channel] = 1

        for channel, count in channel_counts.items():
            if channel in {"tooltip", "detail"}:
                continue
            if count > 1:
                raise ValueError("除 tooltip/detail 外的编码通道必须全局唯一。")

        try:
            json.dumps(self.default_config)
        except TypeError as exc:
            raise ValueError("default_config 必须可 JSON 序列化。") from exc
        return self
