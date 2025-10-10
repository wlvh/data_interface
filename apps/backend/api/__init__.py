"""API 包导出。"""

from apps.backend.api.app import app, create_app

__all__ = [
    "app",
    "create_app",
]
