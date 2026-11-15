import { Platform } from 'react-native';

export type CampusShape = {
  kind: string;
  label: string;
  points: number[][];
};

export type CampusMap = {
  width: number;
  height: number;
  shapes: CampusShape[];
  roads: { label: string; points: number[][]; width: number }[];
  lanes: { label: string; cells: number[][]; label_position: number[] }[];
};

export type Task = {
  id: string;
  robot_id: string;
  status: string;
  user_id: string;
  created_at: number;
  route_revision: number;
  item: string;
  building: string;
  room: string;
  price: number;
  currency: string;
  start: number[];
  entrance: number[];
  arrival_step: number;
  transition_step: number;
  outdoor: { path: number[][]; distance_m: number; arrival_step: number };
  indoor: { route: string };
};

export type TaskProgress = {
  id: string;
  robot_id: string;
  status: string;
  route_revision: number;
  tick: number;
  total_steps: number;
  percent: number;
  phase: string;
  position: { x: number; y: number; floor?: number };
  remaining_seconds: number;
};

const configuredBase = process.env.EXPO_PUBLIC_API_URL?.trim();
let authToken = '';
export type AuthUser = { id: string; username: string };
export function setAuthToken(token: string) { authToken = token; }
export const API_BASE_URL = (configuredBase || (
  Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://127.0.0.1:8000'
)).replace(/\/+$/, '');

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { Accept: 'application/json', 'Content-Type': 'application/json',
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}), ...init?.headers },
    });
  } catch {
    throw new Error(`连接不到 CampusFleet 服务：${API_BASE_URL}。请确认 Python 服务已启动，且手机能访问该地址。`);
  }

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof payload.error === 'string' ? payload.error : `服务返回错误（${response.status}）`);
  }
  return payload as T;
}

export function authenticate(mode: 'login' | 'register', username: string, password: string) {
  return requestJson<{token: string; user: AuthUser}>(`/api/auth/${mode}`, {
    method: 'POST', body: JSON.stringify({ username, password }),
  });
}

export function logout() {
  return requestJson<{ok: boolean}>('/api/auth/logout', { method: 'POST', body: '{}' });
}

export function getCampusMap() {
  return requestJson<CampusMap>('/api/map');
}

export function createTask(item: string, building: string, room: string) {
  return requestJson<Task>('/api/tasks', {
    method: 'POST',
    body: JSON.stringify({ item, building, room }),
  });
}

export function listTasks() {
  return requestJson<Task[]>('/api/tasks');
}

export function getTask(taskId: string) {
  return requestJson<Task>(`/api/tasks/${encodeURIComponent(taskId)}`);
}

export function replanTask(taskId: string) {
  return requestJson<Task>(`/api/tasks/${encodeURIComponent(taskId)}/replan`, {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

export function payTask(taskId: string) {
  return requestJson<Task>(`/api/tasks/${encodeURIComponent(taskId)}/pay`, {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

export function getTaskProgress(taskId: string) {
  return requestJson<TaskProgress>(`/api/tasks/${encodeURIComponent(taskId)}/progress`);
}
