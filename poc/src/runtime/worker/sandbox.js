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
 * 验证槽位代码安全性（主线程轻量级检查）
 */
export function validateSlot(code) {
  const forbidden = [
    /constructor\s*\.\s*constructor/,
    /__proto__/,
    /\beval\s*\(/,
    /\bnew\s+Function\b/,
    /\bimport\s*\(/,
    /\bfetch\b|\bXMLHttpRequest\b|\bWebSocket\b/
  ];

  const errors = [];

  // 检查必须有return语句
  if (!/return\s+/.test(code)) {
    errors.push('Function must have a return statement');
  }

  // 检查禁用模式
  forbidden.forEach(re => {
    if (re.test(code)) {
      errors.push(`Forbidden pattern: ${re}`);
    }
  });

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
 * Worker实例管理
 */
let _worker;

function ensureWorker() {
  if (_worker) return _worker;
  const url = new URL('./slotWorker.js', import.meta.url);
  _worker = new Worker(url, { type: 'module' });
  return _worker;
}

/**
 * 在Worker中安全执行函数槽位
 */
export function runSlot(slotId, code, input, params, options = {}) {
  const worker = ensureWorker();
  const timeout = options.timeout ?? 1000;
  const outputSchema = options.outputSchema;

  return new Promise((resolve) => {
    let timer = setTimeout(() => {
      // 终止超时的Worker
      try {
        worker.terminate();
      } catch (_) {}
      // 重新创建Worker
      _worker = null;
      resolve({
        ok: false,
        error: {
          code: 'EXECUTION_TIMEOUT',
          message: 'Execution timeout',
          phase: 'execution'
        }
      });
    }, timeout + 50);

    worker.onmessage = (e) => {
      clearTimeout(timer);
      resolve(e.data);
    };

    worker.onerror = (error) => {
      clearTimeout(timer);
      // Worker错误时重新创建
      _worker = null;
      resolve({
        ok: false,
        error: {
          code: 'WORKER_ERROR',
          message: error.message || 'Worker execution failed',
          phase: 'execution'
        }
      });
    };

    // 发送任务到Worker
    worker.postMessage({
      slotId,
      code,
      input,
      params,
      outputSchema,
      timeout
    });
  });
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