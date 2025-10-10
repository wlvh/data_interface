# 数据智能编排蓝图

## 目标拆解

- **需求澄清**：在任何用户输入前，系统必须以 `DatasetSummary` 为上下文，自动补全字段概览、采样示例与值域摘要。
- **计划生成**：规划 Agent 将“模糊目标”转化为结构化 `Plan`，涵盖推荐字段、编码映射、图表模板与变换代码草案。
- **多 Agent 编排**：以状态图建模链路节点（Scan → Plan → Transform → Explain → Validate），每个节点对应独立的原子能力与 SLO。
- **可回放与追踪**：所有节点通过 Trace → Span 树记录模型版本、提示版本、耗时、重试次数与失败分类，输出结构化 JSON。
- **解释透明**：解释 Agent 以“数据摘要 + 代码执行结果”生成 Markdown 说明，主 Agent 仅承担编排职责。

## 目录规划

| 路径 | 职责说明 |
| --- | --- |
| `apps/backend/api/` | FastAPI 路由定义与依赖装配，暴露统一最小后端 API。 |
| `apps/backend/agents/` | 原子能力定义：数据扫描、计划细化、变换执行、解释生成、图表推荐。 |
| `apps/backend/infra/` | 通用支撑层：Trace/Span 追踪、SLO 统计、LLM 客户端抽象、时钟与配置管理。 |
| `apps/backend/services/` | 状态图编排器与任务运行器，连接 Redux Store 所需的结构化输出。 |
| `apps/backend/stores/` | 数据集画像与派生表的集中缓存（仅落盘 JSON，不做隐藏状态）。 |
| `docs/` | 架构规划、运行手册与指标定义。 |

## 状态图（概念版）

1. **Scan**：`DatasetScannerAgent` 读取数据源，产出 `DatasetSummary` 与 `DatasetProfile`，同时触发指标 (`scan_duration_ms`, `scan_retry_count`)。
2. **Plan**：`PlanRefinementAgent` 接收用户原始意图与数据摘要，输出 `Plan`（字段推荐、图表模板、代码草案、解释提纲）。
3. **Transform**：`TransformExecutionAgent` 使用计划中的代码草案执行派生表或聚合/分箱，记录中间日志与指标。
4. **Chart**：`ChartRecommendationAgent` 结合模板仓库与编码映射生成 `ChartSpec` 列表；`NaturalEditAgent` 根据自然语言输出 `EncodingPatch`。
5. **Explain**：`ExplanationAgent` 生成 Markdown，总结行为变化、SLO 达成情况与下一步建议。

每个节点通过 `StateMachineOrchestrator` 以 `StateNode`（输入/输出契约 + 事件）形式组合，确保：

- 输入输出均为可 JSON 序列化的 Pydantic 模型；
- 节点执行失败时立即 Fail Fast，阻断后续链路；
- 所有事件通过 Redux `replaceChart` 与 `chart/replaceChart` 统一落地，便于回放。

## 关键约束映射

- **字段知识库**：扫描节点将字段语义、Top-K、值域与样本写入集中缓存，计划与推荐节点仅通过数据依赖访问，不共享隐藏状态。
- **SLO 指标**：`infra/tracing` 统一暴露 `SpanMetrics`，记录耗时、重试、失败分类；失败需返还 `failure_isolation_ratio`。
- **模板适配**：`agents/chart` 以模板 + 编码映射合成 Vega/ECharts 规范；运行前执行 Top-K、分箱与容量控制。
- **中止与超时**：所有 Agent 接口接受 `timeout` 与 `max_retries`，在超时或失败后写入 Trace，停止后续节点。
- **回放能力**：`services/trace_store` 将 Trace → Span 树落盘 JSON，`/api/trace/:task_id` 返回可回放记录，`/api/trace/replay` 重现执行。

## 下一步里程碑

- [x] 建立 `apps/backend/infra` 与 `agents` 核心骨架，引入 FastAPI 服务与依赖注入。
- [x] 实现 `DatasetScannerAgent`、`PlanRefinementAgent`、`TransformExecutionAgent`、`ChartRecommendationAgent` 与 `/api/data/scan`、`/api/plan/refine`、`/api/trace/*`。
- [x] 构建 `/api/task/submit` + `/api/task/stream` SSE 流，结合 `TaskRunner` 推送节点级事件。
- [ ] 接入 OpenTelemetry，输出 Trace → Span 指标并形成统一观测面板。
- [ ] 建立模板仓库、自然语言编辑器与 Redux `replaceChart` 对接，完成图表适配闭环。

## 当前进展与阻塞

### 已完成
- FastAPI 层新增 `/api/task/submit`、`/api/task/stream`，通过 `TaskRunner` + `StateMachineOrchestrator` 推送 Scan → Plan → Transform → Chart → Explain 进度事件。
- `TraceStore` 支持 JSON 落盘并可重放，`TraceRecord` 契约与测试覆盖所有节点。
- `pipeline.py` 抽象完整流程，方便同步调用与后续扩展；新增 `PipelineAgents`、`PipelineConfig`、`PipelineOutcome`。
- 引入 `apps/backend/compat` 适配 Pydantic v1/v2，JSON Schema 自动同步并通过测试验证。
- `test_pipeline.py` 覆盖同步 pipeline 流程，构造 Fake pandas 数据以规避真实依赖。
- 测试用 Fake pandas 模块保证 `pytest` 在无真实依赖环境中可运行：直接执行 `python -m pytest -q` 即可完成后端契约与管线测试。

### 未完成 / TODO
- OpenTelemetry 集成、SLO 仪表板、节点级指标落盘仍在计划中。
- 模板仓库、`replaceChart` Redux 对接、自然语言 `EncodingPatch`、Top-K/分箱预处理仍未落地。
- `/api/task/stream` 仅提供基础 SSE，缺少心跳、错误重试与断线恢复策略。

### 遇到的问题
- 依赖真实 pandas/numpy 时，Mac Accelerate 套件会在导入阶段触发浮点异常；当前通过测试用 Fake pandas 规避，但线上仍需官方 wheel 或容器化环境。
- `TaskRunner` 异步测试长时间挂起：`asyncio.to_thread` 执行真实 Agent 时阻塞事件循环，导致 SSE 队列无法及时返回。现阶段只验证同步 pipeline，异步用例保留 TODO，后续考虑引入 stub Agent 或拆分运行线程池。
- SSE 流未添加鉴权/限流与订阅回收机制，长连线场景下需进一步优化。
