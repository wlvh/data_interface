"""FastAPI 应用工厂。"""

from __future__ import annotations

from fastapi import FastAPI

from apps.backend.api.routes import router


def create_app() -> FastAPI:
    """构建 FastAPI 应用实例。"""

    app = FastAPI(
        title="Data Interface API",
        version="0.1.0",
    )
    app.include_router(router)
    return app


app = create_app()
