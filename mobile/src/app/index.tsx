import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { CampusRouteMap } from '@/components/campus-route-map';
import { API_BASE_URL, authenticate, createTask, getCampusMap, getTask, getTaskProgress, listTasks, logout, payTask, replanTask, setAuthToken } from '@/lib/api';
import type { AuthUser, CampusMap, Task, TaskProgress } from '@/lib/api';

const ITEMS = ['教材', '文件', '包裹'];
const ROOMS = ['A', 'B'];

export default function HomeScreen() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [authBusy, setAuthBusy] = useState(false);
  const [map, setMap] = useState<CampusMap | null>(null);
  const [item, setItem] = useState(ITEMS[0]);
  const [building, setBuilding] = useState('');
  const [room, setRoom] = useState(ROOMS[0]);
  const [task, setTask] = useState<Task | null>(null);
  const [recentTasks, setRecentTasks] = useState<Task[]>([]);
  const [progress, setProgress] = useState<TaskProgress | null>(null);
  const [loadingMap, setLoadingMap] = useState(true);
  const [creating, setCreating] = useState(false);
  const [paying, setPaying] = useState(false);
  const [replanning, setReplanning] = useState(false);
  const [openingTaskId, setOpeningTaskId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('正在连接校园配送服务…');

  const buildings = useMemo(
    () => map?.shapes.filter(shape => shape.kind === 'building').map(shape => shape.label) ?? [],
    [map],
  );

  useEffect(() => {
    if (!user) return;
    let active = true;
    getCampusMap()
      .then(result => {
        if (!active) return;
        setMap(result);
        const firstBuilding = result.shapes.find(shape => shape.kind === 'building')?.label ?? '';
        setBuilding(firstBuilding);
        setMessage('已连接服务，可以创建一笔模拟配送订单。');
        setError('');
      })
      .catch(reason => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : '地图读取失败');
        setMessage('暂时无法加载校园地图。');
      })
      .finally(() => { if (active) setLoadingMap(false); });
    return () => { active = false; };
  }, [user]);

  useEffect(() => {
    if (!user) return;
    let active = true;
    const refresh = async () => {
      try {
        const orders = await listTasks();
        if (active) setRecentTasks(orders.slice().reverse());
      } catch {
        // The selected order has its own error message and retry loop.
      }
    };
    void refresh();
    const interval = setInterval(() => { void refresh(); }, 2000);
    return () => { active = false; clearInterval(interval); };
  }, [user]);

  const taskId = task?.id;
  const taskStatus = task?.status;
  const routeRevision = task?.route_revision;

  useEffect(() => {
    if (!user || !taskId) return;
    let active = true;
    let busy = false;

    const poll = async () => {
      if (busy) return;
      busy = true;
      try {
        const result = await getTaskProgress(taskId);
        if (!active) return;
        setProgress(result);
        if (result.status !== taskStatus || result.route_revision !== routeRevision) {
          const updated = await getTask(taskId);
          if (!active) return;
          setTask(current => current?.id === taskId ? updated : current);
          setMessage(result.status === '已送达' ? '已送达。'
            : result.status === '已模拟支付' ? '支付成功，配送中。'
              : '路线已在另一设备更新，请核对后付款。');
        }
        setError('');
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : '进度读取失败');
      } finally {
        busy = false;
      }
    };

    void poll();
    const interval = taskStatus === '已送达' ? null : setInterval(() => { void poll(); }, 500);
    return () => { active = false; if (interval) clearInterval(interval); };
  }, [user, taskId, taskStatus, routeRevision]);

  async function onAuthenticate(mode: 'login' | 'register') {
    setAuthBusy(true);
    setError('');
    try {
      const result = await authenticate(mode, username.trim(), password);
      setAuthToken(result.token);
      setUser(result.user);
      setPassword('');
      setMessage(`已登录：${result.user.username}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '账户操作失败');
    } finally { setAuthBusy(false); }
  }

  async function onLogout() {
    try { await logout(); } catch { /* Discard the local session even if offline. */ }
    setAuthToken(''); setUser(null); setTask(null); setProgress(null); setRecentTasks([]);
    setMessage('请登录后查看自己的订单。');
  }

  async function onCreateTask() {
    if (!building) return;
    setCreating(true);
    setError('');
    setMessage('正在规划室外路线和室内送达路线…');
    setProgress(null);
    try {
      const result = await createTask(item, building, room);
      setTask(result);
      setMessage('路线与模拟费用已生成；可直接在手机上确认模拟付款。');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '订单创建失败');
      setMessage('订单未能创建。');
    } finally {
      setCreating(false);
    }
  }

  async function onPay() {
    if (!task || task.status !== '待模拟支付') return;
    setPaying(true);
    setError('');
    try {
      const result = await payTask(task.id);
      setTask(result);
      setMessage('支付成功，配送中。');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '模拟支付失败');
      try {
        const updated = await getTask(task.id);
        setTask(current => current?.id === task.id ? updated : current);
      } catch { /* Keep the original payment error. */ }
    } finally {
      setPaying(false);
    }
  }

  async function onReplan() {
    if (!task || task.status !== '待模拟支付') return;
    setReplanning(true);
    setError('');
    try {
      const updated = await replanTask(task.id);
      setTask(current => current?.id === task.id ? updated : current);
      setProgress(null);
      setMessage('路线已更新，请核对后确认模拟付款。');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '重新规划失败');
      try {
        const updated = await getTask(task.id);
        setTask(current => current?.id === task.id ? updated : current);
      } catch { /* Keep the original replan error. */ }
    } finally {
      setReplanning(false);
    }
  }

  async function onOpenTask(taskIdToOpen: string) {
    setOpeningTaskId(taskIdToOpen);
    setError('');
    try {
      const selected = await getTask(taskIdToOpen);
      setTask(selected);
      setProgress(null);
      setMessage(selected.status === '待模拟支付'
        ? '已打开此订单，可直接在手机上确认模拟付款。'
        : selected.status === '已送达' ? '此订单已送达。' : '配送中，正在同步机器人位置。');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '订单读取失败');
    } finally {
      setOpeningTaskId(null);
    }
  }

  function startNewOrder() {
    setTask(null);
    setProgress(null);
    setError('');
    setMessage('选择物品和送达地点，生成配送方案。');
  }

  const percent = progress?.percent ?? 0;
  const phase = task?.status === '已送达' ? '已送达'
    : progress?.phase === '校园道路' ? '配送中'
      : progress ? '即将到达' : task?.status === '已模拟支付' ? '配送中' : '等待模拟付款';
  const positionText = progress?.phase === '建筑室内' || progress?.phase === '进入建筑'
    ? `${task?.building}入口 · 即将送达三楼房间 ${task?.room}`
    : progress
      ? `校园坐标 (${progress.position.x}, ${progress.position.y})`
      : task
        ? `起点 (${task.start[0]}, ${task.start[1]})`
        : '等待下单';

  if (!user) return (
    <SafeAreaView edges={['top']} style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}><View><Text style={styles.eyebrow}>CAMPUS DELIVERY</Text><Text style={styles.title}>CampusFleet</Text></View></View>
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>登录或注册</Text>
          <Text style={styles.mutedText}>登录后可在电脑和手机查看自己的历史订单。</Text>
          <TextInput style={styles.authInput} value={username} onChangeText={setUsername} autoCapitalize="none" autoComplete="username" placeholder="用户名（3–32 位字母、数字或下划线）" />
          <TextInput style={styles.authInput} value={password} onChangeText={setPassword} secureTextEntry autoComplete="password" placeholder="密码（至少 8 个字符）" />
          {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
          <Pressable accessibilityRole="button" disabled={authBusy} onPress={() => { void onAuthenticate('login'); }} style={[styles.primaryButton, authBusy && styles.disabled]}><Text style={styles.primaryButtonText}>登录</Text></Pressable>
          <Pressable accessibilityRole="button" disabled={authBusy} onPress={() => { void onAuthenticate('register'); }} style={[styles.secondaryButton, authBusy && styles.disabled]}><Text style={styles.secondaryButtonText}>注册新账户</Text></Pressable>
        </View>
        <Text style={styles.footerAddress}>服务地址：{API_BASE_URL}</Text>
      </ScrollView>
    </SafeAreaView>
  );

  return (
    <SafeAreaView edges={['top']} style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>CAMPUS DELIVERY</Text>
            <Text style={styles.title}>CampusFleet</Text>
            <Text style={styles.subtitle}>星河校区 · 校园配送</Text>
          </View>
          <Pressable accessibilityRole="button" onPress={() => { void onLogout(); }} style={styles.headerBadge}><Text style={styles.headerBadgeText}>{user.username} · 退出</Text></Pressable>
        </View>

        <View style={styles.notice}>
          <View style={styles.noticeDot} />
          <Text style={styles.noticeText}>模拟下单与支付 · 不产生真实扣款</Text>
        </View>

        {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}

        {!task ? (
          <View style={styles.card}>
            <View style={styles.sectionHeading}>
              <View>
                <Text style={styles.sectionEyebrow}>NEW DELIVERY</Text>
                <Text style={styles.sectionTitle}>创建配送订单</Text>
              </View>
              <Text style={styles.sectionNumber}>01</Text>
            </View>

            <Text style={styles.fieldLabel}>配送物品</Text>
            <View style={styles.chipRow}>
              {ITEMS.map(value => (
                <ChoiceChip key={value} label={value} selected={item === value} onPress={() => setItem(value)} />
              ))}
            </View>

            <Text style={styles.fieldLabel}>送达建筑</Text>
            {loadingMap ? (
              <View style={styles.loadingRow}><ActivityIndicator color="#2c7891" /><Text style={styles.loadingText}>正在读取校园建筑…</Text></View>
            ) : (
              <View style={styles.buildingList}>
                {buildings.map(value => (
                  <ChoiceChip key={value} label={value} selected={building === value} onPress={() => setBuilding(value)} />
                ))}
              </View>
            )}

            <Text style={styles.fieldLabel}>房间（三楼）</Text>
            <View style={styles.chipRow}>
              {ROOMS.map(value => (
                <ChoiceChip key={value} label={`房间 ${value}`} selected={room === value} onPress={() => setRoom(value)} />
              ))}
            </View>

            <Pressable
              accessibilityRole="button"
              disabled={loadingMap || creating || !building}
              onPress={onCreateTask}
              style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed, (loadingMap || creating || !building) && styles.disabled]}>
              {creating ? <ActivityIndicator color="#ffffff" /> : <Text style={styles.primaryButtonText}>一键申请配送 <Text style={styles.buttonArrow}>→</Text></Text>}
            </Pressable>
          </View>
        ) : (
          <>
            <View style={styles.card}>
              <View style={styles.sectionHeading}>
                <View>
                  <Text style={styles.sectionEyebrow}>ORDER PLAN</Text>
                  <Text style={styles.sectionTitle}>配送方案</Text>
                </View>
                <View style={[styles.statusPill, task.status === '已送达' && styles.deliveredPill]}>
                  <Text style={[styles.statusPillText, task.status === '已送达' && styles.deliveredText]}>{task.status === '已模拟支付' ? '配送中' : task.status}</Text>
                </View>
              </View>
              <Text style={styles.orderTitle}>{task.item} → {task.building}</Text>
              <Text style={styles.mutedText}>三楼房间 {task.room} · 室外 {task.outdoor.distance_m.toFixed(1)} 米 · 室内走{task.indoor.route}</Text>
              <Text selectable style={styles.orderMeta}>订单 ID {task.id}{'\n'}申请时间 {new Date(task.created_at * 1000).toLocaleString('zh-CN')}{'\n'}用户 ID {task.user_id} · 路线版本 {task.route_revision + 1}</Text>
              <View style={styles.priceRow}>
                <View><Text style={styles.priceLabel}>模拟配送费用</Text><Text style={styles.price}>{task.price.toFixed(2)} <Text style={styles.currency}>{task.currency}</Text></Text></View>
                <Text style={styles.robotId}>{task.robot_id}</Text>
              </View>

              <CampusRouteMap map={map} task={task} progress={progress} />
              <View style={styles.mapLegend}>
                <Text style={styles.legendItem}><Text style={styles.legendStart}>●</Text> 起点</Text>
                <Text style={styles.legendItem}><Text style={styles.legendRobot}>●</Text> 本单配送机器人</Text>
                <Text style={styles.legendItem}><Text style={styles.legendGoal}>■</Text> 建筑入口</Text>
              </View>

              {task.status === '待模拟支付' ? (
                <View style={styles.paymentActions}>
                  <Text style={styles.demoNotice}>仅供展示使用 · 不会实际扣款</Text>
                  <Text style={styles.providerText}>支持 Alipay · Apple Pay 等方式（演示）</Text>
                  <Pressable accessibilityRole="button" disabled={replanning || paying} onPress={onReplan} style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed, (replanning || paying) && styles.disabled]}>
                    {replanning ? <ActivityIndicator color="#2c7891" /> : <Text style={styles.secondaryButtonText}>重新规划路线</Text>}
                  </Pressable>
                  <Pressable accessibilityRole="button" disabled={paying || replanning} onPress={onPay} style={({ pressed }) => [styles.payButton, pressed && styles.pressed, (paying || replanning) && styles.disabled]}>
                    {paying ? <ActivityIndicator color="#ffffff" /> : <Text style={styles.primaryButtonText}>确认扣款（模拟） <Text style={styles.buttonArrow}>→</Text></Text>}
                  </Pressable>
                </View>
              ) : (
                <View style={styles.trackingCard}>
                  <View style={styles.trackingTop}>
                    <View><Text style={styles.trackingLabel}>配送进度</Text><Text style={styles.phase}>{phase}</Text></View>
                    <Text style={styles.percent}>{percent.toFixed(percent % 1 ? 1 : 0)}%</Text>
                  </View>
                  <View style={styles.progressTrack}><View style={[styles.progressFill, { width: `${Math.max(0, Math.min(100, percent))}%` }]} /></View>
                  <View style={styles.trackingDetails}>
                    <Text style={styles.detailKey}>当前位置</Text><Text style={styles.detailValue}>{positionText}</Text>
                  </View>
                  <View style={styles.trackingDetails}>
                    <Text style={styles.detailKey}>机器人</Text><Text style={styles.detailValue}>{task.robot_id}</Text>
                  </View>
                  <Text style={styles.remaining}>{task.status === '已送达' ? '本单已送达' : `模拟剩余约 ${progress?.remaining_seconds ?? '—'} 秒`}</Text>
                </View>
              )}
              <Text style={styles.message}>{message}</Text>
            </View>

            <Pressable accessibilityRole="button" onPress={startNewOrder} style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}>
              <Text style={styles.secondaryButtonText}>创建另一笔订单</Text>
            </Pressable>
          </>
        )}

        <View style={styles.card}>
          <View style={styles.sectionHeading}>
            <View><Text style={styles.sectionEyebrow}>MY ORDERS</Text><Text style={styles.sectionTitle}>我的历史订单</Text></View>
          </View>
          <Text style={styles.mutedText}>同一账户在电脑和手机上可以查看这些订单。订单会保存在服务器数据库中。</Text>
          {recentTasks.length ? recentTasks.map(order => (
            <Pressable key={order.id} accessibilityRole="button" disabled={openingTaskId !== null} onPress={() => { void onOpenTask(order.id); }} style={({ pressed }) => [styles.orderListItem, pressed && styles.pressed, openingTaskId !== null && styles.disabled]}>
              <View style={styles.orderListText}>
                <Text style={styles.orderListTitle}>{order.item} → {order.building} · 房间 {order.room}</Text>
                <Text style={styles.orderListDetail}>{order.id.slice(0, 8).toUpperCase()} · {order.status === '已模拟支付' ? '配送中' : order.status}</Text>
              </View>
              {openingTaskId === order.id ? <ActivityIndicator color="#2c7891" /> : <Text style={styles.orderListArrow}>›</Text>}
            </Pressable>
          )) : <Text style={styles.mutedText}>暂无订单。可以在手机上直接申请并付款。</Text>}
        </View>

        <View style={styles.footer}>
          <Text style={styles.footerTitle}>服务连接</Text>
          <Text selectable style={styles.footerAddress}>{API_BASE_URL}</Text>
          <Text style={styles.footerNote}>地图与机器人位置来自校园配送模拟服务。</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function ChoiceChip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" accessibilityState={{ selected }} onPress={onPress} style={({ pressed }) => [styles.chip, selected && styles.chipSelected, pressed && styles.pressed]}>
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: '#eef5fa' },
  authInput: { minHeight: 46, borderWidth: 1, borderColor: '#d7e5ec', borderRadius: 10, paddingHorizontal: 12, color: '#2c4556', backgroundColor: '#fff' },
  content: { paddingHorizontal: 18, paddingTop: 10, paddingBottom: 36, gap: 16, alignSelf: 'center', width: '100%', maxWidth: 560 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 8 },
  eyebrow: { color: '#6993a8', fontSize: 9, fontWeight: '800', letterSpacing: 2 },
  title: { color: '#263e4f', fontSize: 29, fontWeight: '800', letterSpacing: -0.8, marginTop: 3 },
  subtitle: { color: '#71899a', fontSize: 13, marginTop: 3 },
  headerBadge: { backgroundColor: '#dcedf5', borderColor: '#c8e0eb', borderWidth: 1, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 7 },
  headerBadgeText: { color: '#46758d', fontSize: 11, fontWeight: '700' },
  notice: { flexDirection: 'row', alignItems: 'center', gap: 9, paddingHorizontal: 13, paddingVertical: 11, backgroundColor: '#e5f2f5', borderRadius: 12 },
  noticeDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#4ca489' },
  noticeText: { color: '#547a80', fontSize: 11, fontWeight: '600' },
  error: { padding: 12, color: '#9a4b43', backgroundColor: '#fff0eb', borderColor: '#f1d1c8', borderWidth: 1, borderRadius: 10, fontSize: 12, lineHeight: 18 },
  card: { padding: 18, borderRadius: 20, backgroundColor: '#ffffff', borderColor: '#dfe9ef', borderWidth: 1, gap: 14, shadowColor: '#355367', shadowOpacity: 0.06, shadowRadius: 16, shadowOffset: { width: 0, height: 7 }, elevation: 2 },
  sectionHeading: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 1 },
  sectionEyebrow: { color: '#7a9aae', fontSize: 9, fontWeight: '800', letterSpacing: 1.6 },
  sectionTitle: { color: '#2c4556', fontSize: 19, fontWeight: '800', marginTop: 4 },
  sectionNumber: { color: '#cadde7', fontSize: 26, fontWeight: '800' },
  fieldLabel: { color: '#5c7383', fontSize: 12, fontWeight: '700', marginTop: 2, marginBottom: -5 },
  chipRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  buildingList: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  chip: { backgroundColor: '#f5f9fb', borderColor: '#e1ebf0', borderWidth: 1, borderRadius: 11, paddingHorizontal: 13, paddingVertical: 10 },
  chipSelected: { backgroundColor: '#eaf5f6', borderColor: '#5ca3a4' },
  chipText: { color: '#607687', fontSize: 12, fontWeight: '600' },
  chipTextSelected: { color: '#286e77', fontWeight: '800' },
  loadingRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8 },
  loadingText: { color: '#788d9c', fontSize: 12 },
  primaryButton: { minHeight: 50, borderRadius: 13, backgroundColor: '#2c7891', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16, marginTop: 3 },
  primaryButtonText: { color: '#ffffff', fontSize: 14, fontWeight: '800' },
  buttonArrow: { fontSize: 18 },
  pressed: { opacity: 0.78 },
  disabled: { opacity: 0.55 },
  statusPill: { borderRadius: 20, paddingVertical: 7, paddingHorizontal: 10, backgroundColor: '#fff3df' },
  deliveredPill: { backgroundColor: '#e6f5ee' },
  statusPillText: { color: '#9a7445', fontSize: 10, fontWeight: '800' },
  deliveredText: { color: '#478267' },
  orderTitle: { color: '#2e4859', fontSize: 17, fontWeight: '800', marginBottom: -8 },
  orderMeta: { color: '#8295a1', fontSize: 10, lineHeight: 17 },
  mutedText: { color: '#71899a', fontSize: 11, lineHeight: 17 },
  priceRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderTopColor: '#edf2f5', borderTopWidth: 1, paddingTop: 12 },
  priceLabel: { color: '#8295a1', fontSize: 10 },
  price: { color: '#2d6678', fontSize: 22, fontWeight: '800', marginTop: 2 },
  currency: { color: '#71899a', fontSize: 10, fontWeight: '600' },
  robotId: { color: '#668598', fontSize: 11, fontWeight: '700', backgroundColor: '#eef5f8', borderRadius: 9, paddingHorizontal: 10, paddingVertical: 7 },
  mapLegend: { flexDirection: 'row', gap: 13, flexWrap: 'wrap', marginTop: -6 },
  legendItem: { color: '#7c8f9c', fontSize: 9 },
  legendStart: { color: '#3d9c75' },
  legendRobot: { color: '#237a91' },
  legendGoal: { color: '#e39a52' },
  trackingCard: { backgroundColor: '#f6fafc', borderColor: '#e3edf2', borderWidth: 1, borderRadius: 15, padding: 14, gap: 10 },
  trackingTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  trackingLabel: { color: '#8295a1', fontSize: 10 },
  phase: { color: '#31596b', fontSize: 14, fontWeight: '800', marginTop: 2 },
  percent: { color: '#2c7891', fontSize: 22, fontWeight: '800' },
  progressTrack: { height: 8, borderRadius: 5, backgroundColor: '#dce8ed', overflow: 'hidden' },
  progressFill: { height: 8, borderRadius: 5, backgroundColor: '#43a28a' },
  trackingDetails: { flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
  detailKey: { color: '#8295a1', fontSize: 10 },
  detailValue: { color: '#4a6373', fontSize: 10, fontWeight: '700', flexShrink: 1, textAlign: 'right' },
  remaining: { color: '#7a8e9b', fontSize: 10, textAlign: 'right' },
  paymentActions: { gap: 9 },
  demoNotice: { color: '#5a7568', fontSize: 11, fontWeight: '800' },
  providerText: { color: '#708b97', fontSize: 10 },
  payButton: { minHeight: 50, borderRadius: 13, backgroundColor: '#16834d', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16 },
  orderListItem: { minHeight: 56, borderWidth: 1, borderColor: '#e1ebf0', borderRadius: 11, paddingHorizontal: 12, paddingVertical: 9, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  orderListText: { flexShrink: 1, gap: 3 },
  orderListTitle: { color: '#355367', fontSize: 12, fontWeight: '700' },
  orderListDetail: { color: '#8398a6', fontSize: 10 },
  orderListArrow: { color: '#7b9eac', fontSize: 22 },
  message: { color: '#748a98', fontSize: 10, lineHeight: 16 },
  secondaryButton: { minHeight: 44, borderRadius: 12, borderWidth: 1, borderColor: '#d7e5ec', backgroundColor: '#f8fbfd', alignItems: 'center', justifyContent: 'center' },
  secondaryButtonText: { color: '#587789', fontSize: 12, fontWeight: '700' },
  footer: { alignItems: 'center', gap: 4, paddingTop: 5 },
  footerTitle: { color: '#8297a4', fontSize: 9, fontWeight: '700' },
  footerAddress: { color: '#8ba0ad', fontSize: 9 },
  footerNote: { color: '#a0afb8', fontSize: 9, textAlign: 'center' },
});
