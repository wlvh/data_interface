"""pydantic 兼容层，为 v1/v2 提供统一接口。"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

import pydantic

BaseModel = pydantic.BaseModel
Field = pydantic.Field

try:  # pragma: no cover - 取决于安装的 pydantic 版本
    from pydantic import ConfigDict as _ConfigDict
except ImportError:  # pragma: no cover
    _ConfigDict = None  # type: ignore[assignment]


def ConfigDict(**kwargs: Any) -> Any:
    """兼容 v1/v2 的 ConfigDict 定义。"""

    if _ConfigDict is None:
        return kwargs
    return _ConfigDict(**kwargs)


try:  # pragma: no cover
    from pydantic import model_validator as _model_validator
except ImportError:  # pragma: no cover
    from pydantic import root_validator

    def _model_validator(*, mode: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """为 v1 提供与 v2 等价的 model_validator 装饰器。"""

        if mode not in {"before", "after"}:
            raise ValueError("model_validator 仅支持 before/after 模式。")

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if mode == "before":
                return root_validator(pre=True, allow_reuse=True)(func)

            def wrapper(cls: type[BaseModel], values: dict[str, Any]) -> dict[str, Any]:
                instance = cls.construct(**values)
                result = func(instance)
                if not isinstance(result, cls):
                    raise TypeError("after validator 必须返回模型实例。")
                return values

            return root_validator(pre=False, allow_reuse=True)(wrapper)

        return decorator


model_validator = _model_validator

def model_dump(payload: Any) -> Any:
    """兼容 v1/v2 的模型序列化接口。"""

    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    if hasattr(payload, "dict"):
        return payload.dict()
    raise TypeError("无法序列化给定对象，需为 Pydantic 模型。")


__all__ = [
    "BaseModel",
    "Field",
    "ConfigDict",
    "model_validator",
    "model_dump",
]
