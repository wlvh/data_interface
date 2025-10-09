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
    this.latestDate = new Date(Math.max(...this.data.map(d => d.dateObj)));

    // 使用reduce构建最新数据缓存（跳过前26周不足数据）
    this.latestDataByStore = this.data.reduce((map, row) => {
      const weeksDiff = Math.floor((this.latestDate - row.dateObj) / (7 * 24 * 60 * 60 * 1000));
      if (weeksDiff <= 26) {
        const cached = map.get(row.store);
        if (!cached || row.dateObj > cached.dateObj) map.set(row.store, row);
      }
      return map;
    }, new Map());

    console.log(`预处理完成: ${this.latestDataByStore.size} 个门店的最新数据已缓存`);
  }

  /**
   * 初始化UI
   */
  initUI() {
    // 初始化参数面板
    this.paramPanel = new ParameterPanel('param-panel');
    this.paramPanel.init();

    // 绑定导出/导入按钮
    ['export', 'import'].forEach(action => {
      const btn = document.getElementById(`${action}-btn`);
      if (btn) btn.addEventListener('click', () => this[`${action}Snapshot`]());
    });
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
    const { params } = paramManager.getSnapshot();
    const { weights, timeWindow, scatter } = params || {};
    if (!weights || !timeWindow || !scatter) {
      throw new Error('必要参数缺失');
    }
    this.updateActivityChart(weights, timeWindow);
    this.updateScatterChart(scatter);
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