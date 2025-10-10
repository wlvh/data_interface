"""后端 API 请求与响应模型。"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from apps.backend.compat import BaseModel, ConfigDict, Field, model_validator

from apps.backend.contracts.chart_spec import ChartSpec
from apps.backend.contracts.dataset_profile import DatasetProfile, DatasetSummary
from apps.backend.contracts.encoding_patch import EncodingPatch
from apps.backend.contracts.explanation import ExplanationArtifact
from apps.backend.contracts.plan import Plan
from apps.backend.contracts.transform import OutputTable, PreparedTable
from apps.backend.contracts.trace import TraceRecord


class ApiModel(BaseModel):
    """统一约束的 API 模型基类，强制禁止额外字段。"""

    model_config = ConfigDict(extra="forbid")


class ScanRequest(ApiModel):
    """触发数据扫描的请求模型。"""

    task_id: str = Field(description="任务标识。", min_length=1)
    dataset_id: str = Field(description="数据集标识。", min_length=1)
    dataset_name: str = Field(description="数据集名称。", min_length=1)
    dataset_version: str = Field(description="数据集版本号。", min_length=1)
    dataset_path: str = Field(description="本地数据源路径。", min_length=1)
    sample_limit: int = Field(
        default=5,
        description="示例采样数量。",
        ge=1,
        le=20,
    )


class ScanResponse(ApiModel):
    """数据扫描响应。"""

    profile: DatasetProfile = Field(description="生成的数据集画像。")
    trace: TraceRecord = Field(description="对应的 Trace 记录。")


class PlanRequest(ApiModel):
    """计划细化请求模型。"""

    task_id: str = Field(description="任务标识。", min_length=1)
    dataset_id: str = Field(description="数据集标识。", min_length=1)
    dataset_name: str = Field(description="数据集名称。", min_length=1)
    dataset_version: str = Field(description="数据集版本。", min_length=1)
    dataset_path: str = Field(description="数据源路径。", min_length=1)
    user_goal: str = Field(description="用户模糊目标描述。", min_length=1)
    sample_limit: int = Field(
        default=5,
        description="示例采样数量。",
        ge=1,
        le=20,
    )


class PlanResponse(ApiModel):
    """计划细化响应模型。"""

    profile: DatasetProfile = Field(description="最新的数据集画像。")
    plan: Plan = Field(description="结构化计划。")
    prepared_table: PreparedTable = Field(description="变换前的准备表描述。")
    output_table: OutputTable = Field(description="主要输出表快照。")
    chart: ChartSpec = Field(description="推荐图表规范。")
    encoding_patch: EncodingPatch = Field(description="图表编码的增量补丁。")
    explanation: ExplanationArtifact = Field(description="解释 Agent 输出。")
    trace: TraceRecord = Field(description="Trace 记录。")


class TraceReplayRequest(ApiModel):
    """Trace 回放请求。"""

    task_id: str = Field(description="需要回放的任务 ID。", min_length=1)
    mode: Literal["return", "rebuild"] = Field(
        default="return",
        description="回放模式，return 表示直接返回历史 Trace，rebuild 表示基于落盘重建。",
    )


class TraceReplayResponse(ApiModel):
    """Trace 回放响应。"""

    trace: TraceRecord = Field(description="回放的 Trace 记录。")


class TaskSubmitRequest(ApiModel):
    """任务提交请求。"""

    dataset_id: str = Field(description="数据集标识。", min_length=1)
    dataset_name: str = Field(description="数据集名称。", min_length=1)
    dataset_version: str = Field(description="数据集版本。", min_length=1)
    dataset_path: str = Field(description="数据源路径。", min_length=1)
    user_goal: str = Field(description="用户模糊目标描述。", min_length=1)
    sample_limit: int = Field(
        default=5,
        description="示例采样数量。",
        ge=1,
        le=20,
    )
    task_id: Optional[str] = Field(
        default=None,
        description="可选的自定义任务 ID，缺省时自动生成。",
    )


class TaskSubmitResponse(ApiModel):
    """任务提交响应。"""

    task_id: str = Field(description="创建的任务 ID。", min_length=1)


class TaskFailurePayload(ApiModel):
    """任务失败结构化信息。"""

    error_type: str = Field(description="异常类型。", min_length=1)
    error_message: str = Field(description="异常消息。", min_length=1)


class TaskResultPayload(ApiModel):
    """任务成功结果载荷。"""

    profile: DatasetProfile = Field(description="任务结束时的画像。")
    plan: Plan = Field(description="最终计划。")
    prepared_table: PreparedTable = Field(description="变换输入快照。")
    output_table: OutputTable = Field(description="变换产出的数据表。")
    chart: ChartSpec = Field(description="推荐图表规范。")
    encoding_patch: EncodingPatch = Field(description="图表编码补丁。")
    explanation: ExplanationArtifact = Field(description="解释 Agent 输出。")
    trace: TraceRecord = Field(description="完整的 Trace 记录。")


class TaskResultResponse(ApiModel):
    """任务状态查询响应。"""

    task_id: str = Field(description="任务标识。", min_length=1)
    status: Literal["running", "completed", "failed"] = Field(description="当前任务执行状态。")
    result: Optional[TaskResultPayload] = Field(
        default=None,
        description="任务完成后的结构化结果，仅在 status=completed 时存在。",
    )
    failure: Optional[TaskFailurePayload] = Field(
        default=None,
        description="任务失败信息，仅在 status=failed 时存在。",
    )


class TransformExecuteRequest(ApiModel):
    """触发数据变换执行的请求。"""

    task_id: str = Field(description="任务标识。", min_length=1)
    dataset_id: str = Field(description="数据集标识。", min_length=1)
    dataset_name: str = Field(description="数据集名称。", min_length=1)
    dataset_version: str = Field(description="数据集版本号。", min_length=1)
    dataset_path: str = Field(description="数据集文件路径。", min_length=1)
    sample_limit: int = Field(
        default=5,
        description="示例采样数量上限。",
        ge=1,
        le=100,
    )
    plan: Plan = Field(description="包含变换草案的计划。")


class TransformExecuteResponse(ApiModel):
    """数据变换执行响应。"""

    prepared_table: PreparedTable = Field(description="准备阶段的表结构与样本。")
    output_table: OutputTable = Field(description="变换后的输出表快照。")
    trace: TraceRecord = Field(description="本次执行的 Trace 记录。")


class TransformAggregateRequest(ApiModel):
    """请求预聚合或分箱的输入模型。"""

    task_id: str = Field(description="任务标识。", min_length=1)
    dataset_id: str = Field(description="数据集标识。", min_length=1)
    dataset_name: str = Field(description="数据集名称。", min_length=1)
    dataset_version: str = Field(description="数据集版本号。", min_length=1)
    dataset_path: str = Field(description="数据集文件路径。", min_length=1)
    sample_limit: int = Field(
        default=5,
        description="示例采样数量上限。",
        ge=1,
        le=100,
    )
    plan: Optional[Plan] = Field(
        default=None,
        description="可选的计划，用于约束字段规划。",
    )
    dataset_summary: Optional[DatasetSummary] = Field(
        default=None,
        description="可选的画像，缺失时自动扫描。",
    )

    @model_validator(mode="after")
    def ensure_context(self) -> "TransformAggregateRequest":
        """确保至少提供计划或摘要以指导预处理。"""

        if self.plan is None and self.dataset_summary is None:
            message = "plan 与 dataset_summary 至少需要提供一个。"
            raise ValueError(message)
        return self


class TransformAggregateResponse(ApiModel):
    """预聚合或分箱响应。"""

    prepared_table: PreparedTable = Field(description="预处理后的表结构与样本。")


class ChartRecommendRequest(ApiModel):
    """图表推荐请求。"""

    task_id: str = Field(description="任务标识。", min_length=1)
    dataset_id: str = Field(description="数据集标识。", min_length=1)
    plan: Plan = Field(description="规划输出，用于决定模板与编码。")
    table_id: str = Field(description="关联的数据表标识。", min_length=1)


class ChartRecommendResponse(ApiModel):
    """图表推荐响应。"""

    chart_spec: ChartSpec = Field(description="推荐的图表规范。")
    trace: TraceRecord = Field(description="推荐过程的 Trace。")


class NaturalEditRequest(ApiModel):
    """自然语言编辑请求。"""

    task_id: str = Field(description="任务标识。", min_length=1)
    chart_spec: ChartSpec = Field(description="待编辑的原始图表。")
    nl_command: str = Field(description="自然语言编辑指令。", min_length=1)


class NaturalEditResponse(ApiModel):
    """自然语言编辑响应。"""

    encoding_patch: EncodingPatch = Field(description="生成的编码补丁。")


class SchemaExportResponse(ApiModel):
    """JSONSchema 批量导出响应。"""

    files: List[str] = Field(description="已落盘的 Schema 文件路径。")
    schemas: Dict[str, object] = Field(description="按 schema_name 索引的 JSONSchema 内容。")
