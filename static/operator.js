const operatorTasks = document.querySelector('#operatorTasks');

async function loadOperatorTasks() {
  try {
    const response = await fetch('/api/operator/tasks');
    if (!response.ok) throw Error('任务列表读取失败');
    const tasks = await response.json();
    if (!tasks.length) {
      operatorTasks.textContent = '当前没有配送请求。';
      return;
    }
    const table = document.createElement('table');
    const header = table.createTHead().insertRow();
    for (const title of ['任务', '目标', '模拟费用', '状态']) {
      const cell = document.createElement('th');
      cell.textContent = title;
      header.append(cell);
    }
    const body = table.createTBody();
    for (const task of tasks.slice().reverse()) {
      const row = body.insertRow();
      for (const value of [task.item, `${task.building} · 三楼房间 ${task.room}`,
                           `${task.price.toFixed(2)} 模拟元`, task.status]) {
        row.insertCell().textContent = value;
      }
    }
    operatorTasks.replaceChildren(table);
  } catch (error) {
    operatorTasks.textContent = error.message;
  }
}

document.querySelector('#operatorRefresh').addEventListener('click', loadOperatorTasks);
loadOperatorTasks();
setInterval(loadOperatorTasks, 5000);
