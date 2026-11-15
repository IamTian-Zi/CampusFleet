import { useMemo, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { LayoutChangeEvent } from 'react-native';

import type { CampusMap, Task, TaskProgress } from '@/lib/api';

type Props = { map: CampusMap | null; task: Task; progress: TaskProgress | null };
type Point = { x: number; y: number };

const COLORS: Record<string, string> = {
  building: '#e7b989', green: '#84bd83', water: '#91cfea', stairs: '#dba875',
};

function bounds(points: number[][]) {
  const xs = points.map(point => point[0]);
  const ys = points.map(point => point[1]);
  return { left: Math.min(...xs), right: Math.max(...xs), top: Math.min(...ys), bottom: Math.max(...ys) };
}

export function CampusRouteMap({ map, task, progress }: Props) {
  const [width, setWidth] = useState(0);
  const height = 300;
  const worldWidth = map?.width ?? 300;
  const worldHeight = map?.height ?? 200;
  const unit = width > 0
    ? Math.min((width - 28) / (worldWidth + worldHeight), (height - 70) / ((worldWidth + worldHeight) * 0.43))
    : 0;
  const planeWidth = (worldWidth + worldHeight) * unit;
  const planeHeight = (worldWidth + worldHeight) * unit * 0.43;
  const offsetX = (width - planeWidth) / 2;
  const offsetY = (height - planeHeight) / 2 + 12;
  const pointAt = (point: number[]): Point => ({
    x: offsetX + (point[0] - point[1] + worldHeight) * unit,
    y: offsetY + (point[0] + point[1]) * unit * 0.43,
  });

  const routePoints = useMemo(() => {
    const path = task.outdoor.path ?? [];
    const stride = Math.max(1, Math.ceil(path.length / 180));
    const points = path.filter((_, index) => index % stride === 0);
    if (path.length && points[points.length - 1] !== path[path.length - 1]) points.push(path[path.length - 1]);
    return points;
  }, [task.outdoor.path]);

  function onLayout(event: LayoutChangeEvent) { setWidth(event.nativeEvent.layout.width); }
  if (!unit) return <View onLayout={onLayout} style={[styles.map, { height }]} />;

  const current = progress && progress.phase !== '建筑室内' && progress.phase !== '进入建筑'
    ? pointAt([progress.position.x, progress.position.y])
    : pointAt(progress ? task.entrance : task.start);

  const terrain = (map?.shapes ?? []).map((shape, index) => {
    const color = COLORS[shape.kind];
    if (!color || shape.points.length < 3) return null;
    const box = bounds(shape.points);
    const center = pointAt([(box.left + box.right) / 2, (box.top + box.bottom) / 2]);
    const span = Math.max(box.right - box.left, box.bottom - box.top);
    const footprint = Math.max(shape.kind === 'building' ? 17 : 6, (box.right - box.left + box.bottom - box.top) * unit * 0.72);
    const depth = shape.kind === 'building' ? Math.max(9, Math.min(27, span * unit * 0.62)) : Math.max(4, footprint * 0.23);
    return (
      <View key={`terrain-${index}`} style={[styles.feature, { left: center.x - footprint / 2, top: center.y - footprint * 0.22 - depth, width: footprint, height: footprint * 0.44 }]}>
        {shape.kind === 'building' ? <>
          <View style={[styles.buildingSide, { backgroundColor: '#bf9067', height: depth, bottom: -depth + 2 }]} />
          <View style={[styles.buildingSideRight, { backgroundColor: '#d0a077', height: depth, bottom: -depth + 2 }]} />
          <View style={[styles.buildingTop, { backgroundColor: color }]} />
          {footprint > 30 ? <Text numberOfLines={1} style={styles.buildingLabel}>{shape.label}</Text> : null}
        </> : shape.kind === 'green' ? <View style={[styles.greenPatch, { backgroundColor: color }]} />
          : <View style={[styles.waterPatch, { backgroundColor: color }]} />}
      </View>
    );
  });

  const routeSegments = routePoints.slice(1).map((point, index) => {
    const start = pointAt(routePoints[index]);
    const end = pointAt(point);
    const length = Math.hypot(end.x - start.x, end.y - start.y);
    const angle = Math.atan2(end.y - start.y, end.x - start.x);
    return <View key={`route-${index}`} style={[styles.route, { width: Math.max(2, length + 1), left: (start.x + end.x - length) / 2, top: (start.y + end.y) / 2 - 2, transform: [{ rotate: `${angle}rad` }] }]} />;
  });

  const roadSegments = (map?.roads ?? []).map((road, index) => {
    const a = pointAt(road.points[0]);
    const b = pointAt(road.points[1]);
    const length = Math.hypot(b.x - a.x, b.y - a.y);
    const angle = Math.atan2(b.y - a.y, b.x - a.x);
    const thickness = Math.max(3, road.width * unit * 0.55);
    return <View key={`road-${index}`} style={[styles.road, { left: (a.x + b.x - length) / 2,
      top: (a.y + b.y - thickness) / 2, width: length + thickness, height: thickness,
      transform: [{ rotate: `${angle}rad` }] }]} />;
  });

  const start = pointAt(task.start);
  const goal = pointAt(task.entrance);
  return (
    <View onLayout={onLayout} style={[styles.map, { height }]}>
      <View style={[styles.ground, { left: offsetX, top: offsetY, width: planeWidth, height: planeHeight }]} />
      {roadSegments}
      {terrain}
      {routeSegments}
      <View style={[styles.marker, styles.startDot, { left: start.x - 4, top: start.y - 4 }]} />
      <View style={[styles.marker, styles.goalDot, { left: goal.x - 5, top: goal.y - 5 }]} />
      <View style={[styles.robot, { left: current.x - 11, top: current.y - 22 }]}>
        <View style={styles.robotBeacon} /><Text style={styles.robotText}>R</Text>
      </View>
      <View style={styles.mapCaption}><Text style={styles.captionText}>校园立体路线</Text></View>
      <Text style={styles.mapHint}>等轴测示意 · 室外规划路段</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  map: { width: '100%', overflow: 'hidden', borderRadius: 18, backgroundColor: '#eaf3f8', position: 'relative' },
  ground: { position: 'absolute', backgroundColor: '#dcecf2', borderRadius: 5 },
  road: { position: 'absolute', backgroundColor: '#4b535c', borderRadius: 2, borderTopColor: '#f3ca50', borderTopWidth: 1 },
  feature: { position: 'absolute', alignItems: 'center', justifyContent: 'center' },
  buildingSide: { position: 'absolute', left: 2, right: 2, borderBottomLeftRadius: 2, borderBottomRightRadius: 2 },
  buildingSideRight: { position: 'absolute', left: 4, right: 0, opacity: 0.8 },
  buildingTop: { position: 'absolute', left: 0, right: 0, top: 0, height: '100%', borderRadius: 5, borderColor: '#d7a473', borderWidth: 1, transform: [{ skewX: '-25deg' }] },
  buildingLabel: { position: 'absolute', color: '#684f3d', fontSize: 7, fontWeight: '800', top: 3, maxWidth: '90%' },
  greenPatch: { width: '90%', height: '72%', borderRadius: 15, borderWidth: 1, borderColor: '#6ea974' },
  waterPatch: { width: '96%', height: '78%', borderRadius: 15, borderWidth: 1, borderColor: '#75b9d4' },
  route: { position: 'absolute', height: 4, borderRadius: 4, backgroundColor: '#277e91', opacity: 0.96 },
  marker: { position: 'absolute', borderWidth: 2, borderColor: '#ffffff' },
  startDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: '#3d9c75' },
  goalDot: { width: 11, height: 11, borderRadius: 3, backgroundColor: '#e39a52' },
  robot: { position: 'absolute', width: 23, height: 27, borderRadius: 11, backgroundColor: '#237a91', borderWidth: 2, borderColor: '#ffffff', alignItems: 'center', justifyContent: 'center', elevation: 5 },
  robotBeacon: { position: 'absolute', width: 3, height: 9, backgroundColor: '#237a91', top: -8 },
  robotText: { color: '#ffffff', fontSize: 9, fontWeight: '900' },
  mapCaption: { position: 'absolute', left: 10, top: 9, paddingHorizontal: 9, paddingVertical: 5, borderRadius: 8, backgroundColor: '#ffffffdd' },
  captionText: { color: '#536e7f', fontSize: 10, fontWeight: '700' },
  mapHint: { position: 'absolute', right: 9, bottom: 8, color: '#78909d', backgroundColor: '#ffffffcc', borderRadius: 6, paddingHorizontal: 6, paddingVertical: 3, fontSize: 8 },
});
