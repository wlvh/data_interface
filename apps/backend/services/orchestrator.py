"""状态图编排器，负责串联多 Agent。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional

from apps.backend.agents.base import Agent, AgentContext, AgentOutcome
from apps.backend.contracts.trace import SpanSLO, TraceSpan


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
        # 汇总节点名称以便在 Span detail 中复现执行链路。
        node_names = [node.name for node in self._nodes]
        combined_detail = {"nodes": node_names, "policy": "best_effort"}
        # 顶层 orchestrate.run Span 作为全链路父节点，保障子节点可设置 parent_span_id。
        orchestrate_span_id = context.trace_recorder.start_span(
            operation="orchestrate.run",
            agent_name="state_machine_orchestrator",
            slo=SpanSLO(
                max_duration_ms=sum(node.agent.slo.max_duration_ms for node in self._nodes),
                max_retries=0,
                failure_isolation_required=True,
            ),
            parent_span_id=None,
            model_name=None,
            prompt_version=None,
            start_detail=combined_detail,
        )
        # 为子节点生成携带 parent_span_id 的上下文，确保父子关系串联。
        child_context = replace(context, parent_span_id=orchestrate_span_id)
        current_node: Optional[str] = None
        try:
            for node in self._nodes:
                current_node = node.name
                # 聚合上游输出后构造节点 payload。
                payload = node.payload_builder(shared_inputs | outputs)
                outcome = node.agent.run(context=child_context, payload=payload)
                outputs[node.name] = outcome.output
                spans.append(outcome.trace_span)
                if progress_callback is not None:
                    progress_callback(node.name, outcome)
        except Exception as error:
            # 子节点抛错时将 orchestrate.run 标记为 failed，并记录失败节点。
            context.trace_recorder.finish_span(
                span_id=orchestrate_span_id,
                status="failed",
                failure_category=error.__class__.__name__,
                failure_isolation_ratio=0.0,
                status_detail={
                    "failed_node": current_node,
                    "nodes": node_names,
                },
            )
            raise
        # 正常完成时记录成功 detail，并把父 Span 放在列表首位。
        root_span = context.trace_recorder.finish_span(
            span_id=orchestrate_span_id,
            status="success",
            failure_category=None,
            failure_isolation_ratio=1.0,
            status_detail=combined_detail,
        )
        spans.insert(0, root_span)
        result = OrchestratorResult(outputs=outputs, spans=spans)
        return result
