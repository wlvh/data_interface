"""面向前端消费的图表规范契约。"""

from __future__ import annotations

from typing import Dict, List

from apps.backend.compat import ConfigDict, Field, model_validator

from apps.backend.contracts.metadata import ContractModel
from apps.backend.contracts.plan import ChartChannelMapping


class ChartSpec(ContractModel):
    """图表最终规范，组合模板与编码映射。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回图表规范契约名称。"""

        return "chart_spec"

    chart_id: str = Field(description="图表唯一标识。", min_length=1)
    template_id: str = Field(description="引用的基础模板 ID。", min_length=1)
    engine: str = Field(description="渲染引擎类型，例如 vega-lite。", min_length=1)
    encodings: List[ChartChannelMapping] = Field(
        description="字段到视觉通道的映射。",
        json_schema_extra={"minItems": 1},
    )
    data_source: str = Field(description="绑定的数据表 ID。", min_length=1)
    parameters: Dict[str, object] = Field(
        description="模板参数或配置项。",
        default_factory=dict,
    )

    @model_validator(mode="after")
    def ensure_encodings(self) -> "ChartSpec":
        """确保至少存在一个编码映射。"""

        if not self.encodings:
            raise ValueError("encodings 至少需要一个映射。")
        return self
