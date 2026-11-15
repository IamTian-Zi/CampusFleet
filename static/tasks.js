const taskElement = id => document.querySelector('#' + id);
const qrTicket = new URLSearchParams(location.hash.slice(1)).get('ticket') || '';
let authToken = qrTicket || localStorage.getItem('campusfleet_token') || '';
function authFetch(url, options = {}) {
  return window.fetch(url, {...options, headers: {...options.headers,
    ...(authToken ? {Authorization: `Bearer ${authToken}`} : {})}});
}
function signedIn(user) {
  taskElement('authPanel').hidden = Boolean(user);
  taskElement('clientMain').hidden = !user;
  if (user) {
    taskElement('signedInName').textContent = `当前用户：${user.username}`;
    refreshTaskHistory().catch(error => { taskElement('taskStatus').textContent = error.message; });
  }
}
async function submitAuth(mode) {
  const username = taskElement('authUsername').value.trim();
  const password = taskElement('authPassword').value;
  taskElement('authError').textContent = '';
  try {
    const response = await window.fetch(`/api/auth/${mode}`, {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username, password})});
    const result = await response.json();
    if (!response.ok) throw Error(result.error || '登录失败');
    authToken = result.token;
    localStorage.setItem('campusfleet_token', authToken);
    taskElement('authPassword').value = '';
    signedIn(result.user);
  } catch (error) { taskElement('authError').textContent = error.message; }
}
taskElement('authLogin').addEventListener('click', () => submitAuth('login'));
taskElement('authRegister').addEventListener('click', () => submitAuth('register'));
taskElement('authLogout').addEventListener('click', async () => {
  await authFetch('/api/auth/logout', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'}).catch(() => {});
  authToken = ''; localStorage.removeItem('campusfleet_token');
  stopTracking(); taskView.current = null; taskView.latestTaskId = null;
  if (taskElement('paymentDialog').open) taskElement('paymentDialog').close();
  taskElement('taskHistory').replaceChildren(); signedIn(null);
});
if (authToken) authFetch('/api/auth/me').then(async response => {
  if (!response.ok) throw Error('登录已失效');
  signedIn(await response.json());
}).catch(() => { authToken = ''; localStorage.removeItem('campusfleet_token'); signedIn(null); });
const checkoutMode = location.pathname === '/checkout';
const taskView = {map: null, current: null, tick: 0, timer: null, poller: null,
  trackingVersion: 0, shareInfo: null, shareError: '', shareLoaded: false,
  latestTaskId: null, followLatest: true};
function simulatedUserId() {
  let id = localStorage.getItem('campusfleet_user_id');
  if (!id) {
    id = 'CF-U-' + (globalThis.crypto?.randomUUID?.().slice(0, 8) || Math.random().toString(36).slice(2, 10)).toUpperCase();
    localStorage.setItem('campusfleet_user_id', id);
  }
  return id;
}

function drawPaymentQr(url) {
  const canvas = taskElement('paymentQr');
  const ctx = canvas.getContext('2d');
  if (!url) {
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#718798'; ctx.font = '14px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText('暂不可扫码', canvas.width / 2, canvas.height / 2);
    return;
  }
  const matrix = window.toQR(url);
  const size = Math.sqrt(matrix.length);
  const unit = canvas.width / (size + 8);
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#172c38';
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    if (matrix[y * size + x]) ctx.fillRect(Math.floor((x + 4) * unit), Math.floor((y + 4) * unit),
      Math.ceil(unit), Math.ceil(unit));
  }
}

