"""状态图编排器，负责串联多 Agent。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from apps.backend.agents.base import Agent, AgentContext, AgentOutcome
from apps.backend.contracts.trace import TraceSpan


@dataclass(frozen=True)
class StateNode:
    """状态图中的节点定义。"""

    name: str
    agent: Agent
    payload_builder: Callable[[Dict[str, object]], object]


@dataclass
class OrchestratorResult:
    """编排执行结果。"""

    outputs: Dict[str, object] = field(default_factory=dict)
    spans: List[TraceSpan] = field(default_factory=list)


class StateMachineOrchestrator:
    """顺序执行节点，形成 Trace → Span 列表。"""

    def __init__(self, nodes: List[StateNode]) -> None:
        """初始化编排器。

        Parameters
        ----------
        nodes: List[StateNode]
            按顺序排列的状态图节点。
        """

        self._nodes = nodes

    def run(
        self,
        context: AgentContext,
        shared_inputs: Dict[str, object],
        progress_callback: Optional[Callable[[str, AgentOutcome], None]] = None,
    ) -> OrchestratorResult:
        """执行状态图。

        Parameters
        ----------
        context: AgentContext
            任务上下文。
        shared_inputs: Dict[str, object]
            运行时共享输入，供各节点构造参数。
        progress_callback: Optional[Callable[[str, object], None]]
            在每个节点完成时触发的回调，便于推送进度。

        Returns
        -------
        OrchestratorResult
            包含各节点输出与 Trace Span 列表。
        """

        outputs: Dict[str, object] = {}
        spans: List[TraceSpan] = []
        for node in self._nodes:
            payload = node.payload_builder(shared_inputs | outputs)
            outcome = node.agent.run(context=context, payload=payload)
            outputs[node.name] = outcome.output
            spans.append(outcome.trace_span)
            if progress_callback is not None:
                progress_callback(node.name, outcome)
        result = OrchestratorResult(outputs=outputs, spans=spans)
        return result
