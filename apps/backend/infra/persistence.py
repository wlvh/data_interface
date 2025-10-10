"""统一的 API 请求/响应落盘工具。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from apps.backend.compat import model_dump

MASK_TOKEN = "***MASKED***"


class ApiRecorder:
    """负责将 API 请求与响应以 JSON 格式落盘，便于审计与回放。"""

    def __init__(
        self,
        base_path: Path,
        *,
        max_bytes: int = 512_000,
        masked_keys: Iterable[str] | None = None,
    ) -> None:
        """初始化落盘器。

        Parameters
        ----------
        base_path: Path
            存放落盘文件的根目录。
        max_bytes: int
            单个 JSON 文件允许的最大字节数，超过时进行截断提示。
        masked_keys: Iterable[str] | None
            需要掩码的敏感字段名称集合。
        """

        if base_path is None:
            raise ValueError("base_path 不能为空。")
        if max_bytes <= 0:
            raise ValueError("max_bytes 必须为正数。")
        self._base_path = base_path
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes
        default_keys = {"dataset_path", "file_path"}
        self._masked_keys = set(masked_keys or default_keys)

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
        path = self._build_target_path(endpoint=endpoint, direction=direction)
        normalized = self._to_serializable(payload=payload)
        masked = self._mask_payload(payload=normalized)
        content = self._serialize_with_limit(payload=masked)
        path.write_text(content, encoding="utf-8")
        return path

    def record_error(self, endpoint: str, payload: Any) -> Path:
        """落盘错误结构，保持 request/response 同步可回放。"""

        path = self._build_target_path(endpoint=endpoint, direction="error")
        normalized = self._to_serializable(payload=payload)
        masked = self._mask_payload(payload=normalized)
        content = self._serialize_with_limit(payload=masked)
        path.write_text(content, encoding="utf-8")
        return path

    def _build_target_path(self, endpoint: str, direction: str) -> Path:
        """生成落盘路径。"""

        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        safe_endpoint = endpoint.strip("/").replace("/", "__") or "root"
        target_dir = self._base_path / safe_endpoint
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f"{timestamp}_{direction}.json"

    @staticmethod
    def _to_serializable(payload: Any) -> Any:
        """将输入对象转换为可 JSON 序列化的 Python 结构。"""

        if payload is None:
            return None
        if isinstance(payload, (dict, list, int, float, str, bool)):
            return payload
        return model_dump(payload)

    def _mask_payload(self, payload: Any) -> Any:
        """递归掩码敏感字段，保证脱敏后再落盘。"""

        if isinstance(payload, dict):
            masked: dict[str, Any] = {}
            for key, value in payload.items():
                if self._should_mask(key=key):
                    masked[key] = MASK_TOKEN
                    continue
                masked[key] = self._mask_payload(payload=value)
            return masked
        if isinstance(payload, list):
            return [self._mask_payload(payload=item) for item in payload]
        return payload

    def _should_mask(self, key: str) -> bool:
        """判定字段是否需要掩码。"""

        lowered = key.lower()
        if key in self._masked_keys:
            return True
        if lowered.endswith("_path"):
            return True
        if "pii" in lowered:
            return True
        return False

    def _serialize_with_limit(self, payload: Any) -> str:
        """在写入前评估大小，超限则给出提示内容。"""

        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        size = len(serialized.encode("utf-8"))
        if size <= self._max_bytes:
            return serialized
        fallback = {
            "truncated": True,
            "original_size": size,
            "max_bytes": self._max_bytes,
            "message": "payload 超过大小门限，已被截断，请参考上游日志或拆分请求。",
        }
        return json.dumps(fallback, ensure_ascii=False, indent=2)
