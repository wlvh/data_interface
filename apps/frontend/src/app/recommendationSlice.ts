import { createAsyncThunk, createSlice, PayloadAction } from "@reduxjs/toolkit";
import { postChartRecommend } from "@/api/client";
import type { Plan, RecommendationList } from "@/api/types";
import type { RootState } from "./store";

export interface RefreshRecommendationsArgs {
  taskId: string;
  datasetId: string;
  plan: Plan;
  tableId: string;
}

export interface RecommendationSliceState {
  payload: RecommendationList | null;
  selectedCandidateId: string | null;
  status: "idle" | "loading" | "ready" | "error";
  error: string | null;
}

const initialState: RecommendationSliceState = {
  payload: null,
  selectedCandidateId: null,
  status: "idle",
  error: null,
};

export const refreshRecommendations = createAsyncThunk(
  "recommendations/refresh",
  async ({ taskId, datasetId, plan, tableId }: RefreshRecommendationsArgs) => {
    const recommendations = await postChartRecommend({
      task_id: taskId,
      dataset_id: datasetId,
      plan,
      table_id: tableId,
    });
    return recommendations;
  },
);

const recommendationSlice = createSlice({
  name: "recommendations",
  initialState,
  reducers: {
    setRecommendations(state, action: PayloadAction<RecommendationList>) {
      state.payload = action.payload;
      state.selectedCandidateId = action.payload.recommendations.length > 0 ? action.payload.recommendations[0].candidate_id : null;
      state.status = "ready";
      state.error = null;
    },
    clearRecommendations(state) {
      state.payload = null;
      state.selectedCandidateId = null;
      state.status = "idle";
      state.error = null;
    },
    selectCandidate(state, action: PayloadAction<string>) {
      state.selectedCandidateId = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(refreshRecommendations.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(refreshRecommendations.fulfilled, (state, action) => {
        state.status = "ready";
        state.payload = action.payload;
        state.selectedCandidateId = action.payload.recommendations.length > 0 ? action.payload.recommendations[0].candidate_id : null;
      })
      .addCase(refreshRecommendations.rejected, (state, action) => {
        state.status = "error";
        state.error = action.error.message ?? "推荐刷新失败";
      });
  },
});

export const { setRecommendations, clearRecommendations, selectCandidate } = recommendationSlice.actions;

export const selectRecommendationState = (state: RootState) => state.recommendations.payload;
export const selectSelectedCandidateId = (state: RootState) => state.recommendations.selectedCandidateId;
export const selectRecommendationStatus = (state: RootState) => state.recommendations.status;
export const selectRecommendationError = (state: RootState) => state.recommendations.error;

export default recommendationSlice.reducer;
