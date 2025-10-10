"""FastAPI 依赖注入配置。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from apps.backend.agents import (
    DatasetScannerAgent,
    ExplanationAgent,
    PlanRefinementAgent,
    TransformExecutionAgent,
    ChartRecommendationAgent,
    NaturalEditAgent,
)
from apps.backend.infra.clock import UtcClock
from apps.backend.infra.persistence import ApiRecorder
from apps.backend.services.pipeline import PipelineAgents
from apps.backend.services.task_runner import TaskRunner
from apps.backend.stores import DatasetStore, TraceStore


@lru_cache
def get_clock() -> UtcClock:
    """提供全局 UTC 时钟实例。"""

    return UtcClock()


@lru_cache
def get_dataset_store() -> DatasetStore:
    """提供数据画像缓存。"""

    return DatasetStore()


@lru_cache
def get_trace_store() -> TraceStore:
    """提供 Trace 缓存。"""

    base_path = Path("var/traces")
    return TraceStore(base_path=base_path)


@lru_cache
def get_api_recorder() -> ApiRecorder:
    """提供 API 请求/响应落盘器。"""

    base_path = Path("var/api_logs")
    return ApiRecorder(base_path=base_path)


@lru_cache
def get_pipeline_agents() -> PipelineAgents:
    """提供多 Agent 流程所需的实例集合。"""

    return PipelineAgents(
        scanner=DatasetScannerAgent(),
        planner=PlanRefinementAgent(),
        transformer=TransformExecutionAgent(),
        chart=ChartRecommendationAgent(),
        explainer=ExplanationAgent(),
    )


@lru_cache
def get_natural_edit_agent() -> NaturalEditAgent:
    """提供自然语言编辑 Agent。"""

    return NaturalEditAgent()


@lru_cache
def get_task_runner() -> TaskRunner:
    """提供任务执行与 SSE 管理器。"""

    return TaskRunner(
        dataset_store=get_dataset_store(),
        trace_store=get_trace_store(),
        clock=get_clock(),
        agents=get_pipeline_agents(),
        api_recorder=get_api_recorder(),
    )
