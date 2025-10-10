# Data Interface

## 愿景与定位

Data Interface 是一个面向多行业、多数据域的智能分析操作系统。我们以“Intent → Fields → Transform → Encode → Chart → Validate → Clean”的闭环为主线，目标是在任何结构化数据集上提供从模糊需求澄清到可回放可解释的最终可视化交付。现阶段演示数据为 Walmart 零售，但整体架构和契约均按通用场景设计。

## 系统能力蓝图

- **目标细化与计划生成**：通过 `/api/plan/refine` 驱动的规划 Agent，将用户模糊目标拆解为字段选择、可视化模板、转换草案等结构化计划。
- **数据扫描与知识库**：`/api/data/scan` 输出字段概览、样本截面和值域摘要，作为所有下游 Agent 的标准上下文输入。
- **可组合原子能力**：数据理解、变换、模板适配、解释生成等 Agent 以状态图编排，避免长上下文串行阻塞，并为 Trace → Span 树打基础。
- **解释与可观测性**：独立解释 Agent 负责 Markdown 化的结果说明；全链路记录模型版本、提示、耗时、重试与错误分类，准备接入 OpenTelemetry。
- **统一状态与可回放**：后端通过契约输出 `ChartSpec`、日志和派生表；前端以 Redux Toolkit + RTK Query 维护唯一 Store，所有交互通过 Action 驱动，可随时回放或回滚。
- **模板化可视化**：图类型以模板+编码映射组合生成 Vega/ECharts 规范，支持自动聚合/分箱、Top-K 截断等运行前防护。
- **用户共创体验**：自然语言与拖拽操作映射到同一状态变更入口（`replaceChart`），支持“给我惊喜”式推荐，强调从零到首图的接受效率。

## 目录与职责

| 路径 | 角色定位 | 关键内容 |
| --- | --- | --- |
| `apps/backend/` | 后端与 AI 服务骨架 | FastAPI 应用、Agent 编排、契约定义、Trace 追踪。 |
| `apps/backend/api/` | HTTP 接口层 | FastAPI 路由，现已覆盖 `/api/data/scan`、`/api/plan/refine`、`/api/trace/*`、`/api/task/*`。 |
| `apps/backend/agents/` | 原子 Agent 能力 | 数据扫描、计划细化、变换执行、图表推荐、解释生成，以及通用 `AgentContext`。 |
| `apps/backend/infra/` | 基础设施 | `UtcClock`、`TraceRecorder` 等跨域工具。 |
| `apps/backend/compat/` | 兼容层 | Pydantic v1/v2 适配，统一 `ConfigDict` 与 `model_validator`。 |
| `apps/backend/services/` | 状态图编排 | `StateMachineOrchestrator`、`pipeline.py` 与 `task_runner.py` 负责多节点组合与任务流。 |
| `apps/backend/stores/` | 内存缓存 | `DatasetStore`、`TraceStore` 用于画像与 Trace 回放。 |
| `apps/backend/contracts/` | 数据契约与领域模型 | `dataset_profile.py`、`plan.py`、`trace.py` 等及镜像 `schema/*.json`。 |
| `apps/backend/tests/` | 契约与流程校验 | Schema 同步测试、状态图单元测试。 |
| `apps/frontend/` | 主产品前端（待 TS 化） | Vite App、Redux 迁移中，承载编码货架、图表模板、AI 交互界面。 |
| `var/` | 运行时落盘 | `traces/` 存储 Trace JSON 以支持回放。 |
| `tmp_traces/` | 开发期调试输出 | 拆分调试阶段的 Trace 栈，便于对比离线与线上结果。 |
| `AGENTS.md` | Agent 策略草案 | 描述现有/计划中的多 Agent 协作框架 |
| `Walmart.csv` | 演示数据 | 示例数据集，未来应替换为可配置数据源 |

> 约定：一个文件夹只负责一个业务领域；新增能力务必先明确归属再落代码，README 必须同步更新。

## 核心流程（状态图视角）

1. **Intent 捕获**：UI 或自然语言请求派发 `task/submit`，后端记录 Trace Root。
2. **Data Scan**：触发 `/api/data/scan` 生成字段知识包（Profile、采样、分布）。
3. **Plan Refine**：调用规划 Agent，输出字段映射、模板候选、转换草案、解释提纲。
4. **Transform Execute / Aggregate Bin**：执行数据派生，产出样本、指标、日志与 SLO。
5. **Chart Recommend / Natural Edit**：模板 + 映射生成 `ChartSpec`，自然语言继续迭代。
6. **Explain Agent**：以“数据摘要 + 代码 + 结果”为输入，输出短 Markdown。
7. **Task Stream & Trace Replay**：`TaskRunner` 挂载 SSE，推送节点完成事件，并将 Trace 树持久化到 `TraceStore` 以支持回放。

## 工程现状

- **前端技术债**：`apps/frontend/src` 仍以 JS 为主，需迁移至 TS + Redux Toolkit，并建立统一的 `ChartSpec` 适配层与事件总线。
- **后端骨架**：已落地 FastAPI `/api/data/scan`、`/api/plan/refine`、`/api/trace/*`、`/api/task/*`，并完成 Scan → Plan → Transform → Chart → Explain 编排；`/api/transform/*` 等细分接口、OpenTelemetry 与 SLO Dashboard 尚缺。
- **任务编排**：`TaskRunner` 将 `execute_pipeline` 以线程池方式异步执行，并通过 SSE 推送节点级事件；缺少失败重试、超时治理和节点级日志清理，需要在后续迭代补齐。
- **知识库建设**：新增内存级 `DatasetStore` 与字段 Top-K 摘要，下阶段需引入持久化、分箱策略与缓存淘汰。
- **状态同步**：`replaceChart` 等事件总线尚未统一，需在 Redux 层收口并打通前后端 Trace 标识。

## 快速开始

### 克隆项目

```bash
git clone https://github.com/wlvh/data_interface.git
cd data_interface
```

### 前端演示

```bash
cd apps/frontend
npm install
npm run dev
```

访问 `http://localhost:3000` 体验现有功能。

### 契约校验

```bash
cd apps/backend
pytest
```

未来新增 API/Agent 时，请在对应目录建立模块级 README，说明输入输出契约、SLO 与回放策略。

## 开发准则

- 后端与 AI 代码统一使用 Python（UTC 时区、Pydantic 校验），前端使用 TypeScript 与 Redux Toolkit。
- 参数集中管理，函数调用必须显式传参名；禁止使用 `.get()` 之类的隐式默认。
- 类、函数必须编写 docstring，函数内关键逻辑块需带注释说明“为什么这样做”。
- 禁止裸 `try/except` 或 `if/else`；捕获需指定异常类型并记录诊断信息，异常应在当前层处理或 fail fast。
- 数据进数据出：所有模块通过 JSON/Pydantic/Typed Dict 传输，不依赖隐藏状态。
- 避免重复代码，提炼公共逻辑为模块；优先使用列表推导、生成器等 Pythonic 写法。
- 任何新增文件夹需在 README 的“目录与职责”表中登记；无法当期完成的事项写入 TODO。

## 指标与可观测性

- 每个 Agent、任务节点需定义 SLO：耗时、重试次数、失败分类。
- Trace 采用 Span 树结构，记录模型/提示版本、输入摘要、输出摘要及错误栈。
- 所有 I/O 结果必须可 JSON 序列化落盘，便于审计、A/B 与缓存复用。
