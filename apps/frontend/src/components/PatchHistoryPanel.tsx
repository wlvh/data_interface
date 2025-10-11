import { useCallback } from "react";
import { useAppDispatch, useAppSelector } from "@/hooks/storeHooks";
import {
  selectPatchHistory,
  selectChartLoading,
  selectChartError,
  revertChartPatch,
} from "@/app/chartSlice";
import { selectTaskIdentifiers } from "@/app/taskSlice";

export default function PatchHistoryPanel() {
  const dispatch = useAppDispatch();
  const patchHistory = useAppSelector(selectPatchHistory);
  const isLoading = useAppSelector(selectChartLoading);
  const error = useAppSelector(selectChartError);
  const { taskId, datasetId } = useAppSelector(selectTaskIdentifiers);

  const handleRevert = useCallback(() => {
    if (!taskId || !datasetId) {
      return;
    }
    dispatch(
      revertChartPatch({
        taskId,
        datasetId,
        steps: 1,
      }),
    );
  }, [dispatch, taskId, datasetId]);

  if (patchHistory.length === 0) {
    return null;
  }

  return (
    <section className="card">
      <header className="card-header">
        <h2>补丁历史</h2>
        <button
          type="button"
          className="secondary-button"
          onClick={handleRevert}
          disabled={isLoading || patchHistory.length <= 1 || !taskId || !datasetId}
        >
          回退一步
        </button>
      </header>
      {error ? <p className="error-text">{error}</p> : null}
      <ol className="patch-history">
        {patchHistory.map((patch, index) => (
          <li key={`${patch.target_chart_id}-${index}`}>
            <div className="patch-header">
              <span className="patch-index">#{index + 1}</span>
              <span>{patch.rationale}</span>
            </div>
            <ul className="op-list">
              {patch.ops.map((op, opIndex) => (
                <li key={opIndex}>
                  <code>{op.op_type}</code> → {op.path.join("/")}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </section>
  );
}
