// The clip payload served by GET /api/clips/{id} (and exported to public/data for the landing page).

export type Side = 'home' | 'away';

export interface Player { id: string; team: Side; name: string; number: number | null; keeper: boolean; x: number; y: number }
export interface Shape { hull: [number, number][]; width_m: number; depth_m: number; area_m2: number; back_line_m: number }
export interface ClipFrame { frame: number; time_s: number; ball: [number, number] | null; players: Player[]; shapes: Partial<Record<Side, Shape>> }
export interface ClipMeta {
  clip_id: string; title: string; focus_team: Side; start_clock?: string; end_clock?: string; frame_rate: number;
  teams: Record<Side, { name: string; formation?: string }>;
  goals?: { time_s: number; clock: string; team: Side; player: string }[];
  source?: string;
}
export interface TeamMetrics { width_m: number; depth_m: number; area_m2: number; back_line_m: number; players_behind_ball?: number }
export interface Facts {
  clip: { title: string; from_clock: string; to_clock: string; clip_seconds: number; seconds_ball_in_play: number };
  teams: { name: string; role: string; players_on_pitch: number; official_formation: string | null; shape_in_clip: string }[];
  goals: { clock: string; player: string; team: string }[];
  ball_carriers: { clock: string; player: string; team: string }[];
  /** every few seconds: the ball's zone and each team's metrics, keyed by team name */
  timeline: ({ clock: string; ball_zone?: string } & Record<string, TeamMetrics | string | undefined>)[];
  notable_changes: { team: string; metric: string; from: number; to: number; from_clock: string; to_clock: string }[];
}
export interface Grounding { passed: boolean; numbers_checked: number; problems: string[] }
export interface Explanation { text: string; provider?: string; model?: string; prompt_version?: string; created_utc?: string; grounding?: Grounding }
export interface ClipPayload {
  meta: ClipMeta & { data_kind?: string; teams: Record<Side, { name: string; formation?: string }> };
  pitch: { length_m: number; width_m: number };
  frame_rate: number;
  frames: ClipFrame[];
  facts: Facts | null;
  explanation: Explanation | null;
  grounding?: Grounding | null;
  has_video: boolean;
}

export async function loadClip(url: string): Promise<ClipPayload> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Could not load ${url}: ${res.status}`);
  return res.json();
}

const mix = (a: number, b: number, w: number) => a + (b - a) * w;

/** Players and ball at any time in seconds from the clip start, blended between the two nearest frames. */
export function sampleAt(clip: ClipPayload, t: number) {
  const frames = clip.frames;
  const t0 = frames[0].time_s;
  const dt = 1 / clip.frame_rate;
  const pos = Math.max(0, Math.min(frames.length - 1, (t + 0) / dt));
  const i = Math.min(frames.length - 2, Math.floor(pos));
  const w = pos - i;
  const a = frames[i], b = frames[i + 1] ?? a;
  const next = new Map(b.players.map((p) => [p.id, p]));
  const players = a.players.map((p) => {
    const q = next.get(p.id) ?? p;
    return { ...p, x: mix(p.x, q.x, w), y: mix(p.y, q.y, w) };
  });
  const ball = a.ball && b.ball ? [mix(a.ball[0], b.ball[0], w), mix(a.ball[1], b.ball[1], w)] as [number, number] : null;
  const shapes = w < 0.5 ? a.shapes : b.shapes;
  return { time: mix(a.time_s, b.time_s, w) - t0, players, ball, shapes, frame: w < 0.5 ? a : b };
}

export function duration(clip: ClipPayload): number {
  return clip.frames[clip.frames.length - 1].time_s - clip.frames[0].time_s;
}

/** Convex hull (monotone chain) of points, used to draw team shapes from the blended positions. */
export function hull(points: [number, number][]): [number, number][] {
  const p = points.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (p.length < 3) return p;
  const cross = (o: number[], a: number[], b: number[]) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: [number, number][] = [], upper: [number, number][] = [];
  for (const q of p) { while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], q) <= 0) lower.pop(); lower.push(q); }
  for (let i = p.length - 1; i >= 0; i--) { const q = p[i]; while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], q) <= 0) upper.pop(); upper.push(q); }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}
