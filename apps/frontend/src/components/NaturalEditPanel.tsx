import { FormEvent } from "react";
import { useAppDispatch, useAppSelector } from "@/hooks/storeHooks";
import { runNaturalEdit, selectNaturalEditState } from "@/app/naturalEditSlice";
import { applyChartPatch } from "@/app/chartSlice";
import { selectTaskIdentifiers } from "@/app/taskSlice";
import { selectChartSpec } from "@/app/chartSlice";

export interface NaturalEditPanelProps {
  command: string;
  onCommandChange: (value: string) => void;
}

export default function NaturalEditPanel({ command, onCommandChange }: NaturalEditPanelProps) {
  const dispatch = useAppDispatch();
  const naturalEditState = useAppSelector(selectNaturalEditState);
  const { taskId, datasetId } = useAppSelector(selectTaskIdentifiers);
  const chartSpec = useAppSelector(selectChartSpec);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!taskId || !datasetId || !chartSpec) {
      return;
    }
    const trimmed = command.trim();
    if (trimmed.length === 0) {
      return;
    }
    dispatch(
      runNaturalEdit({
        taskId,
        datasetId,
        chartSpec,
        command: trimmed,
      }),
    );
  };

  const applyProposal = (proposalId: string) => {
    if (!taskId || !datasetId || !chartSpec) {
      return;
    }
    const proposal = naturalEditState.proposals.find((item) => item.proposal_id === proposalId);
    if (!proposal) {
      return;
    }
    dispatch(
      applyChartPatch({
        taskId,
        datasetId,
        patch: proposal.patch,
      }),
    );
  };

  return (
    <section className="card">
      <header className="card-header">
        <h2>自然语言编辑</h2>
      </header>
      <form className="stack" onSubmit={handleSubmit}>
        <label className="label">
          <span>指令</span>
          <textarea
            value={command}
            onChange={(event) => onCommandChange(event.target.value)}
            rows={3}
            placeholder="例如：交换 x 轴与 y 轴"
          />
        </label>
        <button type="submit" className="primary-button" disabled={naturalEditState.isLoading || !taskId || !datasetId || !chartSpec}>
          {naturalEditState.isLoading ? "解析中…" : "生成补丁"}
        </button>
      </form>
      {naturalEditState.ambiguityReason && <p className="note">{naturalEditState.ambiguityReason}</p>}
      {naturalEditState.error && <p className="error-text">{naturalEditState.error}</p>}
      {naturalEditState.proposals.length > 0 && (
        <ul className="proposal-list">
          {naturalEditState.proposals.map((proposal, index) => (
            <li key={proposal.proposal_id} className={index === naturalEditState.recommendedIndex ? "proposal recommended" : "proposal"}>
              <div className="proposal-header">
                <span className="proposal-summary">{proposal.summary}</span>
                <span className="proposal-confidence">置信度 {Math.round(proposal.confidence * 100)}%</span>
              </div>
              <button type="button" className="secondary-button" onClick={() => applyProposal(proposal.proposal_id)}>
                应用补丁
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
