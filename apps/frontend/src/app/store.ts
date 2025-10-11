import { configureStore } from "@reduxjs/toolkit";
import chartReducer from "./chartSlice";
import taskReducer from "./taskSlice";
import recommendationReducer from "./recommendationSlice";
import naturalEditReducer from "./naturalEditSlice";

export const createAppStore = () =>
  configureStore({
    reducer: {
      chart: chartReducer,
      task: taskReducer,
      recommendations: recommendationReducer,
      naturalEdit: naturalEditReducer,
    },
  });

const store = createAppStore();

export type AppStore = typeof store;
export type RootState = ReturnType<AppStore["getState"]>;
export type AppDispatch = AppStore["dispatch"];

export default store;
