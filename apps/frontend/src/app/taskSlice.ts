import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { fetchTaskResult } from "@/api/client";
import type { Plan, PreparedTable, OutputTable, TaskResultPayload } from "@/api/types";
import type { RootState } from "./store";
import { setChartState, resetChart } from "./chartSlice";
import { setRecommendations, clearRecommendations } from "./recommendationSlice";
import { clearNaturalEdit } from "./naturalEditSlice";

export interface LoadTaskArgs {
  taskId: string;
}

export interface TaskSliceState {
  taskId: string | null;
  datasetId: string | null;
  status: "idle" | "loading" | "ready" | "error";
  plan: Plan | null;
  preparedTable: PreparedTable | null;
  outputTable: OutputTable | null;
  lastTraceTaskId: string | null;
  error: string | null;
}

const initialState: TaskSliceState = {
  taskId: null,
  datasetId: null,
  status: "idle",
  plan: null,
  preparedTable: null,
  outputTable: null,
  lastTraceTaskId: null,
  error: null,
};

export const loadTaskResult = createAsyncThunk(
  "task/load",
  async ({ taskId }: LoadTaskArgs, thunkAPI) => {
    try {
      const response = await fetchTaskResult(taskId);
      if (response.status !== "completed" || response.result === undefined) {
        const detail = response.failure?.error_message ?? "任务尚未完成";
        throw new Error(detail);
      }
      const result: TaskResultPayload = response.result;
      thunkAPI.dispatch(setChartState(result.chart_state));
      thunkAPI.dispatch(setRecommendations(result.recommendations));
      thunkAPI.dispatch(clearNaturalEdit());
      return {
        taskId: response.task_id,
        datasetId: result.profile.dataset_id,
        plan: result.plan,
        preparedTable: result.prepared_table,
        outputTable: result.output_table,
        traceTaskId: result.trace.task_id,
      };
    } catch (error) {
      thunkAPI.dispatch(resetChart());
      thunkAPI.dispatch(clearRecommendations());
      thunkAPI.dispatch(clearNaturalEdit());
      throw error;
    }
  },
);

const taskSlice = createSlice({
  name: "task",
  initialState,
  reducers: {
    resetTask(state) {
      state.taskId = null;
      state.datasetId = null;
      state.status = "idle";
      state.plan = null;
      state.preparedTable = null;
      state.outputTable = null;
      state.lastTraceTaskId = null;
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loadTaskResult.pending, (state) => {
        state.status = "loading";
        state.error = null;
        state.lastTraceTaskId = null;
      })
      .addCase(loadTaskResult.fulfilled, (state, action) => {
        state.status = "ready";
        state.taskId = action.payload.taskId;
        state.datasetId = action.payload.datasetId;
        state.plan = action.payload.plan;
        state.preparedTable = action.payload.preparedTable;
        state.outputTable = action.payload.outputTable;
        state.lastTraceTaskId = action.payload.traceTaskId;
      })
      .addCase(loadTaskResult.rejected, (state, action) => {
        state.status = "error";
        state.error = action.error.message ?? "任务加载失败";
        state.taskId = null;
        state.datasetId = null;
        state.plan = null;
        state.preparedTable = null;
        state.outputTable = null;
        state.lastTraceTaskId = null;
      });
  },
});

export const { resetTask } = taskSlice.actions;

export const selectTaskStatus = (state: RootState) => state.task.status;
export const selectTaskError = (state: RootState) => state.task.error;
export const selectTaskIdentifiers = (state: RootState) => ({
  taskId: state.task.taskId,
  datasetId: state.task.datasetId,
});
export const selectPlan = (state: RootState) => state.task.plan;
export const selectOutputTable = (state: RootState) => state.task.outputTable;

export default taskSlice.reducer;
