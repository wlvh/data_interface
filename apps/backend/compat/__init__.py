"""兼容层工具包。"""

from apps.backend.compat.pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_dump,
    model_validator,
)

__all__ = [
    "BaseModel",
    "ConfigDict",
    "Field",
    "model_dump",
    "model_validator",
]
