"""Trace 回放重建能力测试。"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from apps.backend.api import routes
from apps.backend.contracts.trace import SpanEvent, SpanMetrics, SpanSLO, TraceRecord, TraceSpan
from apps.backend.infra.clock import UtcClock


def _build_trace_record() -> TraceRecord:
    """构造一个最小 TraceRecord 用于测试。"""

    now = datetime.now(timezone.utc)
    slo = SpanSLO(max_duration_ms=1000, max_retries=0, failure_isolation_required=True)
    metrics = SpanMetrics(duration_ms=120, retry_count=0, rows_in=10, rows_out=10)
    root_started = now
    root_events = [
        SpanEvent(event_type="start", timestamp=root_started, detail=None),
        SpanEvent(event_type="success", timestamp=root_started + timedelta(milliseconds=5), detail=None),
    ]
    root_span = TraceSpan(
        span_id="root-span",
        parent_span_id=None,
        operation="data.scan",
        agent_name="scanner",
        status="success",
        started_at=root_started,
        slo=slo,
        metrics=metrics,
        model_name=None,
        prompt_version=None,
        dataset_hash="hash",
        schema_version="1.0",
        abort_reason=None,
        error_class=None,
        fallback_path=None,
        sse_seq=1,
        events=root_events,
    )
    child_started = root_started + timedelta(milliseconds=50)
    child_events = [
        SpanEvent(event_type="start", timestamp=child_started, detail=None),
        SpanEvent(event_type="success", timestamp=child_started + timedelta(milliseconds=5), detail=None),
    ]
    second_span = TraceSpan(
        span_id="child-span",
        parent_span_id="root-span",
        operation="plan.refine",
        agent_name="planner",
        status="success",
        started_at=child_started,
        slo=slo,
        metrics=metrics,
        model_name=None,
        prompt_version=None,
        dataset_hash="hash",
        schema_version="1.0",
        abort_reason=None,
        error_class=None,
        fallback_path=None,
        sse_seq=2,
        events=child_events,
    )
    trace = TraceRecord(
        trace_id="trace-1",
        task_id="task-1",
        dataset_id="dataset-1",
        created_at=now,
        spans=[root_span, second_span],
    )
    return trace


def test_rebuild_trace_record_generates_new_ids() -> None:
    """重建后的 Trace 应保留拓扑但拥有新的 trace_id 与 span_id。"""

    original = _build_trace_record()
    rebuilt = routes._rebuild_trace_record(original=original, clock=UtcClock())
    assert rebuilt.trace_id != original.trace_id
    assert len(rebuilt.spans) == len(original.spans)
    original_ids = {span.span_id for span in original.spans}
    rebuilt_ids = {span.span_id for span in rebuilt.spans}
    assert original_ids.isdisjoint(rebuilt_ids)
    assert [span.operation for span in rebuilt.spans] == [span.operation for span in original.spans]
