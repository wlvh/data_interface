"""面向前端消费的图表规范契约。"""

from __future__ import annotations

from typing import Dict, List, Optional

from apps.backend.compat import ConfigDict, Field, model_validator

from apps.backend.contracts.metadata import VersionedContractModel
from apps.backend.contracts.plan import ChartChannelMapping


class ChartScale(VersionedContractModel):
    """描述单个视觉通道的缩放配置。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回图表缩放契约名称。"""

        return "chart_scale"

    channel: str = Field(description="对应的视觉通道，例如 x 或 color。", min_length=1)
    scale_type: Optional[str] = Field(
        default=None,
        description="缩放类型，例如 linear、point。",
    )
    domain: Optional[List[float | str]] = Field(
        default=None,
        description="缩放域，指定值域范围。",
    )
    range: Optional[List[float | str]] = Field(
        default=None,
        description="缩放值域映射。",
    )
    nice: Optional[bool] = Field(
        default=None,
        description="是否启用 nice 取整策略。",
    )


class ChartLegend(VersionedContractModel):
    """图例配置，确保视觉元素可解读。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回图例契约名称。"""

        return "chart_legend"

    channel: str = Field(description="关联的视觉通道。", min_length=1)
    title: Optional[str] = Field(
        default=None,
        description="图例标题。",
    )
    orient: Optional[str] = Field(
        default=None,
        description="图例位置，如 right、bottom。",
    )
    show: bool = Field(description="是否展示该图例。")


class ChartAxis(VersionedContractModel):
    """坐标轴配置，控制刻度、标题与网格。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回坐标轴契约名称。"""

        return "chart_axis"

    channel: str = Field(description="绑定的视觉通道。", min_length=1)
    title: Optional[str] = Field(
        default=None,
        description="坐标轴标题。",
    )
    grid: Optional[bool] = Field(
        default=None,
        description="是否显示网格线。",
    )
    format: Optional[str] = Field(
        default=None,
        description="刻度格式，如百分比或日期格式字符串。",
    )


class ChartLayout(VersionedContractModel):
    """布局配置，约束画布尺寸与主题。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回布局契约名称。"""

        return "chart_layout"

    width: int = Field(description="画布宽度（像素）。", ge=100)
    height: int = Field(description="画布高度（像素）。", ge=100)
    padding: Optional[int] = Field(
        default=None,
        description="周围留白像素数。",
        ge=0,
    )
    theme: Optional[str] = Field(
        default=None,
        description="主题名称或配色方案。",
    )


class ChartA11y(VersionedContractModel):
    """无障碍配置，辅助屏幕阅读与结构化解释。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回无障碍契约名称。"""

        return "chart_a11y"

    title: str = Field(description="图表的可读标题。", min_length=1)
    summary: str = Field(description="面向屏幕阅读器的结构化总结。", min_length=1)
    annotations: List[str] = Field(
        default_factory=list,
        description="额外的说明或警告列表。",
    )


class ChartSpec(VersionedContractModel):
    """图表最终规范，组合模板与编码映射。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回图表规范契约名称。"""

        return "chart_spec"

    chart_id: str = Field(description="图表唯一标识。", min_length=1)
    template_id: str = Field(description="引用的基础模板 ID。", min_length=1)
    engine: str = Field(description="渲染引擎类型，例如 vega-lite。", min_length=1)
    data_source: str = Field(description="绑定的数据表 ID。", min_length=1)
    encoding: List[ChartChannelMapping] = Field(
        description="字段到视觉通道的映射。",
        json_schema_extra={"minItems": 1},
    )
    scales: List[ChartScale] = Field(
        default_factory=list,
        description="视觉通道对应的缩放集合。",
    )
    legends: List[ChartLegend] = Field(
        default_factory=list,
        description="图例配置列表。",
    )
    axes: List[ChartAxis] = Field(
        default_factory=list,
        description="坐标轴配置列表。",
    )
    layout: ChartLayout = Field(description="图表布局设定。")
    a11y: ChartA11y = Field(description="无障碍相关的说明与提示。")
    parameters: Dict[str, object] = Field(
        description="模板参数或配置项。",
        default_factory=dict,
    )

    @model_validator(mode="after")
    def ensure_encoding(self) -> "ChartSpec":
        """确保至少存在一个编码映射。"""

        if not self.encoding:
            raise ValueError("encoding 至少需要一个映射。")
        return self
