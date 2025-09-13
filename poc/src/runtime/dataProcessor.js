/**
 * 数据预处理与特征计算
 */

import { mean, median } from 'd3-array';
import { timeParse } from 'd3-time-format';
import { validateDataRow } from '../contract/schema.js';
import { paramManager } from './params/manager.js';

// 节日日期映射（2010-2012）
const HOLIDAYS = {
  2010: [
    '2010-02-12', // Super Bowl
    '2010-02-14', // Valentine's Day
    '2010-09-10', // Labor Day
    '2010-11-26', // Thanksgiving
    '2010-12-31'  // Christmas
  ],
  2011: [
    '2011-02-11', // Super Bowl
    '2011-02-14', // Valentine's Day
    '2011-09-09', // Labor Day
    '2011-11-25', // Thanksgiving
    '2011-12-30'  // Christmas
  ],
  2012: [
    '2012-02-10', // Super Bowl
    '2012-02-14', // Valentine's Day
    '2012-09-07', // Labor Day
    '2012-11-23', // Thanksgiving
    '2012-12-28'  // Christmas
  ]
};

export class DataProcessor {
  constructor() {
    this.rawData = [];
    this.processedData = [];
    this.storeFeatures = new Map();
    this.weeklyAggregates = new Map();
  }

  /**
   * 加载和解析CSV数据
   */
  async loadData(csvContent) {
    // 使用UTC时间解析
    const parseDate = (dateStr) => {
      // 支持 YYYY-MM-DD 和 DD-MM-YYYY 格式
      let parts;
      if (dateStr.match(/^\d{4}-\d{2}-\d{2}$/)) {
        parts = dateStr.split('-');
        return new Date(Date.UTC(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2])));
      } else if (dateStr.match(/^\d{2}-\d{2}-\d{4}$/)) {
        parts = dateStr.split('-');
        return new Date(Date.UTC(parseInt(parts[2]), parseInt(parts[1]) - 1, parseInt(parts[0])));
      }
      return null;
    };
    const lines = csvContent.trim().split('\n');
    const headers = lines[0].split(',');

    this.rawData = [];

    for (let i = 1; i < lines.length; i++) {
      const values = lines[i].split(',');
      const row = {};

      headers.forEach((header, index) => {
        let value = values[index];

        // 类型转换
        if (header === 'Store' || header === 'Holiday_Flag') {
          value = parseInt(value);
        } else if (header === 'Date') {
          const parsed = parseDate(value);
          if (!parsed) {
            throw new Error(`日期解析失败: ${value}`);
          }
          row.dateObj = parsed;
          row.year = parsed.getFullYear();
          row.week = this.getISOWeek(parsed);
          row.weekOfYear = this.getWeekOfYear(parsed);
          value = value; // 保留原始字符串
        } else if (header !== 'Date') {
          value = parseFloat(value);
        }

        // 字段名转换
        const fieldMap = {
          'Store': 'store',
          'Date': 'date',
          'Weekly_Sales': 'weeklySales',
          'Holiday_Flag': 'holidayFlag',
          'Temperature': 'temperature',
          'Fuel_Price': 'fuelPrice',
          'CPI': 'cpi',
          'Unemployment': 'unemployment'
        };

        row[fieldMap[header] || header.toLowerCase()] = value;
      });

      // 添加节日映射
      row.isHolidayWeek = this.isHolidayWeek(row.dateObj);
      row.isPreHolidayWeek = this.isPreHolidayWeek(row.dateObj);

      // Schema校验
      const vr = validateDataRow({
        store: row.store,
        date: row.date,
        weeklySales: row.weeklySales,
        holidayFlag: row.holidayFlag,
        temperature: row.temperature,
        fuelPrice: row.fuelPrice,
        cpi: row.cpi,
        unemployment: row.unemployment
      });
      if (!vr.valid) {
        console.warn(`Schema校验警告（行${i}）: ${vr.errors.slice(0, 3).join('; ')}`);
      }

      this.rawData.push(row);
    }

    // 计算特征
    await this.calculateFeatures();

    return this.rawData;
  }

  /**
   * 计算所有特征
   */
  async calculateFeatures() {
    // 按店铺分组
    const storeGroups = this.groupByStore(this.rawData);

    for (const [storeId, storeData] of storeGroups) {
      // 按时间排序
      storeData.sort((a, b) => a.dateObj - b.dateObj);

      // 计算各种特征
      const features = {
        momentum: this.calculateMomentum(storeData),
        holidayLift: this.calculateHolidayLift(storeData),
        fuelSensitivity: this.calculateFuelSensitivity(storeData),
        tempSensitivity: this.calculateTempSensitivity(storeData),
        macroAdaptation: this.calculateMacroAdaptation(storeData),
        trend: this.calculateTrend(storeData)
      };

      // Z-score标准化
      const normalized = this.normalizeFeatures(features, storeData);

      this.storeFeatures.set(storeId, normalized);
    }

    // 计算周度聚合
    this.calculateWeeklyAggregates();
  }

  /**
   * @private
   * 通用的滚动窗口计算器
   * @param {Array<Object>} storeData - 单个门店按时间排序的数据
   * @param {number} windowSize - 窗口大小
   * @param {Function} calculator - 接收窗口数据并返回计算值的函数
   * @returns {Array<number|null>} 计算结果数组
   */
  _calculateRollingFeature(storeData, windowSize, calculator) {
    return storeData.map((_, i) => {
      // 如果窗口未满，返回 null
      if (i < windowSize - 1) {
        return null;
      }
      // 提取窗口数据并执行计算
      const windowData = storeData.slice(i - windowSize + 1, i + 1);
      const result = calculator(windowData);
      // 确保结果是有效的数字
      return Number.isFinite(result) ? result : null;
    });
  }

  /**
   * 计算近端动量
   */
  calculateMomentum(storeData, window = null) {
    const winSize = window ?? paramManager.get('timeWindow.weeks') ?? 8;
    return this._calculateRollingFeature(storeData, winSize, (winData) => {
      const ma = mean(winData.map(d => d.weeklySales));
      const current = winData[winData.length - 1].weeklySales;
      return ma === 0 ? null : current / ma;
    });
  }

  /**
   * 计算节日提升（线性差）
   */
  calculateHolidayLift(storeData) {
    const lift = [];

    for (let i = 0; i < storeData.length; i++) {
      const current = storeData[i];
      const prev = i > 0 ? storeData[i - 1] : null;

      if (current.isHolidayWeek || current.isPreHolidayWeek) {
        if (prev && prev.weeklySales !== null && current.weeklySales !== null) {
          // 使用线性差：HOL = Sales_t - Sales_{t-1}
          lift.push(current.weeklySales - prev.weeklySales);
        } else {
          lift.push(null);
        }
      } else {
        lift.push(null);
      }
    }

    return lift;
  }

  /**
   * 计算油价敏感度（滚动回归）
   */
  calculateFuelSensitivity(storeData, window = null) {
    const winSize = window ?? paramManager.get('timeWindow.rollingWindow') ?? 26;
    return this._calculateRollingFeature(storeData, winSize, (winData) =>
      this.simpleRegression(
        winData.map(d => d.fuelPrice),
        winData.map(d => d.weeklySales)
      )
    );
  }

  /**
   * 计算气温敏感度（滚动回归）
   */
  calculateTempSensitivity(storeData, window = null) {
    const winSize = window ?? paramManager.get('timeWindow.rollingWindow') ?? 26;
    return this._calculateRollingFeature(storeData, winSize, (winData) =>
      this.simpleRegression(
        winData.map(d => d.temperature),
        winData.map(d => d.weeklySales)
      )
    );
  }

  /**
   * 计算宏观敏感度（MACRO_abs）
   */
  calculateMacroAdaptation(storeData, window = null) {
    const winSize = window ?? paramManager.get('timeWindow.rollingWindow') ?? 26;
    return this._calculateRollingFeature(storeData, winSize, (winData) => {
      // 计算与失业率的相关系数绝对值
      const corrUnemployment = Math.abs(this.correlation(
        winData.map(d => d.weeklySales),
        winData.map(d => d.unemployment)
      ));

      // 计算与CPI的相关系数绝对值
      const corrCPI = Math.abs(this.correlation(
        winData.map(d => d.weeklySales),
        winData.map(d => d.cpi)
      ));

      // MACRO_abs = mean(|corr(Sales, Unemployment)|, |corr(Sales, CPI)|)
      return (corrUnemployment + corrCPI) / 2;
    });
  }

  /**
   * 计算稳健趋势
   */
  calculateTrend(storeData, window = null) {
    const winSize = window ?? paramManager.get('timeWindow.weeks') ?? 8;
    return this._calculateRollingFeature(storeData, winSize, (winData) => {
      const sales = winData.map(d => d.weeklySales);

      // 使用中位增量作为稳健趋势
      const increments = [];
      for (let j = 1; j < sales.length; j++) {
        increments.push(sales[j] - sales[j - 1]);
      }

      return median(increments);
    });
  }

  /**
   * Z-score标准化
   */
  normalizeFeatures(features, storeData) {
    const normalized = {};

    for (const [name, values] of Object.entries(features)) {
      const validValues = values.filter(v => v !== null && Number.isFinite(v));

      if (validValues.length === 0) {
        normalized[name] = values.map(() => null);
        continue;
      }

      const m = mean(validValues);
      const std = Math.sqrt(mean(validValues.map(v => Math.pow(v - m, 2))));

      if (std === 0) {
        normalized[name] = values.map(() => 0);
      } else {
        normalized[name] = values.map(v => (v === null || !Number.isFinite(v)) ? null : (v - m) / std);
      }
    }

    // 将数据添加到原始记录
    for (let i = 0; i < storeData.length; i++) {
      storeData[i].features = {};
      for (const [name, values] of Object.entries(normalized)) {
        storeData[i].features[name] = values[i];
      }
    }

    return normalized;
  }

  /**
   * 计算活跃度评分（智能NA处理）
   */
  calculateActivityScore(row, weights, excludeFeatures = new Set()) {
    if (!row.features) {
      return null;
    }

    const f = row.features;

    // 构建特征项（排除被剔除的特征）
    const terms = [];

    if (!excludeFeatures.has('momentum')) {
      terms.push({ name: 'momentum', w: weights.momentum, v: f.momentum });
    }
    if (!excludeFeatures.has('holiday')) {
      terms.push({ name: 'holiday', w: weights.holiday, v: f.holidayLift });
    }
    if (!excludeFeatures.has('fuel')) {
      terms.push({ name: 'fuel', w: weights.fuel, v: (f.fuelSensitivity === null ? null : 1 - Math.abs(f.fuelSensitivity)) });
    }
    if (!excludeFeatures.has('temperature')) {
      terms.push({ name: 'temperature', w: weights.temperature, v: (f.tempSensitivity === null ? null : 1 - Math.abs(f.tempSensitivity)) });
    }
    if (!excludeFeatures.has('macro')) {
      terms.push({ name: 'macro', w: weights.macro, v: (f.macroAdaptation === null ? null : 1 - f.macroAdaptation) });
    }
    if (!excludeFeatures.has('trend')) {
      terms.push({ name: 'trend', w: weights.trend, v: f.trend });
    }

    // 过滤有效项（权重>0且值非NA）
    const validTerms = terms.filter(t => t.w > 0 && t.v !== null && Number.isFinite(t.v));

    // 如果没有有效项，返回null
    if (validTerms.length === 0) {
      return null;
    }

    // 计算加权平均
    const sumW = validTerms.reduce((s, t) => s + t.w, 0);
    if (sumW === 0) return null;

    return validTerms.reduce((s, t) => s + (t.w / sumW) * t.v, 0);
  }

  /**
   * 分析特征NA情况并决定剔除策略
   */
  analyzeFeatureAvailability(data, weights) {
    const featureNames = ['momentum', 'holiday', 'fuel', 'temperature', 'macro', 'trend'];
    const featureNAStats = {};

    // 统计每个特征的NA比例
    featureNames.forEach(name => {
      let naCount = 0;
      let totalCount = 0;

      data.forEach(row => {
        if (row.features) {
          totalCount++;
          let value = row.features[name];

          // 特殊处理需要转换的特征
          if (name === 'fuel' || name === 'temperature') {
            value = row.features[name + 'Sensitivity'];
          } else if (name === 'holiday') {
            value = row.features.holidayLift;
          } else if (name === 'macro') {
            value = row.features.macroAdaptation;
          }

          if (value === null || !Number.isFinite(value)) {
            naCount++;
          }
        }
      });

      featureNAStats[name] = {
        naCount,
        totalCount,
        naRatio: totalCount > 0 ? naCount / totalCount : 1
      };
    });

    // 决定剔除哪些特征（NA比例超过30%的）
    const excludeFeatures = new Set();
    const threshold = 0.3;

    for (const [name, stats] of Object.entries(featureNAStats)) {
      if (stats.naRatio > threshold && weights[name] > 0) {
        console.log(`特征 ${name} 的NA比例为 ${(stats.naRatio * 100).toFixed(1)}%，将被剔除`);
        excludeFeatures.add(name);
      }
    }

    return { featureNAStats, excludeFeatures };
  }

  /**
   * 简单线性回归
   */
  simpleRegression(x, y) {
    const n = x.length;
    if (n < 2) return 0;

    const meanX = mean(x);
    const meanY = mean(y);

    let numerator = 0;
    let denominator = 0;

    for (let i = 0; i < n; i++) {
      numerator += (x[i] - meanX) * (y[i] - meanY);
      denominator += Math.pow(x[i] - meanX, 2);
    }

    return denominator === 0 ? 0 : numerator / denominator;
  }

  /**
   * 计算相关系数
   */
  correlation(x, y) {
    const n = x.length;
    if (n < 2) return 0;

    const meanX = mean(x);
    const meanY = mean(y);

    let cov = 0;
    let varX = 0;
    let varY = 0;

    for (let i = 0; i < n; i++) {
      const dx = x[i] - meanX;
      const dy = y[i] - meanY;
      cov += dx * dy;
      varX += dx * dx;
      varY += dy * dy;
    }

    const denom = Math.sqrt(varX * varY);
    return denom === 0 ? 0 : cov / denom;
  }

  /**
   * 获取ISO周（基于UTC）
   */
  getISOWeek(date) {
    const target = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
    const dayNum = (target.getUTCDay() + 6) % 7;
    target.setUTCDate(target.getUTCDate() - dayNum + 3);
    const firstThursday = target.valueOf();
    target.setUTCMonth(0, 1);
    if (target.getUTCDay() !== 4) {
      target.setUTCMonth(0, 1 + ((4 - target.getUTCDay()) + 7) % 7);
    }
    return 1 + Math.ceil((firstThursday - target) / 604800000);
  }

  /**
   * 获取年内周数（基于UTC）
   */
  getWeekOfYear(date) {
    const start = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
    const diff = date - start;
    const oneWeek = 1000 * 60 * 60 * 24 * 7;
    return Math.floor(diff / oneWeek) + 1;
  }

  /**
   * 判断是否为节日周
   */
  isHolidayWeek(date) {
    const year = date.getFullYear();
    const holidays = HOLIDAYS[year] || [];

    for (const holiday of holidays) {
      const holidayDate = new Date(holiday);
      if (this.getISOWeek(date) === this.getISOWeek(holidayDate)) {
        return true;
      }
    }

    return false;
  }

  /**
   * 判断是否为节日前一周
   */
  isPreHolidayWeek(date) {
    const year = date.getFullYear();
    const holidays = HOLIDAYS[year] || [];
    const nextWeek = new Date(date);
    nextWeek.setDate(nextWeek.getDate() + 7);

    return this.isHolidayWeek(nextWeek);
  }

  /**
   * 按店铺分组
   */
  groupByStore(data) {
    const groups = new Map();

    for (const row of data) {
      if (!groups.has(row.store)) {
        groups.set(row.store, []);
      }
      groups.get(row.store).push(row);
    }

    return groups;
  }

  /**
   * 计算周度聚合
   */
  calculateWeeklyAggregates() {
    const weekGroups = new Map();

    for (const row of this.rawData) {
      const key = `${row.year}-${row.week}`;
      if (!weekGroups.has(key)) {
        weekGroups.set(key, []);
      }
      weekGroups.get(key).push(row);
    }

    for (const [key, rows] of weekGroups) {
      const totalSales = rows.reduce((sum, r) => sum + r.weeklySales, 0);
      this.weeklyAggregates.set(key, {
        totalSales,
        storeCount: rows.length,
        avgSales: totalSales / rows.length
      });
    }
  }

  /**
   * 获取门店近N周数据
   */
  getStoreRecentWeeks(storeId, date, weeks = 8) {
    const storeData = this.rawData.filter(r => r.store === storeId);
    const targetDate = typeof date === 'string' ? this.parseUTCDate(date) : date;

    // 按日期排序
    storeData.sort((a, b) => a.dateObj - b.dateObj);

    // 使用年-周键匹配
    const targetYear = targetDate.getUTCFullYear();
    const targetWeek = this.getISOWeek(targetDate);

    const targetIndex = storeData.findIndex(r =>
      r.year === targetYear && r.week === targetWeek
    );

    if (targetIndex === -1) return [];

    const startIndex = Math.max(0, targetIndex - weeks + 1);
    return storeData.slice(startIndex, targetIndex + 1);
  }

  /**
   * 解析UTC日期
   */
  parseUTCDate(dateStr) {
    if (dateStr.match(/^\d{4}-\d{2}-\d{2}$/)) {
      const parts = dateStr.split('-');
      return new Date(Date.UTC(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2])));
    }
    return new Date(dateStr + 'T00:00:00Z');
  }
}

// 创建单例实例
export const dataProcessor = new DataProcessor();