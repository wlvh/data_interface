/**
 * Web Worker 沙箱执行器
 * 仅在 Worker 线程运行，安全执行槽位代码
 */

importScripts('https://unpkg.com/acorn@8.15.0/dist/acorn.js');

// 黑名单标识符
const BLACKLISTED_IDENTIFIERS = new Set([
  'eval', 'Function', 'constructor', '__proto__',
  'window', 'document', 'fetch', 'XMLHttpRequest',
  'WebSocket', 'importScripts', 'self', 'globalThis',
  'require', 'module', 'exports', 'process'
]);

// 禁止的AST节点类型
const FORBIDDEN_NODE_TYPES = new Set([
  'ImportDeclaration', 'ImportExpression',
  'ExportNamedDeclaration', 'ExportDefaultDeclaration',
  'WithStatement', 'MetaProperty',
  'ImportAttribute', 'DynamicImport'
]);

/**
 * 验证槽位代码安全性（使用AST）
 */
function validateSlot(code) {
  const errors = [];

  // 检查必须有return语句
  if (!/return\s+/.test(code)) {
    errors.push('Function must have a return statement');
  }

  // AST解析和检查
  try {
    const ast = self.acorn.parse(code, {
      ecmaVersion: 2020,
      sourceType: 'script'
    });

    // 递归遍历AST节点
    function walkNode(node) {
      if (!node) return;

      // 检查节点类型
      if (FORBIDDEN_NODE_TYPES.has(node.type)) {
        errors.push(`Forbidden node type: ${node.type}`);
      }

      // 检查标识符
      if (node.type === 'Identifier' && BLACKLISTED_IDENTIFIERS.has(node.name)) {
        errors.push(`Blacklisted identifier: ${node.name}`);
      }

      // 检查new表达式
      if (node.type === 'NewExpression') {
        if (node.callee.type === 'Identifier' && node.callee.name === 'Function') {
          errors.push('new Function is not allowed');
        }
      }

      // 检查成员访问
      if (node.type === 'MemberExpression') {
        if (node.property.type === 'Identifier') {
          if (node.property.name === '__proto__' || node.property.name === 'constructor') {
            errors.push(`Dangerous property access: ${node.property.name}`);
          }
        }
      }

      // 递归遍历子节点
      for (const key in node) {
        if (node[key] && typeof node[key] === 'object') {
          if (Array.isArray(node[key])) {
            node[key].forEach(walkNode);
          } else if (node[key].type) {
            walkNode(node[key]);
          }
        }
      }
    }

    walkNode(ast);
  } catch (parseError) {
    errors.push(`Parse error: ${parseError.message}`);
  }

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
    const _Math = globalThis.Math;
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
      abs: _Math.abs,
      floor: _Math.floor,
      ceil: _Math.ceil,
      round: _Math.round,
      min: _Math.min,
      max: _Math.max,
      pow: _Math.pow,
      sqrt: _Math.sqrt,
      log: _Math.log,
      log1p: _Math.log1p || (x => _Math.log(1 + x)),
      exp: _Math.exp,
      sin: _Math.sin,
      cos: _Math.cos,
      tan: _Math.tan,
      PI: _Math.PI,
      E: _Math.E
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