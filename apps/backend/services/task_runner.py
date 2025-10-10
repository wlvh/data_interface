"""任务编排与 SSE 推送管理。"""

from __future__ import annotations

import asyncio
import uuid
from typing import Dict, List, Optional

from apps.backend.agents import AgentContext
from apps.backend.agents.base import AgentOutcome
from apps.backend.compat import model_dump
from apps.backend.infra.clock import UtcClock
from apps.backend.services.pipeline import (
    PipelineAgents,
    PipelineConfig,
    PipelineOutcome,
    execute_pipeline,
)
from apps.backend.infra.tracing import TraceRecorder
from apps.backend.stores import DatasetStore, TraceStore


def _generate_task_id() -> str:
    return f"task_{uuid.uuid4()}"


class TaskRunner:
    """负责异步执行多 Agent 流程并向订阅者推送 SSE 事件。"""

    def __init__(
        self,
        *,
        dataset_store: DatasetStore,
        trace_store: TraceStore,
        clock: UtcClock,
        agents: PipelineAgents,
    ) -> None:
        self._dataset_store = dataset_store
        self._trace_store = trace_store
        self._clock = clock
        self._agents = agents
        self._history: Dict[str, List[dict]] = {}
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._status: Dict[str, str] = {}
        self._results: Dict[str, PipelineOutcome] = {}

    async def submit_task(self, config: PipelineConfig) -> str:
        """提交任务并立即返回 task_id。"""

        loop = asyncio.get_running_loop()
        task_id = config.task_id or _generate_task_id()
        if task_id in self._history:
            raise ValueError(f"task_id={task_id} 已存在。")
        runtime_config = PipelineConfig(
            task_id=task_id,
            dataset_id=config.dataset_id,
            dataset_name=config.dataset_name,
            dataset_version=config.dataset_version,
            dataset_path=config.dataset_path,
            sample_limit=config.sample_limit,
            user_goal=config.user_goal,
        )
        trace_recorder = TraceRecorder(clock=self._clock)
        self._history[task_id] = []
        self._subscribers[task_id] = []
        self._status[task_id] = "running"
        start_event = {
            "type": "started",
            "task_id": task_id,
            "timestamp": self._clock.now().isoformat(),
        }

        def progress_callback(node_name: str, outcome: AgentOutcome) -> None:
            event = {
                "type": "node_completed",
                "task_id": task_id,
                "node": node_name,
                "span": model_dump(outcome.trace_span),
            }
            loop.call_soon_threadsafe(self._broadcast_event, task_id, event)

        async def runner() -> None:
            context = AgentContext(
                task_id=task_id,
                dataset_id=runtime_config.dataset_id,
                trace_recorder=trace_recorder,
                clock=self._clock,
            )
            try:
                outcome = await asyncio.to_thread(
                    lambda: execute_pipeline(
                        config=runtime_config,
                        context=context,
                        trace_recorder=trace_recorder,
                        agents=self._agents,
                        progress_callback=progress_callback,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(self._handle_failure, task_id, exc)
                return
            loop.call_soon_threadsafe(self._handle_completion, task_id, outcome)

        loop.create_task(runner())
        self._broadcast_event(task_id, start_event)
        return task_id

    async def subscribe(self, task_id: str) -> asyncio.Queue:
        """返回绑定指定 task 的事件队列。"""

        if task_id not in self._history:
            raise KeyError(f"task_id={task_id} 不存在。")
        queue: asyncio.Queue = asyncio.Queue()
        for event in self._history[task_id]:
            await queue.put(event)
        status = self._status.get(task_id)
        if status in {"completed", "failed"}:
            await queue.put(None)
        else:
            self._subscribers[task_id].append(queue)
        return queue

    def _broadcast_event(self, task_id: str, event: dict, finished: bool = False) -> None:
        if task_id not in self._history:
            return
        self._history[task_id].append(event)
        for queue in self._subscribers.get(task_id, []):
            queue.put_nowait(event)
        if finished:
            for queue in self._subscribers.get(task_id, []):
                queue.put_nowait(None)
            self._subscribers[task_id] = []

    def _handle_completion(self, task_id: str, outcome: PipelineOutcome) -> None:
        self._results[task_id] = outcome
        self._status[task_id] = "completed"
        self._dataset_store.save(dataset_id=outcome.profile.dataset_id, profile=outcome.profile)
        self._trace_store.save(trace=outcome.trace)
        event = {
            "type": "completed",
            "task_id": task_id,
            "plan_id": str(outcome.plan.plan_id),
            "chart_id": outcome.chart.chart_id,
            "row_count": outcome.table.row_count,
        }
        self._broadcast_event(task_id, event, finished=True)

    def _handle_failure(self, task_id: str, error: Exception) -> None:
        self._status[task_id] = "failed"
        event = {
            "type": "failed",
            "task_id": task_id,
            "error_type": error.__class__.__name__,
            "error_message": str(error),
        }
        self._broadcast_event(task_id, event, finished=True)

    def latest_result(self, task_id: str) -> Optional[PipelineOutcome]:
        return self._results.get(task_id)
