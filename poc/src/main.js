/**
 * 主应用入口
 */

import { dataProcessor } from './runtime/dataProcessor.js';
import { chartManager } from './runtime/charts/chartManager.js';
import { paramManager } from './runtime/params/manager.js';
import { ParameterPanel } from './ui/panels/parameterPanel.js';
import { runSlot } from './runtime/worker/sandbox.js';

class DataInterfaceApp {
  constructor() {
    this.data = null;
    this.latestDataByStore = new Map(); // 缓存每个门店的最新数据
    this.latestDate = null; // 缓存最新日期
    this.paramPanel = null;
    this.isInitialized = false;
  }

  /**
   * 初始化应用
   */
  async init() {
    try {
      console.log('初始化数据接口应用...');

      // 加载数据
      await this.loadData();

      // 初始化UI
      this.initUI();

      // 初始化图表
      this.initCharts();

      // 绑定事件
      this.bindEvents();

      this.isInitialized = true;
      console.log('应用初始化完成');

      // 初始更新
      this.updateAllCharts();

    } catch (error) {
      console.error('应用初始化失败:', error);
      this.showError(error.message);
    }
  }

  /**
   * 加载数据
   */
  async loadData() {
    try {
      // 加载CSV文件
      const response = await fetch('/Walmart.csv');
      const csvText = await response.text();

      // 使用dataProcessor处理数据
      this.data = await dataProcessor.loadData(csvText);

      console.log(`加载了 ${this.data.length} 条数据记录`);

      // 数据加载后，立即预处理以备后用
      this.prepareLatestData();

    } catch (error) {
      throw new Error(`数据加载失败: ${error.message}`);
    }
  }

  /**
   * 预处理数据，找出每个门店的最新记录
   */
  prepareLatestData() {
    // 找出全局最新日期
    const dates = this.data.map(d => d.dateObj);
    this.latestDate = new Date(Math.max(...dates));

    // 缓存每个门店的最新数据（跳过前面窗口不足的周）
    this.latestDataByStore.clear();

    for (const row of this.data) {
      // 跳过太早的数据（前26周用于滚动窗口计算）
      const weeksDiff = Math.floor((this.latestDate - row.dateObj) / (7 * 24 * 60 * 60 * 1000));
      if (weeksDiff > 26) continue;

      if (!this.latestDataByStore.has(row.store) ||
          row.dateObj > this.latestDataByStore.get(row.store).dateObj) {
        this.latestDataByStore.set(row.store, row);
      }
    }

    console.log(`预处理完成: ${this.latestDataByStore.size} 个门店的最新数据已缓存`);
  }

  /**
   * 初始化UI
   */
  initUI() {
    // 初始化参数面板
    this.paramPanel = new ParameterPanel('param-panel');
    this.paramPanel.init();

    // 设置导出按钮
    const exportBtn = document.getElementById('export-btn');
    if (exportBtn) {
      exportBtn.addEventListener('click', () => this.exportSnapshot());
    }

    // 设置导入按钮
    const importBtn = document.getElementById('import-btn');
    if (importBtn) {
      importBtn.addEventListener('click', () => this.importSnapshot());
    }
  }

  /**
   * 初始化图表
   */
  initCharts() {
    // 任务一：活跃度图表
    chartManager.initChart('activity-chart', 'activity');

    // 任务三：散点图
    chartManager.initChart('scatter-chart', 'scatter');
  }

  /**
   * 绑定事件
   */
  bindEvents() {
    // 监听参数变化
    window.addEventListener('parametersChanged', (event) => {
      const changedPath = event.detail?.changedPath || event.detail?.selectId;
      // 如果时间窗口参数改变，需要重新计算特征
      if (changedPath && changedPath.startsWith('timeWindow')) {
        this.recomputeAndUpdate();
      } else {
        this.updateAllCharts();
      }
    });

    // chartManager已经有自己的onSelectionChange实现，不需要覆盖
  }

