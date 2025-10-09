/**
 * 契约Schema定义与校验
 */

export const ContractSchema = {
  version: '1.0.0',

  // 数据模式定义
  dataSchema: {
    store: { type: 'number', required: true },
    date: { type: 'string', required: true, format: 'date' },
    weeklySales: { type: 'number', required: true },
    holidayFlag: { type: 'number', required: true, enum: [0, 1] },
    temperature: { type: 'number', required: true },
    fuelPrice: { type: 'number', required: true },
    cpi: { type: 'number', required: true },
    unemployment: { type: 'number', required: true }
  },

  // 参数定义
  parameters: {
    // 任务一：活跃度权重参数
    weights: {
      momentum: { type: 'number', min: 0, max: 1, default: 0.2, step: 0.01 },
      holiday: { type: 'number', min: 0, max: 1, default: 0.15, step: 0.01 },
      fuel: { type: 'number', min: 0, max: 1, default: 0.15, step: 0.01 },
      temperature: { type: 'number', min: 0, max: 1, default: 0.15, step: 0.01 },
      macro: { type: 'number', min: 0, max: 1, default: 0.2, step: 0.01 },
      trend: { type: 'number', min: 0, max: 1, default: 0.15, step: 0.01 }
    },

    // 时间窗口参数
    timeWindow: {
      weeks: { type: 'number', enum: [4, 8, 13], default: 8 },
      rollingWindow: { type: 'number', min: 8, max: 52, default: 26 }
    },

    // 显示参数
    display: {
      tooltipWeeks: { type: 'number', enum: [8, 13], default: 8 },
      maxPoints: { type: 'number', default: 30000 }
    },

    // 散点参数（缺失会导致UI变更失效）
    scatter: {
      xField: { type: 'string', enum: ['temperature', 'fuelPrice', 'weekOfYear'], default: 'temperature' },
      yField: { type: 'string', enum: ['weeklySales'], default: 'weeklySales' },
      colorField: { type: 'string', enum: ['store', 'holidayFlag'], default: 'store' }
    }
  },

  // 函数槽位定义
  functionSlots: {
    // 公式槽位
    formula: {
      activity: {
        description: '计算门店活跃度评分',
        input: ['features', 'weights'],
        output: { type: 'number' },
        pure: true
      },

      zscore: {
        description: '计算z-score标准化',
        input: ['value', 'mean', 'std'],
        output: { type: 'number' },
        pure: true
      }
    },

    // 提示槽位
    tooltip: {
      storeWeek: {
        description: '生成门店周度提示数据',
        input: ['point', 'context'],
        output: {
          lines: { type: 'array', items: { label: 'string', value: 'number|string' } },
          miniSeries: { type: 'array', items: { t: 'number', y: 'number' } }
        },
        pure: true
      }
    },

    // 聚合槽位
    aggregate: {
      selection: {
        description: '聚合选中点的统计信息',
        input: ['points', 'params'],
        output: {
          count: { type: 'number' },
          sum: { type: 'number' },
          mean: { type: 'number' },
          median: { type: 'number' },
          stdev: { type: 'number' },
          share: { type: 'number' },
          slope: { type: 'number', optional: true }
        },
        pure: true
      }
    }
  },

  // 图表配置
  charts: {
    // 任务一：活跃度排名图
    activityChart: {
      type: 'bar',
      data: 'activityScores',
      xField: 'store',
      yField: 'activity',
      colorField: 'quantile',
      interactive: true,
      tooltip: 'storeWeek'
    },

    // 任务三：散点图
    scatterChart: {
      type: 'scatter',
      data: 'weeklyData',
      xField: { dynamic: true, options: ['temperature', 'fuelPrice', 'weekOfYear'] },
      yField: 'weeklySales',
      colorField: { dynamic: true, options: ['store', 'holidayFlag'] },
      brush: true,
      aggregate: 'selection'
    }
  }
};

/**
 * 校验数据行是否符合schema
 */
export function validateDataRow(row, schema = ContractSchema.dataSchema) {
  const errors = [];

  for (const [field, rules] of Object.entries(schema)) {
    const value = row[field];

    // 检查必填
    if (rules.required && (value === undefined || value === null)) {
      errors.push(`Missing required field: ${field}`);
      continue;
    }

    // 类型检查
    if (value !== undefined && value !== null) {
      const actualType = typeof value;
      if (rules.type === 'number' && actualType !== 'number') {
        errors.push(`Field ${field} should be number, got ${actualType}`);
      } else if (rules.type === 'string' && actualType !== 'string') {
        errors.push(`Field ${field} should be string, got ${actualType}`);
      }

      // 枚举检查
      if (rules.enum && !rules.enum.includes(value)) {
        errors.push(`Field ${field} value ${value} not in enum ${rules.enum}`);
      }

      // 范围检查
      if (rules.type === 'number') {
        if (rules.min !== undefined && value < rules.min) {
          errors.push(`Field ${field} value ${value} below min ${rules.min}`);
        }
        if (rules.max !== undefined && value > rules.max) {
          errors.push(`Field ${field} value ${value} above max ${rules.max}`);
        }
      }
    }
  }

  return { valid: errors.length === 0, errors };
}

/**
 * 校验参数值
 */
export function validateParameter(name, value, schema = ContractSchema.parameters) {
  // 递归查找参数定义
  const findParam = (obj, path) => {
    const parts = path.split('.');
    let current = obj;
    for (const part of parts) {
      if (!current[part]) return null;
      current = current[part];
    }
    return current;
  };

  const paramDef = findParam(schema, name);
  if (!paramDef) {
    return { valid: false, errors: [`Unknown parameter: ${name}`] };
  }

  const errors = [];

  // 类型检查
  if (paramDef.type === 'number' && typeof value !== 'number') {
    errors.push(`Parameter ${name} should be number`);
  }

  // 范围检查
  if (paramDef.min !== undefined && value < paramDef.min) {
    errors.push(`Parameter ${name} value ${value} below min ${paramDef.min}`);
  }
  if (paramDef.max !== undefined && value > paramDef.max) {
    errors.push(`Parameter ${name} value ${value} above max ${paramDef.max}`);
  }

  // 枚举检查
  if (paramDef.enum && !paramDef.enum.includes(value)) {
    errors.push(`Parameter ${name} value ${value} not in enum ${paramDef.enum}`);
  }

  return { valid: errors.length === 0, errors };
}

/**
 * 生成契约哈希
 */
export function generateContractHash(contract) {
  const str = JSON.stringify(contract);
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return hash.toString(16);
}