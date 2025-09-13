/**
 * ECharts图表管理器
 */

import * as echarts from 'echarts';
import { runSlot } from '../worker/sandbox.js';

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

    // 计算活跃度并排序
    const scored = data.map(store => ({
      ...store,
      activity: this.calculateWeightedScore(store, weights)
    }));

    scored.sort((a, b) => b.activity - a.activity);

    // 计算分位数颜色
    const activities = scored.map(s => s.activity);
    const q25 = this.quantile(activities, 0.25);
    const q50 = this.quantile(activities, 0.5);
    const q75 = this.quantile(activities, 0.75);

    // 更新图表
    chart.setOption({
      xAxis: {
        data: scored.map(s => `Store ${s.store}`)
      },
      series: [{
        data: scored.map(s => ({
          value: s.activity,
          itemStyle: {
            color: this.getQuantileColor(s.activity, q25, q50, q75)
          },
          store: s.store,
          features: s.features
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
      const totalSum = params.totalSum || sum;
      const share = sum / totalSum;

      // 计算局部斜率（可选）
      let slope = null;
      if (input.points.length >= 5) {
        const xValues = input.points.map(p => p.value[0]);
        const yValues = input.points.map(p => p.value[1]);

        // 简单线性回归
        const n = xValues.length;
        const meanX = utils.mean(xValues);
        const meanY = utils.mean(yValues);

        let numerator = 0;
        let denominator = 0;

        for (let i = 0; i < n; i++) {
          numerator += (xValues[i] - meanX) * (yValues[i] - meanY);
          denominator += Math.pow(xValues[i] - meanX, 2);
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

    const result = await runSlot('aggregate', aggregateCode, {
      points: selectedPoints
    }, {
      totalSum: this.calculateTotalSum()
    });

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
    const cacheKey = `activity_${data.store}`;
    if (this.tooltipCache.has(cacheKey)) {
      return this.tooltipCache.get(cacheKey);
    }

    // 构建tooltip内容
    let html = `
      <div style="padding: 10px; min-width: 250px;">
        <div style="font-weight: bold; margin-bottom: 8px;">
          Store ${data.store}
        </div>
        <div>活跃度评分: ${data.value.toFixed(3)}</div>
        <div style="margin-top: 8px; font-size: 12px;">
          <div>贡献分解:</div>
    `;

    if (data.features) {
      const contributions = [
        { name: '近端动量', value: data.features.momentum },
        { name: '节日效应', value: data.features.holidayLift },
        { name: '油价适应', value: 1 - Math.abs(data.features.fuelSensitivity) },
        { name: '气温适应', value: 1 - Math.abs(data.features.tempSensitivity) },
        { name: '宏观适应', value: data.features.macroAdaptation },
        { name: '稳健趋势', value: data.features.trend }
      ];

      contributions.forEach(c => {
        const color = c.value > 0 ? '#5470c6' : '#ee6666';
        html += `
          <div style="display: flex; justify-content: space-between; margin: 2px 0;">
            <span>${c.name}:</span>
            <span style="color: ${color}">${c.value.toFixed(3)}</span>
          </div>
        `;
      });
    }

    html += `
        </div>
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

    // 获取迷你图数据
    const miniSeriesHtml = await this.createMiniSparkline(data);

    const html = `
      <div style="padding: 10px; min-width: 300px;">
        <div style="font-weight: bold;">Store ${data.store} - Week ${data.weekOfYear}</div>
        <div>销售额: ${this.formatNumber(data.weeklySales)}</div>
        <div>温度: ${data.temperature}°F</div>
        <div>油价: $${data.fuelPrice}</div>
        ${data.holidayFlag ? '<div style="color: #ff6b6b;">🎄 节日周</div>' : ''}
        <div style="margin-top: 10px;">
          <div style="font-size: 12px; color: #666;">近8周趋势:</div>
          ${miniSeriesHtml}
        </div>
      </div>
    `;

    return html;
  }

  /**
   * 创建迷你sparkline
   */
  async createMiniSparkline(data) {
    const cacheKey = `sparkline_${data.store}_${data.date}`;

    if (this.miniChartCache.has(cacheKey)) {
      return this.miniChartCache.get(cacheKey);
    }

    // 创建迷你图容器
    const container = document.createElement('div');
    container.style.width = '280px';
    container.style.height = '60px';

    // 获取近期数据（这里简化处理）
    const recentData = this.getRecentWeeksData(data.store, data.date, 8);

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
              .map((d, i) => d.holidayFlag ? { coord: [i, d.weeklySales] } : null)
              .filter(d => d !== null)
          }
        }]
      });

      // 转换为HTML
      const html = container.innerHTML;
      this.miniChartCache.set(cacheKey, html);
      return html;
    }

    return '<div style="color: #999;">无历史数据</div>';
  }

  // 辅助函数
  calculateWeightedScore(store, weights) {
    if (!store.features) return 0;

    const f = store.features;
    return weights.momentum * (f.momentum || 0) +
      weights.holiday * (f.holidayLift || 0) +
      weights.fuel * (1 - Math.abs(f.fuelSensitivity || 0)) +
      weights.temperature * (1 - Math.abs(f.tempSensitivity || 0)) +
      weights.macro * (f.macroAdaptation || 0) +
      weights.trend * (f.trend || 0);
  }

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

  calculateTotalSum() {
    // 这里应该从实际数据计算
    return 1000000;
  }

  getRecentWeeksData(store, date, weeks) {
    // 这里应该从dataProcessor获取
    // 简化返回示例数据
    return Array(weeks).fill(0).map((_, i) => ({
      weeklySales: 1500000 + Math.random() * 200000,
      holidayFlag: i === 3 ? 1 : 0
    }));
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