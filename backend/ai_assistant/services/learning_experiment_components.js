// Shared chart layout. Generated code supplies data and teaching logic.
const chartInstances = new WeakMap();
function renderChart(host, options) {
  if (!(host instanceof HTMLElement)) throw Error('chart.host 必须是 HTML 元素。');
  if (!options || !['bar', 'line'].includes(options.type)) throw Error('chart.type 只支持 bar 或 line。');
  const {labels, series} = options;
  const maxLabels = options.type === 'line' ? 65 : 12;
  if (!Array.isArray(labels)) throw Error('chart.labels 必须是数组。');
  if (labels.length < 1 || labels.length > maxLabels) {
    throw Error(`chart.labels.length 为 ${labels.length}，须为 1 至 ${maxLabels}。`);
  }
  for (const [index, label] of labels.entries()) {
    if (typeof label !== 'string' || !label.trim() || label.length > 48) {
      throw Error(`chart.labels[${index}] 必须是非空字符串，最多 48 字符。`);
    }
  }
  if (!Array.isArray(series)) throw Error('chart.series 必须是数组。');
  if (series.length < 1 || series.length > 3) {
    throw Error(`chart.series.length 为 ${series.length}，须为 1 至 3。`);
  }
  for (const [index, item] of series.entries()) {
    if (!item || typeof item.label !== 'string' || !item.label.trim() || item.label.length > 24) {
      throw Error(`chart.series[${index}].label 必须是非空字符串，最多 24 字符。`);
    }
    if (!Array.isArray(item.values)) throw Error(`chart.series[${index}].values 必须是数组。`);
    if (item.values.length !== labels.length) {
      throw Error(`chart.series[${index}].values.length 为 ${item.values.length}，须等于 labels.length（${labels.length}）。`);
    }
    const invalidValue = Array.from(item.values).findIndex(value => !Number.isFinite(value));
    if (invalidValue !== -1) throw Error(`chart.series[${index}].values[${invalidValue}] 必须是有限数值。`);
  }
  const config = JSON.parse(JSON.stringify(options));
  const colors = ['var(--um-accent)', 'var(--um-secondary)', 'var(--um-positive)'];
  const element = (name, text, parent) => {
    const node = document.createElement(name);
    if (text !== undefined) node.textContent = text;
    parent.appendChild(node);
    return node;
  };
  let instance = chartInstances.get(host);
  if (!instance) {
    instance = {draw: () => {}, width: null};
    const observer = new ResizeObserver(entries => {
      const width = entries[0].contentRect.width;
      if (width === instance.width) return;
      instance.width = width;
      requestAnimationFrame(() => instance.draw());
    });
    observer.observe(host);
    chartInstances.set(host, instance);
  }
  instance.draw = () => {
    host.replaceChildren();
    host.classList.add('um-chart');
    const heading = element('div', undefined, host);
    heading.className = 'um-chart-heading';
    element('span', String(config.yLabel || ''), heading);
    const legend = element('div', undefined, heading);
    legend.className = 'um-chart-legend';
    config.series.forEach((series, index) => {
      const label = element('span', undefined, legend);
      const swatch = element('i', undefined, label);
      swatch.style.background = colors[index];
      element('span', series.label, label);
    });
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    host.appendChild(svg);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', [config.yLabel, config.xLabel, ...config.series.map(series => series.label)].filter(Boolean).join('；'));
    const width = Math.max(160, host.clientWidth), height = width < 420 ? 140 : 182;
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    const add = (tag, attributes, text) => {
      const node = document.createElementNS(svg.namespaceURI, tag);
      Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
      if (text !== undefined) node.textContent = text;
      svg.appendChild(node);
      return node;
    };
    const values = config.series.flatMap(series => series.values);
    const magnitude = Math.max(...values.map(Math.abs)) || 1;
    const low = Math.min(0, ...values.map(value => value / magnitude));
    const high = Math.max(0, ...values.map(value => value / magnitude)) || (low === 0 ? 1 : 0);
    const format = value => Math.abs(value) >= 1e6 || (value !== 0 && Math.abs(value) < .001)
      ? value.toExponential(1) : new Intl.NumberFormat('zh-CN', {maximumSignificantDigits: 4}).format(value);
    const measure = document.createElement('canvas').getContext('2d');
    measure.font = `12px ${getComputedStyle(host).fontFamily}`;
    const ticks = [low, (low + high) / 2, high];
    const left = Math.ceil(Math.max(...ticks.map(value => measure.measureText(format(value * magnitude)).width))) + 10;
    const right = width - 8, top = 12, bottom = width < 420 ? 108 : 148, band = (right - left) / config.labels.length;
    const y = value => bottom - (value / magnitude - low) / (high - low) * (bottom - top);
    const x = index => left + (index + .5) * band;
    ticks.forEach(value => {
      const position = y(value * magnitude);
      add('line', {x1: left, y1: position, x2: right, y2: position, stroke: 'var(--um-line)'});
      add('text', {x: left - 7, y: position + 4, 'text-anchor': 'end', 'font-size': 12, fill: 'var(--um-muted)'}, format(value * magnitude));
    });
    config.series.forEach((series, seriesIndex) => {
      if (config.type === 'line') add('polyline', {points: series.values.map((value, index) => `${x(index)},${y(value)}`).join(' '),
        fill: 'none', stroke: colors[seriesIndex], 'stroke-width': 2, 'stroke-linejoin': 'round'});
      series.values.forEach((value, index) => {
        const barWidth = band * .72 / config.series.length;
        const mark = config.type === 'bar'
          ? add('rect', {x: x(index) - band * .36 + seriesIndex * barWidth, y: Math.min(y(0), y(value)),
              width: barWidth, height: Math.abs(y(value) - y(0)), rx: 2, fill: colors[seriesIndex]})
          : add('circle', {cx: x(index), cy: y(value), r: Math.min(3, band / 3), fill: colors[seriesIndex]});
        const title = document.createElementNS(svg.namespaceURI, 'title');
        title.textContent = `${config.labels[index]} · ${series.label}：${value}`;
        mark.appendChild(title);
      });
    });
    let lastRight = -Infinity;
    config.labels.forEach((label, index) => {
      const textWidth = measure.measureText(label).width;
      const position = Math.max(left + textWidth / 2, Math.min(right - textWidth / 2, x(index)));
      const start = position - textWidth / 2;
      if (start < lastRight + 10 || textWidth > right - left) return;
      add('text', {x: position, y: bottom + 22, 'text-anchor': 'middle', 'font-size': 12, fill: 'var(--um-muted)'}, label);
      lastRight = position + textWidth / 2;
    });
    if (!Number.isFinite(lastRight)) throw Error('图表标签过长，当前宽度无法清晰显示，请缩短标签并在正文解释。');
    if (config.xLabel) element('div', String(config.xLabel), host).className = 'um-chart-axis-label';
  };
  instance.draw();
}
