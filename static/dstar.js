let campusMap = null;
let session = null;
const element = id => document.getElementById(id);
const number = id => Number(element(id).value);
function render() {
  if (!campusMap) return;
  const path = session?.path || [];
  window.drawCampus3D(element('dstarMap'), campusMap,
    session ? [{start: session.start, goal: session.goal}] : [],
    path.length ? [{id: 1, path}] : [], 0, 0, true,
    session?.temporary_obstacles || [], .5, 1.2, []);
  for (const id of ['block', 'unblock', 'advance']) element(id).disabled = !session;
  if (session) element('dstarStatus').textContent = session.found
    ? `D* Lite：路线 ${path.length} 个位置，更新搜索 ${session.explored} 个状态，耗时 ${session.planning_ms} ms。`
    : `当前道路不可达；本次搜索 ${session.explored} 个状态。`;
}
async function post(path, body) {
  const response = await fetch(path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const value = await response.json();
  if (!response.ok) throw Error(value.error || '规划失败');
  return value;
}
async function act(work) {
  try { element('dstarStatus').textContent = '正在计算…'; session = await work(); render(); }
  catch (error) { element('dstarStatus').textContent = error.message; }
}
element('begin').addEventListener('click', () => act(() => post('/api/dstar/sessions', {
  start:[number('startX'),number('startY')], goal:[number('goalX'),number('goalY')], use_terrain:true
})));
for (const [id, blocked] of [['block', true], ['unblock', false]])
  element(id).addEventListener('click', () => act(() => post(`/api/dstar/sessions/${session.session_id}/update`, {
    changes:[{x:number('cellX'),y:number('cellY'),blocked}]
  })));
element('advance').addEventListener('click', () => {
  if (!session?.found || session.path.length < 2) return;
  const [x,y] = session.path[1];
  act(() => post(`/api/dstar/sessions/${session.session_id}/update`, {start:[x,y]}));
});
fetch('/api/map').then(response => response.json()).then(map => {
  campusMap = map; element('dstarStatus').textContent = `地图已加载：${map.width} × ${map.height}。`; render();
}).catch(error => {element('dstarStatus').textContent = error.message;});
