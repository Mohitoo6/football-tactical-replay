// Pure helpers for the replay screen: metric series over time, events, and reading the coach's text.
import type { ClipPayload, Side } from './clip';
import { clockSeconds } from './api';

export type Metric = 'width_m' | 'depth_m' | 'area_m2' | 'back_line_m';
export const METRICS: { key: Metric; label: string; unit: string; help: string }[] = [
  { key: 'width_m', label: 'Width', unit: 'm', help: 'Distance between the widest outfield players, touchline to touchline.' },
  { key: 'depth_m', label: 'Depth', unit: 'm', help: 'Distance from the deepest to the most advanced outfield player.' },
  { key: 'area_m2', label: 'Area', unit: 'm²', help: 'Area of the team shape (convex hull of the outfield players).' },
  { key: 'back_line_m', label: 'Back line', unit: 'm', help: 'Average distance of the four deepest outfield players from their own goal.' },
];

export interface Series { t: number[]; values: Record<Side, Record<Metric, (number | null)[]>> }

/** Each team's shape metrics at every frame (seconds from the clip start). */
export function metricSeries(clip: ClipPayload, maxPoints = 240): Series {
  const t0 = clip.frames[0].time_s;
  const step = Math.max(1, Math.ceil(clip.frames.length / maxPoints));
  const picked = clip.frames.filter((_, i) => i % step === 0);
  const empty = () => ({ width_m: [], depth_m: [], area_m2: [], back_line_m: [] }) as Record<Metric, (number | null)[]>;
  const values: Series['values'] = { home: empty(), away: empty() };
  for (const f of picked) {
    for (const side of ['home', 'away'] as Side[]) {
      for (const m of METRICS) values[side][m.key].push(f.shapes[side]?.[m.key] ?? null);
    }
  }
  return { t: picked.map((f) => f.time_s - t0), values };
}

/** Value of a series at time t (linear between samples; null where the shape is unknown). */
export function valueAt(t: number[], v: (number | null)[], at: number): number | null {
  if (!t.length) return null;
  if (at <= t[0]) return v[0];
  if (at >= t[t.length - 1]) return v[v.length - 1];
  let i = 1;
  while (t[i] < at) i++;
  const a = v[i - 1], b = v[i];
  if (a == null || b == null) return a ?? b;
  const w = (at - t[i - 1]) / (t[i] - t[i - 1]);
  return a + (b - a) * w;
}

export interface MatchEvent { t: number; clock: string; kind: 'touch' | 'goal'; player: string; team: string }

/** Ball carriers and goals as one ordered list, timed in seconds from the clip start. */
export function events(clip: ClipPayload): MatchEvent[] {
  const facts = clip.facts;
  const start = clip.meta.start_clock ? clockSeconds(clip.meta.start_clock) : null;
  if (!facts || start == null) return [];
  const list: MatchEvent[] = [
    ...facts.ball_carriers.map((e) => ({ t: clockSeconds(e.clock) - start, clock: e.clock, kind: 'touch' as const, player: e.player, team: e.team })),
    ...facts.goals.map((e) => ({ t: clockSeconds(e.clock) - start, clock: e.clock, kind: 'goal' as const, player: e.player, team: e.team })),
  ];
  return list.sort((a, b) => a.t - b.t || (a.kind === 'goal' ? 1 : -1));
}

export type Token = { kind: 'text'; text: string } | { kind: 'clock'; text: string } | { kind: 'number'; text: string };

const TOKEN = /(\b\d{1,3}:\d{2}\b)|(\b\d+(?:[.,]\d+)?\s?(?:m²|m\b|metres|meters|seconds|s\b|%|players)|\b\d-\d(?:-\d){1,3}\b)/g;

/** Split a line of the coach's text into plain text, match clocks (clickable) and numbers (highlighted). */
export function tokenize(line: string): Token[] {
  const out: Token[] = [];
  let last = 0;
  for (const m of line.matchAll(TOKEN)) {
    if (m.index! > last) out.push({ kind: 'text', text: line.slice(last, m.index) });
    out.push({ kind: m[1] ? 'clock' : 'number', text: m[0] });
    last = m.index! + m[0].length;
  }
  if (last < line.length) out.push({ kind: 'text', text: line.slice(last) });
  return out;
}

export interface CoachBlock { kind: 'heading' | 'paragraph' | 'bullet'; text: string }

/** The coach's markdown-like answer ("**What happened**", "* point") as blocks. */
export function coachBlocks(text: string): CoachBlock[] {
  return text.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => {
    const heading = l.match(/^\*\*(.+?)\*\*$/);
    if (heading) return { kind: 'heading' as const, text: heading[1] };
    if (/^[*-]\s+/.test(l)) return { kind: 'bullet' as const, text: l.replace(/^[*-]\s+/, '') };
    return { kind: 'paragraph' as const, text: l.replace(/\*\*/g, '') };
  });
}
