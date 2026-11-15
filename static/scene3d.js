// Orthographic isometric projection. Heights are exaggerated for legibility.
window.drawCampus3D = function(canvas, map, agents, paths, tick, selected, showRoutes, obstacles, radius, bodyHeight, pedestrians = []) {
  const ctx = canvas.getContext('2d');
  const scale = Math.min(canvas.width / (map.width + map.height * .55 + 20), canvas.height / ((map.width + map.height) * .35 + 45));
  const project = ([x, y, z = 0]) => [(x - y * .55 + map.height * .55 + 10) * scale,
                                    ((x + y) * .35 - z * 2.5 + 25) * scale];
  const palette = ['#177448', '#ce6936', '#386fc2', '#a64ca1', '#b5901c', '#187e88', '#c14a67', '#7761bb', '#825836', '#456855'];
  const polygon = (points, fill, stroke = '#ffffff66') => {
    ctx.beginPath(); points.map(project).forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
    ctx.closePath(); ctx.fillStyle = fill; ctx.fill(); ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.stroke();
  };
  ctx.fillStyle = '#eef5fb'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  polygon([[0,0], [map.width,0], [map.width,map.height], [0,map.height]], '#e7f0f7');
  for (const road of map.roads || []) {
    const [[ax,ay],[bx,by]] = road.points;
    const length = Math.hypot(bx-ax,by-ay) || 1;
    const nx = -(by-ay) * road.width / (2*length);
    const ny = (bx-ax) * road.width / (2*length);
    polygon([[ax+nx,ay+ny,0],[bx+nx,by+ny,0],
      [bx-nx,by-ny,0],[ax-nx,ay-ny,0]], '#4b535c', '#69737b');
    ctx.save(); ctx.setLineDash([8,7]); ctx.lineWidth = 1.6;
    ctx.strokeStyle = '#f3ca50'; ctx.beginPath();
    [road.points[0],road.points[1]].map(project).forEach(([x,y],index) => index ? ctx.lineTo(x,y) : ctx.moveTo(x,y));
    ctx.stroke(); ctx.restore();
  }
  const drawPath = (path, color) => {
    ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 3;
    path.map(project).forEach(([x,y], i) => i ? ctx.lineTo(x,y) : ctx.moveTo(x,y)); ctx.stroke();
  };
  const objects = map.shapes.map(shape => ({depth: Math.max(...shape.points.map(p => p[0] + p[1])), draw() {
    const height = shape.kind === 'building' ? 7 : shape.kind === 'green' ? .6 : .15;
    const color = {building:'#e7b989', green:'#84bd83', water:'#91cfea', stairs:'#dba875'}[shape.kind];
    if (shape.kind === 'building') {
      shape.points.forEach(([x,y], i) => {
        const b = shape.points[(i+1)%shape.points.length];
        polygon([[x,y,0], [...b,0], [...b,height], [x,y,height]], '#c98d5f');
      });
    }
    polygon(shape.points.map(p => [...p,height]), color);
  }}));
  for (const lane of map.lanes || []) {
    const cells = lane.cells;
    const centerY = lane.label_position[1] + .5;
    objects.push({depth: Math.max(...cells.map(([x, y]) => x + y)), draw() {
      cells.forEach(([x, y]) => polygon([[x,y,0],[x+1,y,0],[x+1,y+1,0],[x,y+1,0]], '#4b535c', '#ffffff18'));
      const marking = lane.label.includes('斜向')
        ? [[100.5,82.5,0],[160.5,112.5,0]]
        : [[13.5,centerY,0],[75.5,centerY,0]];
      ctx.save(); ctx.setLineDash([8,7]); ctx.lineWidth = 2.4; ctx.strokeStyle = '#f3ca50';
      ctx.beginPath(); marking.map(project).forEach(([x,y], index) => index ? ctx.lineTo(x,y) : ctx.moveTo(x,y)); ctx.stroke(); ctx.restore();
    }});
  }
  const bridge = map.bridge;
  const z = x => x < bridge.plateau_start ? (x-bridge.start)*bridge.height/(bridge.plateau_start-bridge.start)
    : x > bridge.plateau_end ? (bridge.end-x)*bridge.height/(bridge.end-bridge.plateau_end) : bridge.height;
  // Draw the ground paths before the bridge deck, so the deck occludes them.
  if (showRoutes) paths.forEach(result => {
    const chunks = []; let chunk = [];
    result.path.forEach(point => { if ((point[2] || 0) === 0) chunk.push(point); else { if(chunk.length) chunks.push(chunk); chunk=[]; } });
    if(chunk.length) chunks.push(chunk);
    chunks.forEach(path => drawPath(path, palette[Number(result.id)-1]));
  });
  for (const [a,b] of [[bridge.start,bridge.plateau_start],[bridge.plateau_start,bridge.plateau_end],[bridge.plateau_end,bridge.end]]) {
    objects.push({depth:b+bridge.y_max, draw() {
      polygon([[a,bridge.y_min,z(a)],[b,bridge.y_min,z(b)],[b,bridge.y_max+1,z(b)],[a,bridge.y_max+1,z(a)]], '#515960');
      polygon([[a,bridge.y_max+1,z(a)],[b,bridge.y_max+1,z(b)],[b,bridge.y_max+1,z(b)-bridge.thickness],[a,bridge.y_max+1,z(a)-bridge.thickness]], '#383f46');
      ctx.save(); ctx.setLineDash([8,7]); ctx.lineWidth=2.4; ctx.strokeStyle='#f3ca50'; ctx.beginPath();
      const centerY = (bridge.y_min + bridge.y_max + 1) / 2;
      const steps = Math.max(2, Math.ceil((b - a) / 4));
      for (let i = 0; i <= steps; i++) {
        const x = a + (b - a) * i / steps, point = project([x, centerY, z(x)]);
        if (i) ctx.lineTo(point[0], point[1]); else ctx.moveTo(point[0], point[1]);
      }
      ctx.stroke(); ctx.restore();
    }});
  }
  objects.sort((a,b)=>a.depth-b.depth).forEach(object=>object.draw());
  obstacles.forEach(([x,y]) => polygon([[x,y,0],[x+1,y,0],[x+1,y+1,0],[x,y+1,0]],'#d67067'));
  if (showRoutes) paths.forEach(result => {
    const elevated = result.path.filter(p => (p[2] || 0) > 0);
    if(elevated.length) drawPath(elevated, palette[Number(result.id)-1]);
  });
  agents.forEach((agent,index) => {
    const result = paths.find(p=>Number(p.id)===index+1);
    const point = result ? result.path[Math.min(tick,result.path.length-1)] : agent.start;
    const [x,y] = project(point), [gx,gy] = project(agent.goal);
    ctx.strokeStyle=palette[index];ctx.lineWidth=2;ctx.strokeRect(gx-5,gy-5,10,10);
    const size = Math.max(3,radius*scale), rise = Math.max(3,bodyHeight*2.5*scale);
    ctx.fillStyle=palette[index];ctx.fillRect(x-size,y-rise,size*2,rise);
    ctx.beginPath();ctx.ellipse(x,y-rise,size,size*.5,0,0,Math.PI*2);ctx.fill();
    ctx.font=`${selected===index?'bold ':''}13px sans-serif`;ctx.textAlign='center';ctx.fillText(index+1,x,y-rise-8);
  });
  pedestrians.forEach(pedestrian => {
    const point = pedestrian.path[Math.min(tick, pedestrian.path.length - 1)];
    const [x,y] = project(point);
    ctx.fillStyle = '#263b47';
    ctx.beginPath(); ctx.arc(x, y - 5, 4, 0, Math.PI * 2); ctx.fill();
    ctx.fillRect(x - 2, y - 2, 4, 8);
  });
  ctx.fillStyle='#536f83';ctx.font='16px sans-serif';ctx.textAlign='left';
  ctx.fillText('立体投影 · 高度放大 2.5 倍 · 桥高 6 米',20,25);
};