function renderPayment(task) {
  if (taskView.ticketOrderId !== task.id) taskView.checkoutUrl = null;
  taskElement('paymentOrder').textContent = task.id;
  taskElement('paymentTime').textContent = new Date(task.created_at * 1000).toLocaleString('zh-CN');
  taskElement('paymentUser').textContent = task.user_id;
  taskElement('paymentDestination').textContent = `${task.building} · 三楼房间 ${task.room}`;
  taskElement('paymentAmount').textContent = `${task.price.toFixed(2)} ${task.currency}`;
  taskElement('paymentRouteNote').textContent = `室外 ${task.outdoor.distance_m} 米 · 路线版本 ${task.route_revision + 1} · 可在确认前重新规划`;
  const baseUrl = taskView.shareInfo?.base_url;
  let url = taskView.checkoutUrl || null;
  const link = taskElement('paymentLink');
  if (url) link.href = url;
  else link.removeAttribute('href');
  link.textContent = url || '等待可供手机访问的局域网地址';
  drawPaymentQr(url);
  if (baseUrl && !checkoutMode && taskView.ticketOrderId !== task.id) {
    taskView.ticketOrderId = task.id;
    authFetch(`/api/tasks/${encodeURIComponent(task.id)}/checkout-ticket`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'
    }).then(async response => {
      const result = await response.json();
      if (!response.ok) throw Error(result.error || '付款链接生成失败');
      if (taskView.current?.id !== task.id) return;
      taskView.checkoutUrl = `${baseUrl}/checkout?order=${encodeURIComponent(task.id)}#ticket=${encodeURIComponent(result.ticket)}`;
      taskView.ticketOrderId = task.id;
      const link = taskElement('paymentLink'); link.href = taskView.checkoutUrl; link.textContent = taskView.checkoutUrl;
      drawPaymentQr(taskView.checkoutUrl);
    }).catch(error => {
      taskView.ticketOrderId = null;
      taskView.shareError = error.message;
      taskElement('paymentNetworkNote').textContent = error.message;
    });
  }
  taskElement('paymentNetworkNote').textContent = taskView.shareError
    || (!taskView.shareLoaded ? '正在获取电脑的局域网地址…'
      : !baseUrl ? '暂未找到局域网 IPv4 地址，可设置 CAMPUSFLEET_SHARE_IP 后重启服务。'
      : !taskView.shareInfo.lan_enabled
        ? '服务器当前仅监听本机。扫码前请用 CAMPUSFLEET_HOST=0.0.0.0 重启服务。'
        : '二维码使用电脑当前的局域网 IPv4 地址。');
  if (taskView.map) window.drawCampus3D(taskElement('paymentMap'), taskView.map,
    [{start: task.start, goal: task.entrance}], [{id: 1, path: task.outdoor.path}],
    0, 0, true, [], .5, 1.2, []);
}

function openPayment(task) {
  renderPayment(task);
  taskElement('taskPay').hidden = !checkoutMode;
  taskElement('paymentStatus').textContent = checkoutMode
    ? '仅供展示使用 · 不会实际扣款。'
    : '请用手机扫描二维码，在手机上确认模拟付款。';
  const dialog = taskElement('paymentDialog');
  if (!dialog.open) dialog.showModal();
}

authFetch('/api/map').then(response => {
  if (!response.ok) throw Error('地图读取失败');
  return response.json();
}).then(map => {
  taskView.map = map;
  taskElement('taskBuilding').replaceChildren(
    ...map.shapes.filter(shape => shape.kind === 'building')
      .map(shape => new Option(shape.label, shape.label))
  );
  taskElement('taskCreate').disabled = false;
  drawTask();
  if (taskView.current?.status === '待模拟支付') renderPayment(taskView.current);
}).catch(error => {
  taskElement('taskStatus').textContent = error.message;
});

authFetch('/api/share-url').then(async response => {
  const result = await response.json();
  if (!response.ok) throw Error(result.error || '局域网地址读取失败');
  return result;
}).then(info => {
  taskView.shareInfo = info;
  taskView.shareLoaded = true;
  if (taskView.current?.status === '待模拟支付') renderPayment(taskView.current);
}).catch(error => {
  taskView.shareError = error.message;
  taskView.shareLoaded = true;
  if (taskView.current?.status === '待模拟支付') renderPayment(taskView.current);
});

function taskStop() {
  clearInterval(taskView.timer);
  taskView.timer = null;
  taskElement('taskPlay').textContent = '回放配送过程';
}

function stopTracking() {
  clearTimeout(taskView.poller);
  taskView.poller = null;
  taskView.trackingVersion++;
}

function taskSummary(task) {
  taskElement('taskReceipt').hidden = false;
  taskElement('taskReceipt').textContent =
    `${task.item} → ${task.building}三楼房间 ${task.room} · 室外路线 ${task.outdoor.distance_m} 米 · 模拟费用 ${task.price.toFixed(2)} ${task.currency} · ${task.status}`;
  taskElement('paymentOpen').hidden = task.status !== '待模拟支付';
  taskElement('taskTracking').hidden = task.status === '待模拟支付';
  taskElement('taskPlay').disabled = task.status !== '已送达';
  taskElement('taskTimeline').disabled = task.status !== '已送达';
  taskElement('taskTimeline').max = task.arrival_step;
  taskElement('taskTimeline').value = 0;
  taskElement('taskTick').textContent = `第 0 / ${task.arrival_step} 步`;
  taskElement('taskStatus').textContent = task.status === '待模拟支付'
    ? '申请已提交，请在弹窗中查看路线并确认模拟付款。'
    : task.status === '已送达' ? '配送模拟已送达，可重新查看回放。'
      : '支付成功，配送中。';
}

