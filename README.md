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

### 后端（`apps/backend`）

| 路径 | 责任焦点 | 关键说明 |
| --- | --- | --- |
| `apps/backend/api/` | HTTP 接入与契约 | `app.py` 构建 FastAPI 应用；`routes.py` 汇集扫描、计划、变换、图表、任务、Trace 等端点并统一落盘审计；`dependencies.py` 管理依赖注入；`schemas.py` 定义所有请求/响应模型，保证 Pydantic 校验一致。 |
| `apps/backend/agents/` | 原子智能能力 | 各 Agent 模块封装扫描、计划细化、变换执行、图表推荐、解释生成等能力，`base.py` 提供统一的 `Agent`/`AgentOutcome` 协议，并暴露 `AgentContext` 以承载 Trace 与任务信息。 |
| `apps/backend/services/` | 流程编排与任务运行时 | `orchestrator.py` 实现 `StateMachineOrchestrator`，以状态图顺序驱动多 Agent；`pipeline.py` 定义 `PipelineConfig/Agents/Outcome` 以及 `execute_pipeline` 主流程；`task_runner.py` 提供异步线程池调度与 SSE 发布，向 `/api/task/*` 提供快照能力。 |
| `apps/backend/stores/` | 运行时缓存层 | `DatasetStore` 与 `TraceStore` 提供内存态缓存/回放入口，负责 Fail Fast 的读取与写入，后续可扩展至持久化后端。 |
| `apps/backend/infra/` | 横切基础设施 | `clock.py` 提供 UTC 时钟抽象；`persistence.py` 封装 `ApiRecorder` 的落盘策略；`tracing.py` 定义 `TraceRecorder`，负责 Span 聚合与 Trace 重建。 |
| `apps/backend/compat/` | Pydantic 兼容层 | 统一封装 `BaseModel`、`ConfigDict`、`model_validator`，屏蔽 v1/v2 差异，确保契约在不同运行环境下保持一致。 |
| `apps/backend/contracts/` | 领域契约 | 定义 `DatasetProfile`、`Plan`、`Transform`、`TraceRecord`、`ChartSpec` 等核心模型；`schema/` 内存放对应 JSONSchema 导出处，供前后端和外部系统复用。 |
| `apps/backend/tests/` | 自动化保障 | 覆盖 API Recorder、Schema 导出、状态图编排、Pipeline 执行与 Trace 回放等关键路径，保证契约与流程不回退。 |

### 前端（`apps/frontend`）

| 路径 | 责任焦点 | 关键说明 |
| --- | --- | --- |
| `apps/frontend/src/main.js` | 客户端入口 | Vite 启动脚本，待迁移至 TypeScript，同时挂载全局状态管理与调试工具。 |
| `apps/frontend/src/contract/` | 前端契约镜像 | 临时维护前端对后端契约的 JS 版本（如 `schema.js`），后续将由自动生成流程替换。 |
| `apps/frontend/src/runtime/` | 客户端运行时工具 | `dataProcessor.js` 等文件负责把后端 `ChartSpec`、`PreparedTable` 加工为前端可渲染结构，未来会接入统一的事件总线。 |
| `apps/frontend/src/ui/` | UI 组件占位 | 预留交互组件与模板库目录，目前为迁移准备阶段。 |
| `apps/frontend/public/` | 静态资源 | favicon、开放路由静态文件等。 |

### 根目录与运行资产

| 路径 | 责任焦点 | 关键说明 |
| --- | --- | --- |
| `var/` | 运行期落盘 | `api_logs/` 保存每次 API 进/出参；`traces/` 存储任务 Trace JSON；`uv-cache/` 用于 uv 依赖缓存，便于离线开发。 |
| `tmp_traces/` | 调试 Trace 输出 | 供开发过程对比本地与线上 Span 链路，随时可清理但须注意版本差异。 |
| `Walmart.csv` | 演示数据源 | 默认演示数据集，真实部署时需替换为多源配置或接入数据仓库。 |
| `AGENTS.md` | Agent 设计蓝图 | 记录现有与规划中的多 Agent 协作策略及 Prompt 约束，是提交新 Agent 的必读文档。 |
| `requirements.txt` | Python 依赖锁定 | 配合 `uv` 管理器，确保 `.venv`（CPython 3.13.5）环境一致。 |
| `tmp_runner.*` / `tmp_sample.csv` / `tmp_runner.log` | 本地实验产物 | 线程池执行、采样脚本的临时输出，便于追踪数据漂移或压测记录，清理前需确认是否进入审计体系。 |

> 约定：新增模块前先定位所属目录并更新此表；若职责存在跨域依赖，必须同步补充 `AGENTS.md` 或根目录 TODO，避免架构漂移。

## 核心流程（状态图视角）

1. **Intent 捕获**：UI 或自然语言请求派发 `task/submit`，后端记录 Trace Root。
2. **Data Scan**：触发 `/api/data/scan` 生成字段知识包（Profile、采样、分布）。
3. **Plan Refine**：调用规划 Agent，输出字段映射、模板候选、转换草案、解释提纲。
4. **Transform Execute / Aggregate Bin**：执行数据派生，产出样本、指标、日志与 SLO。
5. **Chart Recommend / Natural Edit**：模板 + 映射生成 `ChartSpec`，自然语言继续迭代。
6. **Explain Agent**：以“数据摘要 + 代码 + 结果”为输入，输出短 Markdown。
7. **Task Stream & Trace Replay**：`TaskRunner` 推送节点事件，并将 Trace 树与 API 进出参落盘，便于离线回放。


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

### API 回放与审计

- **落盘路径**：所有 FastAPI 请求/响应会写入 `var/api_logs/<endpoint>/`，文件名为 UTC 时间戳（例如 `20250101T010203456789Z_request.json` 与 `..._response.json`）。
- **回放步骤**：
  1. 读取 `*_request.json`，作为请求体重新调用对应接口；
  2. 获取最新响应，与 `*_response.json` 对比（结构与数据）；
  3. 若需还原整条链路，可结合 `var/traces/<task_id>.json` 与 `apps/backend/tests/test_pipeline.py`，复现 Span 序列。

> 注意：所有落盘文件默认使用 UTF-8 编码，确保在版本控制与归档时保持一致。

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
