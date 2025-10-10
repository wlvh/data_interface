"""多 Agent 流程与任务管理测试。"""

from __future__ import annotations

import asyncio
import csv
from types import SimpleNamespace
from pathlib import Path
from typing import Any, Dict, List

import pytest

from apps.backend.agents import (
    AgentContext,
    DatasetScannerAgent,
    ExplanationAgent,
    PlanRefinementAgent,
    TransformExecutionAgent,
    ChartRecommendationAgent,
)
from apps.backend.infra.clock import UtcClock
from apps.backend.infra.tracing import TraceRecorder
from apps.backend.services.pipeline import PipelineAgents, PipelineConfig, execute_pipeline
from apps.backend.services.task_runner import TaskRunner
from apps.backend.stores import DatasetStore, TraceStore


class FakeIsnaResult:
    def __init__(self, values: List[Any]) -> None:
        self._values = values

    def sum(self) -> int:
        return sum(1 for value in self._values if value is None)


class FakeCounts:
    def __init__(self, pairs: List[tuple[Any, float]]) -> None:
        self.index = [item for item, _ in pairs]
        self.values = [value for _, value in pairs]

    def __iter__(self):
        return iter(self.values)


class FakeSeries:
    def __init__(self, values: List[Any]) -> None:
        self._values = values
        self.dtype = self._infer_dtype()

    def _infer_dtype(self) -> str:
        for value in self._values:
            if value is None:
                continue
            if isinstance(value, bool):
                return "boolean"
            if isinstance(value, int):
                return "integer"
            if isinstance(value, float):
                return "number"
            text = str(value)
            if "-" in text and len(text) >= 8:
                return "datetime"
            return "string"
        return "string"

    def isna(self) -> FakeIsnaResult:
        return FakeIsnaResult(self._values)

    def nunique(self, dropna: bool = True) -> int:
        values = [value for value in self._values if value is not None or not dropna]
        return len(set(values))

    def dropna(self) -> "FakeSeries":
        return FakeSeries([value for value in self._values if value is not None])

    def value_counts(self, normalize: bool = False) -> FakeCounts:
        counts: Dict[Any, int] = {}
        for value in self._values:
            if value is None:
                continue
            counts[value] = counts.get(value, 0) + 1
        items = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        if normalize and items:
            total = sum(counts.values())
            normalized = [(label, count / total) for label, count in items]
            return FakeCounts(normalized)
        return FakeCounts(items)

    def head(self, limit: int) -> "FakeSeries":
        return FakeSeries(self._values[:limit])

    def min(self) -> Any:
        values = [value for value in self._values if value is not None]
        return min(values) if values else None

    def max(self) -> Any:
        values = [value for value in self._values if value is not None]
        return max(values) if values else None

    def __iter__(self):
        return iter(self._values)

    @property
    def empty(self) -> bool:
        return len(self._values) == 0


class FakeDataFrame:
    def __init__(self, columns: List[str], rows: List[Dict[str, Any]]) -> None:
        self._columns = columns
        self._rows = rows

    @property
    def shape(self) -> tuple[int, int]:
        return (len(self._rows), len(self._columns))

    @property
    def columns(self) -> List[str]:
        return list(self._columns)

    @property
    def empty(self) -> bool:
        return not self._rows

    def __getitem__(self, column: str) -> FakeSeries:
        return FakeSeries([row.get(column) for row in self._rows])

    def head(self, limit: int) -> "FakeDataFrame":
        return FakeDataFrame(self._columns, self._rows[:limit])

    def iterrows(self):
        for index, row in enumerate(self._rows):
            yield index, row.copy()

    def dropna(self) -> "FakeDataFrame":
        cleaned = [row for row in self._rows if None not in row.values()]
        return FakeDataFrame(self._columns, cleaned)

    def groupby(self, column: str, as_index: bool = False) -> "FakeGroupBy":
        return FakeGroupBy(self._rows, column, as_index)

    def sort_values(self, by: str, ascending: bool = True) -> "FakeDataFrame":
        sorted_rows = sorted(self._rows, key=lambda row: row.get(by), reverse=not ascending)
        return FakeDataFrame(self._columns, sorted_rows)


