/**
 * 参数面板组件
 */

import { paramManager } from '../../runtime/params/manager.js';

export class ParameterPanel {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.sliders = new Map();
    this.debounceTimers = new Map();
  }

  /**
   * 初始化面板
   */
  init() {
    if (!this.container) {
      console.error('Parameter panel container not found');
      return;
    }

    this.render();
    this.attachEventListeners();
  }

  /**
   * 渲染面板
   */
  render() {
    const weights = paramManager.get('weights');

    const html = `
      <div class="panel-header">
        <h3>活跃度权重调整</h3>
        <button id="normalize-btn" class="btn btn-secondary">归一化权重</button>
      </div>

      <div class="panel-body">
        ${this.renderSliderGroup('权重参数', [
      { id: 'weights.momentum', label: '近端动量', value: weights.momentum },
      { id: 'weights.holiday', label: '节日效应', value: weights.holiday },
      { id: 'weights.fuel', label: '油价敏感度(-)' , value: weights.fuel },
      { id: 'weights.temperature', label: '气温敏感度(-)', value: weights.temperature },
      { id: 'weights.macro', label: '宏观敏感度(1-z)', value: weights.macro },
      { id: 'weights.trend', label: '稳健趋势', value: weights.trend }
    ])}

        <div class="param-group">
          <h4>时间窗口</h4>
          <div class="param-item">
            <label>分析周数</label>
            <select id="timeWindow.weeks" class="form-control">
              <option value="4">4周</option>
              <option value="8" selected>8周</option>
              <option value="13">13周</option>
            </select>
          </div>

          <div class="param-item">
            <label>Tooltip周数</label>
            <select id="display.tooltipWeeks" class="form-control">
              <option value="8" selected>8周</option>
              <option value="13">13周</option>
            </select>
          </div>
        </div>

        <div class="param-group">
          <h4>散点图配置</h4>
          <div class="param-item">
            <label>X轴</label>
            <select id="scatter.xField" class="form-control">
              <option value="temperature" selected>温度</option>
              <option value="fuelPrice">油价</option>
              <option value="weekOfYear">周数</option>
            </select>
          </div>

          <div class="param-item">
            <label>颜色</label>
            <select id="scatter.colorField" class="form-control">
              <option value="store" selected>门店</option>
              <option value="holidayFlag">节日</option>
            </select>
          </div>
        </div>

        <div class="weight-sum-display">
          <span>权重总和:</span>
          <span id="weight-sum" class="weight-sum-value">1.00</span>
        </div>
      </div>
    `;

    this.container.innerHTML = html;
  }

  /**
   * 渲染滑块组
   */
  renderSliderGroup(title, sliders) {
    let html = `
      <div class="param-group">
        <h4>${title}</h4>
    `;

    sliders.forEach(slider => {
      html += `
        <div class="param-item">
          <div class="param-label">
            <span>${slider.label}</span>
            <span class="param-value" id="${slider.id}-value">${slider.value.toFixed(2)}</span>
          </div>
          <div class="slider-container">
            <input
              type="range"
              id="${slider.id}"
              class="param-slider"
              min="0"
              max="1"
              step="0.01"
              value="${slider.value}"
            />
            <div class="slider-energy" id="${slider.id}-energy" style="width: ${slider.value * 100}%"></div>
          </div>
        </div>
      `;

      this.sliders.set(slider.id, slider.value);
    });

    html += '</div>';
    return html;
  }

  /**
   * 附加事件监听器
   */
  attachEventListeners() {
    // 滑块变化
    this.container.querySelectorAll('.param-slider').forEach(slider => {
      slider.addEventListener('input', (e) => this.handleSliderChange(e));
    });

    // 下拉框变化
    this.container.querySelectorAll('select').forEach(select => {
      select.addEventListener('change', (e) => this.handleSelectChange(e));
    });

    // 归一化按钮
    const normalizeBtn = document.getElementById('normalize-btn');
    if (normalizeBtn) {
      normalizeBtn.addEventListener('click', () => this.normalizeWeights());
    }

    // 监听参数变化
    paramManager.on('weights.*', () => this.updateWeightSum());
  }

  /**
   * 处理滑块变化
   */
  handleSliderChange(event) {
    const sliderId = event.target.id;
    const value = parseFloat(event.target.value);

    // 更新显示
    const valueDisplay = document.getElementById(`${sliderId}-value`);
    if (valueDisplay) {
      valueDisplay.textContent = value.toFixed(2);
    }

    // 更新能量条
    const energyBar = document.getElementById(`${sliderId}-energy`);
    if (energyBar) {
      energyBar.style.width = `${value * 100}%`;
    }

    // 防抖更新参数
    this.debounceUpdate(sliderId, value);
  }

  /**
   * 防抖更新
   */
  debounceUpdate(path, value) {
    // 清除之前的定时器
    if (this.debounceTimers.has(path)) {
      clearTimeout(this.debounceTimers.get(path));
    }

    // 设置新的定时器
    const timer = setTimeout(() => {
      paramManager.set(path, value);
      this.debounceTimers.delete(path);

      // 触发图表更新
      this.triggerChartUpdate(path);
    }, 300); // 300ms防抖

    this.debounceTimers.set(path, timer);
  }

  /**
   * 处理下拉框变化
   */
  handleSelectChange(event) {
    const selectId = event.target.id;
    const value = event.target.value;

    // 简化类型转换 - 直接使用Number()，参数验证逻辑会处理NaN
    paramManager.set(selectId, Number(value));
    this.triggerChartUpdate(selectId);
  }

  /**
   * 归一化权重
   */
  normalizeWeights() {
    paramManager.normalizeWeights();

    // 更新所有滑块
    const weights = paramManager.get('weights');
    for (const [key, value] of Object.entries(weights)) {
      const sliderId = `weights.${key}`;
      const slider = document.getElementById(sliderId);
      const valueDisplay = document.getElementById(`${sliderId}-value`);
      const energyBar = document.getElementById(`${sliderId}-energy`);

      if (slider) {
        slider.value = value;
      }
      if (valueDisplay) {
        valueDisplay.textContent = value.toFixed(2);
      }
      if (energyBar) {
        energyBar.style.width = `${value * 100}%`;
      }
    }

    this.updateWeightSum();
    this.triggerChartUpdate();
  }

  /**
   * 更新权重总和显示
   */
  updateWeightSum() {
    const weights = paramManager.get('weights');
    const sum = Object.values(weights).reduce((a, b) => a + b, 0);

    const sumDisplay = document.getElementById('weight-sum');
    if (sumDisplay) {
      sumDisplay.textContent = sum.toFixed(2);
      sumDisplay.className = Math.abs(sum - 1) < 0.01 ? 'weight-sum-value valid' : 'weight-sum-value invalid';
    }
  }

  /**
   * 触发图表更新
   */
  triggerChartUpdate(changedPath = null) {
    // 发送自定义事件
    window.dispatchEvent(new CustomEvent('parametersChanged', {
      detail: {
        weights: paramManager.get('weights'),
        timeWindow: paramManager.get('timeWindow'),
        scatter: paramManager.get('scatter'),
        changedPath: changedPath
      }
    }));
  }

  /**
   * 获取当前参数快照
   */
  getSnapshot() {
    return paramManager.getSnapshot();
  }

  /**
   * 恢复参数快照
   */
  restoreSnapshot(snapshot) {
    paramManager.restoreSnapshot(snapshot);
    this.render();
    this.attachEventListeners();
  }
}