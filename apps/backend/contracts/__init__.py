"""数据契约模型包。

该模块提供后端在与前端、代理以及外部任务交互时所需的通用数据契约。
所有模型都应当与对应的 JSONSchema 文件保持镜像关系，保证结构化 I/O
能够被序列化、落盘并复现。
"""

from apps.backend.contracts.chart_spec import (
    ChartA11y,
    ChartAxis,
    ChartLayout,
    ChartLegend,
    ChartScale,
    ChartSpec,
)
from apps.backend.contracts.chart_template import ChartEncoding, ChartTemplate
from apps.backend.contracts.dataset_profile import DatasetProfile, DatasetSampling, DatasetSummary
from apps.backend.contracts.encoding_patch import EncodingPatch, EncodingPatchOp, EncodingPatchProposal
from apps.backend.contracts.explanation import ExplanationArtifact
from apps.backend.contracts.fields import FieldSchema, FieldStatistics, TemporalGranularity, ValueRange
from apps.backend.contracts.plan import (
    ChartChannelMapping,
    ChartPlanItem,
    ExplainOutline,
    FieldPlanItem,
    Plan,
    PlanAssumption,
    TransformDraft,
)
from apps.backend.contracts.task_event import TaskEvent
from apps.backend.contracts.trace import SpanEvent, SpanMetrics, SpanSLO, TraceRecord, TraceSpan
from apps.backend.contracts.transform import (
    OutputMetrics,
    OutputTable,
    PreparedTable,
    PreparedTableLimits,
    PreparedTableStats,
    TableColumn,
    TableSample,
    TransformLog,
)
from apps.backend.contracts.recommendation import ChartRecommendationCandidate, RecommendationList
from apps.backend.contracts.session_bundle import SessionBundle

__all__ = [
    "ChartEncoding",
    "ChartTemplate",
    "ChartSpec",
    "ChartScale",
    "ChartLegend",
    "ChartAxis",
    "ChartLayout",
    "ChartA11y",
    "DatasetSampling",
    "DatasetSummary",
    "DatasetProfile",
    "EncodingPatch",
    "EncodingPatchOp",
    "EncodingPatchProposal",
    "ExplanationArtifact",
    "FieldSchema",
    "FieldStatistics",
    "TemporalGranularity",
    "ValueRange",
    "PlanAssumption",
    "FieldPlanItem",
    "ChartChannelMapping",
    "ChartPlanItem",
    "TransformDraft",
    "ExplainOutline",
    "PreparedTable",
    "PreparedTableStats",
    "PreparedTableLimits",
    "TableColumn",
    "TableSample",
    "OutputMetrics",
    "OutputTable",
    "TransformLog",
    "Plan",
    "RecommendationList",
    "ChartRecommendationCandidate",
    "SessionBundle",
    "SpanSLO",
    "SpanEvent",
    "SpanMetrics",
    "TraceSpan",
    "TraceRecord",
    "TaskEvent",
]
