"""Trace 缓存 Store，支持回放与审计。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from apps.backend.contracts.trace import TraceRecord


def _model_dump(payload: TraceRecord) -> dict:
    """兼容 pydantic v1/v2 的序列化。"""

    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    return payload.dict()


def _model_validate(payload: dict) -> TraceRecord:
    """兼容 pydantic v1/v2 的反序列化。"""

    if hasattr(TraceRecord, "model_validate"):
        return TraceRecord.model_validate(payload)
    return TraceRecord.parse_obj(payload)


@dataclass
class TraceStore:
    """以 task_id 为键缓存 TraceRecord，并落盘 JSON。"""

    base_path: Path
    _records: Dict[str, TraceRecord] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """确保落盘目录存在。"""

        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, trace: TraceRecord) -> None:
        """写入 Trace 并落盘。"""

        self._records[trace.task_id] = trace
        payload = _model_dump(payload=trace)
        path = self.base_path / f"{trace.task_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def require(self, task_id: str) -> TraceRecord:
        """根据 task_id 获取 Trace，若不存在立即失败。"""

        if task_id in self._records:
            return self._records[task_id]
        path = self.base_path / f"{task_id}.json"
        if not path.exists():
            message = f"task_id={task_id} 未找到 Trace 记录。"
            raise KeyError(message)
        payload = json.loads(path.read_text(encoding="utf-8"))
        trace = _model_validate(payload=payload)
        self._records[task_id] = trace
        return trace
