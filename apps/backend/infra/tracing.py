"""Trace 记录器，实现 Span 管理与指标采集。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from apps.backend.contracts.trace import SpanMetrics, SpanSLO, TraceRecord, TraceSpan
from apps.backend.infra.clock import UtcClock

LOGGER = logging.getLogger(__name__)


@dataclass
class _SpanRuntime:
    """Span 运行期数据，用于在完成前累积信息。"""

    span_id: str
    parent_span_id: Optional[str]
    node_name: str
    agent_name: str
    slo: SpanSLO
    model_name: Optional[str]
    prompt_version: Optional[str]
    started_at: datetime
    retry_count: int = 0
    failure_category: Optional[str] = None
    failure_isolation_ratio: float = 1.0


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

    def start_span(
        self,
        node_name: str,
        agent_name: str,
        slo: SpanSLO,
        parent_span_id: Optional[str],
        model_name: Optional[str],
        prompt_version: Optional[str],
    ) -> str:
        """创建新的 Span 并返回标识。

        Parameters
        ----------
        node_name: str
            状态图节点名称。
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
            node_name=node_name,
            agent_name=agent_name,
            slo=slo,
            model_name=model_name,
            prompt_version=prompt_version,
            started_at=started_at,
        )
        self._spans.append(runtime)
        self._span_index[span_id] = runtime
        LOGGER.debug("Span started", extra={"span_id": span_id, "node": node_name})
        return span_id

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
    ) -> TraceSpan:
        """结束 Span 并返回对应的契约对象。

        Parameters
        ----------
        span_id: str
            需要结束的 Span 标识。
        status: str
            节点执行状态，仅接受 success 或 failed。
        failure_category: Optional[str]
            若失败则提供分类。
        failure_isolation_ratio: float
            失败隔离比例。

        Returns
        -------
        TraceSpan
            可用于序列化的 Span 契约对象。
        """

        if status not in {"success", "failed"}:
            message = f"status={status} 非法，仅支持 success 或 failed。"
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
            failure_category=failure_category,
            failure_isolation_ratio=failure_isolation_ratio,
        )
        trace_span = TraceSpan(
            span_id=runtime.span_id,
            parent_span_id=runtime.parent_span_id,
            node_name=runtime.node_name,
            agent_name=runtime.agent_name,
            status=status,
            started_at=runtime.started_at,
            completed_at=completed_at,
            metrics=metrics,
            slo=runtime.slo,
            model_name=runtime.model_name,
            prompt_version=runtime.prompt_version,
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
