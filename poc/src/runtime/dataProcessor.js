/**
 * 数据预处理与特征计算
 */

import { mean, median } from 'd3-array';
import { timeParse } from 'd3-time-format';
import { validateDataRow } from '../contract/schema.js';

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
    const parseYMD = timeParse('%Y-%m-%d');
    const parseDMY = timeParse('%d-%m-%Y');
    const parseDate = (s) => parseYMD(s) || parseDMY(s) || null;
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
   * 计算近端动量
   */
  calculateMomentum(storeData, window = 8) {
    const momentum = [];

    for (let i = 0; i < storeData.length; i++) {
      if (i < window - 1) {
        momentum.push(null); // 窗口不足
      } else {
        const windowData = storeData.slice(i - window + 1, i + 1);
        const ma = mean(windowData.map(d => d.weeklySales));
        const current = storeData[i].weeklySales;
        momentum.push(ma === 0 ? null : current / ma);
      }
    }

    return momentum;
  }

  /**
   * 计算节日提升（对数差）
   */
  calculateHolidayLift(storeData) {
    const lift = [];

    for (let i = 0; i < storeData.length; i++) {
      const current = storeData[i];
      const prev = i > 0 ? storeData[i - 1] : null;

      if (current.isHolidayWeek || current.isPreHolidayWeek) {
        if (prev && prev.weeklySales > 0 && current.weeklySales > 0) {
          // 使用对数差更稳健
          lift.push(Math.log1p(current.weeklySales) - Math.log1p(prev.weeklySales));
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
  calculateFuelSensitivity(storeData, window = 26) {
    const sensitivity = [];

    for (let i = 0; i < storeData.length; i++) {
      if (i < window - 1) {
        sensitivity.push(null); // 窗口不足
      } else {
        const windowData = storeData.slice(i - window + 1, i + 1);
        const beta = this.simpleRegression(
          windowData.map(d => d.fuelPrice),
          windowData.map(d => d.weeklySales)
        );
        sensitivity.push(Number.isFinite(beta) ? beta : null);
      }
    }

    return sensitivity;
  }

  /**
   * 计算气温敏感度（滚动回归）
   */
  calculateTempSensitivity(storeData, window = 26) {
    const sensitivity = [];

    for (let i = 0; i < storeData.length; i++) {
      if (i < window - 1) {
        sensitivity.push(null); // 窗口不足
      } else {
        const windowData = storeData.slice(i - window + 1, i + 1);
        const beta = this.simpleRegression(
          windowData.map(d => d.temperature),
          windowData.map(d => d.weeklySales)
        );
        sensitivity.push(Number.isFinite(beta) ? beta : null);
      }
    }

    return sensitivity;
  }

  /**
   * 计算宏观敏感度（惩罚项）
   */
  calculateMacroAdaptation(storeData, window = 26) {
    const adaptation = [];

    for (let i = 0; i < storeData.length; i++) {
      if (i < window - 1) {
        adaptation.push(null); // 窗口不足
      } else {
        const windowData = storeData.slice(i - window + 1, i + 1);

        // 计算与失业率的负相关
        const corrUnemployment = Math.abs(this.correlation(
          windowData.map(d => d.weeklySales),
          windowData.map(d => -d.unemployment)
        ));

        // 计算与CPI的负相关
        const corrCPI = Math.abs(this.correlation(
          windowData.map(d => d.weeklySales),
          windowData.map(d => -d.cpi)
        ));

        // 定义为"宏观敏感度强度"（越大越敏感→惩罚项）
        adaptation.push((corrUnemployment + corrCPI) / 2);
      }
    }

    return adaptation;
  }

  /**
   * 计算稳健趋势
   */
  calculateTrend(storeData, window = 8) {
    const trends = [];

    for (let i = 0; i < storeData.length; i++) {
      if (i < window - 1) {
        trends.push(null); // 窗口不足
      } else {
        const windowData = storeData.slice(i - window + 1, i + 1);
        const sales = windowData.map(d => d.weeklySales);

        // 使用中位增量作为稳健趋势
        const increments = [];
        for (let j = 1; j < sales.length; j++) {
          increments.push(sales[j] - sales[j - 1]);
        }

        const m = median(increments);
        trends.push(Number.isFinite(m) ? m : null);
      }
    }

    return trends;
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
   * 计算活跃度评分（权重重标）
   */
  calculateActivityScore(row, weights) {
    if (!row.features) return 0;

    const f = row.features;

    // 将null视为"不可用"并做有效权重重标
    const terms = [
      { w: weights.momentum, v: f.momentum },
      { w: weights.holiday, v: f.holidayLift },
      { w: weights.fuel, v: (f.fuelSensitivity === null ? null : 1 - Math.abs(f.fuelSensitivity)) },
      { w: weights.temperature, v: (f.tempSensitivity === null ? null : 1 - Math.abs(f.tempSensitivity)) },
      // 宏观敏感度为惩罚项：1 - |z|
      { w: weights.macro, v: (f.macroAdaptation === null ? null : 1 - Math.abs(f.macroAdaptation)) },
      { w: weights.trend, v: f.trend }
    ];

    // 筛选有效项
    const eff = terms.filter(t => t.v !== null && Number.isFinite(t.v) && t.w > 0);
    if (!eff.length) return 0;

    // 重标权重
    const sumW = eff.reduce((s, t) => s + t.w, 0);
    return eff.reduce((s, t) => s + (t.w / sumW) * t.v, 0);
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
   * 获取ISO周
   */
  getISOWeek(date) {
    const target = new Date(date.valueOf());
    const dayNum = (date.getDay() + 6) % 7;
    target.setDate(target.getDate() - dayNum + 3);
    const firstThursday = target.valueOf();
    target.setMonth(0, 1);
    if (target.getDay() !== 4) {
      target.setMonth(0, 1 + ((4 - target.getDay()) + 7) % 7);
    }
    return 1 + Math.ceil((firstThursday - target) / 604800000);
  }

  /**
   * 获取年内周数
   */
  getWeekOfYear(date) {
    const start = new Date(date.getFullYear(), 0, 1);
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
    const targetDate = typeof date === 'string' ? new Date(date) : date;

    // 按日期排序
    storeData.sort((a, b) => a.dateObj - b.dateObj);

    // 找到目标日期的索引
    const targetIndex = storeData.findIndex(r =>
      Math.abs(r.dateObj - targetDate) < 7 * 24 * 60 * 60 * 1000
    );

    if (targetIndex === -1) return [];

    const startIndex = Math.max(0, targetIndex - weeks + 1);
    return storeData.slice(startIndex, targetIndex + 1);
  }
}

// 创建单例实例
export const dataProcessor = new DataProcessor();