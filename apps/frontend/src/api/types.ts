export interface ChartChannelMapping {
  channel: string;
  field_name: string;
  aggregation: string;
}

export interface ChartLayout {
  width: number;
  height: number;
  padding: number;
  theme: string;
}

export interface ChartA11y {
  title: string;
  summary: string;
  annotations: string[];
}

export interface ChartSpec {
  chart_id: string;
  template_id: string;
  engine: string;
  data_source: string;
  encoding: ChartChannelMapping[];
  scales: unknown[];
  legends: unknown[];
  axes: unknown[];
  layout: ChartLayout;
  a11y: ChartA11y;
  parameters: Record<string, unknown>;
}

export interface EncodingPatchOp {
  op_type: "add" | "remove" | "replace";
  path: string[];
  value?: unknown;
}

export interface EncodingPatch {
  target_chart_id: string;
  ops: EncodingPatchOp[];
  rationale: string;
}

export interface EncodingPatchProposal {
  proposal_id: string;
  patch: EncodingPatch;
  confidence: number;
  summary: string;
}

export interface RecommendationCandidate {
  candidate_id: string;
  chart_spec: ChartSpec;
  confidence: number;
  rationale: string;
  intent_tags: string[];
  coverage?: string;
}

export interface RecommendationList {
  task_id: string;
  dataset_id: string;
  generated_at: string;
  recommendations: RecommendationCandidate[];
  surprise_pool: string[];
}

export interface PlanChartItem {
  template_id: string;
  rationale: string;
  encoding: ChartChannelMapping[];
  confidence: number;
}

export interface PlanFieldItem {
  field_name: string;
  semantic_role: string;
  rationale: string;
}

export interface Plan {
  plan_id: string;
  dataset_id: string;
  refined_goal: string;
  chart_plan: PlanChartItem[];
  field_plan: PlanFieldItem[];
}

export interface TableColumn {
  column_name: string;
  semantic_role: string;
}

export interface TableSample {
  rows: Record<string, unknown>[];
}

export interface PreparedTable {
  prepared_table_id: string;
  schema: TableColumn[];
  sample: TableSample;
}

export interface OutputTable {
  output_table_id: string;
  schema: TableColumn[];
  preview: TableSample;
  metrics: {
    rows_out: number;
  };
}

export interface ChartStatePayload {
  chart_spec: ChartSpec;
  chart_hash: string;
  patch_history: EncodingPatch[];
}

export interface TaskResultPayload {
  profile: {
    dataset_id: string;
    dataset_name: string;
    dataset_version: string;
  };
  plan: Plan;
  prepared_table: PreparedTable;
  output_table: OutputTable;
  chart_state: ChartStatePayload;
  recommendations: RecommendationList;
  explanation: {
    summary: string;
  };
  trace: {
    task_id: string;
  };
}

export interface TaskResultResponse {
  task_id: string;
  status: "running" | "completed" | "failed";
  result?: TaskResultPayload;
  failure?: {
    error_type: string;
    error_message: string;
  };
}

export interface NaturalEditResponse {
  proposals: EncodingPatchProposal[];
  recommended_index: number;
  ambiguity_reason?: string | null;
  trace: {
    task_id: string;
  };
}

export interface ChartReplaceResponse {
  chart_spec: ChartSpec;
  chart_hash: string;
  patch_history: EncodingPatch[];
  trace: {
    task_id: string;
  };
}

export interface ChartRevertResponse {
  chart_spec: ChartSpec;
  chart_hash: string;
  patch_history: EncodingPatch[];
  reverted_steps: number;
  trace: {
    task_id: string;
  };
}
