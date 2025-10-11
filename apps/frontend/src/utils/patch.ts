import type { ChartSpec, EncodingPatch, ChartChannelMapping } from "@/api/types";

export function buildCandidateAdoptionPatch(params: {
  currentChartId: string;
  candidate: ChartSpec;
  rationale: string;
}): EncodingPatch {
  return {
    target_chart_id: params.currentChartId,
    rationale: params.rationale,
    ops: [
      { op_type: "replace", path: ["engine"], value: params.candidate.engine },
      { op_type: "replace", path: ["data_source"], value: params.candidate.data_source },
      { op_type: "replace", path: ["template_id"], value: params.candidate.template_id },
      { op_type: "replace", path: ["encoding"], value: params.candidate.encoding },
      { op_type: "replace", path: ["scales"], value: params.candidate.scales },
      { op_type: "replace", path: ["legends"], value: params.candidate.legends },
      { op_type: "replace", path: ["axes"], value: params.candidate.axes },
      { op_type: "replace", path: ["layout"], value: params.candidate.layout },
      { op_type: "replace", path: ["a11y"], value: params.candidate.a11y },
      { op_type: "replace", path: ["parameters"], value: params.candidate.parameters },
    ],
  };
}

export function buildChannelMappingPatch(params: {
  chartSpec: ChartSpec;
  channel: string;
  fieldName: string;
}): EncodingPatch {
  const updatedEncodings: ChartChannelMapping[] = params.chartSpec.encoding.map((mapping) =>
    mapping.channel === params.channel
      ? { ...mapping, field_name: params.fieldName }
      : { ...mapping },
  );
  return {
    target_chart_id: params.chartSpec.chart_id,
    rationale: `更新 ${params.channel} 通道字段为 ${params.fieldName}`,
    ops: [
      {
        op_type: "replace",
        path: ["encoding"],
        value: updatedEncodings,
      },
    ],
  };
}
