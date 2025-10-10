"""会话打包服务，将任务结果整理为 SessionBundle。"""

from __future__ import annotations

from typing import List, Optional, Sequence, Set, Tuple
from uuid import uuid4

from apps.backend.contracts.chart_spec import ChartSpec
from apps.backend.contracts.dataset_profile import DatasetProfile
from apps.backend.contracts.plan import Plan
from apps.backend.contracts.recommendation import RecommendationList
from apps.backend.contracts.session_bundle import SessionBundle
from apps.backend.contracts.transform import OutputTable, PreparedTable, TableColumn, TableSample
from apps.backend.services.task_runner import TaskRunner
from apps.backend.stores import DatasetStore, TraceStore


def _collect_used_fields(*, plan: Plan, chart_specs: Sequence[ChartSpec]) -> Set[str]:
    """汇总计划与图表使用到的字段集合。"""

    fields: Set[str] = set()
    for item in plan.field_plan:
        fields.add(item.field_name)
    for chart in chart_specs:
        for mapping in chart.encoding:
            fields.add(mapping.field_name)
    return fields


def _mask_value(column: TableColumn, value: str) -> str:
    """对标识类列进行脱敏处理。"""

    if column.semantic_role == "identifier":
        return "[MASKED]"
    return value


def _sanitize_prepared_table(
    *,
    table: PreparedTable,
    used_fields: Set[str],
) -> Tuple[PreparedTable, Optional[str], bool]:
    """过滤 PreparedTable，仅保留被引用的列。"""

    filtered_columns = [column for column in table.schema if column.column_name in used_fields]
    if not filtered_columns:
        note = "未找到引用字段，PreparedTable 保持原样导出。"
        return table, note, True
    sanitized_rows: List[dict] = []
    for row in table.sample.rows:
        sanitized_row: dict = {}
        for column in filtered_columns:
            raw_value = row[column.column_name]
            sanitized_row[column.column_name] = _mask_value(column=column, value=raw_value)
        sanitized_rows.append(sanitized_row)
    sanitized_table = PreparedTable(
        prepared_table_id=table.prepared_table_id,
        source_id=table.source_id,
        transform_id=table.transform_id,
        schema=filtered_columns,
        sample=TableSample(rows=sanitized_rows),
        stats=table.stats,
        limits=table.limits,
    )
    return sanitized_table, None, False


def _sanitize_output_table(
    *,
    table: OutputTable,
    used_fields: Set[str],
) -> Tuple[OutputTable, Optional[str], bool]:
    """过滤 OutputTable 预览，移除未引用列。"""

    filtered_columns = [column for column in table.schema if column.column_name in used_fields]
    if not filtered_columns:
        note = "未找到引用字段，OutputTable 保持原样导出。"
        return table, note, True
    sanitized_rows: List[dict] = []
    for row in table.preview.rows:
        sanitized_row: dict = {}
        for column in filtered_columns:
            raw_value = row[column.column_name]
            sanitized_row[column.column_name] = _mask_value(column=column, value=raw_value)
        sanitized_rows.append(sanitized_row)
    sanitized_table = OutputTable(
        output_table_id=table.output_table_id,
        prepared_table_id=table.prepared_table_id,
        schema=filtered_columns,
        preview=TableSample(rows=sanitized_rows),
        metrics=table.metrics,
        logs=table.logs,
        generated_at=table.generated_at,
    )
    return sanitized_table, None, False


def _build_chart_list(*, primary: ChartSpec, recommendations: RecommendationList) -> List[ChartSpec]:
    """组合首图与候选图表，去重后返回列表。"""

    charts: List[ChartSpec] = [primary]
    primary_id = primary.chart_id
    for candidate in recommendations.recommendations:
        if candidate.chart_spec.chart_id == primary_id:
            continue
        charts.append(candidate.chart_spec)
    return charts


def _build_data_fingerprints(*, profile: DatasetProfile) -> List[dict]:
    """生成数据指纹集合，便于回放校验。"""

    fingerprint = {
        "dataset_id": profile.dataset_id,
        "dataset_version": profile.dataset_version,
        "hash_digest": profile.hash_digest,
    }
    return [fingerprint]


def build_session_bundle(
    *,
    task_id: str,
    task_runner: TaskRunner,
    trace_store: TraceStore,
    dataset_store: DatasetStore,
    clock,
) -> SessionBundle:
    """将指定任务导出为 SessionBundle。"""

    outcome = task_runner.latest_result(task_id=task_id)
    if outcome is None:
        message = f"task_id={task_id} 缺少可导出的结果。"
        raise ValueError(message)
    trace = trace_store.require(task_id=task_id)
    try:
        profile = dataset_store.require(dataset_id=outcome.profile.dataset_id)
    except KeyError:
        profile = outcome.profile
    recommendations = outcome.recommendations
    chart_specs = _build_chart_list(primary=outcome.chart, recommendations=recommendations)
    used_fields = _collect_used_fields(plan=outcome.plan, chart_specs=chart_specs)
    sanitized_prepared, prepared_note, prepared_degraded = _sanitize_prepared_table(
        table=outcome.prepared_table,
        used_fields=used_fields,
    )
    sanitized_output, output_note, output_degraded = _sanitize_output_table(
        table=outcome.output_table,
        used_fields=used_fields,
    )
    notes: List[str] = []
    degraded = False
    if prepared_note is not None:
        notes.append(prepared_note)
        degraded = degraded or prepared_degraded
    if output_note is not None:
        notes.append(output_note)
        degraded = degraded or output_degraded
    data_fingerprints = _build_data_fingerprints(profile=profile)
    bundle = SessionBundle(
        bundle_id=f"bundle_{uuid4()}",
        task_id=task_id,
        mode="read_only" if degraded else "full",
        generated_at=clock.now(),
        dataset_profile=profile,
        plan=outcome.plan,
        prepared_table=sanitized_prepared,
        output_table=sanitized_output,
        chart_specs=chart_specs,
        encoding_patches=[outcome.encoding_patch],
        recommendations=recommendations,
        trace=trace,
        notes=notes,
        data_fingerprints=data_fingerprints,
    )
    return bundle
