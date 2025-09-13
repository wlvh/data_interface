/**
 * Web Worker 沙箱执行器
 * 仅在 Worker 线程运行，安全执行槽位代码
 */

// 禁用的模式（更严格的白名单校验）
const FORBIDDEN_PATTERNS = [
  /constructor\s*\.\s*constructor/,
  /__proto__/,
  /\beval\s*\(/,
  /\bnew\s+Function\b/,
  /\bimport\s*\(/,
  /\bfetch\b|\bXMLHttpRequest\b|\bWebSocket\b/
];

/**
 * 验证槽位代码安全性
 */
function validateSlot(code) {
  const errors = [];

  // 检查必须有return语句
  if (!/return\s+/.test(code)) {
    errors.push('Function must have a return statement');
  }

  // 检查禁用模式
  FORBIDDEN_PATTERNS.forEach(re => {
    if (re.test(code)) {
      errors.push(`Forbidden pattern: ${re}`);
    }
  });

  return { ok: errors.length === 0, errors };
}

/**
 * 创建安全的工具函数集
 */
function createUtils() {
  const utils = {
    // 统计函数
    mean: a => a.length ? a.reduce((s, v) => s + v, 0) / a.length : 0,

    median: a => {
      if (!a.length) return 0;
      const b = [...a].sort((x, y) => x - y);
      const m = Math.floor(b.length / 2);
      return b.length % 2 ? b[m] : (b[m - 1] + b[m]) / 2;
    },

    stdev: a => {
      const m = utils.mean(a);
      return Math.sqrt(utils.mean(a.map(v => (v - m) * (v - m))));
    },

    sum: a => a.reduce((s, v) => s + v, 0),

    quantile: (a, q) => {
      const b = [...a].sort((x, y) => x - y);
      const i = q * (b.length - 1);
      const l = Math.floor(i);
      const u = Math.ceil(i);
      const w = i % 1;
      return b[l] * (1 - w) + b[u] * w;
    },

    // 数学函数
    clamp: (v, mi, ma) => Math.max(mi, Math.min(ma, v)),
    log1p: Math.log1p ?? (x => Math.log(1 + x)),
    exp: Math.exp,

    // 时间函数（固定UTC时间）
    now: () => Date.UTC(2025, 8, 13, 12, 0, 0),

    // 随机函数（使用种子）
    random: (() => {
      let s = 42;
      return () => ((s = (s * 9301 + 49297) % 233280) / 233280);
    })()
  };

  return utils;
}

/**
 * 验证输出结果
 */
function validateOutput(result, schema) {
  if (!schema) return { ok: true, errors: [] };

  const errors = [];

  // 检查类型
  if (schema.type && typeof result !== schema.type) {
    errors.push(`Expected output type ${schema.type}`);
  }

  // 检查必需属性
  if (schema.properties && typeof result === 'object') {
    for (const [k, def] of Object.entries(schema.properties)) {
      if (!(k in result) && !def.optional) {
        errors.push(`Missing required output property: ${k}`);
      }
    }
  }

  // 检查输出大小
  const size = JSON.stringify(result).length;
  if (size > 1024 * 1024) {
    errors.push('Output size too large (max 1MB)');
  }

  return { ok: errors.length === 0, errors };
}

/**
 * Worker消息处理器
 */
self.onmessage = (e) => {
  const { slotId, code, input, params, outputSchema, timeout } = e.data;
  const t0 = performance.now();

  // 验证代码
  const v = validateSlot(code);
  if (!v.ok) {
    self.postMessage({
      ok: false,
      error: {
        code: 'VALIDATION_ERROR',
        message: v.errors.join('; '),
        phase: 'validation'
      }
    });
    return;
  }

  // 创建工具函数
  const utils = createUtils();

  // 构建安全的执行环境
  const wrapped = `
    'use strict';
    const window = undefined;
    const document = undefined;
    const globalThis = undefined;
    const selfRef = undefined;
    const Function = undefined;
    const eval = undefined;
    const fetch = undefined;
    const WebSocket = undefined;
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
      log1p: Math.log1p || (x => Math.log(1 + x)),
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

  let timer = null;

  try {
    // 创建执行函数（仅在Worker中安全）
    const exec = new Function('input', 'params', 'utils', wrapped);

    // 设置超时
    timer = setTimeout(() => {
      throw new Error('Execution timeout');
    }, timeout ?? 1000);

    // 执行函数
    const result = exec(input, params, utils);

    // 清除定时器
    clearTimeout(timer);

    // 验证输出
    const o = validateOutput(result, outputSchema);
    if (!o.ok) {
      self.postMessage({
        ok: false,
        error: {
          code: 'OUTPUT_VALIDATION_ERROR',
          message: o.errors.join('; '),
          phase: 'output'
        }
      });
      return;
    }

    // 返回成功结果
    self.postMessage({
      ok: true,
      data: result,
      exec_time_ms: performance.now() - t0
    });

  } catch (err) {
    if (timer) clearTimeout(timer);

    self.postMessage({
      ok: false,
      error: {
        code: 'EXECUTION_ERROR',
        message: err.message,
        phase: 'execution'
      }
    });
  }
};