"""自然语言编辑 Agent，将 NL 指令解析为编码补丁候选。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional
from uuid import uuid4

from apps.backend.agents.base import Agent, AgentContext, AgentOutcome
from apps.backend.compat import model_dump
from apps.backend.contracts.chart_spec import ChartSpec
from apps.backend.contracts.encoding_patch import EncodingPatch, EncodingPatchOp, EncodingPatchProposal
from apps.backend.contracts.plan import ChartChannelMapping
from apps.backend.contracts.trace import SpanSLO


@dataclass(frozen=True)
class NaturalEditPayload:
    """封装自然语言编辑所需的输入载荷。"""

    chart_spec: ChartSpec
    nl_command: str


@dataclass(frozen=True)
class NaturalEditOutcome:
    """自然语言编辑的产出，包含候选补丁与推荐索引。"""

    proposals: List[EncodingPatchProposal]
    recommended_index: int
    ambiguity_reason: Optional[str]


class _NaturalCommandInterpreter:
    """基于启发式规则的自然语言指令解析器。"""

    def __init__(self, *, chart_spec: ChartSpec, command: str) -> None:
        self._chart_spec = chart_spec
        self._command = command
        self._command_lower = command.lower()
        self._dimension_fields = [
            mapping.field_name
            for mapping in chart_spec.encoding
            if mapping.aggregation == "none"
        ]
        self._measure_fields = [
            mapping.field_name
            for mapping in chart_spec.encoding
            if mapping.aggregation != "none"
        ]

    def generate_proposals(self) -> List[EncodingPatchProposal]:
        """生成候选补丁列表，按置信度降序排列。"""

        candidates: List[EncodingPatchProposal] = []
        candidates.extend(self._build_template_candidates())
        candidates.extend(self._build_swap_candidates())
        candidates.extend(self._build_color_candidates())
        candidates.extend(self._build_aggregation_candidates())
        if not candidates:
            candidates.append(self._build_fallback_proposal())
            return candidates
        sorted_candidates = sorted(
            candidates,
            key=lambda proposal: proposal.confidence,
            reverse=True,
        )
        return sorted_candidates

    def _build_template_candidates(self) -> List[EncodingPatchProposal]:
        """根据指令切换模板，避免与当前模板重复。"""

        keyword_to_template = {
            "line_basic": ("line", ["line", "trend", "折线", "趋势"]),
            "bar_basic": ("bar", ["bar", "column", "柱状", "对比"]),
            "scatter_basic": ("scatter", ["scatter", "散点", "相关"]),
            "metric_table": ("table", ["table", "列表", "明细", "表格"]),
        }
        proposals: List[EncodingPatchProposal] = []
        for template_id, (label, keywords) in keyword_to_template.items():
            if template_id == self._chart_spec.template_id:
                continue
            if not self._contains_any(keywords=keywords):
                continue
            rationale = f"将模板调整为 {label}，以匹配语句中的“{keywords[0]}”意图。"
            operation = EncodingPatchOp(
                op_type="replace",
                path=["template_id"],
                value=template_id,
            )
            patch = self._build_patch(operations=[operation], rationale=rationale)
            proposal = EncodingPatchProposal(
                proposal_id=f"proposal_{uuid4()}",
                patch=patch,
                confidence=0.75,
                summary=rationale,
            )
            proposals.append(proposal)
        return proposals

    def _build_swap_candidates(self) -> List[EncodingPatchProposal]:
        """构造交换 X/Y 通道的补丁候选。"""

        swap_keywords = ["swap", "flip", "交换", "互换", "调换"]
        if not self._contains_any(keywords=swap_keywords):
            return []
        encoded = list(self._chart_spec.encoding)
        x_mapping = self._find_channel(encoded, "x")
        y_mapping = self._find_channel(encoded, "y")
        if x_mapping is None or y_mapping is None:
            return []
        updated_mappings: List[ChartChannelMapping] = []
        for mapping in encoded:
            if mapping.channel == "x":
                updated_mappings.append(
                    ChartChannelMapping(
                        channel="x",
                        field_name=y_mapping.field_name,
                        aggregation=y_mapping.aggregation,
                    ),
                )
            elif mapping.channel == "y":
                updated_mappings.append(
                    ChartChannelMapping(
                        channel="y",
                        field_name=x_mapping.field_name,
                        aggregation=x_mapping.aggregation,
                    ),
                )
            else:
                updated_mappings.append(mapping)
        serialized = self._serialize_encodings(encodings=updated_mappings)
        operation = EncodingPatchOp(
            op_type="replace",
            path=["encoding"],
            value=serialized,
        )
        rationale = "交换 X/Y 轴字段，满足“交换轴”指令。"
        patch = self._build_patch(operations=[operation], rationale=rationale)
        proposal = EncodingPatchProposal(
            proposal_id=f"proposal_{uuid4()}",
            patch=patch,
            confidence=0.85,
            summary=rationale,
        )
        return [proposal]

    def _build_color_candidates(self) -> List[EncodingPatchProposal]:
        """根据指令调整颜色编码通道。"""

        color_keywords = ["color", "颜色", "着色"]
        if not self._contains_any(keywords=color_keywords):
            return []
        candidates: List[EncodingPatchProposal] = []
        target_fields = self._match_fields(self._dimension_fields)
        if not target_fields:
            target_fields = self._dimension_fields[:2]
        for index, field_name in enumerate(target_fields):
            updated = self._apply_color_mapping(field_name=field_name)
            serialized = self._serialize_encodings(encodings=updated)
            operation = EncodingPatchOp(
                op_type="replace",
                path=["encoding"],
                value=serialized,
            )
            summary = f"使用 {field_name} 维度进行颜色区分。"
            confidence = 0.9 if index == 0 else 0.6
            patch = self._build_patch(operations=[operation], rationale=summary)
            candidates.append(
                EncodingPatchProposal(
                    proposal_id=f"proposal_{uuid4()}",
                    patch=patch,
                    confidence=confidence,
                    summary=summary,
                ),
            )
        return candidates

    def _build_aggregation_candidates(self) -> List[EncodingPatchProposal]:
        """识别聚合指令并调整映射的聚合方式。"""

        avg_keywords = ["average", "avg", "平均"]
        sum_keywords = ["sum", "total", "合计", "总量", "总计"]
        target_aggregation: Optional[str] = None
        rationale = ""
        if self._contains_any(keywords=avg_keywords):
            target_aggregation = "avg"
            rationale = "将度量聚合方式调整为平均值。"
        elif self._contains_any(keywords=sum_keywords):
            target_aggregation = "sum"
            rationale = "将度量聚合方式调整为总和。"
        if target_aggregation is None:
            return []
        encoded = list(self._chart_spec.encoding)
        updated: List[ChartChannelMapping] = []
        changed = False
        for mapping in encoded:
            if mapping.channel == "y" and mapping.aggregation != target_aggregation:
                updated.append(
                    ChartChannelMapping(
                        channel="y",
                        field_name=mapping.field_name,
                        aggregation=target_aggregation,
                    ),
                )
                changed = True
            else:
                updated.append(mapping)
        if not changed:
            return []
        serialized = self._serialize_encodings(encodings=updated)
        operation = EncodingPatchOp(
            op_type="replace",
            path=["encoding"],
            value=serialized,
        )
        patch = self._build_patch(operations=[operation], rationale=rationale)
        proposal = EncodingPatchProposal(
            proposal_id=f"proposal_{uuid4()}",
            patch=patch,
            confidence=0.8,
            summary=rationale,
        )
        return [proposal]

    def _build_fallback_proposal(self) -> EncodingPatchProposal:
        """在无法解析时返回低置信度的备注型补丁。"""

        note_payload = {
            "command": self._command,
            "recorded_at": "pending",
        }
        operation = EncodingPatchOp(
            op_type="add",
            path=["parameters", "natural_edit_notes", str(uuid4())],
            value=note_payload,
        )
        summary = "无法解析指令，已记录备注以供人工复核。"
        patch = self._build_patch(operations=[operation], rationale=summary)
        return EncodingPatchProposal(
            proposal_id=f"proposal_{uuid4()}",
            patch=patch,
            confidence=0.1,
            summary=summary,
        )

    def _contains_any(self, *, keywords: Iterable[str]) -> bool:
        """判断当前指令是否包含任意关键词。"""

        for keyword in keywords:
            if keyword.lower() in self._command_lower:
                return True
        return False

    def _find_channel(self, mappings: List[ChartChannelMapping], channel: str) -> Optional[ChartChannelMapping]:
        """查找指定通道的编码映射。"""

        for mapping in mappings:
            if mapping.channel == channel:
                return mapping
        return None

    def _serialize_encodings(self, *, encodings: List[ChartChannelMapping]) -> List[dict]:
        """将编码映射序列化为原始字典，便于写入补丁。"""

        return [model_dump(mapping) for mapping in encodings]

    def _match_fields(self, fields: Iterable[str]) -> List[str]:
        """匹配指令中提及的字段名称，忽略大小写。"""

        matches: List[str] = []
        for field_name in fields:
            pattern = re.escape(field_name.lower())
            if re.search(pattern, self._command_lower):
                matches.append(field_name)
        return matches

    def _apply_color_mapping(self, *, field_name: str) -> List[ChartChannelMapping]:
        """生成包含颜色编码的映射集合。"""

        updated: List[ChartChannelMapping] = []
        color_replaced = False
        for mapping in self._chart_spec.encoding:
            if mapping.channel == "color":
                updated.append(
                    ChartChannelMapping(
                        channel="color",
                        field_name=field_name,
                        aggregation="none",
                    ),
                )
                color_replaced = True
            else:
                updated.append(mapping)
        if not color_replaced:
            updated.append(
                ChartChannelMapping(
                    channel="color",
                    field_name=field_name,
                    aggregation="none",
                ),
            )
        return updated

    def _build_patch(self, *, operations: List[EncodingPatchOp], rationale: str) -> EncodingPatch:
        """构建 EncodingPatch，目标为当前图表。"""

        return EncodingPatch(
            target_chart_id=self._chart_spec.chart_id,
            ops=operations,
            rationale=rationale,
        )


class NaturalEditAgent(Agent):
    """根据 NL 指令生成编码补丁候选。"""

    name = "natural_editor"
    slo = SpanSLO(
        max_duration_ms=800,
        max_retries=0,
        failure_isolation_required=True,
    )

    def run(self, context: AgentContext, payload: NaturalEditPayload) -> AgentOutcome:
        """解析自然语言并返回补丁候选。"""

        span_id = context.trace_recorder.start_span(
            operation="natural.edit",
            agent_name=self.name,
            slo=self.slo,
            parent_span_id=None,
            model_name="rule-based",
            prompt_version="v1",
        )
        interpreter = _NaturalCommandInterpreter(chart_spec=payload.chart_spec, command=payload.nl_command)
        proposals = interpreter.generate_proposals()
        recommended_index = 0
        ambiguity_reason = None
        if len(proposals) > 1:
            ambiguity_reason = "指令存在多种解释，已按置信度排序返回候选。"
        trace_span = context.trace_recorder.finish_span(
            span_id=span_id,
            status="success",
            failure_category=None,
            failure_isolation_ratio=1.0,
        )
        outcome = NaturalEditOutcome(
            proposals=proposals,
            recommended_index=recommended_index,
            ambiguity_reason=ambiguity_reason,
        )
        return AgentOutcome(
            output=outcome,
            span_id=span_id,
            trace_span=trace_span,
        )
