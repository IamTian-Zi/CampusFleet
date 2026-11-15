const $ = selector => document.querySelector(selector);
const canvas = $('#map');
const ctx = canvas.getContext('2d');
const colors = ['#177448', '#ce6936', '#386fc2', '#a64ca1', '#b5901c', '#187e88', '#c14a67', '#7761bb', '#825836', '#456855'];
const roadMark = '#f3ca50';
const blockedKinds = new Set(['building', 'stairs', 'water', 'green', 'obstacle']);
const cellKey = point => point.join(',');
let map, agents = [], selected = 0, mode = 'start', obstacles = new Set();
let paths = [], pedestrians = [], inflated = [], tick = 0, timer = null, requestId = 0, busy = false;

function status(message) { $('#status').textContent = message; }
function stopPlayback() {
  clearInterval(timer);
  timer = null;
  $('#play').textContent = '播放';
}
function invalidate() {
  requestId++;
  stopPlayback();
  paths = [];
  pedestrians = [];
  inflated = [];
  tick = 0;
  $('#timeline').value = 0;
  $('#timeline').max = 0;
  $('#timeline').disabled = true;
  $('#play').disabled = true;
  $('#results').replaceChildren();
  $('#metrics').textContent = '';
  $('#speed').textContent = '';
}
function refreshAgents() {
  $('#agent').replaceChildren(...agents.map((agent, index) => new Option(`机器人 ${index + 1}`, index)));
  $('#agent').value = selected;
  $('#add').disabled = agents.length >= 10;
  $('#remove').disabled = agents.length <= 1;
  render();
}
function loadScenario() {
  invalidate();
  const scenario = map.scenarios[Number($('#scenario').value)];
  agents = structuredClone(scenario.agents);
  selected = 0;
  obstacles.clear();
  refreshAgents();
  status('场景已加载，可编辑端点或开始规划。');
}
function render() {
  if (!map) return;
  const scale = 8;
  canvas.width = map.width * scale;
  canvas.height = $('#view').value === '3d' ? Math.round(canvas.width * .52) : map.height * scale;
  $('#grid').disabled = $('#view').value === '3d';
  $('#inflation').disabled = $('#view').value === '3d';
  if ($('#view').value === '3d') {
    window.drawCampus3D(canvas, map, agents, paths, tick, selected, $('#routes').checked,
      [...obstacles].map(key=>key.split(',').map(Number)), Number($('#radius').value), Number($('#height').value), pedestrians);
  } else {
  ctx.fillStyle = '#eef5fb';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  for (const lane of map.lanes || []) {
    ctx.fillStyle = '#4b535c';
    for (const [x, y] of lane.cells) ctx.fillRect(x * scale, y * scale, scale, scale);
  }
  const terrain = {building: '#e7b989', stairs: '#dba875', water: '#91cfea', green: '#84bd83', obstacle: '#df7d71'};
  // Draw the exact occupied cells used by the server, including polygon boundaries.
  for (let y = 0; y < map.height; y++) {
    for (let x = 0; x < map.width; x++) {
      const color = terrain[map.cells[y][x]];
      if (color) { ctx.fillStyle = color; ctx.fillRect(x * scale, y * scale, scale, scale); }
    }
  }
  drawRoadMarkings(ctx, map.lanes || [], scale);
  if ($('#inflation').checked) {
    ctx.fillStyle = '#e6a25388';
    for (const [x, y] of inflated) ctx.fillRect(x * scale, y * scale, scale, scale);
  }
  ctx.fillStyle = '#d67067';
  for (const key of obstacles) {
    const [x, y] = key.split(',').map(Number);
    ctx.fillRect(x * scale, y * scale, scale, scale);
  }
  if ($('#grid').checked) {
    ctx.strokeStyle = '#52765a30';
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    for (let x = 0; x <= map.width; x++) { ctx.moveTo(x * scale, 0); ctx.lineTo(x * scale, canvas.height); }
    for (let y = 0; y <= map.height; y++) { ctx.moveTo(0, y * scale); ctx.lineTo(canvas.width, y * scale); }
    ctx.stroke();
  }
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.font = 'bold 12px sans-serif';
  ctx.fillStyle = '#754f35';
  for (const shape of map.shapes) {
    if (shape.kind !== 'building') continue;
    const x = shape.points.reduce((sum, p) => sum + p[0], 0) / shape.points.length;
    const y = shape.points.reduce((sum, p) => sum + p[1], 0) / shape.points.length;
    ctx.fillText(shape.label, x * scale, y * scale);
  }
  for (const lane of map.lanes || []) {
    const [x, y] = lane.label_position;
    ctx.fillStyle = '#e8f4fb';
    ctx.fillText(lane.label, x * scale, y * scale);
  }
  for (const result of paths) {
    const index = Number(result.id) - 1;
    const path = result.path;
    if ($('#routes').checked) {
      ctx.beginPath(); ctx.strokeStyle = colors[index]; ctx.lineWidth = 2.5;
      path.forEach(([x, y], n) => n ? ctx.lineTo((x + .5) * scale, (y + .5) * scale) : ctx.moveTo((x + .5) * scale, (y + .5) * scale));
      ctx.stroke();
    }
    const point = path[Math.min(tick, path.length - 1)];
    marker(point, index, false, true);
  }
  for (const pedestrian of pedestrians) {
    const point = pedestrian.path[Math.min(tick, pedestrian.path.length - 1)];
    ctx.fillStyle = '#273b46';
    ctx.beginPath(); ctx.arc((point[0] + .5) * scale, (point[1] + .5) * scale, 3.5, 0, Math.PI * 2); ctx.fill();
  }
  function marker(point, index, goal = false, moving = false) {
    const x = (point[0] + .5) * scale, y = (point[1] + .5) * scale;
    const size = moving ? Math.max(1, Number($('#radius').value) * scale) : 7;
    ctx.fillStyle = colors[index]; ctx.strokeStyle = '#ffffff'; ctx.lineWidth = selected === index ? 2.5 : 1.5;
    ctx.beginPath();
    if (goal) ctx.rect(x - size, y - size, size * 2, size * 2);
    else ctx.arc(x, y, size, 0, Math.PI * 2);
    ctx.fill(); ctx.stroke(); ctx.fillStyle = 'white'; ctx.font = 'bold 10px sans-serif';
    if (moving) {
      ctx.fillStyle = colors[index];
      ctx.fillText(index + 1, x, y - size - 7);
    } else ctx.fillText(index + 1, x, y);
  }
  agents.forEach((agent, index) => {
    marker(agent.goal, index, true);
    if (!paths.some(result => Number(result.id) === index + 1)) marker(agent.start, index);
  });
  const bridge = map.bridge;
  ctx.strokeStyle = '#d69a5e'; ctx.lineWidth = 2;
  ctx.strokeRect(bridge.start * scale, bridge.y_min * scale, (bridge.end - bridge.start) * scale, (bridge.y_max - bridge.y_min + 1) * scale);
  ctx.fillStyle = '#755235'; ctx.font = '14px sans-serif'; ctx.fillText('坡道 → 桥面 6m → 坡道', 230 * scale, 143 * scale);
  }
  $('#startText').textContent = `(${agents[selected].start.join(', ')})`;
  $('#goalText').textContent = `(${agents[selected].goal.join(', ')})`;
  $('#tick').textContent = `第 ${tick} / ${$('#timeline').max} 步`;
  const active = paths.find(result => Number(result.id) === selected + 1);
  if (active) {
    const speed = active.speed_profile_mps?.[tick] || 0;
    $('#speed').textContent = `机器人 ${selected + 1} · 当前区间速度 ${speed.toFixed(2)} 米/秒`;
  } else $('#speed').textContent = '';
}

