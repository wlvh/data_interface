"""多 Agent 流程与任务管理测试（使用真实 pandas 环境）。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Tuple

import pytest
from fastapi.testclient import TestClient

from apps.backend.api.app import create_app
from apps.backend.api.dependencies import (
    get_task_runner,
    get_trace_store,
    get_dataset_store,
    get_clock,
    get_natural_edit_agent,
    get_api_recorder,
)
from apps.backend.agents import (
    AgentContext,
    DatasetScannerAgent,
    ExplanationAgent,
    PlanRefinementAgent,
    TransformArtifacts,
    TransformExecutionAgent,
    ChartRecommendationAgent,
    NaturalEditAgent,
)
from apps.backend.compat import model_dump
from apps.backend.infra.clock import UtcClock
from apps.backend.infra.persistence import ApiRecorder
from apps.backend.infra.tracing import TraceRecorder
from apps.backend.services.pipeline import PipelineAgents, PipelineConfig, execute_pipeline
from apps.backend.services.task_runner import TaskRunner
from apps.backend.stores import DatasetStore, TraceStore


def _create_sample_dataset(path: Path) -> None:
    """写入用于测试的简单 CSV 数据。"""

    payload = (
        "store,sales,date\n"
        "A,10,2024-01-01\n"
        "B,25,2024-01-02\n"
        "A,15,2024-01-03\n"
    )
    path.write_text(payload, encoding="utf-8")


def _build_agents() -> PipelineAgents:
    """构造流程所需的 Agent 集合。"""

    return PipelineAgents(
        scanner=DatasetScannerAgent(),
        planner=PlanRefinementAgent(),
        transformer=TransformExecutionAgent(),
        chart=ChartRecommendationAgent(),
        explainer=ExplanationAgent(),
    )


async def _run_task_and_wait(runner: TaskRunner, config: PipelineConfig) -> Tuple[str, List[dict]]:
    """提交任务并消费完所有事件，返回 task_id 与事件记录。"""

    events: List[dict] = []
    task_id = await runner.submit_task(config=config)
    queue = await runner.subscribe(task_id=task_id)
    while True:
        item = await queue.get()
        if item is None:
            break
        events.append(model_dump(item))
    return task_id, events


def test_execute_pipeline_returns_outcome(tmp_path: Path) -> None:
    """执行完整流程应返回图表、编码补丁与回放友好的表结构。"""

    dataset_path = tmp_path / "sample.csv"
    _create_sample_dataset(path=dataset_path)
    agents = _build_agents()
    clock = UtcClock()
    trace_recorder = TraceRecorder(clock=clock)
    config = PipelineConfig(
        task_id="task_pipeline",
        dataset_id="dataset_pipeline",
        dataset_name="Pipeline Dataset",
        dataset_version="v1",
        dataset_path=dataset_path,
        sample_limit=3,
        user_goal="分析销售趋势",
    )
    context = AgentContext(
        task_id=config.task_id,
        dataset_id=config.dataset_id,
        trace_recorder=trace_recorder,
        clock=clock,
    )
    outcome = execute_pipeline(
        config=config,
        context=context,
        trace_recorder=trace_recorder,
        agents=agents,
    )
    assert outcome.plan.dataset_id == config.dataset_id
    assert isinstance(outcome.prepared_table.schema, list)
    assert outcome.output_table.metrics.rows_out >= 1
    assert outcome.chart.data_source == outcome.output_table.output_table_id
    assert outcome.encoding_patch.target_chart_id == outcome.chart.chart_id
    assert outcome.recommendations.recommendations
    assert outcome.trace.task_id == config.task_id


def test_task_runner_streams_events(tmp_path: Path) -> None:
    """TaskRunner 应推送开始、节点完成与结束事件，并生成行数统计。"""

    async def _run() -> None:
        dataset_path = tmp_path / "runner.csv"
        trace_dir = tmp_path / "traces"
        _create_sample_dataset(path=dataset_path)
        agents = _build_agents()
        clock = UtcClock()
        dataset_store = DatasetStore()
        trace_store = TraceStore(base_path=trace_dir)
        api_recorder = ApiRecorder(base_path=tmp_path / "api_logs_runner")
        runner = TaskRunner(
            dataset_store=dataset_store,
            trace_store=trace_store,
            clock=clock,
            agents=agents,
            api_recorder=api_recorder,
        )
        config = PipelineConfig(
            task_id="task_runner",
            dataset_id="dataset_runner",
            dataset_name="Runner Dataset",
            dataset_version="v1",
            dataset_path=dataset_path,
            sample_limit=3,
            user_goal="查看门店销售对比",
        )
        task_id, events = await _run_task_and_wait(runner=runner, config=config)
        event_types = [event["type"] for event in events]
        assert "started" in event_types
        assert "node_completed" in event_types
        assert event_types[-1] == "completed"
        completed_event = next(item for item in events if item["type"] == "completed")
        assert completed_event["payload"]["rows_out"] >= 1
        trace = trace_store.require(task_id=task_id)
        assert trace.task_id == task_id
        profile = dataset_store.require(dataset_id=config.dataset_id)
        assert profile.dataset_id == config.dataset_id
        snapshot = runner.get_snapshot(task_id=task_id)
        assert snapshot.outcome is not None
        assert snapshot.outcome.recommendations.recommendations

    asyncio.run(_run())


def test_task_result_endpoint_returns_snapshot(tmp_path: Path) -> None:
    """异步任务完成后，API 应返回包含编码补丁的结果快照。"""

    async def _run() -> None:
        dataset_path = tmp_path / "runner_api.csv"
        trace_dir = tmp_path / "traces_api"
        _create_sample_dataset(path=dataset_path)
        agents = _build_agents()
        clock = UtcClock()
        dataset_store = DatasetStore()
        trace_store = TraceStore(base_path=trace_dir)
        api_recorder = ApiRecorder(base_path=tmp_path / "api_logs_runner_api")
        runner = TaskRunner(
            dataset_store=dataset_store,
            trace_store=trace_store,
            clock=clock,
            agents=agents,
            api_recorder=api_recorder,
        )
        config = PipelineConfig(
            task_id="task_api",
            dataset_id="dataset_api",
            dataset_name="API Dataset",
            dataset_version="v1",
            dataset_path=dataset_path,
            sample_limit=3,
            user_goal="分析 API 返回值",
        )
        task_id, _ = await _run_task_and_wait(runner=runner, config=config)
        snapshot = runner.get_snapshot(task_id=task_id)
        assert snapshot.status == "completed"
        assert snapshot.outcome is not None
        assert snapshot.outcome.output_table.metrics.rows_out >= 1
        app = create_app()
        app.dependency_overrides[get_task_runner] = lambda: runner
        app.dependency_overrides[get_trace_store] = lambda: trace_store
        app.dependency_overrides[get_dataset_store] = lambda: dataset_store
        app.dependency_overrides[get_clock] = lambda: clock
        natural_agent = NaturalEditAgent()
        app.dependency_overrides[get_natural_edit_agent] = lambda: natural_agent
        app.dependency_overrides[get_api_recorder] = lambda: api_recorder
        client = TestClient(app)
        response = client.get(f"/api/task/{task_id}/result")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "completed"
        assert payload["result"]["plan"]["dataset_id"] == config.dataset_id
        assert payload["result"]["output_table"]["metrics"]["rows_out"] >= 1
        assert payload["result"]["encoding_patch"]["target_chart_id"] == payload["result"]["chart"]["chart_id"]
        assert payload["result"]["recommendations"]["recommendations"]
        first_candidate = payload["result"]["recommendations"]["recommendations"][0]
        assert first_candidate["chart_spec"]["data_source"] == payload["result"]["output_table"]["output_table_id"]
        assert payload["result"]["trace"]["task_id"] == task_id
        natural_payload = {
            "task_id": task_id,
            "dataset_id": config.dataset_id,
            "chart_spec": payload["result"]["chart"],
            "nl_command": "交换 x 和 y 轴",
        }
        natural_response = client.post("/api/natural/edit", json=natural_payload)
        assert natural_response.status_code == 200
        natural_json = natural_response.json()
        assert natural_json["proposals"]
        assert natural_json["trace"]["task_id"] == task_id
        session_response = client.get(f"/api/session/{task_id}/bundle")
        assert session_response.status_code == 200
        bundle_payload = session_response.json()["bundle"]
        assert bundle_payload["task_id"] == task_id
        assert bundle_payload["chart_specs"]
        assert bundle_payload["prepared_table"]
        app.dependency_overrides.clear()

    asyncio.run(_run())
