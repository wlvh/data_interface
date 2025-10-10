"""状态图编排器单元测试。"""

from __future__ import annotations

from apps.backend.agents import AgentContext, AgentOutcome
from apps.backend.contracts.trace import SpanSLO
from apps.backend.infra import TraceRecorder, UtcClock
from apps.backend.services import StateMachineOrchestrator, StateNode


class DoublingAgent:
    """简单的倍增 Agent，用于验证 orchestrator 行为。"""

    name = "doubling"
    slo = SpanSLO(
        max_duration_ms=100,
        max_retries=0,
        failure_isolation_required=True,
    )

    def run(self, context: AgentContext, payload: int) -> AgentOutcome:
        """将输入整数乘以 2。"""

        span_id = context.trace_recorder.start_span(
            operation=f"{self.name}.execute",
            agent_name=self.name,
            slo=self.slo,
            parent_span_id=context.parent_span_id,
            model_name=None,
            prompt_version=None,
        )
        result = payload * 2
        trace_span = context.trace_recorder.finish_span(
            span_id=span_id,
            status="success",
            failure_category=None,
            failure_isolation_ratio=1.0,
        )
        return AgentOutcome(
            output=result,
            span_id=span_id,
            trace_span=trace_span,
        )


def test_orchestrator_executes_nodes_in_order() -> None:
    """编排器应当顺序执行节点并汇总输出。"""

    clock = UtcClock()
    recorder = TraceRecorder(clock=clock)
    context = AgentContext(
        task_id="task_orchestrator",
        dataset_id="dataset_orchestrator",
        trace_recorder=recorder,
        clock=clock,
    )
    agent = DoublingAgent()

    def first_payload(shared: dict[str, object]) -> int:
        """返回起始值。"""

        return 2

    def second_payload(shared: dict[str, object]) -> int:
        """使用上一节点输出。"""

        if "first" not in shared:
            raise AssertionError("缺少 first 节点输出。")
        return shared["first"]

    orchestrator = StateMachineOrchestrator(
        nodes=[
            StateNode(
                name="first",
                agent=agent,
                payload_builder=first_payload,
            ),
            StateNode(
                name="second",
                agent=agent,
                payload_builder=second_payload,
            ),
        ],
    )
    result = orchestrator.run(context=context, shared_inputs={})
    assert result.outputs["first"] == 4
    assert result.outputs["second"] == 8
    assert len(result.spans) == 3
    root_span = result.spans[0]
    assert root_span.operation == "orchestrate.run"
    child_parent_ids = {span.parent_span_id for span in result.spans[1:]}
    assert child_parent_ids == {root_span.span_id}
