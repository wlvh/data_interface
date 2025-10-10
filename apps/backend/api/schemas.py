"""后端 API 请求与响应模型。"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from apps.backend.contracts.chart_spec import ChartSpec
from apps.backend.contracts.dataset_profile import DatasetProfile
from apps.backend.contracts.encoding_patch import EncodingPatch
from apps.backend.contracts.explanation import ExplanationArtifact
from apps.backend.contracts.plan import Plan
from apps.backend.contracts.transform import OutputTable, PreparedTable
from apps.backend.contracts.trace import TraceRecord


class ScanRequest(BaseModel):
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


class ScanResponse(BaseModel):
    """数据扫描响应。"""

    profile: DatasetProfile = Field(description="生成的数据集画像。")
    trace: TraceRecord = Field(description="对应的 Trace 记录。")


class PlanRequest(BaseModel):
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


class PlanResponse(BaseModel):
    """计划细化响应模型。"""

    profile: DatasetProfile = Field(description="最新的数据集画像。")
    plan: Plan = Field(description="结构化计划。")
    prepared_table: PreparedTable = Field(description="变换前的准备表描述。")
    output_table: OutputTable = Field(description="主要输出表快照。")
    chart: ChartSpec = Field(description="推荐图表规范。")
    encoding_patch: EncodingPatch = Field(description="图表编码的增量补丁。")
    explanation: ExplanationArtifact = Field(description="解释 Agent 输出。")
    trace: TraceRecord = Field(description="Trace 记录。")


class TraceReplayRequest(BaseModel):
    """Trace 回放请求。"""

    task_id: str = Field(description="需要回放的任务 ID。", min_length=1)


class TraceReplayResponse(BaseModel):
    """Trace 回放响应。"""

    trace: TraceRecord = Field(description="回放的 Trace 记录。")


class TaskSubmitRequest(BaseModel):
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


class TaskSubmitResponse(BaseModel):
    """任务提交响应。"""

    task_id: str = Field(description="创建的任务 ID。", min_length=1)


class TaskFailurePayload(BaseModel):
    """任务失败结构化信息。"""

    error_type: str = Field(description="异常类型。", min_length=1)
    error_message: str = Field(description="异常消息。", min_length=1)


class TaskResultPayload(BaseModel):
    """任务成功结果载荷。"""

    profile: DatasetProfile = Field(description="任务结束时的画像。")
    plan: Plan = Field(description="最终计划。")
    prepared_table: PreparedTable = Field(description="变换输入快照。")
    output_table: OutputTable = Field(description="变换产出的数据表。")
    chart: ChartSpec = Field(description="推荐图表规范。")
    encoding_patch: EncodingPatch = Field(description="图表编码补丁。")
    explanation: ExplanationArtifact = Field(description="解释 Agent 输出。")
    trace: TraceRecord = Field(description="完整的 Trace 记录。")


class TaskResultResponse(BaseModel):
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
