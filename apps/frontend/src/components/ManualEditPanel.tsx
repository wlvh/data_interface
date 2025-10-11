import { FormEvent, useEffect, useMemo, useState } from "react";
import { useAppDispatch, useAppSelector } from "@/hooks/storeHooks";
import { selectChartSpec, applyChartPatch, selectChartError } from "@/app/chartSlice";
import { selectPlan, selectTaskIdentifiers } from "@/app/taskSlice";
import { buildChannelMappingPatch } from "@/utils/patch";

export default function ManualEditPanel() {
  const dispatch = useAppDispatch();
  const chartSpec = useAppSelector(selectChartSpec);
  const plan = useAppSelector(selectPlan);
  const { taskId, datasetId } = useAppSelector(selectTaskIdentifiers);
  const chartError = useAppSelector(selectChartError);

  const channels = useMemo(() => (chartSpec ? chartSpec.encoding.map((item) => item.channel) : []), [chartSpec]);
  const fieldOptions = useMemo(() => plan?.field_plan ?? [], [plan]);
  const fieldRoleMap = useMemo(() => {
    const map = new Map<string, string>();
    fieldOptions.forEach((item) => {
      map.set(item.field_name, item.semantic_role);
    });
    return map;
  }, [fieldOptions]);

  const [selectedChannel, setSelectedChannel] = useState<string>(channels[0] ?? "");
  const [selectedField, setSelectedField] = useState<string>(fieldOptions[0]?.field_name ?? "");
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (channels.length > 0 && !channels.includes(selectedChannel)) {
      setSelectedChannel(channels[0]);
    }
  }, [channels, selectedChannel]);

  useEffect(() => {
    if (fieldOptions.length > 0 && !fieldOptions.some((item) => item.field_name === selectedField)) {
      setSelectedField(fieldOptions[0].field_name);
    }
  }, [fieldOptions, selectedField]);

  if (!chartSpec || !plan || !taskId || !datasetId) {
    return null;
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedChannel || !selectedField) {
      return;
    }
    const targetEncoding = chartSpec.encoding.find((item) => item.channel === selectedChannel);
    const fieldRole = fieldRoleMap.get(selectedField);
    if (!targetEncoding || !fieldRole) {
      setFormError("未能匹配到对应的通道或字段角色。");
      return;
    }
    if (["sum", "avg"].includes(targetEncoding.aggregation) && fieldRole !== "measure") {
      setFormError(`通道 ${selectedChannel} 需要数值度量字段，请选择 measure 字段。`);
      return;
    }
    setFormError(null);
    const patch = buildChannelMappingPatch({
      chartSpec,
      channel: selectedChannel,
      fieldName: selectedField,
    });
    dispatch(
      applyChartPatch({
        taskId,
        datasetId,
        patch,
      }),
    );
  };

  return (
    <section className="card">
      <header className="card-header">
        <h2>拖拽映射（表单模拟）</h2>
      </header>
      {formError ? <p className="error-text">{formError}</p> : null}
      {chartError ? <p className="error-text">{chartError}</p> : null}
      <form className="horizontal" onSubmit={handleSubmit}>
        <label className="label">
          <span>通道</span>
          <select value={selectedChannel} onChange={(event) => setSelectedChannel(event.target.value)}>
            {channels.map((channel) => (
              <option key={channel} value={channel}>
                {channel}
              </option>
            ))}
          </select>
        </label>
        <label className="label">
          <span>字段</span>
          <select value={selectedField} onChange={(event) => setSelectedField(event.target.value)}>
            {fieldOptions.map((item) => (
              <option key={item.field_name} value={item.field_name}>
                {item.field_name}（{item.semantic_role}）
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="secondary-button">
          应用映射
        </button>
      </form>
    </section>
  );
}
