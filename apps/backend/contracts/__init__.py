"""数据契约模型包。

该模块提供后端在与前端、代理以及外部任务交互时所需的通用数据契约。
所有模型都应当与对应的 JSONSchema 文件保持镜像关系，保证结构化 I/O
能够被序列化、落盘并复现。
"""

from apps.backend.contracts.chart_template import ChartEncoding, ChartTemplate
from apps.backend.contracts.dataset_profile import DatasetProfile, DatasetSummary
from apps.backend.contracts.fields import FieldSchema, FieldStatistics, ValueRange

__all__ = [
    "ChartEncoding",
    "ChartTemplate",
    "DatasetProfile",
    "DatasetSummary",
    "FieldSchema",
    "FieldStatistics",
    "ValueRange",
]