class FakeGroupBy:
    def __init__(self, rows: List[Dict[str, Any]], key: str, as_index: bool) -> None:
        self._rows = rows
        self._key = key
        self._as_index = as_index

    def __getitem__(self, value_column: str) -> "FakeAggregator":
        return FakeAggregator(self._rows, self._key, value_column, self._as_index)


class FakeAggregator:
    def __init__(self, rows: List[Dict[str, Any]], key: str, value_column: str, as_index: bool) -> None:
        self._rows = rows
        self._key = key
        self._value_column = value_column
        self._as_index = as_index

    def sum(self) -> FakeDataFrame:
        totals: Dict[Any, float] = {}
        for row in self._rows:
            label = row.get(self._key)
            value = row.get(self._value_column)
            if value is None:
                continue
            totals[label] = totals.get(label, 0.0) + float(value)
        aggregated = [
            {self._key: key, self._value_column: totals[key]}
            for key in totals
        ]
        return FakeDataFrame([self._key, self._value_column], aggregated)


class FakePandasModule:
    def __init__(self) -> None:
        self.api = SimpleNamespace(
            types=SimpleNamespace(
                is_integer_dtype=lambda dtype: dtype == "integer",
                is_numeric_dtype=lambda dtype: dtype in {"integer", "number"},
                is_bool_dtype=lambda dtype: dtype == "boolean",
                is_datetime64_any_dtype=lambda dtype: dtype == "datetime",
            ),
        )
        self.DataFrame = FakeDataFrame

    def read_csv(self, path: Path) -> FakeDataFrame:
        with path.open(encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows: List[Dict[str, Any]] = []
            for raw in reader:
                parsed: Dict[str, Any] = {}
                for column, value in raw.items():
                    if value == "":
                        parsed[column] = None
                        continue
                    try:
                        parsed[column] = int(value)
                        continue
                    except ValueError:
                        pass
                    try:
                        parsed[column] = float(value)
                        continue
                    except ValueError:
                        pass
                    parsed[column] = value
                rows.append(parsed)
        return FakeDataFrame(reader.fieldnames or [], rows)


@pytest.fixture(autouse=True)
def patch_pandas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "pandas", FakePandasModule())


def _create_sample_dataset(path: Path) -> None:
    path.write_text(
        "store,sales,date\n"
        "A,10,2024-01-01\n"
        "B,25,2024-01-02\n"
        "A,15,2024-01-03\n",
        encoding="utf-8",
    )


def _build_agents() -> PipelineAgents:
    return PipelineAgents(
        scanner=DatasetScannerAgent(),
        planner=PlanRefinementAgent(),
        transformer=TransformExecutionAgent(),
        chart=ChartRecommendationAgent(),
        explainer=ExplanationAgent(),
    )


def test_execute_pipeline_returns_outcome(tmp_path: Path) -> None:
    """执行完整流程应返回图表、表格与 trace。"""

    dataset_path = tmp_path / "sample.csv"
    _create_sample_dataset(dataset_path)
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
    assert outcome.table.row_count >= 1
    assert outcome.chart.data_source == outcome.table.table_id
    assert outcome.trace.task_id == config.task_id


def test_task_runner_streams_events(tmp_path: Path) -> None:
    """TaskRunner 应推送开始、节点完成与结束事件。"""

    async def _run() -> None:
        dataset_path = tmp_path / "runner.csv"
        trace_dir = tmp_path / "traces"
        _create_sample_dataset(dataset_path)
        agents = _build_agents()
        clock = UtcClock()
        dataset_store = DatasetStore()
        trace_store = TraceStore(base_path=trace_dir)
        runner = TaskRunner(
            dataset_store=dataset_store,
            trace_store=trace_store,
            clock=clock,
            agents=agents,
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
        task_id = await runner.submit_task(config=config)
        queue = await runner.subscribe(task_id=task_id)
        events = []
        while True:
            item = await queue.get()
            if item is None:
                break
            events.append(item)
        event_types = [event["type"] for event in events]
        assert "started" in event_types
        assert "node_completed" in event_types
        assert event_types[-1] == "completed"
        trace = trace_store.require(task_id=task_id)
        assert trace.task_id == task_id
        profile = dataset_store.require(dataset_id=config.dataset_id)
        assert profile.dataset_id == config.dataset_id

    asyncio.run(_run())
