function paintIndoor(canvas, floor, robots, car, tick) {
  const ctx = canvas.getContext('2d');
  const unit = 24;
  const originX = 42;
  const originY = 38;
  const rect = (x, y, width, height, color) => {
    ctx.fillStyle = color;
    ctx.fillRect(originX + x * unit, originY + y * unit, width * unit, height * unit);
  };
  ctx.fillStyle = '#eef5fb';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  rect(0, 0, 30, 18, '#e7f0f7');
  rect(0, 8, 30, 3, '#4b535c');
  rect(13, 9, 4, 9, '#4b535c');
  ctx.strokeStyle = '#f3ca50'; ctx.lineWidth = 2; ctx.setLineDash([10, 8]);
  ctx.beginPath(); ctx.moveTo(originX, originY + 9.5 * unit); ctx.lineTo(originX + 30 * unit, originY + 9.5 * unit); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(originX + 14.5 * unit, originY + 11 * unit); ctx.lineTo(originX + 14.5 * unit, originY + 18 * unit); ctx.stroke(); ctx.setLineDash([]);
  for (const x of [4, 12, 20]) {
    rect(x, 1, 6, 6, '#84bd83');
    rect(x + 2, 7, 2, 1, '#e7f0f7');
  }
  rect(3, 8, 1, 3, '#e7b989');
  rect(27, 8, 1, 3, '#e7b989');
  rect(15, 8, 1, 3, '#91cfea');
  ctx.fillStyle = '#52687a';
  ctx.font = '16px sans-serif';
  for (const [label, x, y] of [['楼梯 A', 1, 12], ['楼梯 B', 25, 12],
                               ['电梯厅', 12, 12], ['房间', 6, 4], ['房间', 24, 4]]) {
    ctx.fillText(label, originX + x * unit, originY + y * unit);
  }
  ctx.font = 'bold 19px sans-serif';
  ctx.fillText(`${floor} 楼`, 38, 27);
  if (!car) return;
  for (const robot of robots) {
    const point = robot.path[Math.min(tick, robot.path.length - 1)];
    if (Math.abs(point[2] - floor) > .2) continue;
    const x = originX + point[0] * unit;
    const y = originY + point[1] * unit;
    ctx.fillStyle = robot.id === 1 ? '#177448' : '#ce6936';
    ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = 'white'; ctx.font = 'bold 13px sans-serif';
    ctx.textAlign = 'center'; ctx.fillText(robot.id, x, y + 4); ctx.textAlign = 'left';
  }
  ctx.fillStyle = '#d8eaf5';
  ctx.fillRect(800, 65, 46, 326);
  ctx.fillStyle = '#7198b4';
  const carY = 357 - (car.floor - 1) * 135;
  ctx.fillRect(803, carY, 40, 30);
  ctx.fillStyle = '#52687a'; ctx.font = '14px sans-serif';
  ctx.fillText(`电梯 ${car.floor.toFixed(1)} 楼`, 750, 423);
  ctx.fillText(`${car.phase} · 空位 ${car.free_places}`, 735, 444);
}
