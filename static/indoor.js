const indoor = {
  canvas: document.querySelector('#indoorCanvas'),
  result: null,
  tick: 0,
  timer: null
};
const indoorElement = id => document.querySelector('#' + id);

window.addEventListener('campus-map-ready', event => {
  const buildings = event.detail.shapes.filter(shape => shape.kind === 'building');
  indoorElement('indoorBuilding').replaceChildren(
    ...buildings.map(shape => new Option(shape.label, shape.label))
  );
  indoorElement('indoorPlan').disabled = false;
  drawIndoor();
});

function stopIndoor() {
  clearInterval(indoor.timer);
  indoor.timer = null;
  indoorElement('indoorPlay').textContent = '播放';
}

function drawIndoor() {
  const floor = Number(indoorElement('indoorFloor').value);
  const car = indoor.result?.elevator[Math.min(indoor.tick, indoor.result.elevator.length - 1)];
  paintIndoor(indoor.canvas, floor, indoor.result?.robots || [], car, indoor.tick);
}

indoorElement('indoorPlan').addEventListener('click', async () => {
  stopIndoor();
  const crowd = Number(indoorElement('indoorCrowd').value);
  const seed = Number(indoorElement('indoorSeed').value);
  if (!Number.isInteger(crowd) || crowd < 0 || crowd > 30 ||
      !Number.isInteger(seed) || seed < 0 || seed > 2147483647) {
    indoorElement('indoorStatus').textContent = '请检查候梯行人数量和随机种子。';
    return;
  }
  const button = indoorElement('indoorPlan');
  button.disabled = true;
  indoorElement('indoorStatus').textContent = '正在模拟电梯与候梯队列…';
  try {
    const response = await fetch('/api/indoor', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({building: indoorElement('indoorBuilding').value,
                            crowd, seed, can_climb: indoorElement('indoorClimb').checked})
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.error || '室内规划失败');
    indoor.result = result;
    indoor.tick = 0;
    const timeline = indoorElement('indoorTimeline');
    timeline.max = result.makespan_steps;
    timeline.value = 0;
    timeline.disabled = false;
    indoorElement('indoorPlay').disabled = false;
    indoorElement('indoorFloor').value = '1';
    indoorElement('indoorResults').textContent = result.robots.map(robot =>
      `机器人 ${robot.id} 走${robot.route}，第 ${robot.arrival_step} 步到达`
    ).join(' · ');
    indoorElement('indoorStatus').textContent = `${result.building} · ${crowd} 名行人候梯 · 电梯容量 ${result.capacity} 人位`;
    indoorElement('indoorTick').textContent = `第 0 / ${result.makespan_steps} 步`;
    drawIndoor();
  } catch (error) {
    indoorElement('indoorStatus').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

function setIndoorTick(tick) {
  indoor.tick = tick;
  indoorElement('indoorTimeline').value = tick;
  indoorElement('indoorTick').textContent = `第 ${tick} / ${indoor.result.makespan_steps} 步`;
  drawIndoor();
}
indoorElement('indoorFloor').addEventListener('change', drawIndoor);
for (const id of ['indoorBuilding', 'indoorCrowd', 'indoorSeed', 'indoorClimb']) {
  indoorElement(id).addEventListener('change', () => {
    stopIndoor();
    indoor.result = null;
    indoor.tick = 0;
    indoorElement('indoorTimeline').disabled = true;
    indoorElement('indoorPlay').disabled = true;
    indoorElement('indoorResults').textContent = '';
    indoorElement('indoorStatus').textContent = '参数已更改，请重新规划室内配送。';
    drawIndoor();
  });
}
indoorElement('indoorTimeline').addEventListener('input', () => {
  stopIndoor();
  setIndoorTick(Number(indoorElement('indoorTimeline').value));
});
indoorElement('indoorPlay').addEventListener('click', () => {
  if (indoor.timer) return stopIndoor();
  if (indoor.tick >= indoor.result.makespan_steps) setIndoorTick(0);
  indoorElement('indoorPlay').textContent = '暂停';
  indoor.timer = setInterval(() => {
    setIndoorTick(Math.min(indoor.tick + 1, indoor.result.makespan_steps));
    if (indoor.tick >= indoor.result.makespan_steps) stopIndoor();
  }, 140);
});