  /**
   * 重新计算特征并更新图表
   */
  async recomputeAndUpdate() {
    try {
      // 显示加载状态
      const loadingMsg = document.createElement('div');
      loadingMsg.id = 'recomputing-msg';
      loadingMsg.innerHTML = '正在重新计算特征...';
      loadingMsg.style.cssText = 'position: fixed; top: 10px; right: 10px; background: #fff; padding: 10px; border: 1px solid #ccc; z-index: 1000;';
      document.body.appendChild(loadingMsg);

      // 重新计算特征（会读取最新的窗口参数）
      await dataProcessor.calculateFeatures();

      // 重新预处理数据缓存
      this.prepareLatestData();

      // 更新图表
      this.updateAllCharts();

      // 移除加载状态
      document.body.removeChild(loadingMsg);
    } catch (error) {
      console.error('特征重算失败:', error);
      this.showError('特征重算失败: ' + error.message);
    }
  }

  /**
   * 更新所有图表
   */
  updateAllCharts() {
    const weights = paramManager.get('weights');
    const timeWindow = paramManager.get('timeWindow');
    const scatterConfig = paramManager.get('scatter');

    // 更新活跃度图表
    this.updateActivityChart(weights, timeWindow);

    // 更新散点图
    this.updateScatterChart(scatterConfig);
  }

  /**
   * 更新活跃度图表
   */
  updateActivityChart(weights, timeWindow) {
    // 直接从缓存中获取每个门店的最新数据
    const storeData = Array.from(this.latestDataByStore.values());

    // 分析特征可用性，决定剔除策略
    const { featureNAStats, excludeFeatures } = dataProcessor.analyzeFeatureAvailability(storeData, weights);

    // 计算每个门店的活跃度评分（使用智能NA处理）
    let scoredData = storeData.map(store => ({
      ...store,
      activity: dataProcessor.calculateActivityScore(store, weights, excludeFeatures)
    }));

    // 如果超过30%的门店评分为null，说明数据质量问题严重
    const nullCount = scoredData.filter(s => s.activity === null).length;
    const nullRatio = nullCount / scoredData.length;

    if (nullRatio > 0.3) {
      console.warn(`警告：${(nullRatio * 100).toFixed(1)}%的门店无法计算活跃度评分`);
      // 只保留有效评分的门店
      scoredData = scoredData.filter(s => s.activity !== null);
    }

    // 更新图表
    chartManager.updateActivityChart('activity-chart', scoredData, weights);
  }

  /**
   * 更新散点图
   */
  updateScatterChart(config) {
    // 使用原始数据
    const scatterData = this.data.filter(d => {
      // 可以添加过滤条件
      return true;
    });

    // 更新图表
    chartManager.updateScatterChart(
      'scatter-chart',
      scatterData,
      config.xField,
      'weeklySales',
      config.colorField
    );
  }

  /**
   * 获取最新周数据（使用缓存）
   */
  getLatestWeekData() {
    if (!this.latestDate) return [];

    // 获取最新周的数据
    return this.data.filter(d => {
      const diff = Math.abs(d.dateObj - this.latestDate);
      return diff < 7 * 24 * 60 * 60 * 1000; // 一周内
    });
  }

  // 以下两个方法已移至chartManager.js，这里保留为空避免调用错误
  /**
   * 处理选择变化（已废弃，功能移至chartManager.js）
   */
  async handleSelectionChange_deprecated(selectedPoints) {
    if (selectedPoints.length === 0) {
      document.getElementById('aggregate-card').style.display = 'none';
      return;
    }

    // 使用Worker槽位计算聚合统计
    const aggregateCode = `
      const values = input.points.map(p => p.weeklySales || p.value[1]);
      const count = input.points.length;
      const sum = utils.sum(values);
      const mean = utils.mean(values);
      const median = utils.median(values);
      const stdev = utils.stdev(values);

      // 计算占比（基于筛选后的总和）
      const share = params.totalSum > 0 ? sum / params.totalSum : 0;

      // 计算局部斜率（样本充足才计算）
      let slope = null;
      if (count >= 5) {
        const xValues = input.points.map(p => p[params.xField] || p.value[0]);
        const meanX = utils.mean(xValues);
        const meanY = mean;
        let numerator = 0;
        let denominator = 0;

        for (let i = 0; i < count; i++) {
          numerator += (xValues[i] - meanX) * (values[i] - meanY);
          denominator += (xValues[i] - meanX) * (xValues[i] - meanX);
        }

        slope = denominator === 0 ? 0 : numerator / denominator;
      }

      return {
        count,
        sum,
        mean,
        median,
        stdev,
        share,
        slope
      };
    `;

    try {
      // 获取当前筛选上下文的总和（使用散点图当前显示的数据）
      const totalSum = chartManager.getScatterTotalSum('scatter-chart');
      const xField = paramManager.get('scatter.xField');

      const result = await runSlot(
        'aggregate',
        aggregateCode,
        { points: selectedPoints },
        { totalSum, xField },
        {
          timeout: 1000,
          outputSchema: {
            type: 'object',
            properties: {
              count: {},
              sum: {},
              mean: {},
              median: {},
              stdev: {},
              share: {},
              slope: { optional: true }
            }
          }
        }
      );

      if (result.ok) {
        this.displayAggregateCard_deprecated(result.data);
      } else {
        console.error('聚合计算失败:', result.error);
      }
    } catch (error) {
      console.error('Worker执行失败:', error);
    }
  }

