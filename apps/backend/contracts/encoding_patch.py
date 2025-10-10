"""编码补丁契约，描述对现有图表编码的增量修改。"""

from __future__ import annotations

from typing import Any, List, Literal

from apps.backend.compat import ConfigDict, Field, model_validator

from apps.backend.contracts.metadata import VersionedContractModel


class EncodingPatchOp(VersionedContractModel):
    """单个编码补丁操作。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回补丁操作的 Schema 名称。"""

        return "encoding_patch_op"

    op_type: Literal["add", "remove", "replace"] = Field(description="操作类型。")
    path: List[str] = Field(
        description="指向编码对象的路径，按层级拆分。",
        json_schema_extra={"minItems": 1},
    )
    value: Any = Field(
        default=None,
        description="在 add/replace 操作中写入的具体值。",
    )

    @model_validator(mode="after")
    def validate_value(self) -> "EncodingPatchOp":
        """确保 add/replace 操作必须提供值。"""

        if self.op_type in {"add", "replace"} and self.value is None:
            raise ValueError("add/replace 操作必须提供 value。")
        if self.op_type == "remove" and self.value is not None:
            raise ValueError("remove 操作不应提供 value。")
        return self


class EncodingPatch(VersionedContractModel):
    """针对 ChartSpec 的增量编码变更。"""

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def schema_name(cls) -> str:
        """返回补丁契约 Schema 名称。"""

        return "encoding_patch"

    target_chart_id: str = Field(description="需要应用补丁的图表 ID。", min_length=1)
    ops: List[EncodingPatchOp] = Field(
        description="补丁操作集合，按顺序执行。",
        json_schema_extra={"minItems": 1},
    )
    rationale: str = Field(description="提出该补丁的原因说明。", min_length=1)
