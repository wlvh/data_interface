"""数据契约模型包。

该模块提供后端在与前端、代理以及外部任务交互时所需的通用数据契约。
所有模型都应当与对应的 JSONSchema 文件保持镜像关系，保证结构化 I/O
能够被序列化、落盘并复现。
"""

from apps.backend.contracts.chart_template import ChartEncoding, ChartTemplate
from apps.backend.contracts.dataset_profile import DatasetProfile, DatasetSummary
from apps.backend.contracts.fields import FieldSchema, FieldStatistics, ValueRange
from apps.backend.contracts.chart_spec import ChartSpec
from apps.backend.contracts.transform import OutputTable, TransformLog
from apps.backend.contracts.explanation import ExplanationArtifact
from apps.backend.contracts.plan import (
    ChartCandidate,
    ChartChannelMapping,
    ExplanationOutline,
    FieldRecommendation,
    Plan,
    TransformDraft,
)
from apps.backend.contracts.trace import (
    SpanMetrics,
    SpanSLO,
    TraceRecord,
    TraceSpan,
)

__all__ = [
    "ChartEncoding",
    "ChartTemplate",
    "DatasetProfile",
    "DatasetSummary",
    "FieldSchema",
    "FieldStatistics",
    "ValueRange",
    "ChartSpec",
    "FieldRecommendation",
    "ChartChannelMapping",
    "ChartCandidate",
    "TransformDraft",
    "OutputTable",
    "TransformLog",
    "ExplanationOutline",
    "ExplanationArtifact",
    "Plan",
    "SpanSLO",
    "SpanMetrics",
    "TraceSpan",
    "TraceRecord",
]