function showTaskProgress(progress) {
  taskElement('taskTracking').hidden = false;
  taskElement('taskRobot').textContent = `配送机器人 ${progress.robot_id}`;
  taskElement('taskPhase').textContent = progress.status === '已送达' ? '已送达'
    : progress.phase === '校园道路' ? '配送中' : '即将到达';
  const position = progress.position;
  taskElement('taskPosition').textContent = progress.status === '已送达'
      ? `${taskView.current.building}三楼房间 ${taskView.current.room} · 已送达`
    : progress.phase !== '校园道路'
      ? `${taskView.current.building}入口 · 即将送达三楼房间 ${taskView.current.room}`
      : `校园道路 · 坐标 (${position.x}, ${position.y})`;
  taskElement('taskProgress').value = progress.percent;
  taskElement('taskPercent').textContent = `${progress.percent}%`;
  taskElement('taskRemaining').textContent = progress.status === '已送达'
    ? '配送完成' : `模拟剩余约 ${progress.remaining_seconds} 秒`;
}

async function pollTaskProgress(version, taskId) {
  try {
    const response = await authFetch(`/api/tasks/${encodeURIComponent(taskId)}/progress`);
    const progress = await response.json();
    if (version !== taskView.trackingVersion || taskView.current?.id !== taskId) return;
    if (!response.ok) throw Error(progress.error || '进度读取失败');
    if (progress.route_revision !== taskView.current.route_revision) {
      const detailResponse = await authFetch(`/api/tasks/${encodeURIComponent(taskId)}`);
      const updated = await detailResponse.json();
      if (version !== taskView.trackingVersion || taskView.current?.id !== taskId) return;
      if (!detailResponse.ok) throw Error(updated.error || '更新路线失败');
      taskView.current = updated;
      taskSummary(updated);
      if (updated.status === '待模拟支付') renderPayment(updated);
      drawTask();
    }
    if (progress.status !== taskView.current.status) {
      taskView.current = {...taskView.current, status: progress.status};
      taskSummary(taskView.current);
    }
    if (progress.status !== '待模拟支付') {
      if (taskElement('paymentDialog').open) taskElement('paymentDialog').close();
      showTaskProgress(progress);
      setTaskTick(progress.tick);
    }
    if (progress.status === '已送达') {
      await refreshTaskHistory();
      return;
    }
  } catch (error) {
    if (version !== taskView.trackingVersion || taskView.current?.id !== taskId) return;
    taskElement('taskStatus').textContent = `进度暂时无法更新：${error.message}`;
  }
  if (version === taskView.trackingVersion && taskView.current?.id === taskId) {
    taskView.poller = setTimeout(() => pollTaskProgress(version, taskId), 500);
  }
}

function selectTask(task) {
  taskStop();
  stopTracking();
  taskView.current = task;
  taskView.tick = 0;
  taskSummary(task);
  drawTask();
  if (task.status === '待模拟支付') openPayment(task);
  else {
    if (taskElement('paymentDialog').open) taskElement('paymentDialog').close();
  }
  pollTaskProgress(taskView.trackingVersion, task.id);
}

async function loadTask(taskId) {
  stopTracking();
  const version = taskView.trackingVersion;
  const response = await authFetch(`/api/tasks/${encodeURIComponent(taskId)}`);
  const task = await response.json();
  if (!response.ok) throw Error(task.error || '任务读取失败');
  if (version === taskView.trackingVersion) selectTask(task);
}

