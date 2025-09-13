/**
 * 参数中心 - 集中管理所有参数
 */

import { validateParameter } from '../../contract/schema.js';

class ParameterManager {
  constructor() {
    // 参数存储
    this.params = {
      // 权重参数（任务一）
      weights: {
        momentum: 0.2,
        holiday: 0.15,
        fuel: 0.15,
        temperature: 0.15,
        macro: 0.2,
        trend: 0.15
      },

      // 时间窗口参数
      timeWindow: {
        weeks: 8,
        rollingWindow: 26
      },

      // 显示参数
      display: {
        tooltipWeeks: 8,
        maxPoints: 30000
      },

      // 散点图轴配置（任务三）
      scatter: {
        xField: 'temperature',
        yField: 'weeklySales',
        colorField: 'store'
      }
    };

    // 参数变化监听器
    this.listeners = new Map();

    // 参数历史（用于回放）
    this.history = [];
  }

  /**
   * 获取参数值
   */
  get(path) {
    const parts = path.split('.');
    let value = this.params;

    for (const part of parts) {
      if (value === undefined || value === null) return undefined;
      value = value[part];
    }

    return value;
  }

  /**
   * 设置参数值
   */
  set(path, value) {
    // 校验参数
    const validation = validateParameter(path, value);
    if (!validation.valid) {
      console.error(`Parameter validation failed: ${validation.errors.join(', ')}`);
      return false;
    }

    // 更新参数
    const parts = path.split('.');
    let target = this.params;

    for (let i = 0; i < parts.length - 1; i++) {
      if (!(parts[i] in target)) {
        target[parts[i]] = {};
      }
      target = target[parts[i]];
    }

    const oldValue = target[parts[parts.length - 1]];
    target[parts[parts.length - 1]] = value;

    // 记录历史
    this.history.push({
      timestamp: Date.UTC(2025, 8, 13, 12, 0, 0), // 使用固定UTC时间
      path,
      oldValue,
      newValue: value
    });

    // 触发监听器
    this.notify(path, value, oldValue);

    return true;
  }

  /**
   * 批量设置参数
   */
  setMultiple(updates) {
    const results = [];

    for (const [path, value] of Object.entries(updates)) {
      results.push(this.set(path, value));
    }

    return results.every(r => r);
  }

  /**
   * 归一化权重（使和为1）
   */
  normalizeWeights() {
    const weights = this.get('weights');
    const sum = Object.values(weights).reduce((a, b) => a + b, 0);

    if (sum === 0) {
      // 平均分配
      const avg = 1 / Object.keys(weights).length;
      for (const key in weights) {
        this.set(`weights.${key}`, avg);
      }
    } else {
      // 按比例归一化
      for (const key in weights) {
        this.set(`weights.${key}`, weights[key] / sum);
      }
    }
  }

  /**
   * 注册参数变化监听器
   */
  on(path, callback) {
    if (!this.listeners.has(path)) {
      this.listeners.set(path, new Set());
    }
    this.listeners.get(path).add(callback);

    // 返回取消函数
    return () => {
      const callbacks = this.listeners.get(path);
      if (callbacks) {
        callbacks.delete(callback);
      }
    };
  }

  /**
   * 触发监听器
   */
  notify(path, newValue, oldValue) {
    // 触发精确匹配的监听器
    const callbacks = this.listeners.get(path);
    if (callbacks) {
      callbacks.forEach(cb => cb(newValue, oldValue, path));
    }

    // 触发父路径的监听器（支持通配）
    const parts = path.split('.');
    for (let i = parts.length - 1; i > 0; i--) {
      const parentPath = parts.slice(0, i).join('.');
      const parentCallbacks = this.listeners.get(parentPath + '.*');
      if (parentCallbacks) {
        parentCallbacks.forEach(cb => cb(newValue, oldValue, path));
      }
    }
  }

  /**
   * 获取参数快照
   */
  getSnapshot() {
    return {
      params: JSON.parse(JSON.stringify(this.params)),
      timestamp: Date.UTC(2025, 8, 13, 12, 0, 0)
    };
  }

  /**
   * 恢复参数快照
   */
  restoreSnapshot(snapshot) {
    if (!snapshot || !snapshot.params) {
      console.error('Invalid snapshot');
      return false;
    }

    // 批量更新参数
    const updates = this.flattenObject(snapshot.params);
    return this.setMultiple(updates);
  }

  /**
   * 展平嵌套对象
   */
  flattenObject(obj, prefix = '') {
    const result = {};

    for (const [key, value] of Object.entries(obj)) {
      const path = prefix ? `${prefix}.${key}` : key;

      if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        Object.assign(result, this.flattenObject(value, path));
      } else {
        result[path] = value;
      }
    }

    return result;
  }

  /**
   * 获取参数历史
   */
  getHistory() {
    return [...this.history];
  }

  /**
   * 清除历史
   */
  clearHistory() {
    this.history = [];
  }
}

// 创建单例实例
export const paramManager = new ParameterManager();

// 导出便捷函数
export const getParam = (path) => paramManager.get(path);
export const setParam = (path, value) => paramManager.set(path, value);
export const onParamChange = (path, callback) => paramManager.on(path, callback);