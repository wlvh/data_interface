"""图表推荐 Agent，生成多候选 ChartSpec 列表。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence
from uuid import uuid4

from apps.backend.agents.base import Agent, AgentContext, AgentOutcome
from apps.backend.contracts.chart_spec import ChartA11y, ChartLayout, ChartSpec
from apps.backend.contracts.plan import ChartChannelMapping, ChartPlanItem, Plan
from apps.backend.contracts.recommendation import ChartRecommendationCandidate, RecommendationList
from apps.backend.contracts.trace import SpanSLO

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChartPayload:
    """图表生成所需输入。

    Attributes
    ----------
    plan: Plan
        规划阶段输出，用于指引编码与模板选择。
    table_id: str
        变换阶段产出的主输出表标识。
    row_count: int
        输出表的行数，用于稀疏检测与降级决策。
    """

    plan: Plan
    table_id: str
    row_count: int


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


def _detect_sparse(*, row_count: int, plan: Plan) -> bool:
    """根据输出行数与字段规划判断是否需要降级。"""

    if row_count <= 3:
        return True
    dimension_like = [
        item for item in plan.field_plan if item.semantic_role in {"dimension", "temporal", "identifier"}
    ]
    if row_count <= len(dimension_like):
        return True
    return False


def _build_fallback_candidates(*, plan: Plan, row_count: int) -> List[ChartPlanItem]:
    """生成稀疏数据场景下的降级备选项。"""

    dimensions = [
        item for item in plan.field_plan if item.semantic_role in {"dimension", "temporal", "identifier"}
    ]
    measures = [item for item in plan.field_plan if item.semantic_role == "measure"]
    candidates: List[ChartPlanItem] = []
    metric_field = measures[0].field_name if measures else (dimensions[0].field_name if dimensions else plan.field_plan[0].field_name)
    metric_agg = "avg" if measures else "count"
    candidates.append(
        ChartPlanItem(
            template_id="metric_table",
            engine="vega-lite",
            confidence=0.45,
            rationale=f"数据仅 {row_count} 行，优先展示关键指标。",
            encoding=[
                ChartChannelMapping(channel="metric", field_name=metric_field, aggregation=metric_agg),
            ],
            layout_hint=None,
        ),
    )
    if dimensions and measures:
        dimension_field = dimensions[0].field_name
        measure_field = measures[0].field_name
        candidates.append(
            ChartPlanItem(
                template_id="bar_basic",
                engine="vega-lite",
                confidence=0.4,
                rationale=f"{dimension_field} → {measure_field} 聚合，突出稀疏样本趋势。",
                encoding=[
                    ChartChannelMapping(channel="x", field_name=dimension_field, aggregation="none"),
                    ChartChannelMapping(channel="y", field_name=measure_field, aggregation="sum"),
                ],
                layout_hint=None,
            ),
        )
    elif dimensions:
        dimension_field = dimensions[0].field_name
        candidates.append(
            ChartPlanItem(
                template_id="bar_basic",
                engine="vega-lite",
                confidence=0.35,
                rationale=f"{dimension_field} 维度计数作为迷你图集视图。",
                encoding=[
                    ChartChannelMapping(channel="x", field_name=dimension_field, aggregation="none"),
                    ChartChannelMapping(channel="y", field_name=dimension_field, aggregation="count"),
                ],
                layout_hint=None,
            ),
        )
    return candidates


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
        candidates: List[ChartPlanItem]
        fallback_reason: Optional[str] = None
        if not sorted_candidates or _detect_sparse(row_count=payload.row_count, plan=payload.plan):
            fallback_candidates = _build_fallback_candidates(plan=payload.plan, row_count=payload.row_count)
            if fallback_candidates:
                candidates = fallback_candidates
                fallback_reason = f"sparse_data(row_count={payload.row_count})"
            else:
                candidates = sorted_candidates
        else:
            candidates = sorted_candidates
        if not candidates:
            message = "缺少候选模板，无法生成图表。"
            raise ValueError(message)
        if fallback_reason is not None:
            context.trace_recorder.update_span(span_id=span_id, fallback_path=fallback_reason)
            LOGGER.warning(
                "触发稀疏数据降级",
                extra={
                    "task_id": context.task_id,
                    "row_count": payload.row_count,
                    "candidate_count": len(candidates),
                },
            )
        recommendation_entries: List[ChartRecommendationCandidate] = []
        chart_specs: List[ChartSpec] = []
        for index, candidate in enumerate(candidates):
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
