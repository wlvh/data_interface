"""图表推荐 Agent，生成多候选 ChartSpec 列表。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Sequence
from uuid import uuid4

from apps.backend.agents.base import Agent, AgentContext, AgentOutcome
from apps.backend.contracts.chart_spec import ChartA11y, ChartLayout, ChartSpec
from apps.backend.contracts.plan import ChartChannelMapping, ChartPlanItem, Plan
from apps.backend.contracts.recommendation import ChartRecommendationCandidate, RecommendationList
from apps.backend.contracts.trace import SpanSLO

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChartPayload:
    """图表生成所需输入。"""

    plan: Plan
    table_id: str


@dataclass(frozen=True)
class ChartRecommendationResult:
    """图表推荐产物，包含首图与推荐列表。"""

    primary_chart: ChartSpec
    recommendations: RecommendationList


def _sort_candidates(candidates: Sequence[ChartPlanItem]) -> List[ChartPlanItem]:
    """按置信度降序排序候选集合。"""

    return sorted(candidates, key=lambda item: item.confidence, reverse=True)


def _intent_tags(template_id: str) -> List[str]:
    """根据模板映射分析意图标签。"""

    mapping = {
        "line_basic": ["trend", "time"],
        "area_trend": ["trend", "distribution"],
        "bar_basic": ["comparison", "ranking"],
        "stacked_bar": ["comparison", "composition"],
        "scatter_basic": ["correlation"],
        "metric_table": ["overview"],
    }
    if template_id in mapping:
        return mapping[template_id]
    return ["explore"]


def _format_coverage(mappings: Sequence[ChartChannelMapping]) -> str:
    """组合字段覆盖信息，帮助前端展示差异。"""

    channel_descriptions = []
    for mapping in mappings:
        description = f"{mapping.channel}:{mapping.field_name}"
        channel_descriptions.append(description)
    joined = ", ".join(channel_descriptions)
    return f"字段映射：{joined}"


def _clone_encoding(mappings: Sequence[ChartChannelMapping]) -> List[ChartChannelMapping]:
    """深拷贝编码映射，避免引用计划对象。"""

    return [
        ChartChannelMapping(
            channel=mapping.channel,
            field_name=mapping.field_name,
            aggregation=mapping.aggregation,
        )
        for mapping in mappings
    ]


def _build_chart_spec(
    *,
    candidate: ChartPlanItem,
    data_source: str,
    plan_title: str,
    tags: List[str],
) -> ChartSpec:
    """由 ChartPlanItem 生成 ChartSpec。"""

    layout = ChartLayout(width=720, height=480, padding=24, theme="default")
    if candidate.template_id == "metric_table":
        layout = ChartLayout(width=720, height=640, padding=16, theme="default")
    a11y = ChartA11y(
        title=f"{plan_title} - {candidate.template_id}",
        summary=candidate.rationale,
        annotations=[],
    )
    chart_id = f"chart_{uuid4()}"
    encoding_copy = _clone_encoding(mappings=candidate.encoding)
    return ChartSpec(
        chart_id=chart_id,
        template_id=candidate.template_id,
        engine=candidate.engine,
        encoding=encoding_copy,
        data_source=data_source,
        scales=[],
        legends=[],
        axes=[],
        layout=layout,
        a11y=a11y,
        parameters={"intent_tags": tags},
    )


def _build_surprise_pool(plan: Plan) -> List[str]:
    """基于字段规划生成“给我惊喜”指令候选。"""

    prompts: List[str] = []
    if plan.field_plan:
        first_field = plan.field_plan[0].field_name
        prompts.append(f"请给我看一下 {first_field} 的走势")
    measure_fields = [item.field_name for item in plan.field_plan if item.semantic_role == "measure"]
    if len(measure_fields) >= 2:
        prompts.append(f"把 {measure_fields[0]} 和 {measure_fields[1]} 的关系展示一下")
    if plan.chart_plan:
        template = plan.chart_plan[0].template_id
        prompts.append(f"换一个 {template} 以外的角度给我惊喜")
    capped = prompts[:3]
    return capped


class ChartRecommendationAgent(Agent):
    """根据计划生成多候选 ChartSpec。"""

    name = "chart_recommender"
    slo = SpanSLO(
        max_duration_ms=1000,
        max_retries=0,
        failure_isolation_required=True,
    )

    def run(self, context: AgentContext, payload: ChartPayload) -> AgentOutcome:
        """生成推荐列表并返回首图。"""

        span_id = context.trace_recorder.start_span(
            operation="chart.recommend",
            agent_name=self.name,
            slo=self.slo,
            parent_span_id=None,
            model_name=None,
            prompt_version=None,
        )
        sorted_candidates = _sort_candidates(payload.plan.chart_plan)
        if not sorted_candidates:
            message = "计划缺少 chart_plan，无法生成图表。"
            raise ValueError(message)
        recommendation_entries: List[ChartRecommendationCandidate] = []
        chart_specs: List[ChartSpec] = []
        for index, candidate in enumerate(sorted_candidates):
            tags = _intent_tags(candidate.template_id)
            chart_spec = _build_chart_spec(
                candidate=candidate,
                data_source=payload.table_id,
                plan_title=payload.plan.refined_goal,
                tags=tags,
            )
            chart_specs.append(chart_spec)
            coverage = _format_coverage(candidate.encoding)
            recommendation_entries.append(
                ChartRecommendationCandidate(
                    candidate_id=f"candidate_{index}",
                    chart_spec=chart_spec,
                    confidence=candidate.confidence,
                    rationale=candidate.rationale,
                    intent_tags=tags,
                    coverage=coverage,
                ),
            )
        recommendation_list = RecommendationList(
            task_id=context.task_id,
            dataset_id=context.dataset_id,
            generated_at=context.clock.now(),
            recommendations=recommendation_entries,
            surprise_pool=_build_surprise_pool(payload.plan),
        )
        primary_chart = chart_specs[0]
        result = ChartRecommendationResult(
            primary_chart=primary_chart,
            recommendations=recommendation_list,
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
                "candidate_count": len(recommendation_entries),
            },
        )
        return AgentOutcome(
            output=result,
            span_id=span_id,
            trace_span=trace_span,
        )