function drawRoadMarkings(context, lanes, scale) {
  context.save();
  context.strokeStyle = roadMark;
  context.lineWidth = Math.max(1.5, scale * .22);
  context.lineCap = 'round';
  context.setLineDash([scale * 1.5, scale * 1.2]);
  for (const lane of lanes) {
    const [x, y] = lane.label_position;
    context.beginPath();
    if (lane.label.includes('斜向')) {
      context.moveTo(100.5 * scale, 82.5 * scale);
      context.lineTo(160.5 * scale, 112.5 * scale);
    } else {
      context.moveTo(13.5 * scale, (y + .5) * scale);
      context.lineTo(75.5 * scale, (y + .5) * scale);
    }
    context.stroke();
  }
  context.restore();
}

function canvasPoint(event) {
  const rect = canvas.getBoundingClientRect();
  return [Math.floor((event.clientX - rect.left) / rect.width * map.width),
          Math.floor((event.clientY - rect.top) / rect.height * map.height)];
}
canvas.addEventListener('click', event => {
  if (!map) return;
  if ($('#view').value === '3d') { status('选择“俯视编辑”视角后可编辑端点与临时障碍。'); return; }
  let point = canvasPoint(event); const [x, y] = point;
  if (!map.cells[y] || !map.cells[y][x]) return;
  const surface = $('#terrain').checked && $('#surface').value === 'bridge' && mode !== 'obstacle';
  if (!surface && blockedKinds.has(map.cells[y][x])) { status('这里被建筑、水池或花坛占据。'); return; }
  const key = cellKey(point);
  if (mode === 'obstacle') {
    if (agents.some(agent => cellKey(agent.start.slice(0,2)) === key || cellKey(agent.goal.slice(0,2)) === key)) {
      status('机器人起终点不能设置为障碍。'); return;
    }
    if (obstacles.has(key)) obstacles.delete(key);
    else obstacles.add(key);
  } else {
    if (obstacles.has(key)) { status('请先移除此处的临时障碍。'); return; }
    if (surface) {
      const b = map.bridge;
      if (x < b.start || x > b.end || y < b.y_min || y > b.y_max) { status('请点击桥面或坡道范围。'); return; }
      const z = x < b.plateau_start ? (x-b.start)*b.height/(b.plateau_start-b.start)
        : x > b.plateau_end ? (b.end-x)*b.height/(b.end-b.plateau_end) : b.height;
      point = [x,y,z];
    }
    agents[selected][mode] = point;
  }
  invalidate(); render(); status('地图已更改，请重新规划。');
});
canvas.addEventListener('mousemove', event => {
  if (map) $('#coords').textContent = `栅格 (${canvasPoint(event).join(', ')})`;
});
document.querySelectorAll('.mode').forEach(button => button.addEventListener('click', () => {
  mode = button.dataset.mode;
  document.querySelectorAll('.mode').forEach(other => other.classList.toggle('active', other === button));
}));
$('#agent').addEventListener('change', () => { selected = Number($('#agent').value); render(); });
$('#scenario').addEventListener('change', loadScenario);
$('#reset').addEventListener('click', () => {
  $('#radius').value = .3; $('#margin').value = .2; $('#horizon').value = 400; $('#limit').value = 8;
  $('#height').value = 1; $('#slope').value = 20;
  $('#pedestrians').value = 4; $('#pedestrianSeed').value = 1;
  loadScenario();
});
$('#add').addEventListener('click', () => {
  if (agents.length >= 10) return;
  const occupied = new Set(agents.flatMap(agent => [cellKey(agent.start), cellKey(agent.goal)]));
  const available = [];
  for (let y = 3; y < map.height - 3 && available.length < 2; y += 3) {
    for (let x = 3; x < map.width - 3 && available.length < 2; x += 3) {
      const point = [x, y], key = cellKey(point);
      if (!blockedKinds.has(map.cells[y][x]) && !occupied.has(key) && !obstacles.has(key)) available.push(point);
    }
  }
  if (available.length < 2) { status('请先腾出可用的起终点。'); return; }
  agents.push({start: available[0], goal: available[1]}); selected = agents.length - 1;
  invalidate(); refreshAgents(); status('已添加机器人，请检查或编辑它的起终点。');
});
$('#remove').addEventListener('click', () => {
  if (agents.length <= 1) return;
  agents.splice(selected, 1); selected = Math.min(selected, agents.length - 1);
  invalidate(); refreshAgents(); status('机器人已移除，请重新规划。');
});
for (const id of ['grid', 'inflation', 'routes', 'view']) $('#' + id).addEventListener('change', render);
for (const id of ['radius', 'margin', 'horizon', 'limit', 'method', 'slowdown', 'terrain', 'height', 'slope', 'pedestrians', 'pedestrianSeed']) $('#' + id).addEventListener('input', () => {
  invalidate(); render(); status('参数已更改，请重新规划。');
});
$('#timeline').addEventListener('input', () => { stopPlayback(); tick = Number($('#timeline').value); render(); });
$('#play').addEventListener('click', () => {
  if (timer) { stopPlayback(); return; }
  if (tick >= Number($('#timeline').max)) tick = 0;
  $('#play').textContent = '暂停';
  timer = setInterval(() => {
    tick = Math.min(tick + 1, Number($('#timeline').max));
    $('#timeline').value = tick; render();
    if (tick >= Number($('#timeline').max)) stopPlayback();
  }, 140);
});
$('#search').addEventListener('click', async () => {
  if (busy || !map) return;
  invalidate(); render();
  const id = requestId;
  const number = selector => $(selector).value.trim() === '' ? NaN : Number($(selector).value);
  const radius = number('#radius'), margin = number('#margin'), max_steps = number('#horizon'), time_limit_s = number('#limit');
  if (![radius, margin].every(value => Number.isFinite(value) && value >= 0 && value <= 3)
      || !Number.isInteger(max_steps) || max_steps < 1 || max_steps > 800
      || !Number.isFinite(time_limit_s) || time_limit_s < 1 || time_limit_s > 20
      || !Number.isInteger(number('#pedestrians')) || number('#pedestrians') < 0 || number('#pedestrians') > 15
      || !Number.isInteger(number('#pedestrianSeed')) || number('#pedestrianSeed') < 0) {
    status('请检查半径、余量、时间步和计算时限的有效范围。'); return;
  }
  const method = $('#method').value;
  const single = method === 'single' && !$('#terrain').checked && number('#pedestrians') === 0;
  const selectedAtRequest = selected;
  const body = {radius, margin, max_steps, time_limit_s, method: method === 'single' ? 'priority' : method,
                use_terrain: $('#terrain').checked, height: number('#height'), max_slope: number('#slope'), allow_slowdown: $('#slowdown').checked,
                pedestrian_count: number('#pedestrians'), pedestrian_seed: number('#pedestrianSeed'),
                obstacles: [...obstacles].map(key => key.split(',').map(Number))};
  if (single) Object.assign(body, agents[selected]);
  else body.agents = method === 'single' ? [agents[selected]] : agents;
  busy = true; $('#search').disabled = true; status('正在规划并检查冲突…');
  try {
    const response = await fetch(single ? '/api/path' : '/api/fleet', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
    });
    const data = await response.json();
    if (id !== requestId) return;
    if (!response.ok) throw Error(data.error || '服务器返回错误');
    inflated = data.inflated || [];
    if (!data.found) { status(data.reason); render(); return; }
    pedestrians = data.pedestrians || [];
    paths = single ? [{id: String(selectedAtRequest + 1), path: data.path, arrival_step: data.steps,
      distance_m: data.distance_m, wait_steps: 0, slow_steps: 0,
      speed_profile_mps: data.path.slice(1).map((point, index) => Math.hypot(point[0] - data.path[index][0], point[1] - data.path[index][1]) / Math.SQRT2)}] : data.agents;
    if (method === 'single') paths[0].id = String(selectedAtRequest + 1);
    const lastTick = Math.max(...paths.map(agent => agent.arrival_step));
    $('#timeline').max = lastTick; $('#timeline').disabled = false; $('#play').disabled = lastTick === 0;
    const distance = paths.reduce((sum, agent) => sum + agent.distance_m, 0).toFixed(2);
    const waits = paths.reduce((sum, agent) => sum + agent.wait_steps, 0);
    const slowSteps = paths.reduce((sum, agent) => sum + (agent.slow_steps || 0), 0);
    $('#metrics').textContent = single ? `长度 ${distance} 米 · 搜索 ${data.explored} 个节点`
      : `总长度 ${distance} 米 · 总到达 ${data.sum_arrival_steps} 步 · 全部到达 ${lastTick} 步 · 等待 ${waits} 步 · 半速 ${slowSteps} 步 · 冲突 ${data.conflicts} · 计算 ${data.planning_ms} 毫秒`;
    const table = document.createElement('table');
    const header = table.createTHead().insertRow();
    for (const title of ['机器人', '长度 / 米', '到达 / 步', '等待 / 步', '半速 / 步']) { const th = document.createElement('th'); th.textContent = title; header.append(th); }
    const tbody = table.createTBody();
    paths.forEach(agent => {
      const row = tbody.insertRow(); row.style.color = colors[Number(agent.id) - 1];
      for (const value of [agent.id, agent.distance_m, agent.arrival_step, agent.wait_steps, agent.slow_steps || 0]) row.insertCell().textContent = value;
    });
    $('#results').replaceChildren(table);
    status(single ? '当前机器人路线已生成。可播放或拖动时间轴。'
      : data.warning || '协同规划完成，整段移动的间距检查已通过。可播放或拖动时间轴。');
    render();
  } catch (error) {
    if (id === requestId) status('规划失败：' + error.message);
  } finally {
    busy = false; $('#search').disabled = false;
  }
});
fetch('/api/map').then(response => {
  if (!response.ok) throw Error('地图读取失败');
  return response.json();
}).then(data => {
  map = data;
  window.dispatchEvent(new CustomEvent('campus-map-ready', {detail: map}));
  if (!map.scenarios) map.scenarios = [{name: '默认校园', agents: [{start: map.default_start, goal: map.default_goal}]}];
  $('#mapSize').textContent = `${map.width} × ${map.height} 米`;
  $('#scenario').replaceChildren(...map.scenarios.map((scenario, index) => new Option(scenario.name, index)));
  $('#scenario').value = String(map.scenarios.findIndex(scenario => scenario.name.startsWith('立体校园')));
  $('#search').disabled = false;
  $('#reset').disabled = false;
  loadScenario();
}).catch(error => status('无法加载地图：' + error.message));
