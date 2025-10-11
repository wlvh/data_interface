import { useState } from "react";
import TaskLoader from "./TaskLoader";
import NaturalEditPanel from "./NaturalEditPanel";
import ManualEditPanel from "./ManualEditPanel";
import ChartSummary from "./ChartSummary";
import RecommendationPanel from "./RecommendationPanel";
import PatchHistoryPanel from "./PatchHistoryPanel";
import { useAppSelector } from "@/hooks/storeHooks";
import { selectChartError } from "@/app/chartSlice";

export default function App() {
  const [command, setCommand] = useState("");
  const chartError = useAppSelector(selectChartError);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <TaskLoader onCommandReset={() => setCommand("")} />
        <NaturalEditPanel command={command} onCommandChange={setCommand} />
        <ManualEditPanel />
      </aside>
      <main className="main-content">
        {chartError && <p className="error-text">{chartError}</p>}
        <ChartSummary />
        <RecommendationPanel onCommandSample={setCommand} />
        <PatchHistoryPanel />
      </main>
    </div>
  );
}
