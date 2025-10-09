# Data Interface


## 项目概述

本项目是一个专注于零售数据分析的高性能可视化系统，采用模块化架构设计，实现了声明式参数管理、Web Worker安全沙箱和ECharts高性能渲染，支持多维度特征分析和实时交互。

### 🚀 前端演示系统

在 `apps/frontend/` 目录下包含了完整的生产级实现，展示了三大核心功能：

1. **门店活跃度动态权重调参** - 基于6维特征的实时评分系统（近端动量、节日提升、油价敏感度、气温敏感度、宏观适应性、稳健趋势）
2. **高级图表交互与智能提示** - ECharts驱动的柱状图和散点图，支持悬浮Sparkline展示
3. **散点圈选与即时聚合** - 支持矩形/套索选择，实时计算统计指标（均值、中位数、标准差、局部斜率）

## 快速开始

### 前端演示系统运行

```bash
# 克隆仓库
git clone https://github.com/wlvh/data_interface.git

# 进入前端目录
cd data_interface/apps/frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

访问 http://localhost:3000 查看完整演示

## 核心特性

### 技术架构

- **模块化系统设计** - 主入口(main.js) + 运行时模块(runtime/) + UI组件(ui/) + 契约系统(contract/)
- **声明式参数管理** - ParamManager统一管理所有参数，支持路径访问和事件驱动更新
- **Web Worker沙箱** - 基于Acorn的AST安全检查，隔离执行环境，5秒超时控制
- **ECharts可视化引擎** - Canvas高性能渲染，支持5万行柱状图和3万点散点图
- **智能特征工程** - 6维特征计算（滚动窗口26周），Z-score标准化，NA智能处理
- **可回放机制** - JSON快照导出/导入，UTC时间戳确保确定性

### 性能指标

- **滑块响应**: <500ms（6维权重实时更新）
- **图表渲染**: 柱状图支持5万条数据，散点图支持3万数据点
- **悬浮提示**: <16ms（单帧渲染，固定尺寸无抖动）
- **圈选聚合**: <200ms（Worker异步计算）
- **特征计算**: 滚动窗口26周，支持增量更新

### 安全机制

- **AST黑名单验证** - 禁用window/document/eval/fetch/XMLHttpRequest等危险标识符
- **语法白名单** - 仅允许安全的语句类型（变量声明、函数、循环、条件等）
- **深度数据冻结** - 输入数据使用Object.freeze防止修改
- **执行超时控制** - 默认5000ms，可配置最大10分钟
- **确定性执行** - 固定UTC时间(2025-09-13 12:00:00)，种子随机数生成器

## 项目结构

```
data_interface/
├── apps/
│   ├── backend/
│       ├── contracts/             # 通用契约模型（JSONSchema + Pydantic 镜像）
│       │   ├── chart_template.py
│       │   ├── dataset_profile.py
│       │   ├── fields.py
│       │   └── schema/*.json
│       ├── tests/                 # 契约一致性测试
│       │   └── test_contract_schemas.py
│       └── __init__.py
│   └── frontend/                # 前端演示系统
│       ├── src/
│       │   ├── main.js              # 应用主入口，协调所有模块
│       │   ├── contract/            # 契约系统
│       │   │   └── schema.js        # 数据模式定义与校验
│       │   ├── runtime/             # 运行时核心
│       │   │   ├── dataProcessor.js # 数据处理与特征工程
│       │   │   ├── params/
│       │   │   │   └── manager.js   # 参数集中管理
│       │   │   ├── worker/
│       │   │   │   ├── sandbox.js   # Worker沙箱执行器
│       │   │   │   └── slotWorker.js   # Worker线程代码
│       │   │   └── charts/
│       │   │       └── chartManager.js # ECharts管理器
│       │   └── ui/
│       │       └── panels/
│       │           └── parameterPanel.js # 参数面板UI
│       ├── public/                 # 静态资源
│       │   └── Walmart.csv         # 演示数据
│       ├── index.html              # 主页面
│       ├── package.json            # 依赖配置
│       └── vite.config.js          # Vite构建配置
├── Walmart.csv                 # 数据集（45店×143周）
└── README.md                   # 本文件
```

### 版本同步说明

- 后端契约通过自定义的轻量级 `pydantic` 兼容层生成 JSONSchema，确保在无法联网安装依赖的环境下仍能进行模型校验。
- 更新契约模型后需运行 `python apps/backend/tests/test_contract_schemas.py` 或 `pytest` 以重建 `schema/*.json` 并验证镜像一致性。

## 功能详解

### 1. 动态权重调参系统

### 2. 高级图表交互
- **ECharts柱状图** - 支持5万条数据，DataZoom缩放
- **散点图圈选** - 矩形/套索工具，Brush API实现
- **悬浮Sparkline** - 近8/13周趋势迷你图表
- **固定位置提示** - 无抖动悬浮卡片，16ms响应

### 3. 实时统计分析
- **圈选聚合** - Worker异步计算选中数据统计
- **统计指标** - count/sum/mean/median/stdev/share
- **局部斜率** - 样本>=5时计算敏感度
- **结果卡片** - 格式化数字展示，占比百分比

## 数据说明

### Walmart销售数据集（2010-2012）
- **数据规模**: 45家门店 × 143周 = 6,435条记录
- **时间跨度**: 2010-02-05 至 2012-10-26
- **核心字段**:
  - Store: 门店ID (1-45)
  - Date: 日期 (YYYY-MM-DD格式)
  - Weekly_Sales: 周销售额
  - Holiday_Flag: 节日标记 (0/1)
  - Temperature: 温度 (华氏度)
  - Fuel_Price: 油价
  - CPI: 消费者价格指数
  - Unemployment: 失业率
- **特殊日期**: Super Bowl、Valentine's Day、Labor Day、Thanksgiving、Christmas

## 开发指南

### 环境要求
- **Node.js**: 16.0+
- **npm**: 7.0+
- **浏览器**: 现代浏览器（Chrome 90+/Firefox 88+/Safari 14+）
- **依赖库**:
  - ECharts 5.5.0 (可视化)
  - D3.js (d3-array, d3-time-format等)
  - Acorn 8.15.0 (AST解析)
  - Vite 5.0.0 (开发服务器)

### 构建部署

```bash
# 生产构建
cd apps/frontend
npm run build

# 构建产物在 dist/ 目录
```
## License

MIT

## TODO

- [ ] 建立后端最小 API (`/api/data/scan`, `/api/task/submit`, `/api/task/stream`, `/api/trace/:task_id`, `/api/trace/replay`) 及扫描落盘服务，满足双落盘与回放要求。
- [ ] 引入 Redux Toolkit、RTK Query、SSE 客户端与 ChartSpec 适配层，完成前端 Store 重构与可回放视图态。
- [ ] 配置 `.pre-commit-config.yaml` 与 CI 工作流，落实契约镜像门禁与体积限制等质量门。
- [ ] 补齐安全与性能修复（UTC 全链路、圈选抽样、tooltip 贡献、图例、快照哈希、fetch 守卫、Worker 并发协议等）。
- [ ] 规划可选增强（ChartSpec 扩展、Trace 指标、FolderCard/Ingestion）并补充自动化覆盖。

