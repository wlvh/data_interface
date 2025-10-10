"""图表推荐 Agent。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List
from uuid import uuid4

from apps.backend.agents.base import Agent, AgentContext, AgentOutcome
from apps.backend.contracts.chart_spec import ChartSpec
from apps.backend.contracts.plan import ChartCandidate, Plan
from apps.backend.contracts.trace import SpanSLO

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChartPayload:
    """图表生成所需输入。"""

    plan: Plan
    table_id: str


def _select_candidate(candidates: List[ChartCandidate]) -> ChartCandidate:
    """按置信度排序，选择最优候选。"""

    sorted_candidates = sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True)
    return sorted_candidates[0]


class ChartRecommendationAgent(Agent):
    """根据计划与数据表生成 ChartSpec。"""

    name = "chart_recommender"
    slo = SpanSLO(
        max_duration_ms=1000,
        max_retries=0,
        failure_isolation_required=True,
    )

    def run(self, context: AgentContext, payload: ChartPayload) -> AgentOutcome:
        """生成单个 ChartSpec。"""

        span_id = context.trace_recorder.start_span(
            node_name="chart",
            agent_name=self.name,
            slo=self.slo,
            parent_span_id=None,
            model_name=None,
            prompt_version=None,
        )
        candidate = _select_candidate(candidates=payload.plan.chart_candidates)
        chart_spec = ChartSpec(
            chart_id=str(uuid4()),
            template_id=candidate.template_id,
            engine=candidate.engine,
            encodings=candidate.encodings,
            data_source=payload.table_id,
            parameters={},
        )
        trace_span = context.trace_recorder.finish_span(
            span_id=span_id,
            status="success",
            failure_category=None,
            failure_isolation_ratio=1.0,
        )
        LOGGER.info(
            "图表推荐完成",
            extra={
                "task_id": context.task_id,
                "template_id": candidate.template_id,
            },
        )
        return AgentOutcome(
            output=chart_spec,
            span_id=span_id,
            trace_span=trace_span,
        )

