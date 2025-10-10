"""FastAPI 路由定义。"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from apps.backend.agents import AgentContext, ScanPayload, TransformPayload, ChartPayload
from apps.backend.compat import model_dump
from apps.backend.agents.transform import TransformArtifacts
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
    TransformExecuteRequest,
    TransformExecuteResponse,
    TransformAggregateRequest,
    TransformAggregateResponse,
    ChartRecommendRequest,
    ChartRecommendResponse,
    NaturalEditRequest,
    NaturalEditResponse,
    SchemaExportResponse,
)
from apps.backend.contracts.chart_spec import ChartSpec
from apps.backend.contracts.dataset_profile import DatasetProfile, DatasetSummary
from apps.backend.contracts.metadata import SCHEMA_VERSION
from apps.backend.contracts.encoding_patch import EncodingPatch, EncodingPatchOp
from apps.backend.contracts.plan import Plan
from apps.backend.contracts.task_event import TaskEvent
from apps.backend.contracts.trace import TraceRecord, TraceSpan, SpanMetrics, SpanEvent, SpanSLO
from apps.backend.contracts.transform import (
    PreparedTable,
    PreparedTableLimits,
    PreparedTableStats,
    TableColumn,
    TableSample,
    OutputTable,
)
from apps.backend.infra.persistence import ApiRecorder
from apps.backend.infra.tracing import TraceRecorder
from apps.backend.services.pipeline import PipelineConfig, PipelineOutcome, execute_pipeline
from apps.backend.services.task_runner import TaskRunner
from apps.backend.stores import DatasetStore, TraceStore

LOGGER = logging.getLogger(__name__)

router = APIRouter()

SCHEMA_EXPORT_MODELS: dict[str, type] = {
    DatasetSummary.schema_name(): DatasetSummary,
    Plan.schema_name(): Plan,
    PreparedTable.schema_name(): PreparedTable,
    OutputTable.schema_name(): OutputTable,
    ChartSpec.schema_name(): ChartSpec,
    EncodingPatch.schema_name(): EncodingPatch,
    TraceRecord.schema_name(): TraceRecord,
    TaskEvent.schema_name(): TaskEvent,
}


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


def _record_request(api_recorder: ApiRecorder, endpoint: str, payload: object) -> None:
    """统一请求落盘入口。"""

    api_recorder.record(endpoint=endpoint, direction="request", payload=payload)


def _record_response(api_recorder: ApiRecorder, endpoint: str, payload: object) -> None:
    """统一响应落盘入口。"""

    api_recorder.record(endpoint=endpoint, direction="response", payload=payload)


def _record_error(
    api_recorder: ApiRecorder,
    endpoint: str,
    *,
    error_type: str,
    error_message: str,
    status_code: int,
) -> None:
    """落盘错误信息并记录日志。"""

    LOGGER.warning(
        "API 调用失败",
        extra={
            "endpoint": endpoint,
            "error_type": error_type,
            "status_code": status_code,
        },
    )
    api_recorder.record_error(
        endpoint=endpoint,
        payload={
            "error_type": error_type,
            "error_message": error_message,
            "status_code": status_code,
        },
    )


def _load_or_scan_profile(
    *,
    dataset_id: str,
    dataset_name: str,
    dataset_version: str,
    dataset_path: Path,
    sample_limit: int,
    dataset_store: DatasetStore,
    agents,
    context: AgentContext,
) -> Tuple[DatasetProfile, List[TraceSpan]]:
    """从缓存中加载画像，或触发扫描生成。"""

    spans: List[TraceSpan] = []
    try:
        profile = dataset_store.require(dataset_id=dataset_id)
    except KeyError:
        payload = ScanPayload(
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            path=dataset_path,
            sample_limit=sample_limit,
        )
        outcome = agents.scanner.run(context=context, payload=payload)
        profile = outcome.output
        dataset_store.save(dataset_id=dataset_id, profile=profile)
        spans.append(outcome.trace_span)
    else:
        # 命中缓存时仍生成 data.scan Span，确保 Trace 可观测。
        span_id = context.trace_recorder.start_span(
            operation="data.scan",
            agent_name=agents.scanner.name,
            slo=agents.scanner.slo,
            parent_span_id=context.parent_span_id,
            model_name=None,
            prompt_version=None,
            start_detail={"source": "cache"},
        )
        context.trace_recorder.update_span(
            span_id=span_id,
            rows_in=profile.row_count,
            rows_out=profile.row_count,
            dataset_hash=profile.hash_digest,
            schema_version=SCHEMA_VERSION,
        )
        context.trace_recorder.record_event(
            span_id=span_id,
            event_type="cache_hit",
            detail={"reason": "dataset_store"},
        )
        cache_span = context.trace_recorder.finish_span(
            span_id=span_id,
            status="success",
            failure_category=None,
            failure_isolation_ratio=1.0,
            status_detail={"source": "cache"},
        )
        spans.append(cache_span)
    return profile, spans


def _summary_to_prepared_table(
    *,
    summary: DatasetSummary,
    sample_limit: int,
    transform_id: str,
) -> PreparedTable:
    """将 DatasetSummary 转换为 PreparedTable。"""

    semantic_role_map = {
        "dimension": "dimension",
        "measure": "measure",
        "temporal": "temporal",
        "identifier": "identifier",
        "geo": "dimension",
        "unknown": "dimension",
    }
    columns: List[TableColumn] = []
    for field in summary.fields:
        role = semantic_role_map.get(field.semantic_type, "dimension")
        columns.append(
            TableColumn(
                column_name=field.name,
                data_type=field.data_type,
                semantic_role=role,
                nullable=field.nullable,
                description=field.description or field.title,
            ),
        )
    sample_rows: List[dict[str, str]] = []
    for row in summary.sample_rows[:sample_limit]:
        normalized_row: dict[str, str] = {}
        for column in columns:
            value = row.get(column.column_name, "")
            normalized_row[column.column_name] = str(value)
        sample_rows.append(normalized_row)
    stats = PreparedTableStats(
        row_count=summary.row_count,
        estimated_bytes=None,
        distinct_row_count=None,
    )
    limits = PreparedTableLimits(
        row_limit=None,
        timeout_ms=None,
        sample_limit=sample_limit,
    )
    prepared = PreparedTable(
        prepared_table_id=f"prepared_{transform_id}",
        source_id=summary.dataset_id,
        transform_id=transform_id,
        schema=columns,
        sample=TableSample(rows=sample_rows),
        stats=stats,
        limits=limits,
    )
    return prepared


def _rebuild_trace_record(
    *,
    original: TraceRecord,
    clock,
) -> TraceRecord:
    """根据落盘 Trace 生成新的同构 Trace。"""

    base_started_at = clock.now()
    span_id_map: dict[str, str] = {}
    rebuilt_spans: List[TraceSpan] = []
    for index, span in enumerate(original.spans):
        new_span_id = str(uuid4())
        span_id_map[span.span_id] = new_span_id
        parent_new_id: Optional[str] = None
        if span.parent_span_id is not None:
            parent_new_id = span_id_map.get(span.parent_span_id)
        started_at = base_started_at + timedelta(milliseconds=index * 100)
        slo_copy = SpanSLO.model_validate(model_dump(span.slo))
        metrics_source = span.metrics
        metrics_copy = SpanMetrics(
            duration_ms=metrics_source.duration_ms,
            retry_count=metrics_source.retry_count,
            rows_in=metrics_source.rows_in,
            rows_out=metrics_source.rows_out,
        )
        events_copy: List[SpanEvent] = []
        for event_index, event in enumerate(span.events):
            event_timestamp = started_at + timedelta(milliseconds=event_index * 10 + 1)
            events_copy.append(
                SpanEvent(
                    event_type=event.event_type,
                    timestamp=event_timestamp,
                    detail=event.detail,
                ),
            )
        rebuilt_spans.append(
            TraceSpan(
                span_id=new_span_id,
                parent_span_id=parent_new_id,
                operation=span.operation,
                agent_name=span.agent_name,
                status=span.status,
                started_at=started_at,
                slo=slo_copy,
                metrics=metrics_copy,
                model_name=span.model_name,
                prompt_version=span.prompt_version,
                dataset_hash=span.dataset_hash,
                schema_version=span.schema_version,
                abort_reason=span.abort_reason,
                error_class=span.error_class,
                fallback_path=span.fallback_path,
                sse_seq=span.sse_seq,
                events=events_copy,
            ),
        )
    rebuilt_trace = TraceRecord(
        trace_id=str(uuid4()),
        task_id=original.task_id,
        dataset_id=original.dataset_id,
        created_at=clock.now(),
        spans=rebuilt_spans,
    )
    return rebuilt_trace


@router.post("/api/data/scan", response_model=ScanResponse)
def trigger_scan(
    request: ScanRequest,
    dataset_store: DatasetStore = Depends(get_dataset_store),
    trace_store: TraceStore = Depends(get_trace_store),
    clock=Depends(get_clock),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> ScanResponse:
    """触发数据扫描流程。"""

    endpoint = "api_data_scan"
    _record_request(api_recorder=api_recorder, endpoint=endpoint, payload=request)
    try:
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
    except HTTPException as error:
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error.detail),
            status_code=error.status_code,
        )
        raise
    except Exception as error:  # noqa: BLE001 - 统一捕获记录后继续抛出
        LOGGER.exception("数据扫描出现未预期错误", extra={"endpoint": endpoint})
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        raise
    _record_response(api_recorder=api_recorder, endpoint=endpoint, payload=response)
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

    endpoint = "api_plan_refine"
    _record_request(api_recorder=api_recorder, endpoint=endpoint, payload=request)
    try:
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
    except HTTPException as error:
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error.detail),
            status_code=error.status_code,
        )
        raise
    except Exception as error:  # noqa: BLE001 - 用于统一记录意外异常
        LOGGER.exception("计划生成失败", extra={"endpoint": endpoint})
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        raise
    _record_response(api_recorder=api_recorder, endpoint=endpoint, payload=response)
    return response


@router.get("/api/trace/{task_id}", response_model=TraceRecord)
def get_trace(
    task_id: str,
    trace_store: TraceStore = Depends(get_trace_store),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> TraceRecord:
    """根据 task_id 获取 Trace 记录。"""

    endpoint = "api_trace_get"
    _record_request(api_recorder=api_recorder, endpoint=endpoint, payload={"task_id": task_id})
    try:
        trace = trace_store.require(task_id=task_id)
    except KeyError as error:
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error),
            status_code=status.HTTP_404_NOT_FOUND,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    _record_response(api_recorder=api_recorder, endpoint=endpoint, payload=trace)
    return trace


@router.post("/api/trace/replay", response_model=TraceReplayResponse)
def replay_trace(
    request: TraceReplayRequest,
    trace_store: TraceStore = Depends(get_trace_store),
    clock=Depends(get_clock),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> TraceReplayResponse:
    """回放已存储的 Trace。"""

    endpoint = "api_trace_replay"
    _record_request(api_recorder=api_recorder, endpoint=endpoint, payload=request)
    try:
        trace = trace_store.require(task_id=request.task_id)
    except KeyError as error:
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error),
            status_code=status.HTTP_404_NOT_FOUND,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    try:
        if request.mode == "rebuild":
            replay_trace_record = _rebuild_trace_record(original=trace, clock=clock)
        else:
            replay_trace_record = trace
        response = TraceReplayResponse(trace=replay_trace_record)
    except Exception as error:  # noqa: BLE001 - 兜底记录异常
        LOGGER.exception("Trace 回放失败", extra={"endpoint": endpoint})
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        raise
    _record_response(api_recorder=api_recorder, endpoint=endpoint, payload=response)
    return response


@router.post("/api/task/submit", response_model=TaskSubmitResponse)
async def submit_task(
    request: TaskSubmitRequest,
    task_runner: TaskRunner = Depends(get_task_runner),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> TaskSubmitResponse:
    """提交任务并异步执行完整流程。"""

    endpoint = "api_task_submit"
    _record_request(api_recorder=api_recorder, endpoint=endpoint, payload=request)
    try:
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
    except HTTPException as error:
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error.detail),
            status_code=error.status_code,
        )
        raise
    except Exception as error:  # noqa: BLE001 - 捕获未知错误用于日志与落盘
        LOGGER.exception("任务提交失败", extra={"endpoint": endpoint})
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        raise
    _record_response(api_recorder=api_recorder, endpoint=endpoint, payload=response)
    return response


@router.get("/api/task/{task_id}/result", response_model=TaskResultResponse)
def fetch_task_result(
    task_id: str,
    task_runner: TaskRunner = Depends(get_task_runner),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> TaskResultResponse:
    """获取任务执行状态与结果。"""

    endpoint = "api_task_result"
    _record_request(api_recorder=api_recorder, endpoint=endpoint, payload={"task_id": task_id})
    try:
        snapshot = task_runner.get_snapshot(task_id=task_id)
    except KeyError as error:
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error),
            status_code=status.HTTP_404_NOT_FOUND,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    try:
        if snapshot.status == "completed":
            outcome = snapshot.outcome
            if outcome is None:
                message = "任务已完成但缺少结果。"
                _record_error(
                    api_recorder=api_recorder,
                    endpoint=endpoint,
                    error_type="MissingOutcomeError",
                    error_message=message,
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
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
        elif snapshot.status == "failed":
            failure = snapshot.failure
            if failure is None:
                message = "任务失败但缺少错误信息。"
                _record_error(
                    api_recorder=api_recorder,
                    endpoint=endpoint,
                    error_type="MissingFailureError",
                    error_message=message,
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
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
        else:
            response = TaskResultResponse(
                task_id=task_id,
                status=snapshot.status,
                result=None,
                failure=None,
            )
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001 - 统一兜底记录
        LOGGER.exception("查询任务状态失败", extra={"endpoint": endpoint})
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        raise
    _record_response(api_recorder=api_recorder, endpoint=endpoint, payload=response)
    return response


@router.get("/api/task/stream")
async def stream_task(
    task_id: str,
    task_runner: TaskRunner = Depends(get_task_runner),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
):
    """通过 SSE 返回任务执行进度。"""

    endpoint = "api_task_stream"
    _record_request(api_recorder=api_recorder, endpoint=endpoint, payload={"task_id": task_id})
    try:
        queue = await task_runner.subscribe(task_id=task_id)
    except KeyError as error:
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error),
            status_code=status.HTTP_404_NOT_FOUND,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    async def event_generator():
        while True:
            item = await queue.get()
            if item is None:
                yield "event: end\n\n"
                break
            payload = json.dumps(model_dump(item), ensure_ascii=False)
            yield f"data: {payload}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
@router.post("/api/transform/execute", response_model=TransformExecuteResponse)
def execute_transform(
    request: TransformExecuteRequest,
    dataset_store: DatasetStore = Depends(get_dataset_store),
    trace_store: TraceStore = Depends(get_trace_store),
    clock=Depends(get_clock),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> TransformExecuteResponse:
    """执行单个变换草案并返回准备表及输出表。"""

    endpoint = "api_transform_execute"
    _record_request(api_recorder=api_recorder, endpoint=endpoint, payload=request)
    try:
        dataset_path = _ensure_path(path_str=request.dataset_path)
        trace_recorder = _create_trace_recorder(clock=clock)
        agents = get_pipeline_agents()
        context = AgentContext(
            task_id=request.task_id,
            dataset_id=request.dataset_id,
            trace_recorder=trace_recorder,
            clock=clock,
        )
        profile, spans = _load_or_scan_profile(
            dataset_id=request.dataset_id,
            dataset_name=request.dataset_name,
            dataset_version=request.dataset_version,
            dataset_path=dataset_path,
            sample_limit=request.sample_limit,
            dataset_store=dataset_store,
            agents=agents,
            context=context,
        )
        transform_payload = TransformPayload(
            dataset_profile=profile,
            plan=request.plan,
            dataset_path=dataset_path,
            sample_limit=request.sample_limit,
        )
        outcome = agents.transformer.run(context=context, payload=transform_payload)
        artifacts = outcome.output
        if not isinstance(artifacts, TransformArtifacts):
            message = "变换输出类型非法。"
            raise TypeError(message)
        spans.append(outcome.trace_span)
        trace = trace_recorder.build_trace(
            task_id=request.task_id,
            dataset_id=request.dataset_id,
            spans=spans,
        )
        trace_store.save(trace=trace)
        response = TransformExecuteResponse(
            prepared_table=artifacts.prepared_table,
            output_table=artifacts.output_table,
            trace=trace,
        )
    except HTTPException as error:
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error.detail),
            status_code=error.status_code,
        )
        raise
    except Exception as error:  # noqa: BLE001 - 记录并抛出未知异常
        LOGGER.exception("变换执行失败", extra={"endpoint": endpoint})
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        raise
    _record_response(api_recorder=api_recorder, endpoint=endpoint, payload=response)
    return response
@router.post("/api/transform/aggregate_bin", response_model=TransformAggregateResponse)
def aggregate_transform(
    request: TransformAggregateRequest,
    dataset_store: DatasetStore = Depends(get_dataset_store),
    clock=Depends(get_clock),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> TransformAggregateResponse:
    """生成预处理表，支持基于计划或摘要的占位实现。"""

    endpoint = "api_transform_aggregate_bin"
    _record_request(api_recorder=api_recorder, endpoint=endpoint, payload=request)
    try:
        dataset_path = _ensure_path(path_str=request.dataset_path)
        agents = get_pipeline_agents()
        trace_recorder = _create_trace_recorder(clock=clock)
        context = AgentContext(
            task_id=request.task_id,
            dataset_id=request.dataset_id,
            trace_recorder=trace_recorder,
            clock=clock,
        )
        prepared_table: PreparedTable
        if request.plan is not None:
            profile, _ = _load_or_scan_profile(
                dataset_id=request.dataset_id,
                dataset_name=request.dataset_name,
                dataset_version=request.dataset_version,
                dataset_path=dataset_path,
                sample_limit=request.sample_limit,
                dataset_store=dataset_store,
                agents=agents,
                context=context,
            )
            transform_payload = TransformPayload(
                dataset_profile=profile,
                plan=request.plan,
                dataset_path=dataset_path,
                sample_limit=request.sample_limit,
            )
            outcome = agents.transformer.run(context=context, payload=transform_payload)
            artifacts = outcome.output
            if not isinstance(artifacts, TransformArtifacts):
                message = "变换输出类型非法。"
                raise TypeError(message)
            prepared_table = artifacts.prepared_table
        else:
            if request.dataset_summary is not None:
                summary = request.dataset_summary
            else:
                profile, _ = _load_or_scan_profile(
                    dataset_id=request.dataset_id,
                    dataset_name=request.dataset_name,
                    dataset_version=request.dataset_version,
                    dataset_path=dataset_path,
                    sample_limit=request.sample_limit,
                    dataset_store=dataset_store,
                    agents=agents,
                    context=context,
                )
                summary = profile.summary
            transform_id = f"aggregate_{request.task_id}"
            prepared_table = _summary_to_prepared_table(
                summary=summary,
                sample_limit=request.sample_limit,
                transform_id=transform_id,
            )
        response = TransformAggregateResponse(prepared_table=prepared_table)
    except HTTPException as error:
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error.detail),
            status_code=error.status_code,
        )
        raise
    except Exception as error:  # noqa: BLE001 - 记录并抛出未知异常
        LOGGER.exception("预聚合生成失败", extra={"endpoint": endpoint})
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        raise
    _record_response(api_recorder=api_recorder, endpoint=endpoint, payload=response)
    return response
@router.post("/api/chart/recommend", response_model=ChartRecommendResponse)
def recommend_chart(
    request: ChartRecommendRequest,
    trace_store: TraceStore = Depends(get_trace_store),
    clock=Depends(get_clock),
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> ChartRecommendResponse:
    """根据计划推荐图表规范。"""

    endpoint = "api_chart_recommend"
    _record_request(api_recorder=api_recorder, endpoint=endpoint, payload=request)
    try:
        trace_recorder = _create_trace_recorder(clock=clock)
        agents = get_pipeline_agents()
        context = AgentContext(
            task_id=request.task_id,
            dataset_id=request.dataset_id,
            trace_recorder=trace_recorder,
            clock=clock,
        )
        payload = ChartPayload(
            plan=request.plan,
            table_id=request.table_id,
        )
        outcome = agents.chart.run(context=context, payload=payload)
        trace = trace_recorder.build_trace(
            task_id=request.task_id,
            dataset_id=request.dataset_id,
            spans=[outcome.trace_span],
        )
        trace_store.save(trace=trace)
        response = ChartRecommendResponse(
            chart_spec=outcome.output,
            trace=trace,
        )
    except HTTPException as error:
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error.detail),
            status_code=error.status_code,
        )
        raise
    except Exception as error:  # noqa: BLE001 - 记录并抛出未知异常
        LOGGER.exception("图表推荐失败", extra={"endpoint": endpoint})
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        raise
    _record_response(api_recorder=api_recorder, endpoint=endpoint, payload=response)
    return response
@router.post("/api/natural/edit", response_model=NaturalEditResponse)
def natural_edit(
    request: NaturalEditRequest,
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> NaturalEditResponse:
    """基于自然语言指令生成编码补丁占位实现。"""

    endpoint = "api_natural_edit"
    _record_request(api_recorder=api_recorder, endpoint=endpoint, payload=request)
    try:
        patch = EncodingPatch(
            target_chart_id=request.chart_spec.chart_id,
            ops=[
                EncodingPatchOp(
                    op_type="add",
                    path=["parameters", "natural_edit_notes"],
                    value={
                        "command": request.nl_command,
                        "applied_at": "auto",
                    },
                ),
            ],
            rationale="记录自然语言编辑指令，后续由前端解释执行。",
        )
        response = NaturalEditResponse(encoding_patch=patch)
    except Exception as error:  # noqa: BLE001 - 记录并抛出未知异常
        LOGGER.exception("自然语言编辑生成补丁失败", extra={"endpoint": endpoint})
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        raise
    _record_response(api_recorder=api_recorder, endpoint=endpoint, payload=response)
    return response


@router.get("/api/schema/export", response_model=SchemaExportResponse)
def export_contract_schemas(
    api_recorder: ApiRecorder = Depends(get_api_recorder),
) -> SchemaExportResponse:
    """导出核心契约的 JSONSchema，并落盘保存。"""

    endpoint = "api_schema_export"
    _record_request(api_recorder=api_recorder, endpoint=endpoint, payload={})
    try:
        schema_dir = Path("var/schemas")
        schema_dir.mkdir(parents=True, exist_ok=True)
        files: List[str] = []
        schemas: dict[str, object] = {}
        for schema_name, model in SCHEMA_EXPORT_MODELS.items():
            schema_payload = model.model_json_schema()
            target = schema_dir / f"{schema_name}.json"
            target.write_text(json.dumps(schema_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            files.append(str(target))
            schemas[schema_name] = schema_payload
        response = SchemaExportResponse(files=files, schemas=schemas)
    except Exception as error:  # noqa: BLE001 - 统一兜底记录
        LOGGER.exception("Schema 导出失败", extra={"endpoint": endpoint})
        _record_error(
            api_recorder=api_recorder,
            endpoint=endpoint,
            error_type=error.__class__.__name__,
            error_message=str(error),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        raise
    _record_response(api_recorder=api_recorder, endpoint=endpoint, payload=response)
    return response
