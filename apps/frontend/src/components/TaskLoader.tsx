import { FormEvent, useState } from "react";
import { useAppDispatch, useAppSelector } from "@/hooks/storeHooks";
import { loadTaskResult, selectTaskError, selectTaskIdentifiers, selectTaskStatus } from "@/app/taskSlice";

export interface TaskLoaderProps {
  onCommandReset?: () => void;
}

export default function TaskLoader({ onCommandReset }: TaskLoaderProps) {
  const dispatch = useAppDispatch();
  const status = useAppSelector(selectTaskStatus);
  const error = useAppSelector(selectTaskError);
  const { taskId, datasetId } = useAppSelector(selectTaskIdentifiers);
  const [inputValue, setInputValue] = useState(taskId ?? "");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = inputValue.trim();
    if (trimmed.length === 0) {
      return;
    }
    if (onCommandReset) {
      onCommandReset();
    }
    dispatch(loadTaskResult({ taskId: trimmed }));
  };

  return (
    <section className="card">
      <header className="card-header">
        <h2>任务上下文</h2>
      </header>
      <form className="stack" onSubmit={handleSubmit}>
        <label className="label">
          <span>task_id</span>
          <input
            type="text"
            value={inputValue}
            onChange={(event) => setInputValue(event.target.value)}
            placeholder="task_xxxxx"
            autoComplete="off"
          />
        </label>
        <button type="submit" className="primary-button" disabled={status === "loading"}>
          {status === "loading" ? "加载中…" : "加载任务"}
        </button>
      </form>
      {taskId && datasetId && (
        <dl className="meta">
          <div>
            <dt>当前任务</dt>
            <dd>{taskId}</dd>
          </div>
          <div>
            <dt>数据集</dt>
            <dd>{datasetId}</dd>
          </div>
        </dl>
      )}
      {error && <p className="error-text">{error}</p>}
    </section>
  );
}
