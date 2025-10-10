"""契约模型元数据工具。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.backend.compat import BaseModel, ConfigDict


@dataclass(frozen=True)
class SchemaMetadata:
    """描述契约 JSONSchema 元数据的结构化对象。

    Attributes
    ----------
    schema_name: str
        契约模型的名称，用于拼接 `$id`。
    version: str
        当前契约的版本号，所有模型保持一致，便于门禁校验。
    base_uri: str
        `$id` 的基础 URI，通常与文档或开放平台域名一致。
    """

    schema_name: str
    version: str
    base_uri: str

    def as_dict(self) -> dict[str, str]:
        """生成可直接注入到 Pydantic `json_schema_extra` 的元数据字典。"""

        schema_uri = f"{self.base_uri}/{self.schema_name}.json"
        return {
            "$id": schema_uri,
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "version": self.version,
        }


SCHEMA_VERSION: str = "1.0.0"
"""契约 Schema 的版本号，作为统一门禁依据。"""

SCHEMA_BASE_URI: str = "https://schemas.data-interface.local/contracts"
"""所有契约 Schema `$id` 的统一前缀，便于离线落盘引用。"""


def build_json_schema_extra(schema_name: str) -> dict[str, str]:
    """构造契约模型通用的 JSONSchema 元数据。

    Parameters
    ----------
    schema_name: str
        契约模型的名称，通常与类名保持一致。

    Returns
    -------
    dict[str, str]
        包含 `$id`、`$schema` 与 `version` 的字典，可直接作为
        `ConfigDict.json_schema_extra` 使用。
    """

    metadata = SchemaMetadata(
        schema_name=schema_name,
        version=SCHEMA_VERSION,
        base_uri=SCHEMA_BASE_URI,
    )
    return metadata.as_dict()


def _convert_legacy_schema(payload: dict[str, Any]) -> dict[str, Any]:
    """将 pydantic v1 的 schema 结果转换为 v2 风格。"""

    definitions = payload.pop("definitions", None)
    if definitions is not None:
        payload["$defs"] = definitions
    for key, value in list(payload.items()):
        if isinstance(value, dict):
            payload[key] = _convert_legacy_schema(value)
        elif isinstance(value, list):
            payload[key] = [
                _convert_legacy_schema(item) if isinstance(item, dict) else item
                for item in value
            ]
    properties = payload.get("properties")
    if isinstance(properties, dict) and "model_config" in properties:
        properties.pop("model_config", None)
    return payload


_HAS_MODEL_JSON_SCHEMA = hasattr(BaseModel, "model_json_schema")


class ContractModel(BaseModel):
    """所有契约模型的基类，统一注入 JSONSchema 元数据。"""

    class Config:
        extra = "forbid"

    @classmethod
    def schema_name(cls) -> str:
        """返回模型对应的 Schema 名称，供 `$id` 拼接使用。"""

        msg = f"{cls.__name__} 未实现 schema_name() 方法。"
        raise NotImplementedError(msg)

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """扩展默认的 Schema 输出，追加契约元数据。"""

        if _HAS_MODEL_JSON_SCHEMA:
            schema = super().model_json_schema(*args, **kwargs)
        else:
            schema = super().schema(*args, **kwargs)
            schema = _convert_legacy_schema(schema)
        extra = build_json_schema_extra(schema_name=cls.schema_name())
        schema.update(extra)
        cls._inject_additional_properties(schema=schema)
        return schema

    @staticmethod
    def _inject_additional_properties(schema: dict[str, Any]) -> None:
        """递归为对象类型补充 `additionalProperties: false`。"""

        if schema.get("type") == "object" and "additionalProperties" not in schema:
            schema["additionalProperties"] = False
        defs = schema.get("$defs")
        if isinstance(defs, dict):
            for nested in defs.values():
                if isinstance(nested, dict):
                    ContractModel._inject_additional_properties(schema=nested)
