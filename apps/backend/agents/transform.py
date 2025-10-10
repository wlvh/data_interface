"""数据变换执行 Agent。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from apps.backend.agents.base import Agent, AgentContext, AgentOutcome
from apps.backend.contracts.dataset_profile import DatasetProfile
from apps.backend.contracts.plan import Plan, TransformDraft
from apps.backend.contracts.transform import OutputTable, TransformLog
from apps.backend.contracts.trace import SpanSLO

LOGGER = logging.getLogger(__name__)

_PD_MODULE: Optional[Any] = None


def _get_pandas() -> Any:
    """延迟加载 pandas，避免在不支持环境中提前导入。"""

    global _PD_MODULE
    if _PD_MODULE is None:
        import pandas as pd  # noqa: WPS433 - 延迟导入

        _PD_MODULE = pd
    return _PD_MODULE


@dataclass(frozen=True)
class TransformPayload:
    """变换执行所需输入。"""

    dataset_profile: DatasetProfile
    plan: Plan
    dataset_path: Path
    sample_limit: int


def _ensure_transform_function(namespace: dict) -> callable:
    """保证提供的命名空间中存在 transform 函数。"""

    if "transform" not in namespace:
        message = "变换代码必须定义 transform 函数。"
        raise ValueError(message)
    transform = namespace["transform"]
    if not callable(transform):
        message = "transform 必须是可调用对象。"
        raise ValueError(message)
    return transform


class TransformExecutionAgent(Agent):
    """执行计划中的数据变换。"""

    name = "transform_executor"
    slo = SpanSLO(
        max_duration_ms=4000,
        max_retries=0,
        failure_isolation_required=True,
    )

    def run(self, context: AgentContext, payload: TransformPayload) -> AgentOutcome:
        """运行变换并返回 OutputTable。"""

        span_id = context.trace_recorder.start_span(
            node_name="transform",
            agent_name=self.name,
            slo=self.slo,
            parent_span_id=None,
            model_name=None,
            prompt_version=None,
        )
        transform_draft = payload.plan.transform_drafts[0]
        if transform_draft.language != "python":
            message = f"暂不支持语言 {transform_draft.language}"
            raise ValueError(message)
        pd = _get_pandas()
        dataframe = pd.read_csv(payload.dataset_path)
        namespace: dict = {}
        logs: List[TransformLog] = []
        try:
            exec(transform_draft.code, {"pd": pd}, namespace)  # noqa: S102 - 受控代码来源
            transform_fn = _ensure_transform_function(namespace=namespace)
            result_df = transform_fn(df=dataframe)
        except Exception as error:  # noqa: BLE001 - 需要捕获以记录日志
            log_entry = TransformLog(
                level="error",
                message=str(error),
                timestamp=context.clock.now(),
            )
            logs.append(log_entry)
            context.trace_recorder.finish_span(
                span_id=span_id,
                status="failed",
                failure_category=error.__class__.__name__,
                failure_isolation_ratio=0.0,
            )
            raise
        if not isinstance(result_df, pd.DataFrame):
            message = "transform 函数必须返回 pandas.DataFrame。"
            raise ValueError(message)
        sample_rows = []
        for _, row in result_df.head(payload.sample_limit).iterrows():
            sample_rows.append({column: str(row[column]) for column in result_df.columns})
        output_table = OutputTable(
            table_id="derived_main",
            source_plan_id=str(payload.plan.plan_id),
            row_count=int(result_df.shape[0]),
            columns=list(result_df.columns),
            sample_rows=sample_rows,
            generated_at=context.clock.now(),
            logs=logs,
        )
        trace_span = context.trace_recorder.finish_span(
            span_id=span_id,
            status="success",
            failure_category=None,
            failure_isolation_ratio=1.0,
        )
        LOGGER.info(
            "数据变换完成",
            extra={
                "task_id": context.task_id,
                "dataset_id": context.dataset_id,
                "rows": output_table.row_count,
            },
        )
        return AgentOutcome(
            output=output_table,
            span_id=span_id,
            trace_span=trace_span,
        )
