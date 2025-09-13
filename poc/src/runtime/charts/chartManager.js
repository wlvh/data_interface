/**
 * ECharts图表管理器
 */

import * as echarts from 'echarts';
import { runSlot } from '../worker/sandbox.js';
import { dataProcessor } from '../dataProcessor.js';
import { paramManager } from '../params/manager.js';

export class ChartManager {
  constructor() {
    this.charts = new Map();
    this.tooltipCache = new Map();
    this.miniChartCache = new Map();
  }

  /**
   * 初始化图表
   */
  initChart(containerId, type, options = {}) {
    const container = document.getElementById(containerId);
    if (!container) {
      console.error(`Container ${containerId} not found`);
      return null;
    }

    // 销毁已存在的图表
    if (this.charts.has(containerId)) {
      this.charts.get(containerId).dispose();
    }

    // 创建新图表
    const chart = echarts.init(container);
    this.charts.set(containerId, chart);

    // 根据类型设置默认配置
    const config = this.getChartConfig(type, options);
    chart.setOption(config);

    // 自适应
    window.addEventListener('resize', () => chart.resize());

    return chart;
  }

  /**
   * 获取图表配置
   */
  getChartConfig(type, options) {
    const configs = {
      // 任务一：活跃度柱状图
      activity: {
        title: {
          text: '门店活跃度评分',
          left: 'center'
        },
        tooltip: {
          trigger: 'axis',
          formatter: (params) => this.formatActivityTooltip(params),
          position: function (point, params, dom, rect, size) {
            // 固定宽高，避免抖动
            return [point[0] - size.contentSize[0] / 2, '10%'];
          }
        },
        xAxis: {
          type: 'category',
          data: [],
          axisLabel: {
            rotate: 45
          }
        },
        yAxis: {
          type: 'value',
          name: '活跃度评分'
        },
        series: [{
          name: '活跃度',
          type: 'bar',
          data: [],
          itemStyle: {
            color: (params) => this.getActivityColor(params.value)
          }
        }],
        dataZoom: [{
          type: 'slider',
          show: true,
          start: 0,
          end: 100
        }]
      },

      // 任务三：散点图
      scatter: {
        title: {
          text: '销售数据散点图',
          left: 'center'
        },
        tooltip: {
          trigger: 'item',
          formatter: (params) => this.formatScatterTooltip(params),
          position: 'top'
        },
        xAxis: {
          type: 'value',
          name: options.xLabel || 'X轴'
        },
        yAxis: {
          type: 'value',
          name: options.yLabel || '周销售额'
        },
        series: [{
          name: '销售数据',
          type: 'scatter',
          data: [],
          symbolSize: 8,
          itemStyle: {
            opacity: 0.8
          }
        }],
        brush: {
          toolbox: ['rect', 'polygon', 'clear'],
          xAxisIndex: 0,
          yAxisIndex: 0
        },
        toolbox: {
          feature: {
            brush: {
              type: ['rect', 'polygon', 'clear']
            }
          }
        }
      },

      // 迷你折线图（用于tooltip）
      sparkline: {
        grid: {
          top: 5,
          right: 5,
          bottom: 5,
          left: 5
        },
        xAxis: {
          type: 'category',
          show: false,
          data: []
        },
        yAxis: {
          type: 'value',
          show: false
        },
        series: [{
          type: 'line',
          data: [],
          smooth: true,
          showSymbol: false,
          lineStyle: {
            width: 1,
            color: '#5470c6'
          },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [{
                offset: 0,
                color: 'rgba(84, 112, 198, 0.3)'
              }, {
                offset: 1,
                color: 'rgba(84, 112, 198, 0.05)'
              }]
            }
          },
          markPoint: {
            data: []
          }
        }]
      }
    };

    return { ...configs[type], ...options };
  }

  /**
   * 更新活跃度图表
   */
  updateActivityChart(chartId, data, weights) {
    const chart = this.charts.get(chartId);
    if (!chart) return;

    // 保留null值，标记NA状态
    const scored = data.map(store => ({
      ...store,
      activity: store.activity,
      isNA: store.activity === null
    }));

    // 排序：NA值放到最后
    scored.sort((a, b) => {
      if (a.isNA && b.isNA) return 0;
      if (a.isNA) return 1;
      if (b.isNA) return -1;
      return b.activity - a.activity;
    });

    // 计算分位数颜色（只基于非NA值）
    const validActivities = scored.filter(s => !s.isNA).map(s => s.activity);
    const q25 = validActivities.length > 0 ? this.quantile(validActivities, 0.25) : 0;
    const q50 = validActivities.length > 0 ? this.quantile(validActivities, 0.5) : 0;
    const q75 = validActivities.length > 0 ? this.quantile(validActivities, 0.75) : 0;

    // 更新图表
    chart.setOption({
      xAxis: {
        data: scored.map(s => `Store ${s.store}`)
      },
      series: [{
        data: scored.map(s => ({
          value: s.isNA ? null : s.activity,
          itemStyle: {
            color: s.isNA ? '#cccccc' : this.getQuantileColor(s.activity, q25, q50, q75)
          },
          store: s.store,
          features: s.features,
          isNA: s.isNA
        }))
      }]
    });
  }

  /**
   * 更新散点图
   */
  updateScatterChart(chartId, data, xField, yField, colorField) {
    const chart = this.charts.get(chartId);
    if (!chart) return;

    // 准备数据
    const scatterData = data.map(d => ({
      value: [d[xField], d[yField]],
      ...d
    }));

    // 颜色映射
    const colorMap = this.createColorMap(data, colorField);

    // 更新图表
    chart.setOption({
      xAxis: {
        name: this.getFieldLabel(xField)
      },
      yAxis: {
        name: this.getFieldLabel(yField)
      },
      series: [{
        data: scatterData,
        itemStyle: {
          color: (params) => colorMap.get(params.data[colorField])
        }
      }]
    });

    // 监听圈选事件
    chart.on('brushEnd', (params) => {
      if (params.areas && params.areas.length > 0) {
        this.handleBrushSelection(chartId, params.areas[0].coordRange);
      }
    });
  }

  /**
   * 处理圈选
   */
  handleBrushSelection(chartId, range) {
    const chart = this.charts.get(chartId);
    if (!chart) return;

    const option = chart.getOption();
    const data = option.series[0].data;

    // 找出选中的点
    const selected = data.filter(d => {
      const x = d.value[0];
      const y = d.value[1];
      return x >= range[0][0] && x <= range[1][0] &&
        y >= range[0][1] && y <= range[1][1];
    });

    // 触发聚合计算
    this.onSelectionChange(selected);
  }

  /**
   * 选择变化回调
   */
  async onSelectionChange(selectedPoints) {
    if (selectedPoints.length === 0) return;

    // 调用聚合函数槽位
    const aggregateCode = `
      const count = input.points.length;
      const values = input.points.map(p => p.value[1]);
      const sum = utils.sum(values);
      const mean = utils.mean(values);
      const median = utils.median(values);
      const stdev = utils.stdev(values);

      // 计算占比
      const share = params.totalSum > 0 ? sum / params.totalSum : 0;

      // 计算局部斜率（样本充足才给）
      let slope = null;
      if (count >= 5) {
        const x = input.points.map(p => p.value[0]);
        const mx = utils.mean(x);
        const my = mean;
        let num = 0, den = 0;
        for (let i = 0; i < count; i++) {
          num += (x[i] - mx) * (values[i] - my);
          den += (x[i] - mx) * (x[i] - mx);
        }
        slope = den === 0 ? 0 : num / den;
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

    // 获取正确的分母
    const total = this.getScatterTotalSum();

    const result = await runSlot(
      'aggregate',
      aggregateCode,
      { points: selectedPoints },
      { totalSum: total },
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
      this.displayAggregateCard(result.data);
    }
  }

  /**
   * 显示聚合卡片
   */
  displayAggregateCard(stats) {
    const card = document.getElementById('aggregate-card');
    if (!card) return;

    card.innerHTML = `
      <div class="card-header">选中区域统计</div>
      <div class="card-body">
        <div class="stat-item">
          <span class="stat-label">数量:</span>
          <span class="stat-value">${stats.count}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">总和:</span>
          <span class="stat-value">${this.formatNumber(stats.sum)}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">均值:</span>
          <span class="stat-value">${this.formatNumber(stats.mean)}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">中位数:</span>
          <span class="stat-value">${this.formatNumber(stats.median)}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">标准差:</span>
          <span class="stat-value">${this.formatNumber(stats.stdev)}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">占比:</span>
          <span class="stat-value">${(stats.share * 100).toFixed(2)}%</span>
        </div>
        ${stats.slope !== null ? `
        <div class="stat-item">
          <span class="stat-label">局部斜率:</span>
          <span class="stat-value">${stats.slope.toFixed(2)}</span>
        </div>
        ` : ''}
      </div>
    `;

    card.style.display = 'block';
  }

  /**
   * 格式化活跃度tooltip
   */
  async formatActivityTooltip(params) {
    const data = params[0].data;

    // 检查缓存
    const cacheKey = `activity_${data.store}_${data.isNA}`;
    if (this.tooltipCache.has(cacheKey)) {
      return this.tooltipCache.get(cacheKey);
    }

    // 构建tooltip内容
    let html = `
      <div style="padding: 10px; min-width: 250px;">
        <div style="font-weight: bold; margin-bottom: 8px;">
          Store ${data.store}
        </div>
    `;

    if (data.isNA) {
      html += `
        <div style="color: #999;">活跃度评分: 不可用</div>
        <div style="margin-top: 8px; font-size: 12px; color: #999;">
          原因：存在NA特征值（数据不足）
        </div>
      `;
    } else {
      html += `
        <div>活跃度评分: ${data.value.toFixed(3)}</div>
        <div style="margin-top: 8px; font-size: 12px;">
          <div>贡献分解:</div>
      `;

    if (data.features) {
      const weights = paramManager.get('weights');
      const contributions = [
        { name: '近端动量', value: data.features.momentum, weight: weights.momentum },
        { name: '节日效应', value: data.features.holidayLift, weight: weights.holiday },
        { name: '油价敏感度(-)', value: data.features.fuelSensitivity === null ? null : 1 - Math.abs(data.features.fuelSensitivity), weight: weights.fuel },
        { name: '气温敏感度(-)', value: data.features.tempSensitivity === null ? null : 1 - Math.abs(data.features.tempSensitivity), weight: weights.temperature },
        { name: '宏观敏感度(1-z)', value: data.features.macroAdaptation === null ? null : 1 - data.features.macroAdaptation, weight: weights.macro },
        { name: '稳健趋势', value: data.features.trend, weight: weights.trend }
      ];

      contributions.forEach(c => {
        if (c.value === null) {
          html += `
            <div style="display: flex; justify-content: space-between; margin: 2px 0;">
              <span>${c.name}:</span>
              <span style="color: #999">N/A</span>
            </div>
          `;
        } else {
          const weightedValue = c.weight * c.value;
          const color = weightedValue > 0 ? '#5470c6' : '#ee6666';
          html += `
            <div style="display: flex; justify-content: space-between; margin: 2px 0;">
              <span>${c.name}:</span>
              <span style="color: ${color}">${weightedValue.toFixed(3)}</span>
            </div>
          `;
        }
      });
    }
    }

    html += `
      </div>
    `;

    // 缓存结果
    this.tooltipCache.set(cacheKey, html);

    return html;
  }

  /**
   * 格式化散点tooltip
   */
  async formatScatterTooltip(params) {
    const data = params.data;

    // 计算Share_t（当周该店销售额占当前视图中同一周可见点的总销售额比例）
    const weekTotal = this.getWeekTotalSumInCurrentView(data.year, data.week, 'scatter-chart');
    const share = weekTotal > 0 ? (data.weeklySales / weekTotal * 100).toFixed(2) : 0;

    // 计算WoW（基于ISO年-周）
    const prevWeekData = (() => {
      let y = data.year, w = data.week;
      if (w > 1) {
        w -= 1;
      } else {
        // 跨年：找上一年的最后一周
        y -= 1;
        // ISO周年的最后一周通常是52或53
        const lastWeekDate = new Date(Date.UTC(y, 11, 28)); // 12月28日肯定在最后一周
        w = dataProcessor.getISOWeek(lastWeekDate);
      }
      return dataProcessor.rawData.find(r => r.store === data.store && r.year === y && r.week === w);
    })();

    // 计算YoY
    const prevYearData = dataProcessor.rawData.find(r =>
      r.store === data.store &&
      r.year === data.year - 1 &&
      r.week === data.week
    );

    const wow = prevWeekData ? ((data.weeklySales - prevWeekData.weeklySales) / prevWeekData.weeklySales * 100).toFixed(1) : null;
    const yoy = prevYearData ? ((data.weeklySales - prevYearData.weeklySales) / prevYearData.weeklySales * 100).toFixed(1) : null;

    // 获取迷你图数据
    const miniSeriesHtml = await this.createMiniSparkline(data);

    // 判断节日标记（节日本周+前一周）
    const holidayMark = data.holidayFlag || data.isHolidayWeek || data.isPreHolidayWeek;

    const html = `
      <div style="padding: 10px; min-width: 300px;">
        <div style="font-weight: bold;">Store ${data.store} - Week ${data.weekOfYear}</div>
        <div>销售额: ${this.formatNumber(data.weeklySales)}</div>
        <div>占比(Share_t): ${share}%</div>
        ${wow !== null ? `<div>周环比(WoW): ${wow > 0 ? '+' : ''}${wow}%</div>` : ''}
        ${yoy !== null ? `<div>年同比(YoY): ${yoy > 0 ? '+' : ''}${yoy}%</div>` : ''}
        <div style="margin-top: 5px;">
          <div>温度: ${data.temperature}°F</div>
          <div>油价: $${data.fuelPrice}</div>
        </div>
        ${holidayMark ? '<div style="color: #ff6b6b; margin-top: 5px;">🎄 节日周</div>' : ''}
        <div style="margin-top: 10px;">
          <div style="font-size: 12px; color: #666;">近8周趋势:</div>
          ${miniSeriesHtml}
        </div>
      </div>
    `;

    return html;
  }

  /**
   * 创建迷你sparkline（图片模式）
   */
  async createMiniSparkline(data) {
    const N = paramManager.get('display.tooltipWeeks') || 8;
    const cacheKey = `spark_${data.store}_${data.date}_${N}`;

    if (this.miniChartCache.has(cacheKey)) {
      return this.miniChartCache.get(cacheKey);
    }

    // 创建迷你图容器
    const container = document.createElement('div');
    container.style.width = '280px';
    container.style.height = '60px';
    container.style.position = 'absolute';
    container.style.left = '-9999px';
    document.body.appendChild(container);

    try {
      // 获取真实数据
      const recentData = dataProcessor.getStoreRecentWeeks(data.store, data.date, N);

      if (recentData.length > 0) {
        const miniChart = echarts.init(container);

        miniChart.setOption({
          grid: {
            top: 5,
            right: 5,
            bottom: 5,
            left: 5
          },
          xAxis: {
            type: 'category',
            show: false,
            data: recentData.map((_, i) => i)
          },
          yAxis: {
            type: 'value',
            show: false
          },
          series: [{
            type: 'line',
            data: recentData.map(d => d.weeklySales),
            smooth: true,
            showSymbol: false,
            lineStyle: {
              width: 1.5,
              color: '#5470c6'
            },
            areaStyle: {
              color: 'rgba(84, 112, 198, 0.15)'
            },
            markPoint: {
              symbol: 'circle',
              symbolSize: 4,
              data: recentData
                .map((d, i) => (d.holidayFlag || d.isHolidayWeek || d.isPreHolidayWeek) ? { coord: [i, d.weeklySales] } : null)
                .filter(d => d !== null)
            }
          }]
        });

        // 导出为图片
        const url = miniChart.getDataURL({
          pixelRatio: 2,
          backgroundColor: '#fff'
        });
        miniChart.dispose();

        const html = `<img src="${url}" width="280" height="60" alt="sparkline"/>`;
        this.miniChartCache.set(cacheKey, html);
        return html;
      }
    } finally {
      // 清理容器
      document.body.removeChild(container);
    }

    return '<div style="color: #999;">无历史数据</div>';
  }

  // 辅助函数
  getActivityColor(value) {
    const colors = ['#ee6666', '#fac858', '#91cc75', '#5470c6'];
    if (value < -0.5) return colors[0];
    if (value < 0) return colors[1];
    if (value < 0.5) return colors[2];
    return colors[3];
  }

  getQuantileColor(value, q25, q50, q75) {
    if (value < q25) return '#ee6666';
    if (value < q50) return '#fac858';
    if (value < q75) return '#91cc75';
    return '#5470c6';
  }

  quantile(arr, q) {
    const sorted = [...arr].sort((a, b) => a - b);
    const index = q * (sorted.length - 1);
    const lower = Math.floor(index);
    const upper = Math.ceil(index);
    const weight = index % 1;
    return sorted[lower] * (1 - weight) + sorted[upper] * weight;
  }

  getFieldLabel(field) {
    const labels = {
      temperature: '温度 (°F)',
      fuelPrice: '油价 ($)',
      weekOfYear: '周数',
      weeklySales: '周销售额',
      cpi: 'CPI',
      unemployment: '失业率 (%)'
    };
    return labels[field] || field;
  }

  createColorMap(data, field) {
    const uniqueValues = [...new Set(data.map(d => d[field]))];
    const colors = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272'];
    const map = new Map();

    uniqueValues.forEach((val, i) => {
      map.set(val, colors[i % colors.length]);
    });

    return map;
  }

  formatNumber(num) {
    return new Intl.NumberFormat('en-US').format(Math.round(num));
  }

  /**
   * 获取散点图总和（当前上下文）
   */
  getScatterTotalSum(chartId = 'scatter-chart') {
    const chart = this.charts.get(chartId);
    if (!chart) return 0;

    const option = chart.getOption();
    const data = (option.series?.[0]?.data) || [];
    return data.reduce((s, d) => s + (d.value?.[1] ?? d.weeklySales ?? 0), 0);
  }

  /**
   * 获取当前周总和（用于占比计算）
   */
  getCurrentWeekTotalSum(date) {
    // 从预聚合表获取
    const row = dataProcessor.rawData.find(r => r.date === date);
    if (!row) return 0;

    const key = `${row.year}-${row.week}`;
    const aggregate = dataProcessor.weeklyAggregates.get(key);
    return aggregate ? aggregate.totalSales : 0;
  }

  /**
   * 通过年-周获取周总和
   */
  getWeekTotalSumByYW(year, week) {
    const key = `${year}-${week}`;
    const aggregate = dataProcessor.weeklyAggregates.get(key);
    return aggregate ? aggregate.totalSales : 0;
  }

  /**
   * 获取当前视图中指定周的总和
   * @param {number} year - ISO年
   * @param {number} week - ISO周
   * @param {string} chartId - 图表ID
   * @returns {number} 当前视图中该周所有可见点的销售额总和
   */
  getWeekTotalSumInCurrentView(year, week, chartId = 'scatter-chart') {
    const chart = this.charts.get(chartId);
    if (!chart) return 0;
    const data = (chart.getOption().series?.[0]?.data) || [];
    // 只累计当前视图可见数据里、同一ISO年-周的点
    return data.reduce((s, d) => {
      return (d.year === year && d.week === week)
        ? s + (d.weeklySales ?? (d.value?.[1] ?? 0))
        : s;
    }, 0);
  }

  calculateTotalSum() {
    // 废弃的方法，保留以避免其他地方调用出错
    return this.getScatterTotalSum();
  }

  getRecentWeeksData(store, date, weeks) {
    // 现在使用dataProcessor获取真实数据
    return dataProcessor.getStoreRecentWeeks(store, date, weeks);
  }

  /**
   * 销毁所有图表
   */
  dispose() {
    this.charts.forEach(chart => chart.dispose());
    this.charts.clear();
    this.tooltipCache.clear();
    this.miniChartCache.clear();
  }
}

// 创建单例实例
export const chartManager = new ChartManager();