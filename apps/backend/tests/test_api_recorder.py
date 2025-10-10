"""针对 ApiRecorder 的脱敏与大小限制测试。"""

from __future__ import annotations

import json

from apps.backend.infra.persistence import ApiRecorder, MASK_TOKEN


def test_api_recorder_masks_sensitive_fields(tmp_path) -> None:
    """dataset_path 等敏感字段应被掩码。"""

    recorder = ApiRecorder(base_path=tmp_path)
    recorder.record(endpoint="test_endpoint", direction="request", payload={"dataset_path": "/secret/data.csv", "note": "ok"})
    target_dir = tmp_path / "test_endpoint"
    files = list(target_dir.glob("*_request.json"))
    assert files, "请求文件未落盘。"
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["dataset_path"] == MASK_TOKEN
    assert payload["note"] == "ok"


def test_api_recorder_truncates_large_payload(tmp_path) -> None:
    """超出大小限制的 payload 应返回截断提示。"""

    recorder = ApiRecorder(base_path=tmp_path, max_bytes=32)
    recorder.record(endpoint="endpoint", direction="response", payload={"huge": "x" * 100})
    target_dir = tmp_path / "endpoint"
    files = list(target_dir.glob("*_response.json"))
    assert files, "响应文件未落盘。"
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["truncated"] is True
    assert payload["original_size"] > payload["max_bytes"]
