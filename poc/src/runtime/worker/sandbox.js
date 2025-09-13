/**
 * Web Worker 沙箱执行器
 * 安全执行动态函数代码
 */

// AST黑名单
const BLACKLISTED_IDENTIFIERS = [
  'window', 'document', 'globalThis', 'global', 'self',
  'fetch', 'XMLHttpRequest', 'WebSocket',
  'Function', 'eval', 'import', 'require',
  'setTimeout', 'setInterval', 'setImmediate',
  'postMessage', 'addEventListener',
  'Date', 'Math.random'
];

// 允许的语法结构
const ALLOWED_STATEMENTS = [
  'VariableDeclaration',
  'FunctionDeclaration',
  'ExpressionStatement',
  'ReturnStatement',
  'IfStatement',
  'ForStatement',
  'WhileStatement',
  'BlockStatement',
  'AssignmentExpression',
  'BinaryExpression',
  'UnaryExpression',
  'LogicalExpression',
  'ConditionalExpression',
  'CallExpression',
  'MemberExpression',
  'ArrayExpression',
  'ObjectExpression',
  'Literal',
  'Identifier'
];

/**
 * 简单的AST解析和检查
 * 注意：生产环境应使用更完整的AST解析器
 */
export function validateSlot(code) {
  const errors = [];

  // 检查黑名单标识符
  for (const blacklisted of BLACKLISTED_IDENTIFIERS) {
    // 使用正则表达式检查（简化版本）
    const regex = new RegExp(`\\b${blacklisted}\\b`, 'g');
    if (regex.test(code)) {
      errors.push(`Blacklisted identifier found: ${blacklisted}`);
    }
  }

  // 检查危险的语法
  if (/new\s+Function/.test(code)) {
    errors.push('Dynamic function creation not allowed');
  }
  if (/eval\s*\(/.test(code)) {
    errors.push('eval() not allowed');
  }
  if (/import\s*\(/.test(code)) {
    errors.push('Dynamic import not allowed');
  }

  // 检查是否有return语句
  if (!/return\s+/.test(code)) {
    errors.push('Function must have a return statement');
  }

  return { ok: errors.length === 0, errors };
}

/**
 * 创建安全的执行环境
 */
function createSafeEnvironment() {
  // 提供的工具函数
  const utils = {
    // 数学函数
    mean: (arr) => {
      if (!arr || arr.length === 0) return 0;
      return arr.reduce((sum, val) => sum + val, 0) / arr.length;
    },

    median: (arr) => {
      if (!arr || arr.length === 0) return 0;
      const sorted = [...arr].sort((a, b) => a - b);
      const mid = Math.floor(sorted.length / 2);
      return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
    },

    stdev: (arr) => {
      if (!arr || arr.length === 0) return 0;
      const m = utils.mean(arr);
      const variance = arr.reduce((sum, val) => sum + Math.pow(val - m, 2), 0) / arr.length;
      return Math.sqrt(variance);
    },

    sum: (arr) => arr.reduce((sum, val) => sum + val, 0),

    min: (arr) => Math.min(...arr),

    max: (arr) => Math.max(...arr),

    quantile: (arr, q) => {
      const sorted = [...arr].sort((a, b) => a - b);
      const index = q * (sorted.length - 1);
      const lower = Math.floor(index);
      const upper = Math.ceil(index);
      const weight = index % 1;
      return sorted[lower] * (1 - weight) + sorted[upper] * weight;
    },

    // 数学函数
    clamp: (value, min, max) => Math.max(min, Math.min(max, value)),

    scale: (value, inMin, inMax, outMin, outMax) => {
      return ((value - inMin) / (inMax - inMin)) * (outMax - outMin) + outMin;
    },

    log1p: (x) => Math.log(1 + x),

    exp: (x) => Math.exp(x),

    // 时间函数（使用固定UTC时间）
    now: () => Date.UTC(2025, 8, 13, 12, 0, 0), // 固定UTC时间

    parseUtc: (dateStr) => {
      const date = new Date(dateStr + 'T00:00:00Z');
      return date.getTime();
    },

    // 随机函数（使用种子）
    random: (() => {
      let seed = 42;
      return () => {
        seed = (seed * 9301 + 49297) % 233280;
        return seed / 233280;
      };
    })(),

    // 数组函数
    groupBy: (arr, keyFn) => {
      return arr.reduce((groups, item) => {
        const key = keyFn(item);
        if (!groups[key]) groups[key] = [];
        groups[key].push(item);
        return groups;
      }, {});
    },

    rolling: (arr, window, fn) => {
      const result = [];
      for (let i = 0; i < arr.length; i++) {
        const start = Math.max(0, i - window + 1);
        const windowData = arr.slice(start, i + 1);
        result.push(fn(windowData));
      }
      return result;
    }
  };

  return utils;
}

/**
 * 在沙箱中执行函数槽位
 */
export function runSlot(slotId, code, input, params, options = {}) {
  const startTime = performance.now();
  const timeout = options.timeout || 5000;

  try {
    // 验证代码
    const validation = validateSlot(code);
    if (!validation.ok) {
      return {
        ok: false,
        error: {
          code: 'VALIDATION_ERROR',
          message: validation.errors.join('; '),
          phase: 'validation'
        }
      };
    }

    // 深度冻结输入
    const frozenInput = deepFreeze(JSON.parse(JSON.stringify(input)));
    const frozenParams = deepFreeze(JSON.parse(JSON.stringify(params)));

    // 创建工具函数
    const utils = createSafeEnvironment();

    // 构建安全的执行函数
    // 注意：生产环境应使用更安全的隔离方案
    const wrappedCode = `
      'use strict';
      const window = undefined;
      const document = undefined;
      const globalThis = undefined;
      const self = undefined;
      const Function = undefined;
      const eval = undefined;
      const Date = undefined;
      const Math = Object.freeze({
        abs: Math.abs,
        floor: Math.floor,
        ceil: Math.ceil,
        round: Math.round,
        min: Math.min,
        max: Math.max,
        pow: Math.pow,
        sqrt: Math.sqrt,
        log: Math.log,
        exp: Math.exp,
        sin: Math.sin,
        cos: Math.cos,
        tan: Math.tan,
        PI: Math.PI,
        E: Math.E
      });

      return (function(input, params, utils) {
        ${code}
      })(input, params, utils);
    `;

    // 创建执行函数
    const executor = new Function('input', 'params', 'utils', wrappedCode);

    // 设置超时控制
    let timeoutId;
    const promise = new Promise((resolve, reject) => {
      timeoutId = setTimeout(() => {
        reject(new Error('Execution timeout'));
      }, timeout);

      try {
        const result = executor(frozenInput, frozenParams, utils);
        resolve(result);
      } catch (error) {
        reject(error);
      }
    });

    // 执行并获取结果
    return promise.then(result => {
      clearTimeout(timeoutId);
      const execTime = performance.now() - startTime;

      // 验证输出
      const outputValidation = validateOutput(result, options.outputSchema);
      if (!outputValidation.ok) {
        return {
          ok: false,
          error: {
            code: 'OUTPUT_VALIDATION_ERROR',
            message: outputValidation.errors.join('; '),
            phase: 'output'
          }
        };
      }

      return {
        ok: true,
        data: result,
        exec_time_ms: execTime
      };
    }).catch(error => {
      clearTimeout(timeoutId);
      return {
        ok: false,
        error: {
          code: 'EXECUTION_ERROR',
          message: error.message,
          phase: 'execution'
        }
      };
    });

  } catch (error) {
    return Promise.resolve({
      ok: false,
      error: {
        code: 'SETUP_ERROR',
        message: error.message,
        phase: 'setup'
      }
    });
  }
}

/**
 * 深度冻结对象
 */
function deepFreeze(obj) {
  Object.freeze(obj);
  Object.getOwnPropertyNames(obj).forEach(prop => {
    if (obj[prop] !== null
      && (typeof obj[prop] === 'object' || typeof obj[prop] === 'function')
      && !Object.isFrozen(obj[prop])) {
      deepFreeze(obj[prop]);
    }
  });
  return obj;
}

/**
 * 验证输出结果
 */
function validateOutput(result, schema) {
  if (!schema) return { ok: true };

  const errors = [];

  // 检查结果类型
  if (schema.type) {
    const actualType = typeof result;
    if (schema.type !== actualType) {
      errors.push(`Expected output type ${schema.type}, got ${actualType}`);
    }
  }

  // 检查对象属性
  if (schema.properties && typeof result === 'object') {
    for (const [key, propSchema] of Object.entries(schema.properties)) {
      if (!(key in result) && !propSchema.optional) {
        errors.push(`Missing required output property: ${key}`);
      }
    }
  }

  // 检查数组长度限制
  if (Array.isArray(result) && result.length > 50000) {
    errors.push('Output array too large (max 50000 items)');
  }

  // 检查输出大小
  const size = JSON.stringify(result).length;
  if (size > 1024 * 1024) { // 1MB
    errors.push('Output size too large (max 1MB)');
  }

  return { ok: errors.length === 0, errors };
}