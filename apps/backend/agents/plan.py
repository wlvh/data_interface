"""计划细化 Agent，将意图映射为结构化计划。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

from apps.backend.agents.base import Agent, AgentContext, AgentOutcome
from apps.backend.contracts.dataset_profile import DatasetProfile
from apps.backend.contracts.plan import (
    ChartPlanItem,
    ChartChannelMapping,
    ExplainOutline,
    FieldPlanItem,
    PlanAssumption,
    Plan,
    TransformDraft,
)
from apps.backend.contracts.trace import SpanSLO

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlanPayload:
    """计划生成所需输入。"""

    dataset_profile: DatasetProfile
    user_goal: str


def _sort_field_recommendations(recommendations: List[FieldPlanItem]) -> List[FieldPlanItem]:
    """按优先级排序字段推荐。"""

    return sorted(recommendations, key=lambda item: item.priority)


class PlanRefinementAgent(Agent):
    """根据数据画像与用户意图生成计划。"""

    name = "plan_refiner"
    slo = SpanSLO(
        max_duration_ms=2000,
        max_retries=1,
        failure_isolation_required=True,
    )

    def run(self, context: AgentContext, payload: PlanPayload) -> AgentOutcome:
        """执行计划生成逻辑。

        Parameters
        ----------
        context: AgentContext
            当前任务上下文。
        payload: PlanPayload
            包含数据画像与用户意图。

        Returns
        -------
        AgentOutcome
            输出 Plan 契约与 Trace Span。
        """

        LOGGER.info(
            "开始计划细化",
            extra={
                "task_id": context.task_id,
                "dataset_id": context.dataset_id,
            },
        )
        span_id = context.trace_recorder.start_span(
            operation="plan.refine",
            agent_name=self.name,
            slo=self.slo,
            parent_span_id=context.parent_span_id,
            model_name="gpt-5",
            prompt_version="v1",
        )
        summary = payload.dataset_profile.summary
        field_plan_items: List[FieldPlanItem] = []
        dimension_field = None
        measure_field = None
        temporal_field = None
        priority_counter = 0
        for field_schema in summary.fields:
            semantic = field_schema.semantic_type
            reason = "字段缺失率较低，适合用于分组。"
            if field_schema.statistics.missing_ratio > 0.3:
                reason = "尽管缺失率较高，但仍可用于探索。"
            recommendation = FieldPlanItem(
                field_name=field_schema.name,
                semantic_role=semantic,
                priority=priority_counter,
                rationale=reason,
                operations=[],
            )
            field_plan_items.append(recommendation)
            if semantic == "dimension" and dimension_field is None:
                dimension_field = field_schema.name
            if semantic == "measure" and measure_field is None:
                measure_field = field_schema.name
            if semantic == "temporal" and temporal_field is None:
                temporal_field = field_schema.name
            priority_counter += 1
        sorted_recommendations = _sort_field_recommendations(recommendations=field_plan_items)
        chart_plan_items: List[ChartPlanItem] = []
        encodings: List[ChartChannelMapping] = []
        rationale = ""
        template_id = ""
        engine = "vega-lite"
        confidence = 0.6
        if temporal_field is not None and measure_field is not None:
            template_id = "line_basic"
            rationale = "包含时间与度量字段，推荐折线趋势图。"
            encodings = [
                ChartChannelMapping(
                    channel="x",
                    field_name=temporal_field,
                    aggregation="none",
                ),
                ChartChannelMapping(
                    channel="y",
                    field_name=measure_field,
                    aggregation="sum",
                ),
            ]
            confidence = 0.8
        elif dimension_field is not None and measure_field is not None:
            template_id = "bar_basic"
            rationale = "适合对比维度与度量，推荐柱状图。"
            encodings = [
                ChartChannelMapping(
                    channel="x",
                    field_name=dimension_field,
                    aggregation="none",
                ),
                ChartChannelMapping(
                    channel="y",
                    field_name=measure_field,
                    aggregation="sum",
                ),
            ]
            confidence = 0.7
        elif dimension_field is not None:
            template_id = "table_overview"
            rationale = "仅存在维度字段，推荐列表查看。"
            encodings = [
                ChartChannelMapping(
                    channel="row",
                    field_name=dimension_field,
                    aggregation="none",
                ),
            ]
            confidence = 0.5
        else:
            template_id = "stat_overview"
            rationale = "缺少可视化字段，提供统计摘要。"
            encodings = []
            confidence = 0.4
        chart_candidate = ChartPlanItem(
            template_id=template_id,
            engine=engine,
            confidence=confidence,
            rationale=rationale,
            encoding=encodings,
            layout_hint=None,
        )
        chart_plan_items.append(chart_candidate)
        transform_code_lines: List[str] = []
        transform_code_lines.append("import pandas as pd")
        transform_code_lines.append("")
        transform_code_lines.append("def transform(df: pd.DataFrame) -> pd.DataFrame:")
        transform_code_lines.append("    \"\"\"根据推荐字段生成聚合结果。\"\"\"")
        transform_code_lines.append("    if df.empty:")
        transform_code_lines.append("        raise ValueError('输入数据不能为空')")
        if dimension_field is not None and measure_field is not None:
            transform_code_lines.append(
                f"    grouped = df.groupby('{dimension_field}', as_index=False)['{measure_field}'].sum()",
            )
            transform_code_lines.append("    grouped = grouped.sort_values(by=grouped.columns[1], ascending=False)")
            transform_code_lines.append("    return grouped")
        elif temporal_field is not None and measure_field is not None:
            transform_code_lines.append(
                f"    grouped = df.groupby('{temporal_field}', as_index=False)['{measure_field}'].sum()",
            )
            transform_code_lines.append("    grouped = grouped.sort_values(by=grouped.columns[0], ascending=True)")
            transform_code_lines.append("    return grouped")
        else:
            transform_code_lines.append("    return df")
        transform_code = "\n".join(transform_code_lines)
        transform_draft = TransformDraft(
            language="python",
            code=transform_code,
            output_table="derived_main",
            intent_summary="为推荐图表准备聚合数据。",
        )
        explain_outline = ExplainOutline(
            bullets=[
                "回顾用户目标与澄清后的计划。",
                "说明推荐字段与图表模板的选择依据。",
                "列出数据变换草案以及潜在后续操作。",
            ],
        )
        assumptions = [
            PlanAssumption(
                statement="数据集结构与扫描摘要保持一致，字段语义未发生变化。",
                confidence=0.8,
                impact="medium",
            ),
        ]
        plan = Plan(
            task_id=context.task_id,
            dataset_id=context.dataset_id,
            refined_goal=f"针对 {payload.user_goal} 的分析计划",
            generated_at=context.clock.now(),
            assumptions=assumptions,
            field_plan=sorted_recommendations,
            chart_plan=chart_plan_items,
            transform_drafts=[transform_draft],
            explain_outline=explain_outline,
        )
        trace_span = context.trace_recorder.finish_span(
            span_id=span_id,
            status="success",
            failure_category=None,
            failure_isolation_ratio=1.0,
            status_detail={
                "chart_candidates": len(chart_plan_items),
                "field_plan": len(sorted_recommendations),
            },
        )
        LOGGER.info(
            "计划细化完成",
            extra={
                "task_id": context.task_id,
                "chart_plan": len(chart_plan_items),
            },
        )
        return AgentOutcome(
            output=plan,
            span_id=span_id,
            trace_span=trace_span,
        )