  /**
   * 显示聚合卡片（已废弃，功能移至chartManager.js）
   */
  displayAggregateCard_deprecated(stats) {
    const card = document.getElementById('aggregate-card');
    if (!card) return;

    const formatNumber = (num) => new Intl.NumberFormat('en-US').format(Math.round(num));

    card.innerHTML = `
      <div class="card-header">
        <h4>选中区域统计</h4>
      </div>
      <div class="card-body">
        <div class="stat-row">
          <span class="stat-label">数量:</span>
          <span class="stat-value">${stats.count}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">总和:</span>
          <span class="stat-value">$${formatNumber(stats.sum)}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">均值:</span>
          <span class="stat-value">$${formatNumber(stats.mean)}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">中位数:</span>
          <span class="stat-value">$${formatNumber(stats.median)}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">标准差:</span>
          <span class="stat-value">${formatNumber(stats.stdev)}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">占比:</span>
          <span class="stat-value">${(stats.share * 100).toFixed(2)}%</span>
        </div>
        ${stats.slope !== null ? `
        <div class="stat-row">
          <span class="stat-label">局部斜率:</span>
          <span class="stat-value">${stats.slope.toFixed(2)}</span>
        </div>
        ` : ''}
      </div>
    `;

    card.style.display = 'block';
  }

  /**
   * 导出快照
   */
  exportSnapshot() {
    const snapshot = {
      version: '1.0.0',
      timestamp: Date.UTC(2025, 8, 13, 12, 0, 0),
      params: paramManager.getSnapshot(),
      contractHash: this.generateHash(JSON.stringify(this.data.slice(0, 10))),
      dataHash: this.generateHash(JSON.stringify(this.data.length))
    };

    const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = `data-interface-snapshot-${Date.now()}.json`;
    a.click();

    URL.revokeObjectURL(url);

    console.log('快照已导出');
  }

  /**
   * 导入快照
   */
  importSnapshot() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';

    input.onchange = async (event) => {
      const file = event.target.files[0];
      if (!file) return;

      try {
        const text = await file.text();
        const snapshot = JSON.parse(text);

        // 恢复参数
        paramManager.restoreSnapshot(snapshot.params);

        // 重新初始化UI
        this.paramPanel.render();
        this.paramPanel.attachEventListeners();

        // 更新图表
        this.updateAllCharts();

        console.log('快照已导入');
      } catch (error) {
        console.error('导入失败:', error);
        this.showError('快照导入失败: ' + error.message);
      }
    };

    input.click();
  }

  /**
   * 生成哈希
   */
  generateHash(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return hash.toString(16);
  }

  /**
   * 显示错误
   */
  showError(message) {
    const errorCard = document.getElementById('error-card');
    if (errorCard) {
      errorCard.innerHTML = `
        <div class="error-header">错误</div>
        <div class="error-body">${message}</div>
      `;
      errorCard.style.display = 'block';

      setTimeout(() => {
        errorCard.style.display = 'none';
      }, 5000);
    } else {
      alert(message);
    }
  }
}

// 启动应用
document.addEventListener('DOMContentLoaded', () => {
  const app = new DataInterfaceApp();
  app.init();
});