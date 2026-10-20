// The backend API (FastAPI, see src/tactics/api.py). In development Vite proxies /api to port 8000.
import type { Checks, ClipPayload, Explanation, Grounding } from './clip';

export interface ClipSummary {
  clip_id: string; title: string; origin: 'bundled' | 'user'; data_kind: 'tracking' | 'video' | 'uploaded' | string;
  start_clock?: string; end_clock?: string; teams: { home: string; away: string };
  has_video: boolean; has_explanation: boolean;
}
export interface Check { name: string; passed: boolean; value: string; requirement: string; blocking: boolean }
export interface Report { status: 'ok' | 'warning' | 'rejected' | string; checks: Check[] }
export interface UploadResult { clip_id: string | null; report: Report }
export interface Job { state: 'running' | 'done' | 'rejected' | 'failed'; progress: number; message: string; clip_id: string | null; report: Report | null }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try { res = await fetch(path, init); } catch { throw new ApiError(0, 'The analysis server is not reachable. Start it with: uv run uvicorn tactics.api:app'); }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new ApiError(res.status, String(detail));
  }
  return res.json();
}

export const api = {
  health: () => call<{ status: string; drone_video: boolean }>('/api/health'),
  clips: () => call<ClipSummary[]>('/api/clips'),
  clip: (id: string, step = 1) => call<ClipPayload>(`/api/clips/${encodeURIComponent(id)}?step=${step}`),
  explain: (id: string) => call<Explanation & { grounding: Grounding; checks: Checks; from_cache?: boolean }>(`/api/clips/${encodeURIComponent(id)}/explanation`, { method: 'POST' }),
  uploadTracking: (form: FormData) => call<UploadResult>('/api/uploads/tracking', { method: 'POST', body: form }),
  uploadProvider: (form: FormData) => call<UploadResult>('/api/uploads/provider', { method: 'POST', body: form }),
  uploadDrone: (form: FormData) => call<{ job_id: string }>('/api/uploads/drone', { method: 'POST', body: form }),
  job: (id: string) => call<Job>(`/api/jobs/${encodeURIComponent(id)}`),
};

/** "88:15" -> seconds. */
export function clockSeconds(clock: string): number {
  const [m, s] = clock.split(':').map(Number);
  return m * 60 + s;
}
export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}
