# [EPIC] 从契约到闭环：Scan → ChartSpec 完成度复盘

## 总结

- ✅ **契约镜像门禁（M1-A）仅完成模型与 Schema 的对齐、UTC 校验与统计不变量校验。** 当前仓库含有契约模型及其镜像测试，能在 Pydantic ↔ JSONSchema 之间进行一致性校验。【7c5345†L1-L3】【1e365a†L1-L96】【cd91ad†L1-L78】
- ❌ **其余关键链路尚未落地。** 后端缺少 API、扫描服务、落盘逻辑与追踪骨架；前端仍为老版集中式实现，未引入 Redux Store、RTK Query、SSE 客户端与 ChartSpec 适配层。【7c5345†L1-L3】【ebfbe9†L1-L2】【a17b4c†L1-L120】
- ❌ **CI/质量门与运营要求未完成。** 仓库缺少 pre-commit/CI 配置、体积门控制、SSE 断线恢复策略、Worker 并发协议与快照哈希等必做项。【31a366†L1-L2】【1b3e36†L1-L2】

## 需求逐条核对

### M1-A 契约镜像 & 门禁

| 需求 | 状态 | 说明 |
| --- | --- | --- |
| Pydantic ↔ JSONSchema 镜像测试 | ✅ | `apps/backend/tests/test_contract_schemas.py` 校验三大契约并覆盖 UTC/统计异常路径。【1e365a†L1-L160】 |
| UTC & 统计不变量 | ✅ | `DatasetSummary`/`DatasetProfile` 对 UTC 与统计做强约束。【6cbda6†L1-L104】 |
| ChartTemplate 通道约束 | ✅ | 契约定义包含唯一性与默认配置序列化校验（详见仓库历史 commit）。 |
| `$id/$schema/version` & `additionalProperties:false` | ✅ | `ContractModel` 基类统一注入元数据并递归补充 `additionalProperties`。【cd91ad†L1-L78】 |
| pre-commit/CI 门禁 | ❌ | 仓库不存在 `.pre-commit-config.yaml` 或 CI 配置，无法阻断违规提交。【31a366†L1-L2】【1b3e36†L1-L2】 |

> 结论：M1-A 仅在模型侧完成，尚未配置工程门禁，整体状态为 **部分完成**。

### M1-B 扫描 API + 落盘 + 回放

| 需求 | 状态 | 说明 |
| --- | --- | --- |
| `POST /api/data/scan` API | ❌ | `apps/backend/` 下仅包含契约与测试，缺乏 `api/` 与 `services/` 目录。【7c5345†L1-L3】 |
| DatasetSummary 落盘（artifacts/traces） | ❌ | 仓库中不存在 `artifacts/` 与 `traces/` 目录或相关落盘逻辑。 |
| 1MB 体积限制 & 错误统一结构 | ❌ | 未见响应包装器或错误类型定义。 |
| Trace 导出/回放 | ❌ | 缺少 `trace.py`、`replay.py` 等实现。 |

> 结论：M1-B 尚未启动。

### M1-C 单一 Store + RTK Query + SSE

| 需求 | 状态 | 说明 |
| --- | --- | --- |
| Redux Store 切片 | ❌ | 前端目录结构无 `app/` 与 `store.ts` 等文件，仍为旧式全局对象。【ebfbe9†L1-L2】【a17b4c†L1-L120】 |
| RTK Query（scanApi/traceApi） | ❌ | 未见 `services/scanApi.ts` 等文件。 |
| SSE 客户端骨架 | ❌ | `sse/stream.ts` 不存在。 |
| 快照导出/导入 | ⚠️ | 旧版实现提供快照导出按钮，但未统一 Store 结构且缺少哈希策略。【a17b4c†L1-L120】 |

> 结论：M1-C 未达成目标。

### M1-D ChartSpec 适配层

| 需求 | 状态 | 说明 |
| --- | --- | --- |
| 后端 ChartSpec 生成 | ❌ | 后端缺少 `ChartSpec` 数据模型与模板映射逻辑。 |
| 前端 `adapter.toECharts()` | ❌ | 现有 `chartManager` 直接消费旧结构，无独立适配层。【a17b4c†L1-L120】 |
| 仅消费 ChartSpec 渲染 | ❌ | 图表仍通过内部约定渲染。 |

> 结论：M1-D 未落地。

### M1-E 前端正确性/性能/安全修复

| 需求 | 状态 | 说明 |
| --- | --- | --- |
| UTC 全链路 | ❌ | `main.js` 中仍使用本地时间对象，没有统一 UTC 工具。【a17b4c†L1-L120】 |
| brushSelected 圈选 & 抽样策略 | ❌ | 现有 `chartManager` 未迁移，圈选逻辑沿用旧实现。 |
| tooltip/图例/缓存修复 | ❌ | 未找到相关补丁。 |
| fetch 守卫 & Worker 并发协议 | ❌ | `main.js` 中 `fetch` 缺少 `response.ok` 检查；Worker 协议沿用旧版结构。【a17b4c†L35-L80】 |

> 结论：M1-E 尚未执行。

### M2 可选增强

未发现 `ChartSpec` 拓展、Trace 字段扩展或 FolderCard/Ingestion 相关代码，整体状态为 **未开始**。

## 建议

1. 立即补全工程骨架：创建 `apps/backend/api/`、`services/`、`telemetry/` 目录，先实现最小扫描 API 与落盘逻辑。
2. 在根目录添加 `.pre-commit-config.yaml` 与 CI 工作流，保障契约镜像门禁真正生效。
3. 重构前端架构，引入 Redux Toolkit、RTK Query 与 SSE 客户端，建立 ChartSpec 适配层。
4. 针对安全/性能缺陷撰写测试与文档，逐项关闭 M1-E 列出的缺陷。

