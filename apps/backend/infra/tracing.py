"""Trace 记录器，实现 Span 管理与指标采集。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from apps.backend.contracts.metadata import SCHEMA_VERSION
from apps.backend.contracts.trace import SpanEvent, SpanMetrics, SpanSLO, TraceRecord, TraceSpan
from apps.backend.infra.clock import UtcClock

LOGGER = logging.getLogger(__name__)


@dataclass
class _SpanRuntime:
    """Span 运行期数据，用于在完成前累积信息。"""

    span_id: str
    parent_span_id: Optional[str]
    operation: str
    agent_name: str
    slo: SpanSLO
    model_name: Optional[str]
    prompt_version: Optional[str]
    started_at: datetime
    retry_count: int = 0
    dataset_hash: Optional[str] = None
    schema_version: str = SCHEMA_VERSION
    abort_reason: Optional[str] = None
    error_class: Optional[str] = None
    fallback_path: Optional[str] = None
    sse_seq: Optional[int] = None
    rows_in: Optional[int] = None
    rows_out: Optional[int] = None
    events: List[SpanEvent] = field(default_factory=list)


class TraceRecorder:
    """记录 Trace → Span 树结构并输出契约对象。"""

    def __init__(self, clock: UtcClock) -> None:
        """初始化记录器。

        Parameters
        ----------
        clock: UtcClock
            提供时间戳的统一时钟。
        """

        # 使用列表维护 Span 顺序，确保回放时与执行顺序一致。
        self._spans: List[_SpanRuntime] = []
        self._clock = clock
        # 建立索引以便根据 span_id 快速定位。
        self._span_index: Dict[str, _SpanRuntime] = {}
        self._root_span_id: Optional[str] = None

    @staticmethod
    def _serialize_detail(detail: Optional[Any]) -> Optional[str]:
        """将事件细节序列化为 JSON 字符串。"""

        if detail is None:
            return None
        if isinstance(detail, str):
            return detail
        try:
            return json.dumps(detail, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        except TypeError:
            fallback = {"detail": str(detail)}
            return json.dumps(fallback, ensure_ascii=True, separators=(",", ":"), sort_keys=True)

    def start_span(
        self,
        operation: str,
        agent_name: str,
        slo: SpanSLO,
        parent_span_id: Optional[str],
        model_name: Optional[str],
        prompt_version: Optional[str],
        start_detail: Optional[Any] = None,
    ) -> str:
        """创建新的 Span 并返回标识。

        Parameters
        ----------
        operation: str
            状态图节点名称，遵循 `范畴.动作` 的命名规范。
        agent_name: str
            执行节点的 Agent 名称。
        slo: SpanSLO
            节点的服务目标配置。
        parent_span_id: Optional[str]
            父节点的 Span 标识。
        model_name: Optional[str]
            如果调用模型则记录模型名称。
        prompt_version: Optional[str]
            模型提示词版本。
        start_detail: Optional[Any]
            若需要为 start 事件添加补充信息，则以可序列化对象给出。

        Returns
        -------
        str
            新 Span 的唯一标识。
        """

        span_id = str(uuid4())
        started_at = self._clock.now()
        runtime = _SpanRuntime(
            span_id=span_id,
            parent_span_id=parent_span_id,
            operation=operation,
            agent_name=agent_name,
            slo=slo,
            model_name=model_name,
            prompt_version=prompt_version,
            started_at=started_at,
        )
        runtime.events.append(
            SpanEvent(
                event_type="start",
                timestamp=started_at,
                detail=self._serialize_detail(detail=start_detail),
            ),
        )
        self._spans.append(runtime)
        self._span_index[span_id] = runtime
        if parent_span_id is None and self._root_span_id is None:
            self._root_span_id = span_id
        LOGGER.debug("Span started", extra={"span_id": span_id, "operation": operation})
        return span_id

    def record_event(self, span_id: str, event_type: str, *, detail: Optional[Any] = None) -> None:
        """为已有 Span 追加事件。

        Parameters
        ----------
        span_id: str
            目标 Span 的唯一标识。
        event_type: str
            事件类型，需符合既有约定。
        detail: Optional[Any]
            可选的事件附加信息，将被序列化为 JSON 字符串。
        """

        if span_id not in self._span_index:
            message = f"span_id={span_id} 不存在，无法记录事件。"
            raise KeyError(message)
        runtime = self._span_index[span_id]
        serialized = self._serialize_detail(detail=detail)
        runtime.events.append(
            SpanEvent(event_type=event_type, timestamp=self._clock.now(), detail=serialized),
        )
        LOGGER.debug(
            "Span event recorded",
            extra={
                "span_id": span_id,
                "event_type": event_type,
            },
        )

    def update_span(
        self,
        span_id: str,
        *,
        rows_in: Optional[int] = None,
        rows_out: Optional[int] = None,
        dataset_hash: Optional[str] = None,
        schema_version: Optional[str] = None,
        fallback_path: Optional[str] = None,
        abort_reason: Optional[str] = None,
        sse_seq: Optional[int] = None,
    ) -> None:
        """更新运行期 Span 元信息。

        Parameters
        ----------
        span_id: str
            需要更新的 Span 标识。
        rows_in: Optional[int]
            节点输入行数。
        rows_out: Optional[int]
            节点输出行数。
        dataset_hash: Optional[str]
            数据来源哈希，用于回放一致性。
        schema_version: Optional[str]
            运行时契约版本。
        fallback_path: Optional[str]
            若发生降级，记录采用的路径。
        abort_reason: Optional[str]
            若节点提前终止，记录原因。
        sse_seq: Optional[int]
            SSE 推送序号。
        """

        if span_id not in self._span_index:
            message = f"span_id={span_id} 不存在，无法更新。"
            raise KeyError(message)
        runtime = self._span_index[span_id]
        if rows_in is not None:
            runtime.rows_in = rows_in
        if rows_out is not None:
            runtime.rows_out = rows_out
        if dataset_hash is not None:
            runtime.dataset_hash = dataset_hash
        if schema_version is not None:
            runtime.schema_version = schema_version
        if fallback_path is not None:
            runtime.fallback_path = fallback_path
        if abort_reason is not None:
            runtime.abort_reason = abort_reason
        if sse_seq is not None:
            runtime.sse_seq = sse_seq

    def register_retry(self, span_id: str) -> None:
        """为指定 Span 累加一次重试数量。

        Parameters
        ----------
        span_id: str
            需要更新的 Span 标识。
        """

        if span_id not in self._span_index:
            message = f"span_id={span_id} 不存在，无法记录重试。"
            raise KeyError(message)
        runtime = self._span_index[span_id]
        runtime.retry_count += 1
        self.record_event(span_id=span_id, event_type="retry", detail={"retry_count": runtime.retry_count})
        LOGGER.info(
            "Span retry recorded",
            extra={
                "span_id": span_id,
                "retry_count": runtime.retry_count,
            },
        )

    def finish_span(
        self,
        span_id: str,
        status: str,
        failure_category: Optional[str],
        failure_isolation_ratio: float,
        status_detail: Optional[Any] = None,
    ) -> TraceSpan:
        """结束 Span 并返回对应的契约对象。

        Parameters
        ----------
        span_id: str
            需要结束的 Span 标识。
        status: str
            节点执行状态，仅接受 success/failed/aborted。
        failure_category: Optional[str]
            若失败则提供分类。
        failure_isolation_ratio: float
            失败隔离比例。
        status_detail: Optional[Any]
            追加的事件 detail 信息。

        Returns
        -------
        TraceSpan
            可用于序列化的 Span 契约对象。
        """

        if status not in {"success", "failed", "aborted"}:
            message = f"status={status} 非法，仅支持 success/failed/aborted。"
            raise ValueError(message)
        if span_id not in self._span_index:
            message = f"span_id={span_id} 不存在，无法结束。"
            raise KeyError(message)
        runtime = self._span_index[span_id]
        completed_at = self._clock.now()
        duration_ms = int((completed_at - runtime.started_at).total_seconds() * 1000)
        metrics = SpanMetrics(
            duration_ms=duration_ms,
            retry_count=runtime.retry_count,
            rows_in=runtime.rows_in,
            rows_out=runtime.rows_out,
        )
        event_type = "success"
        event_detail: Optional[str] = None
        if status in {"failed", "aborted"}:
            runtime.error_class = failure_category
            event_type = "abort"
            detail_payload: Dict[str, Any] = {
                "error_class": failure_category,
                "abort_reason": runtime.abort_reason,
            }
            if status_detail is not None:
                detail_payload["meta"] = status_detail
            event_detail = self._serialize_detail(detail=detail_payload)
            runtime.abort_reason = failure_category or runtime.abort_reason
        elif status_detail is not None:
            event_detail = self._serialize_detail(detail=status_detail)
        runtime.events.append(
            SpanEvent(event_type=event_type, timestamp=completed_at, detail=event_detail),
        )
        trace_span = TraceSpan(
            span_id=runtime.span_id,
            parent_span_id=runtime.parent_span_id,
            operation=runtime.operation,
            agent_name=runtime.agent_name,
            status=status,
            started_at=runtime.started_at,
            slo=runtime.slo,
            metrics=metrics,
            model_name=runtime.model_name,
            prompt_version=runtime.prompt_version,
            dataset_hash=runtime.dataset_hash,
            schema_version=runtime.schema_version,
            abort_reason=runtime.abort_reason,
            error_class=runtime.error_class,
            fallback_path=runtime.fallback_path,
            sse_seq=runtime.sse_seq,
            events=runtime.events,
        )
        LOGGER.info(
            "Span finished",
            extra={
                "span_id": span_id,
                "status": status,
                "duration_ms": duration_ms,
            },
        )
        return trace_span

    def get_root_span_id(self) -> Optional[str]:
        """返回首个根 Span 的标识，用于 SSE 对齐。"""

        return self._root_span_id

    def build_trace(
        self,
        task_id: str,
        dataset_id: str,
        spans: List[TraceSpan],
    ) -> TraceRecord:
        """根据已完成的 Span 构造 Trace 记录。

        Parameters
        ----------
        task_id: str
            任务标识。
        dataset_id: str
            数据集标识。
        spans: List[TraceSpan]
            完成后的 Span 顺序列表。

        Returns
        -------
        TraceRecord
            可直接落盘与返回的 Trace 契约。
        """

        created_at = self._clock.now()
        trace = TraceRecord(
            trace_id=str(uuid4()),
            task_id=task_id,
            dataset_id=dataset_id,
            created_at=created_at,
            spans=spans,
        )
        LOGGER.debug(
            "Trace assembled",
            extra={
                "task_id": task_id,
                "span_count": len(spans),
            },
        )
        return trace
