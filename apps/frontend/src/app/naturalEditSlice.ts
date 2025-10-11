import { createAsyncThunk, createSlice, PayloadAction } from "@reduxjs/toolkit";
import { postNaturalEdit } from "@/api/client";
import type { EncodingPatchProposal, NaturalEditResponse } from "@/api/types";
import type { RootState } from "./store";

export interface RunNaturalEditArgs {
  taskId: string;
  datasetId: string;
  chartSpec: unknown;
  command: string;
}

export interface NaturalEditSliceState {
  proposals: EncodingPatchProposal[];
  recommendedIndex: number | null;
  ambiguityReason: string | null;
  isLoading: boolean;
  error: string | null;
  lastCommand: string;
}

const initialState: NaturalEditSliceState = {
  proposals: [],
  recommendedIndex: null,
  ambiguityReason: null,
  isLoading: false,
  error: null,
  lastCommand: "",
};

export const runNaturalEdit = createAsyncThunk(
  "naturalEdit/run",
  async ({ taskId, datasetId, chartSpec, command }: RunNaturalEditArgs) => {
    const response: NaturalEditResponse = await postNaturalEdit({
      task_id: taskId,
      dataset_id: datasetId,
      chart_spec: chartSpec,
      nl_command: command,
    });
    return { response, command };
  },
);

const naturalEditSlice = createSlice({
  name: "naturalEdit",
  initialState,
  reducers: {
    clearNaturalEdit(state) {
      state.proposals = [];
      state.recommendedIndex = null;
      state.ambiguityReason = null;
      state.error = null;
      state.lastCommand = "";
    },
    selectProposal(state, action: PayloadAction<string>) {
      const index = state.proposals.findIndex((proposal) => proposal.proposal_id === action.payload);
      state.recommendedIndex = index >= 0 ? index : state.recommendedIndex;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(runNaturalEdit.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(runNaturalEdit.fulfilled, (state, action) => {
        state.isLoading = false;
        state.proposals = action.payload.response.proposals;
        state.recommendedIndex = action.payload.response.recommended_index ?? null;
        state.ambiguityReason = action.payload.response.ambiguity_reason ?? null;
        state.lastCommand = action.payload.command;
      })
      .addCase(runNaturalEdit.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.error.message ?? "自然语言解析失败";
      });
  },
});

export const { clearNaturalEdit, selectProposal } = naturalEditSlice.actions;

export const selectNaturalEditState = (state: RootState) => state.naturalEdit;

export default naturalEditSlice.reducer;
