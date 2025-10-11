"""统一封装多 Agent 流程。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from apps.backend.agents import (
    AgentContext,
    DatasetScannerAgent,
    ExplanationAgent,
    ExplanationPayload,
    PlanPayload,
    PlanRefinementAgent,
    ScanPayload,
    TransformExecutionAgent,
    TransformPayload,
    ChartPayload,
    ChartRecommendationAgent,
    ChartRecommendationResult,
    TransformArtifacts,
)
from apps.backend.agents.base import AgentOutcome
from apps.backend.contracts.dataset_profile import DatasetProfile
from apps.backend.contracts.encoding_patch import EncodingPatch, EncodingPatchOp
from apps.backend.contracts.explanation import ExplanationArtifact
from apps.backend.contracts.plan import Plan
from apps.backend.contracts.chart_spec import ChartSpec
from apps.backend.contracts.recommendation import RecommendationList
from apps.backend.contracts.trace import TraceRecord, TraceSpan
from apps.backend.contracts.transform import OutputTable, PreparedTable
from apps.backend.infra.tracing import TraceRecorder
from apps.backend.services import OrchestratorResult, StateMachineOrchestrator, StateNode


@dataclass(frozen=True)
class PipelineConfig:
    """描述执行多 Agent 流程所需的参数。"""

    task_id: str
    dataset_id: str
    dataset_name: str
    dataset_version: str
    dataset_path: Path
    sample_limit: int
    user_goal: str


@dataclass(frozen=True)
class PipelineAgents:
    """封装流程涉及的 Agent 实例集合。"""

    scanner: DatasetScannerAgent
    planner: PlanRefinementAgent
    transformer: TransformExecutionAgent
    chart: ChartRecommendationAgent
    explainer: ExplanationAgent


@dataclass(frozen=True)
class PipelineOutcome:
    """流程执行产出的聚合结果。"""

    profile: DatasetProfile
    plan: Plan
    prepared_table: PreparedTable
    output_table: OutputTable
    chart: ChartSpec
    recommendations: RecommendationList
    encoding_patch: EncodingPatch
    explanation: ExplanationArtifact
    trace: TraceRecord
    spans: list[TraceSpan]


def execute_pipeline(
    *,
    config: PipelineConfig,
    context: AgentContext,
    trace_recorder: TraceRecorder,
    agents: PipelineAgents,
    progress_callback: Optional[Callable[[str, AgentOutcome], None]] = None,
) -> PipelineOutcome:
    """执行 Scan → Plan → Transform → Chart → Explain 流程。"""

    dataset_path = config.dataset_path

    def build_scan_payload(_: dict[str, object]) -> ScanPayload:
        return ScanPayload(
            dataset_id=config.dataset_id,
            dataset_name=config.dataset_name,
            dataset_version=config.dataset_version,
            path=dataset_path,
            sample_limit=config.sample_limit,
        )

    def build_plan_payload(shared: dict[str, object]) -> PlanPayload:
        if "scan" not in shared:
            raise ValueError("缺少扫描输出，无法生成计划。")
        profile = shared["scan"]
        if not isinstance(profile, DatasetProfile):
            raise TypeError("扫描输出类型非法。")
        return PlanPayload(
            dataset_profile=profile,
            user_goal=config.user_goal,
        )

    def build_transform_payload(shared: dict[str, object]) -> TransformPayload:
        if "plan" not in shared or "scan" not in shared:
            raise ValueError("缺少计划或扫描结果，无法执行变换。")
        profile = shared["scan"]
        plan = shared["plan"]
        return TransformPayload(
            dataset_profile=profile,
            plan=plan,
            dataset_path=dataset_path,
            sample_limit=config.sample_limit,
        )

    def build_chart_payload(shared: dict[str, object]) -> ChartPayload:
        if "plan" not in shared or "transform" not in shared:
            raise ValueError("缺少计划或变换结果，无法生成图表。")
        plan = shared["plan"]
        artifacts = shared["transform"]
        if not isinstance(artifacts, TransformArtifacts):
            raise TypeError("变换输出类型非法。")
        return ChartPayload(
            plan=plan,
            table_id=artifacts.output_table.output_table_id,
            row_count=artifacts.output_table.metrics.rows_out,
        )

    def build_explanation_payload(shared: dict[str, object]) -> ExplanationPayload:
        missing_keys = {"plan", "scan", "transform"} - shared.keys()
        if missing_keys:
            message = f"缺少 {', '.join(sorted(missing_keys))} 输出，无法生成解释。"
            raise ValueError(message)
        plan = shared["plan"]
        profile = shared["scan"]
        artifacts = shared["transform"]
        if not isinstance(artifacts, TransformArtifacts):
            raise TypeError("变换输出类型非法。")
        preview = f"{artifacts.output_table.output_table_id}: {artifacts.output_table.metrics.rows_out} 行"
        return ExplanationPayload(
            dataset_profile=profile,
            plan=plan,
            transform_preview=preview,
        )

    orchestrator = StateMachineOrchestrator(
        nodes=[
            StateNode(name="scan", agent=agents.scanner, payload_builder=build_scan_payload),
            StateNode(name="plan", agent=agents.planner, payload_builder=build_plan_payload),
            StateNode(name="transform", agent=agents.transformer, payload_builder=build_transform_payload),
            StateNode(name="chart", agent=agents.chart, payload_builder=build_chart_payload),
            StateNode(name="explain", agent=agents.explainer, payload_builder=build_explanation_payload),
        ],
    )
    result: OrchestratorResult = orchestrator.run(
        context=context,
        shared_inputs={},
        progress_callback=progress_callback,
    )
    profile = result.outputs["scan"]
    plan = result.outputs["plan"]
    artifacts = result.outputs["transform"]
    if not isinstance(artifacts, TransformArtifacts):
        raise TypeError("变换节点输出类型非法。")
    chart_output = result.outputs["chart"]
    if not isinstance(chart_output, ChartRecommendationResult):
        raise TypeError("图表节点输出类型非法。")
    explanation = result.outputs["explain"]
    primary_chart = chart_output.primary_chart
    encoding_patch = EncodingPatch(
        target_chart_id=primary_chart.chart_id,
        ops=[
            EncodingPatchOp(
                op_type="add",
                path=["parameters", "notes"],
                value=f"initial render for {plan.refined_goal}",
            ),
        ],
        rationale="记录初次编码生成时的模板参数。",
    )
    trace = trace_recorder.build_trace(
        task_id=config.task_id,
        dataset_id=config.dataset_id,
        spans=result.spans,
    )
    return PipelineOutcome(
        profile=profile,
        plan=plan,
        prepared_table=artifacts.prepared_table,
        output_table=artifacts.output_table,
        chart=primary_chart,
        recommendations=chart_output.recommendations,
        encoding_patch=encoding_patch,
        explanation=explanation,
        trace=trace,
        spans=result.spans,
    )
