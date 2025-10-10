"""Pydantic v2 统一出口，封装常用导入与辅助函数。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def model_dump(payload: Any, **kwargs: Any) -> Any:
    """序列化 Pydantic v2 模型，返回可 JSON 化对象。"""

    if payload is None:
        return None
    if isinstance(payload, BaseModel):
        if "by_alias" not in kwargs:
            kwargs["by_alias"] = True
        if "mode" not in kwargs:
            kwargs["mode"] = "json"
        return payload.model_dump(**kwargs)
    if hasattr(payload, "model_dump"):
        if "by_alias" not in kwargs:
            kwargs["by_alias"] = True
        if "mode" not in kwargs:
            kwargs["mode"] = "json"
        return payload.model_dump(**kwargs)
    if hasattr(payload, "model_dump_json"):
        if "by_alias" not in kwargs:
            kwargs["by_alias"] = True
        json_payload = payload.model_dump_json(**kwargs)
        return json.loads(json_payload)
    if isinstance(payload, (dict, list, str, int, float, bool)):
        return payload
    raise TypeError("无法序列化给定对象，需为 Pydantic 模型或基础类型。")


__all__ = [
    "BaseModel",
    "Field",
    "ConfigDict",
    "model_validator",
    "model_dump",
]
