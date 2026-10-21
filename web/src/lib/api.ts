// The backend API (FastAPI, see src/tactics/api.py). In development Vite proxies /api to port 8000;
// deployed, the same server serves this app and the API.
// The online demo is a static site (VITE_STATIC=1, D38): the bundled clips are files made by
// scripts/build_static_site.py, and there is no analysis server for uploads or new explanations.
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
  try { res = await fetch(path, init); } catch {
    throw new ApiError(0, import.meta.env.DEV ? 'The analysis server is not reachable. Start it with: uv run uvicorn tactics.api:app'
      : 'The analysis server is not reachable. It may be waking up: try again in a minute.');
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new ApiError(res.status, String(detail));
  }
  return res.json();
}

// The deployed library is shared, so it lists only the bundled clips and the uploads made in this browser.
const MY_UPLOADS = 'vyuh.myUploads';
export function myUploads(): string[] {
  try { return JSON.parse(localStorage.getItem(MY_UPLOADS) ?? '[]'); } catch { return []; }
}
function remember(id: string | null) {
  if (!id || myUploads().includes(id)) return;
  try { localStorage.setItem(MY_UPLOADS, JSON.stringify([...myUploads(), id].slice(-50))); } catch { /* private mode */ }
}
const remembered = <T extends { clip_id: string | null }>(r: T) => { remember(r.clip_id); return r; };

export const STATIC = import.meta.env.VITE_STATIC === '1';
export const STATIC_NOTE = 'This online demo has no analysis server, so uploads are off. Run Vyuh on your machine to analyse your own data.';
const noServer = <T,>(): Promise<T> => Promise.reject(new ApiError(0, STATIC_NOTE));
const enc = encodeURIComponent;

export const api = {
  health: () => STATIC ? Promise.resolve({ status: 'static', drone_video: false })
    : call<{ status: string; drone_video: boolean }>('/api/health'),
  clips: () => STATIC ? call<ClipSummary[]>('/data/clips/index.json')
    : call<ClipSummary[]>(`/api/clips?mine=${enc(myUploads().join(','))}`),
  // static: a full replay file (12.5 per second, blended to 60 fps on screen) and a light preview for the library
  clip: (id: string, step = 1) => STATIC ? call<ClipPayload>(`/data/clips/${enc(id)}${step >= 5 ? '.preview' : ''}.json`)
    : call<ClipPayload>(`/api/clips/${enc(id)}?step=${step}`),
  explain: (id: string) => STATIC ? noServer<Explanation & { grounding: Grounding; checks: Checks; from_cache?: boolean }>()
    : call<Explanation & { grounding: Grounding; checks: Checks; from_cache?: boolean }>(`/api/clips/${enc(id)}/explanation`, { method: 'POST' }),
  uploadTracking: (form: FormData) => STATIC ? noServer<UploadResult>()
    : call<UploadResult>('/api/uploads/tracking', { method: 'POST', body: form }).then(remembered),
  uploadProvider: (form: FormData) => STATIC ? noServer<UploadResult>()
    : call<UploadResult>('/api/uploads/provider', { method: 'POST', body: form }).then(remembered),
  uploadDrone: (form: FormData) => STATIC ? noServer<{ job_id: string }>()
    : call<{ job_id: string }>('/api/uploads/drone', { method: 'POST', body: form }),
  job: (id: string) => call<Job>(`/api/jobs/${enc(id)}`).then(remembered),
};

export const urls = {
  source: (id: string) => STATIC ? `/data/clips/${enc(id)}/source.mp4` : `/api/clips/${enc(id)}/source`,
  template: STATIC ? '/templates/tracking_template.csv' : '/api/template',
  example: STATIC ? '/templates/example_musiala_winner.csv' : '/api/template/example',
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
