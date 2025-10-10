"""Agent 抽象定义，约束输入输出与追踪机制。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from apps.backend.contracts.trace import SpanSLO
from apps.backend.infra.clock import UtcClock
from apps.backend.infra.tracing import TraceRecorder


@dataclass(frozen=True)
class AgentContext:
    """Agent 执行上下文，封装任务元数据与追踪记录器。"""

    task_id: str
    dataset_id: str
    trace_recorder: TraceRecorder
    clock: UtcClock
    parent_span_id: Optional[str] = None


@dataclass(frozen=True)
class AgentOutcome:
    """Agent 执行结果包装，携带输出与 Span 记录。"""

    output: object
    span_id: str
    trace_span: object


class Agent(Protocol):
    """所有 Agent 必须实现的接口。"""

    name: str
    slo: SpanSLO

    def run(self, context: AgentContext, payload: object) -> AgentOutcome:
        """执行 Agent 逻辑。

        Parameters
        ----------
        context: AgentContext
            任务级上下文。
        payload: object
            上一个节点输出或原始输入。

        Returns
        -------
        AgentOutcome
            包含输出与 Trace Span 的执行结果。
        """
