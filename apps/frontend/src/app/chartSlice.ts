import { createAsyncThunk, createSlice, PayloadAction } from "@reduxjs/toolkit";
import { postChartReplace, postChartRevert } from "@/api/client";
import { ChartStatePayload, EncodingPatch } from "@/api/types";
import type { RootState } from "./store";

export interface ApplyPatchArgs {
  taskId: string;
  datasetId: string;
  patch: EncodingPatch;
}

export interface RevertPatchArgs {
  taskId: string;
  datasetId: string;
  steps?: number;
}

export interface ChartSliceState {
  chartSpec: ChartStatePayload["chart_spec"] | null;
  chartHash: string | null;
  patchHistory: EncodingPatch[];
  isLoading: boolean;
  error: string | null;
  lastTrace: { task_id: string } | null;
}

const initialState: ChartSliceState = {
  chartSpec: null,
  chartHash: null,
  patchHistory: [],
  isLoading: false,
  error: null,
  lastTrace: null,
};

export const applyChartPatch = createAsyncThunk(
  "chart/applyPatch",
  async ({ taskId, datasetId, patch }: ApplyPatchArgs) => {
    const response = await postChartReplace({
      task_id: taskId,
      dataset_id: datasetId,
      encoding_patch: patch,
    });
    return response;
  },
);

export const revertChartPatch = createAsyncThunk(
  "chart/revertPatch",
  async ({ taskId, datasetId, steps = 1 }: RevertPatchArgs) => {
    const response = await postChartRevert({
      task_id: taskId,
      dataset_id: datasetId,
      steps,
    });
    return response;
  },
);

const chartSlice = createSlice({
  name: "chart",
  initialState,
  reducers: {
    setChartState(state, action: PayloadAction<ChartStatePayload>) {
      const payload = action.payload;
      state.chartSpec = payload.chart_spec;
      state.chartHash = payload.chart_hash;
      state.patchHistory = payload.patch_history;
      state.error = null;
    },
    resetChart(state) {
      state.chartSpec = null;
      state.chartHash = null;
      state.patchHistory = [];
      state.error = null;
      state.lastTrace = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(applyChartPatch.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(applyChartPatch.fulfilled, (state, action) => {
        state.isLoading = false;
        state.chartSpec = action.payload.chart_spec;
        state.chartHash = action.payload.chart_hash;
        state.patchHistory = action.payload.patch_history;
        state.lastTrace = action.payload.trace;
      })
      .addCase(applyChartPatch.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.error.message ?? "图表替换失败";
      })
      .addCase(revertChartPatch.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(revertChartPatch.fulfilled, (state, action) => {
        state.isLoading = false;
        state.chartSpec = action.payload.chart_spec;
        state.chartHash = action.payload.chart_hash;
        state.patchHistory = action.payload.patch_history;
        state.lastTrace = action.payload.trace;
      })
      .addCase(revertChartPatch.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.error.message ?? "图表回退失败";
      });
  },
});

export const { setChartState, resetChart } = chartSlice.actions;

export const selectChartSpec = (state: RootState) => state.chart.chartSpec;
export const selectChartHash = (state: RootState) => state.chart.chartHash;
export const selectPatchHistory = (state: RootState) => state.chart.patchHistory;
export const selectChartLoading = (state: RootState) => state.chart.isLoading;
export const selectChartError = (state: RootState) => state.chart.error;

export default chartSlice.reducer;
