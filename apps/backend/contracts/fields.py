"""字段级契约模型。

该模块定义字段的统计信息、取值范围以及字段契约结构，供数据扫描器、
图表模板以及执行器共享。模型遵循以下约束：

* 所有字段必须显式声明数据类型与语义角色，避免隐式推断。
* 统计指标仅存储可验证的数据，确保可以通过落盘后的 JSON 进行复现。
* 不允许额外字段混入，保障契约的稳定性。
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import ConfigDict, Field, model_validator

from apps.backend.contracts.metadata import ContractModel


class ValueRange(ContractModel):
    """字段的值域信息。

    该模型既服务于数值字段，也服务于分类型字段，用以约束可视化和
    质量检测阶段的边界条件。对于数值字段，使用 ``minimum`` 与 ``maximum``
    描述上下界；对于类别字段，则通过 ``categories`` 与 ``top_k_frequencies``
    列出受控的取值集合及其频次。所有取值均应基于 UTC 时间窗口内计算。
    """

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回值域契约的 Schema 名称。"""

        return "value_range"

    minimum: Optional[float] = Field(
        default=None,
        description="字段在扫描窗口内的最小值，仅适用于数值字段。",
    )
    maximum: Optional[float] = Field(
        default=None,
        description="字段在扫描窗口内的最大值，仅适用于数值字段。",
    )
    categories: Optional[List[str]] = Field(
        default=None,
        description="按频次降序排列的类别取值列表，仅适用于类别字段。",
    )
    top_k_frequencies: Optional[List[int]] = Field(
        default=None,
        description="与 categories 对应的频次列表，用于前端显示 Top-K。",
    )

    @model_validator(mode="after")
    def validate_range(cls, data: "ValueRange") -> "ValueRange":
        """校验值域配置的互斥与配对关系。

        * 当 ``categories`` 存在时，必须同时提供 ``top_k_frequencies`` 且长度一致。
        * 当 ``minimum`` 或 ``maximum`` 存在时，不允许提供类别取值，避免语义冲突。
        * 若同时设置 ``minimum`` 与 ``maximum``，则 ``minimum`` 不能大于 ``maximum``。
        """

        has_categories = data.categories is not None
        has_frequencies = data.top_k_frequencies is not None
        if has_categories != has_frequencies:
            raise ValueError(
                "categories 与 top_k_frequencies 必须同时提供，或同时为空。",
            )
        if has_categories:
            if len(data.categories) != len(data.top_k_frequencies):
                raise ValueError("categories 与 top_k_frequencies 长度必须一致。")
        if data.minimum is not None and data.maximum is not None:
            if data.minimum > data.maximum:
                raise ValueError("minimum 不能大于 maximum。")
        if data.minimum is not None and has_categories:
            raise ValueError("数值范围与类别枚举不能同时出现。")
        return data


class FieldStatistics(ContractModel):
    """字段的基础统计指标。

    该模型聚焦于用于可视化和质量监控的核心指标，不参与任何隐式推断。
    缺失率与唯一值计数均需通过数据扫描流程显式计算并写入。所有比率
    均在 ``[0, 1]`` 范围内，使用浮点数并保留中间精度。
    """

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回字段统计契约的 Schema 名称。"""

        return "field_statistics"

    total_count: int = Field(
        description="扫描窗口内的记录总数，要求为非负整数。",
        ge=0,
    )
    missing_count: int = Field(
        description="缺失值数量，必须小于等于 total_count。",
        ge=0,
    )
    distinct_count: Optional[int] = Field(
        default=None,
        description="唯一值数量，适用于类别或标识字段。",
        ge=0,
    )
    missing_ratio: float = Field(
        description="缺失率，范围为 [0, 1]。",
        ge=0.0,
        le=1.0,
    )
    entropy: Optional[float] = Field(
        default=None,
        description="离散字段的信息熵，用于辅助排序和推荐。",
        ge=0.0,
    )

    @model_validator(mode="after")
    def validate_statistics(cls, data: "FieldStatistics") -> "FieldStatistics":
        """确保统计量之间的基本约束关系成立。"""

        if data.missing_count > data.total_count:
            raise ValueError("缺失数量不能超过总数。")
        if data.total_count == 0:
            if data.missing_count != 0:
                raise ValueError("total_count 为 0 时不应出现缺失值计数。")
            if data.missing_ratio != 0.0:
                raise ValueError("total_count 为 0 时缺失率必须为 0。")
        else:
            ratio = data.missing_count / data.total_count
            if abs(ratio - data.missing_ratio) > 1e-6:
                raise ValueError("缺失率与缺失数量不一致。")
        if data.distinct_count is not None and data.distinct_count > data.total_count:
            raise ValueError("唯一值数量不能超过总数。")
        return data


class FieldSchema(ContractModel):
    """字段契约描述。

    每个字段契约都需要明确数据类型、语义角色以及可视化所需的补充信息。
    该模型既被数据扫描服务使用，也被图表模板、规划与执行模块共用。
    """

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回字段契约的 Schema 名称。"""

        return "field_schema"

    name: str = Field(description="字段的原始名称。", min_length=1)
    path: List[str] = Field(
        default_factory=list,
        description="字段在嵌套结构中的访问路径，按层级排列。",
    )
    title: Optional[str] = Field(
        default=None,
        description="面向用户展示的字段标题，可选。",
    )
    data_type: Literal[
        "integer",
        "number",
        "boolean",
        "string",
        "datetime",
    ] = Field(description="字段的基础数据类型。")
    semantic_type: Literal[
        "dimension",
        "measure",
        "temporal",
        "identifier",
        "geo",
        "unknown",
    ] = Field(description="字段的语义类型，用于图表推荐与校验。")
    nullable: bool = Field(description="字段是否允许缺失值。")
    unit: Optional[str] = Field(
        default=None,
        description="字段的度量单位，例如 USD、% 等。",
    )
    description: Optional[str] = Field(
        default=None,
        description="字段的业务描述，用于提示与文档。",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="与字段相关的标签集合，可用于检索。",
    )
    sample_values: List[str] = Field(
        default_factory=list,
        description="可展示给用户的示例取值列表，按字符串形式存储。",
        max_items=20,
    )
    value_range: Optional[ValueRange] = Field(
        default=None,
        description="字段的值域信息。",
    )
    statistics: FieldStatistics = Field(
        description="字段的统计信息，用于质量与推荐。",
    )

    @model_validator(mode="after")
    def validate_samples(cls, data: "FieldSchema") -> "FieldSchema":
        """确保示例值数量与字段类型匹配。"""

        if data.sample_values and data.semantic_type == "measure":
            # 度量字段的示例值仅用于展示，不允许超过三条以控制上下文大小。
            if len(data.sample_values) > 3:
                raise ValueError("度量字段的示例值不能超过 3 个。")
        if data.semantic_type == "temporal" and data.data_type != "datetime":
            raise ValueError("时间语义字段必须声明为 datetime 类型。")
        if data.statistics.missing_count > 0 and not data.nullable:
            raise ValueError("存在缺失值的字段必须标记为可为空。")
        return data

