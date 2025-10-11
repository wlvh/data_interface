import { useAppSelector } from "@/hooks/storeHooks";
import { selectChartHash, selectChartSpec } from "@/app/chartSlice";
import { selectPlan } from "@/app/taskSlice";

export default function ChartSummary() {
  const chartSpec = useAppSelector(selectChartSpec);
  const chartHash = useAppSelector(selectChartHash);
  const plan = useAppSelector(selectPlan);

  if (!chartSpec) {
    return (
      <section className="card">
        <header className="card-header">
          <h2>图表状态</h2>
        </header>
        <p className="placeholder">尚未加载任务。</p>
      </section>
    );
  }

  return (
    <section className="card">
      <header className="card-header">
        <h2>图表状态</h2>
        {chartHash && <span className="hash-badge">hash {chartHash.slice(0, 8)}</span>}
      </header>
      <dl className="meta">
        <div>
          <dt>模板</dt>
          <dd>{chartSpec.template_id}</dd>
        </div>
        <div>
          <dt>数据源</dt>
          <dd>{chartSpec.data_source}</dd>
        </div>
        {plan && (
          <div>
            <dt>目标</dt>
            <dd>{plan.refined_goal}</dd>
          </div>
        )}
      </dl>
      <table className="encoding-table">
        <thead>
          <tr>
            <th>通道</th>
            <th>字段</th>
            <th>聚合</th>
          </tr>
        </thead>
        <tbody>
          {chartSpec.encoding.map((mapping) => (
            <tr key={mapping.channel}>
              <td>{mapping.channel}</td>
              <td>{mapping.field_name}</td>
              <td>{mapping.aggregation}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
