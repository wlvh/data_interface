"""统一的 API 请求/响应落盘工具。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.backend.compat import model_dump


class ApiRecorder:
    """负责将 API 请求与响应以 JSON 格式落盘，便于审计与回放。"""

    def __init__(self, base_path: Path) -> None:
        if base_path is None:
            raise ValueError("base_path 不能为空。")
        self._base_path = base_path
        self._base_path.mkdir(parents=True, exist_ok=True)

    def record(self, endpoint: str, direction: str, payload: Any) -> Path:
        """将给定 payload 序列化后写入磁盘。

        Parameters
        ----------
        endpoint: str
            API 路径或逻辑名称，用于生成子目录。
        direction: str
            标识 request / response。
        payload: Any
            需要落盘的对象，必须可被 Pydantic 模型或 JSON 序列化。
        """

        if not endpoint:
            raise ValueError("endpoint 不能为空。")
        if direction not in {"request", "response"}:
            raise ValueError("direction 仅支持 request 或 response。")
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        safe_endpoint = endpoint.strip("/").replace("/", "__") or "root"
        target_dir = self._base_path / safe_endpoint
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{timestamp}_{direction}.json"
        serialized = self._to_serializable(payload=payload)
        path.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _to_serializable(payload: Any) -> Any:
        """将输入对象转换为可 JSON 序列化的 Python 结构。"""

        if payload is None:
            return None
        if isinstance(payload, (dict, list, int, float, str, bool)):
            return payload
        return model_dump(payload)
