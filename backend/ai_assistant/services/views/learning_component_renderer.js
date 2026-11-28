(() => {
  const { specification } = JSON.parse(document.getElementById('lc-spec').textContent);
  const { sliders = [], choices = [], zones = [], items = [], outputs = [] } = specification;
  const root = document.getElementById('lc-component');
  const initialValues = Object.fromEntries([
    ...sliders.map(row => [row.id, row.value]),
    ...choices.map(row => [row.id, row.options[0].value]),
  ]);
  const initialLocations = Object.fromEntries(items.map(row => [row.id, row.zone]));
  const values = { ...initialValues };
  const locations = { ...initialLocations };
  const saved = window.unimind.getState();
  const zoneNodes = new Map();
  const itemNodes = new Map();
  const valueNodes = new Map();
  const outputNodes = new Map();
  const optionNodes = new Map();
  const sliderNodes = new Map();

  for (const row of sliders) {
    const value = saved.values?.[row.id];
    if (Number.isInteger(value) && row.min <= value && value <= row.max) values[row.id] = value;
  }
  for (const row of choices) {
    const value = saved.values?.[row.id];
    if (row.options.some(option => option.value === value)) values[row.id] = value;
  }
  for (const row of items) {
    const location = saved.locations?.[row.id];
    if (zones.some(zone => zone.id === location)) locations[row.id] = location;
  }

  function node(tag, parent, text, id) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (id) element.id = id;
    parent.append(element);
    return element;
  }

  function button(parent, text, id, action) {
    const element = node('button', parent, text, id);
    element.type = 'button';
    element.onclick = action;
    return element;
  }

  function calculate(expression, counts) {
    if (typeof expression === 'number') return expression;
    if (typeof expression === 'string') return values[expression];
    if ('count' in expression) return counts[expression.count];
    if ('in_zone' in expression) {
      const [item, zone] = expression.in_zone;
      return Number(locations[item] === zone);
    }
    const [left, right] = expression.args.map(arg => calculate(arg, counts));
    if (left === null || right === null) return null;
    switch (expression.op) {
      case 'add': return left + right;
      case 'sub': return left - right;
      case 'mul': return left * right;
      case 'div': return right ? left / right : null;
    }
  }

  function refresh() {
    for (const [id, value] of Object.entries(values)) {
      const badge = valueNodes.get(id);
      badge.dataset.value = String(value);
      badge.textContent = String(value);
      if (sliderNodes.has(id)) sliderNodes.get(id).value = String(value);
      for (const [option, element] of optionNodes.get(id) ?? []) {
        element.setAttribute('aria-pressed', String(option === value));
      }
    }
    const counts = Object.fromEntries(zones.map(zone => [zone.id, 0]));
    for (const [id, zone] of Object.entries(locations)) {
      counts[zone] += 1;
      const item = itemNodes.get(id);
      const target = zoneNodes.get(zone);
      if (item.parentElement !== target) target.append(item);
      for (const choice of item.querySelectorAll('[data-zone]')) choice.disabled = choice.dataset.zone === zone;
    }
    for (const row of outputs) {
      const amount = calculate(row.expression, counts);
      const text = Number.isFinite(amount) && Math.abs(amount) <= 1e10
        ? (Math.floor(amount * 100 + .5) / 100).toFixed(2) : '—';
      const output = outputNodes.get(row.id);
      output.dataset.value = text;
      output.textContent = row.unit ? text + ' ' + row.unit : text;
    }
  }

  function change() {
    refresh();
    window.unimind.setState({ values, locations });
  }

  const style = node('style', root);
  style.textContent = `
    #lc-component { display: grid; gap: 12px; overflow-wrap: anywhere; min-width: 0; }
    #lc-component fieldset, #lc-component section { min-width: 0; margin: 0; padding: 10px; border: 1px solid var(--um-line); border-radius: 8px; }
    #lc-component .lc-actions { display: flex; flex-wrap: wrap; gap: 6px; }
    #lc-component input[type=range] { width: 100%; box-sizing: border-box; }
    #lc-component button[aria-pressed=true] { border-color: var(--um-accent); font-weight: bold; }
    #lc-component article { display: grid; gap: 6px; margin-top: 8px; }
    #lc-component h3 { margin: 0 0 6px; font-size: 1rem; }
    #lc-component output { font-variant-numeric: tabular-nums; }
  `;
  for (const row of [...sliders, ...choices]) {
    const group = node('fieldset', root);
    node('legend', group, row.label);
    valueNodes.set(row.id, node('output', group, undefined, 'lc-value-' + row.id));
    if ('options' in row) {
      const buttons = node('div', group);
      buttons.className = 'lc-actions';
      optionNodes.set(row.id, row.options.map((option, index) => [option.value,
        button(buttons, option.label, 'lc-option-' + row.id + '-' + index, () => {
          values[row.id] = option.value;
          change();
        })]));
    } else {
      const input = node('input', group, undefined, 'lc-control-' + row.id);
      input.type = 'range';
      input.min = row.min;
      input.max = row.max;
      input.setAttribute('aria-label', row.label);
      input.oninput = () => {
        values[row.id] = Number(input.value);
        change();
      };
      sliderNodes.set(row.id, input);
    }
  }
  for (const zone of zones) {
    const section = node('section', root, undefined, 'lc-zone-' + zone.id);
    node('h3', section, zone.label);
    zoneNodes.set(zone.id, section);
  }
  for (const row of items) {
    const item = node('article', zoneNodes.get(locations[row.id]), undefined, 'lc-item-' + row.id);
    node('strong', item, row.label);
    const buttons = node('div', item);
    buttons.className = 'lc-actions';
    for (const zone of zones) {
      const move = button(buttons, zone.label, 'lc-move-' + row.id + '-' + zone.id, () => {
        locations[row.id] = zone.id;
        change();
      });
      move.dataset.zone = zone.id;
      move.setAttribute('aria-label', row.label + ' → ' + zone.label);
    }
    itemNodes.set(row.id, item);
  }
  if (outputs.length) {
    const result = node('section', root);
    result.setAttribute('aria-live', 'polite');
    for (const row of outputs) {
      const line = node('div', result);
      node('span', line, row.label + ' ');
      outputNodes.set(row.id, node('output', line, undefined, 'lc-output-' + row.id));
    }
  }
  button(root, '重置 / Reset', 'lc-reset', () => {
    Object.assign(values, initialValues);
    Object.assign(locations, initialLocations);
    change();
  });
  refresh();
})();
