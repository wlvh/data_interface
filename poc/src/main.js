/**
 * 主应用入口
 */

import { dataProcessor } from './runtime/dataProcessor.js';
import { chartManager } from './runtime/charts/chartManager.js';
import { paramManager } from './runtime/params/manager.js';
import { ParameterPanel } from './ui/panels/parameterPanel.js';
import Papa from 'papaparse';

class DataInterfaceApp {
  constructor() {
    this.data = null;
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

      // 获取最新一周的数据用于展示
      this.latestWeekData = this.getLatestWeekData();

    } catch (error) {
      throw new Error(`数据加载失败: ${error.message}`);
    }
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
      this.updateAllCharts();
    });

    // 监听图表选择变化
    chartManager.onSelectionChange = (selectedPoints) => {
      this.handleSelectionChange(selectedPoints);
    };
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
    // 获取最新周的门店数据
    const storeData = this.getStoreActivityData(timeWindow.weeks);

    // 计算每个门店的活跃度评分
    const scoredData = storeData.map(store => ({
      ...store,
      activity: dataProcessor.calculateActivityScore(store, weights)
    }));

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
   * 获取最新周数据
   */
  getLatestWeekData() {
    // 找出最新的日期
    const dates = this.data.map(d => d.dateObj);
    const latestDate = new Date(Math.max(...dates));

    // 获取最新周的数据
    return this.data.filter(d => {
      const diff = Math.abs(d.dateObj - latestDate);
      return diff < 7 * 24 * 60 * 60 * 1000; // 一周内
    });
  }

  /**
   * 获取门店活跃度数据
   */
  getStoreActivityData(weeks) {
    // 获取每个门店的最新数据
    const storeMap = new Map();

    // 按门店分组并获取最新记录
    for (const row of this.data) {
      if (!storeMap.has(row.store)) {
        storeMap.set(row.store, row);
      } else {
        const existing = storeMap.get(row.store);
        if (row.dateObj > existing.dateObj) {
          storeMap.set(row.store, row);
        }
      }
    }

    return Array.from(storeMap.values());
  }

  /**
   * 处理选择变化
   */
  async handleSelectionChange(selectedPoints) {
    if (selectedPoints.length === 0) {
      document.getElementById('aggregate-card').style.display = 'none';
      return;
    }

    // 计算聚合统计
    const stats = this.calculateAggregateStats(selectedPoints);

    // 显示统计卡片
    this.displayAggregateCard(stats);
  }

  /**
   * 计算聚合统计
   */
  calculateAggregateStats(points) {
    const values = points.map(p => p.weeklySales || p.value[1]);

    const sum = values.reduce((a, b) => a + b, 0);
    const mean = sum / values.length;

    const sorted = [...values].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)];

    const variance = values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length;
    const stdev = Math.sqrt(variance);

    // 计算占比
    const totalSum = this.data.reduce((sum, d) => sum + d.weeklySales, 0);
    const share = sum / totalSum;

    // 计算局部斜率（如果有足够的点）
    let slope = null;
    if (points.length >= 5) {
      const xValues = points.map(p => p[paramManager.get('scatter.xField')] || p.value[0]);
      const yValues = values;
      slope = this.calculateSlope(xValues, yValues);
    }

    return {
      count: points.length,
      sum,
      mean,
      median,
      stdev,
      share,
      slope
    };
  }

  /**
   * 计算斜率
   */
  calculateSlope(x, y) {
    const n = x.length;
    const meanX = x.reduce((a, b) => a + b, 0) / n;
    const meanY = y.reduce((a, b) => a + b, 0) / n;

    let numerator = 0;
    let denominator = 0;

    for (let i = 0; i < n; i++) {
      numerator += (x[i] - meanX) * (y[i] - meanY);
      denominator += Math.pow(x[i] - meanX, 2);
    }

    return denominator === 0 ? 0 : numerator / denominator;
  }

  /**
   * 显示聚合卡片
   */
  displayAggregateCard(stats) {
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