async function taskRequest(url, body) {
  const response = await authFetch(url, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const result = await response.json();
  if (!response.ok) throw Error(result.error || '任务请求失败');
  return result;
}

async function refreshTaskHistory() {
  if (!authToken) return;
  const response = await authFetch('/api/tasks');
  if (!response.ok) return;
  const tasks = await response.json();
  const latestId = tasks[tasks.length - 1]?.id;
  const newOrder = latestId && latestId !== taskView.latestTaskId;
  taskView.latestTaskId = latestId || null;
  const container = taskElement('taskHistory');
  container.replaceChildren();
  for (const task of tasks.slice().reverse()) {
    const button = document.createElement('button');
    button.className = 'secondary';
    button.textContent = `${task.item} → ${task.building}房间 ${task.room} · ${task.status}`;
    button.addEventListener('click', async () => {
      try {
        taskView.followLatest = false;
        await loadTask(task.id);
      } catch (error) {
        taskElement('taskStatus').textContent = error.message;
      }
    });
    container.append(button);
  }
  const requestedId = new URLSearchParams(location.search).get('order');
  if (requestedId && !tasks.some(task => task.id === requestedId)) {
    taskElement('taskStatus').textContent = '订单不存在或服务已重启，请在电脑上重新申请。';
    return;
  }
  if (!taskView.current && latestId) {
    await loadTask(requestedId || latestId);
  } else if (!checkoutMode && taskView.followLatest && newOrder && taskView.current?.id !== latestId) {
    await loadTask(latestId);
  }
}

taskElement('taskCreate').addEventListener('click', async () => {
  taskStop();
  stopTracking();
  const button = taskElement('taskCreate');
  button.disabled = true;
  taskElement('taskStatus').textContent = '正在计算室外路线、建筑入口和室内送达时间…';
  try {
    const result = await taskRequest('/api/tasks', {
      item: taskElement('taskItem').value,
      building: taskElement('taskBuilding').value,
      room: taskElement('taskRoom').value,
      user_id: simulatedUserId()
    });
    taskView.followLatest = true;
    selectTask(result);
    await refreshTaskHistory();
  } catch (error) {
    taskElement('taskStatus').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

taskElement('paymentOpen').addEventListener('click', () => {
  if (taskView.current?.status === '待模拟支付') openPayment(taskView.current);
});
taskElement('paymentClose').addEventListener('click', () => taskElement('paymentDialog').close());
taskElement('paymentReplan').addEventListener('click', async () => {
  const task = taskView.current;
  if (!task || task.status !== '待模拟支付') return;
  const button = taskElement('paymentReplan');
  button.disabled = true;
  taskElement('paymentStatus').textContent = '正在重新规划室外路线…';
  try {
    const result = await taskRequest(`/api/tasks/${encodeURIComponent(task.id)}/replan`, {});
    if (taskView.current?.id !== task.id) return;
    taskView.current = result;
    taskSummary(result);
    renderPayment(result);
    drawTask();
    taskElement('paymentStatus').textContent = checkoutMode
      ? '路线已更新，请核对后确认模拟扣款。'
      : '路线已更新，请用手机扫码确认模拟付款。';
  } catch (error) {
    taskElement('paymentStatus').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

taskElement('taskPay').addEventListener('click', async () => {
  if (!checkoutMode) return;
  const task = taskView.current;
  if (!task || task.status !== '待模拟支付') return;
  const button = taskElement('taskPay');
  button.disabled = true;
  try {
    const result = await taskRequest(`/api/tasks/${encodeURIComponent(task.id)}/pay`, {});
    if (taskView.current?.id === task.id) selectTask(result);
    await refreshTaskHistory();
  } catch (error) {
    taskElement('paymentStatus').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

function drawTask() {
  const canvas = taskElement('taskCanvas');
  const ctx = canvas.getContext('2d');
  const task = taskView.current;
  ctx.fillStyle = '#eef5fb';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (!taskView.map) return;
  window.drawCampus3D(canvas, taskView.map,
    task ? [{start:task.start, goal:task.entrance}] : [],
    task ? [{id:1, path:task.outdoor.path}] : [],
    taskView.tick, 0, Boolean(task), [], .5, 1.2,
    task?.pedestrians || []);
  if (!task) return;
  const label = taskView.tick >= task.arrival_step ? '已送达'
    : taskView.tick >= task.outdoor.arrival_step ? '即将到达' : '室外配送中';
  ctx.fillStyle = '#233f34'; ctx.font = '18px sans-serif';
  ctx.fillText(label, 20, 52);
}

function setTaskTick(tick) {
  taskView.tick = tick;
  taskElement('taskTimeline').value = tick;
  taskElement('taskTick').textContent = `第 ${tick} / ${taskView.current.arrival_step} 步`;
  drawTask();
}
taskElement('taskTimeline').addEventListener('input', () => {
  if (taskView.current?.status !== '已送达') return;
  taskStop();
  setTaskTick(Number(taskElement('taskTimeline').value));
});
taskElement('taskPlay').addEventListener('click', () => {
  if (taskView.current?.status !== '已送达') return;
  if (taskView.timer) return taskStop();
  if (taskView.tick >= taskView.current.arrival_step) setTaskTick(0);
  taskElement('taskPlay').textContent = '暂停';
  taskView.timer = setInterval(() => {
    setTaskTick(Math.min(taskView.tick + 1, taskView.current.arrival_step));
    if (taskView.tick >= taskView.current.arrival_step) {
      taskStop();
    }
  }, 140);
});

refreshTaskHistory().catch(() => {});
setInterval(() => refreshTaskHistory().catch(() => {}), 2000);
