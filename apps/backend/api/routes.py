"""FastAPI 路由定义。"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from apps.backend.agents import AgentContext, ScanPayload
from apps.backend.api.dependencies import (
    get_api_recorder,
    get_clock,
    get_dataset_store,
    get_pipeline_agents,
    get_task_runner,
    get_trace_store,
)
from apps.backend.api.schemas import (
    PlanRequest,
    PlanResponse,
    ScanRequest,
    ScanResponse,
    TaskFailurePayload,
    TaskResultPayload,
    TaskResultResponse,
    TraceReplayRequest,
    TraceReplayResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
)
from apps.backend.contracts.trace import TraceRecord
from apps.backend.infra.persistence import ApiRecorder
from apps.backend.infra.tracing import TraceRecorder
from apps.backend.services.pipeline import PipelineConfig, PipelineOutcome, execute_pipeline
from apps.backend.services.task_runner import TaskRunner
from apps.backend.stores import DatasetStore, TraceStore

router = APIRouter()


def _create_trace_recorder(clock) -> TraceRecorder:
    """构造 TraceRecorder。"""

    return TraceRecorder(clock=clock)


def _ensure_path(path_str: str) -> Path:
    """校验本地路径存在。"""

    path = Path(path_str)
    if not path.exists():
        message = f"数据源路径不存在: {path_str}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return path


@router.post("/api/data/scan", response_model=ScanResponse)
def trigger_scan(
    request: ScanRequest,
    dataset_store: DatasetStore = Depends(get_dataset_store),
    trace_store: TraceStore = Depends(get_trace_store),
    clock=Depends(get_clock),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> ScanResponse:
    """触发数据扫描流程。"""

    dataset_path = _ensure_path(path_str=request.dataset_path)
    trace_recorder = _create_trace_recorder(clock=clock)
    agents = get_pipeline_agents()
    context = AgentContext(
        task_id=request.task_id,
        dataset_id=request.dataset_id,
        trace_recorder=trace_recorder,
        clock=clock,
    )
    payload = ScanPayload(
        dataset_id=request.dataset_id,
        dataset_name=request.dataset_name,
        dataset_version=request.dataset_version,
        path=dataset_path,
        sample_limit=request.sample_limit,
    )
    outcome = agents.scanner.run(context=context, payload=payload)
    profile = outcome.output
    dataset_store.save(dataset_id=request.dataset_id, profile=profile)
    trace = trace_recorder.build_trace(
        task_id=request.task_id,
        dataset_id=request.dataset_id,
        spans=[outcome.trace_span],
    )
    trace_store.save(trace=trace)
    response = ScanResponse(
        profile=profile,
        trace=trace,
    )
    api_recorder.record(endpoint="api_data_scan", direction="request", payload=request)
    api_recorder.record(endpoint="api_data_scan", direction="response", payload=response)
    return response


@router.post("/api/plan/refine", response_model=PlanResponse)
def refine_plan(
    request: PlanRequest,
    dataset_store: DatasetStore = Depends(get_dataset_store),
    trace_store: TraceStore = Depends(get_trace_store),
    clock=Depends(get_clock),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> PlanResponse:
    """生成计划、解释与 Trace。"""

    dataset_path = _ensure_path(path_str=request.dataset_path)
    trace_recorder = _create_trace_recorder(clock=clock)
    agents = get_pipeline_agents()
    context = AgentContext(
        task_id=request.task_id,
        dataset_id=request.dataset_id,
        trace_recorder=trace_recorder,
        clock=clock,
    )
    config = PipelineConfig(
        task_id=request.task_id,
        dataset_id=request.dataset_id,
        dataset_name=request.dataset_name,
        dataset_version=request.dataset_version,
        dataset_path=dataset_path,
        sample_limit=request.sample_limit,
        user_goal=request.user_goal,
    )
    outcome: PipelineOutcome = execute_pipeline(
        config=config,
        context=context,
        trace_recorder=trace_recorder,
        agents=agents,
    )
    dataset_store.save(dataset_id=request.dataset_id, profile=outcome.profile)
    trace_store.save(trace=outcome.trace)
    response = PlanResponse(
        profile=outcome.profile,
        plan=outcome.plan,
        prepared_table=outcome.prepared_table,
        output_table=outcome.output_table,
        chart=outcome.chart,
        encoding_patch=outcome.encoding_patch,
        explanation=outcome.explanation,
        trace=outcome.trace,
    )
    api_recorder.record(endpoint="api_plan_refine", direction="request", payload=request)
    api_recorder.record(endpoint="api_plan_refine", direction="response", payload=response)
    return response


@router.get("/api/trace/{task_id}", response_model=TraceRecord)
def get_trace(
    task_id: str,
    trace_store: TraceStore = Depends(get_trace_store),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> TraceRecord:
    """根据 task_id 获取 Trace 记录。"""

    try:
        trace = trace_store.require(task_id=task_id)
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    api_recorder.record(endpoint="api_trace_get", direction="request", payload={"task_id": task_id})
    api_recorder.record(endpoint="api_trace_get", direction="response", payload=trace)
    return trace


@router.post("/api/trace/replay", response_model=TraceReplayResponse)
def replay_trace(
    request: TraceReplayRequest,
    trace_store: TraceStore = Depends(get_trace_store),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> TraceReplayResponse:
    """回放已存储的 Trace。"""

    try:
        trace = trace_store.require(task_id=request.task_id)
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    response = TraceReplayResponse(trace=trace)
    api_recorder.record(endpoint="api_trace_replay", direction="request", payload=request)
    api_recorder.record(endpoint="api_trace_replay", direction="response", payload=response)
    return response


@router.post("/api/task/submit", response_model=TaskSubmitResponse)
async def submit_task(
    request: TaskSubmitRequest,
    task_runner: TaskRunner = Depends(get_task_runner),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> TaskSubmitResponse:
    """提交任务并异步执行完整流程。"""

    dataset_path = _ensure_path(path_str=request.dataset_path)
    task_id = request.task_id or f"task_{uuid4()}"
    config = PipelineConfig(
        task_id=task_id,
        dataset_id=request.dataset_id,
        dataset_name=request.dataset_name,
        dataset_version=request.dataset_version,
        dataset_path=dataset_path,
        sample_limit=request.sample_limit,
        user_goal=request.user_goal,
    )
    await task_runner.submit_task(config=config)
    response = TaskSubmitResponse(task_id=task_id)
    api_recorder.record(endpoint="api_task_submit", direction="request", payload=request)
    api_recorder.record(endpoint="api_task_submit", direction="response", payload=response)
    return response


@router.get("/api/task/{task_id}/result", response_model=TaskResultResponse)
def fetch_task_result(
    task_id: str,
    task_runner: TaskRunner = Depends(get_task_runner),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> TaskResultResponse:
    """获取任务执行状态与结果。"""

    try:
        snapshot = task_runner.get_snapshot(task_id=task_id)
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    if snapshot.status == "completed":
        outcome = snapshot.outcome
        if outcome is None:
            message = "任务已完成但缺少结果。"
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message)
        result_payload = TaskResultPayload(
            profile=outcome.profile,
            plan=outcome.plan,
            prepared_table=outcome.prepared_table,
            output_table=outcome.output_table,
            chart=outcome.chart,
            encoding_patch=outcome.encoding_patch,
            explanation=outcome.explanation,
            trace=outcome.trace,
        )
        response = TaskResultResponse(
            task_id=task_id,
            status="completed",
            result=result_payload,
            failure=None,
        )
        api_recorder.record(endpoint="api_task_result", direction="request", payload={"task_id": task_id})
        api_recorder.record(endpoint="api_task_result", direction="response", payload=response)
        return response

    if snapshot.status == "failed":
        failure = snapshot.failure
        if failure is None:
            message = "任务失败但缺少错误信息。"
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message)
        failure_payload = TaskFailurePayload(
            error_type=failure.error_type,
            error_message=failure.error_message,
        )
        response = TaskResultResponse(
            task_id=task_id,
            status="failed",
            result=None,
            failure=failure_payload,
        )
        api_recorder.record(endpoint="api_task_result", direction="request", payload={"task_id": task_id})
        api_recorder.record(endpoint="api_task_result", direction="response", payload=response)
        return response

    response = TaskResultResponse(
        task_id=task_id,
        status=snapshot.status,
        result=None,
        failure=None,
    )
    api_recorder.record(endpoint="api_task_result", direction="request", payload={"task_id": task_id})
    api_recorder.record(endpoint="api_task_result", direction="response", payload=response)
    return response


@router.get("/api/task/stream")
async def stream_task(
    task_id: str,
    task_runner: TaskRunner = Depends(get_task_runner),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
):
    """通过 SSE 返回任务执行进度。"""

    try:
        queue = await task_runner.subscribe(task_id=task_id)
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    async def event_generator():
        while True:
            item = await queue.get()
            if item is None:
                yield "event: end\n\n"
                break
            payload = json.dumps(item, ensure_ascii=False, default=str)
            yield f"data: {payload}\n\n"

    api_recorder.record(endpoint="api_task_stream", direction="request", payload={"task_id": task_id})
    return StreamingResponse(event_generator(), media_type="text/event-stream")
