"""解释 Agent，负责产出 Markdown 说明。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from apps.backend.agents.base import Agent, AgentContext, AgentOutcome
from apps.backend.contracts.dataset_profile import DatasetProfile
from apps.backend.contracts.explanation import ExplanationArtifact
from apps.backend.contracts.plan import Plan
from apps.backend.contracts.trace import SpanSLO

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExplanationPayload:
    """解释生成所需输入。"""

    dataset_profile: DatasetProfile
    plan: Plan
    transform_preview: Optional[str]


class ExplanationAgent(Agent):
    """根据计划与画像生成解释。"""

    name = "explanation_agent"
    slo = SpanSLO(
        max_duration_ms=1500,
        max_retries=1,
        failure_isolation_required=True,
    )

    def run(self, context: AgentContext, payload: ExplanationPayload) -> AgentOutcome:
        """生成解释 Markdown。

        Parameters
        ----------
        context: AgentContext
            当前任务上下文。
        payload: ExplanationPayload
            包含数据画像、计划与变换预览。

        Returns
        -------
        AgentOutcome
            输出 ExplanationArtifact 与 Trace Span。
        """

        span_id = context.trace_recorder.start_span(
            operation="explain.summarize",
            agent_name=self.name,
            slo=self.slo,
            parent_span_id=None,
            model_name="gpt-4o-mini",
            prompt_version="v1",
        )
        profile = payload.dataset_profile
        plan = payload.plan
        bullet_lines = []
        bullet_lines.append(f"- 任务目标：{plan.refined_goal}")
        top_fields = ", ".join(item.field_name for item in plan.field_plan[:3])
        bullet_lines.append(f"- 推荐字段：{top_fields}")
        chart = plan.chart_plan[0]
        bullet_lines.append(f"- 主推图表：{chart.template_id}（{chart.rationale}）")
        if payload.transform_preview is not None:
            bullet_lines.append(f"- 预览变换：{payload.transform_preview}")
        bullet_lines.append(
            f"- 数据行数：{profile.row_count}，字段数：{len(profile.summary.fields)}",
        )
        markdown_lines = ["## 计划摘要", ""]
        markdown_lines.extend(bullet_lines)
        markdown = "\n".join(markdown_lines)
        artifact = ExplanationArtifact(
            markdown=markdown,
            key_points=bullet_lines,
            generated_at=context.clock.now(),
        )
        trace_span = context.trace_recorder.finish_span(
            span_id=span_id,
            status="success",
            failure_category=None,
            failure_isolation_ratio=1.0,
        )
        LOGGER.info(
            "解释生成完成",
            extra={
                "task_id": context.task_id,
            },
        )
        return AgentOutcome(
            output=artifact,
            span_id=span_id,
            trace_span=trace_span,
        )
