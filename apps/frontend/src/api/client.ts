import {
  ChartReplaceResponse,
  ChartRevertResponse,
  EncodingPatch,
  NaturalEditResponse,
  RecommendationList,
  TaskResultResponse,
} from "./types";

const DEFAULT_HEADERS = {
  "Content-Type": "application/json",
};

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${detail}`);
  }
  return (await response.json()) as T;
}

export async function fetchTaskResult(taskId: string): Promise<TaskResultResponse> {
  return http<TaskResultResponse>(`/api/task/${taskId}/result`);
}

export interface NaturalEditRequestPayload {
  task_id: string;
  dataset_id: string;
  chart_spec: unknown;
  nl_command: string;
}

export async function postNaturalEdit(payload: NaturalEditRequestPayload): Promise<NaturalEditResponse> {
  return http<NaturalEditResponse>("/api/natural/edit", {
    method: "POST",
    headers: DEFAULT_HEADERS,
    body: JSON.stringify(payload),
  });
}

export interface ChartReplaceRequestPayload {
  task_id: string;
  dataset_id: string;
  encoding_patch: EncodingPatch;
}

export async function postChartReplace(payload: ChartReplaceRequestPayload): Promise<ChartReplaceResponse> {
  return http<ChartReplaceResponse>("/api/chart/replace", {
    method: "POST",
    headers: DEFAULT_HEADERS,
    body: JSON.stringify(payload),
  });
}

export interface ChartRevertRequestPayload {
  task_id: string;
  dataset_id: string;
  steps?: number;
}

export async function postChartRevert(payload: ChartRevertRequestPayload): Promise<ChartRevertResponse> {
  return http<ChartRevertResponse>("/api/chart/revert", {
    method: "POST",
    headers: DEFAULT_HEADERS,
    body: JSON.stringify(payload),
  });
}

export interface ChartRecommendRequestPayload {
  task_id: string;
  dataset_id: string;
  plan: unknown;
  table_id: string;
}

interface ChartRecommendResponse {
  recommendations: RecommendationList;
}

export async function postChartRecommend(payload: ChartRecommendRequestPayload): Promise<RecommendationList> {
  const data = await http<ChartRecommendResponse>("/api/chart/recommend", {
    method: "POST",
    headers: DEFAULT_HEADERS,
    body: JSON.stringify(payload),
  });
  return data.recommendations;
}
