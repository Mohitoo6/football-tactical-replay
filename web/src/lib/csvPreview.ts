// Read a tracking CSV in the browser (our template) to preview it before anything is uploaded:
// how many rows, moments and players, the frame rate, and the first moment drawn on a pitch.
import type { ClipPayload, Player, Side } from './clip';

export type Units = 'metres' | 'metres_corner' | 'normalised';

export interface CsvPreview {
  rows: number;
  moments: number;
  seconds: number;
  frameRate: number | null;
  players: Record<Side, number>;   // in the first moment
  ballShare: number;               // share of moments with a ball row
  missing: string[];               // required columns not found
  clip: ClipPayload | null;        // the first moment as a one-frame clip, for the pitch preview
}

const REQUIRED = ['time_s', 'team', 'x', 'y'];

function toMetres(x: number, y: number, units: Units): [number, number] {
  if (units === 'metres_corner') return [x - 52.5, y - 34];
  if (units === 'normalised') return [(x - 0.5) * 105, (y - 0.5) * 68];
  return [x, y];
}

/** Simple CSV split (our template has no quoted commas); handles \r\n. */
function rowsOf(text: string): string[][] {
  return text.split(/\r?\n/).filter((l) => l.trim()).map((l) => l.split(',').map((c) => c.trim()));
}

export function previewCsv(text: string, units: Units): CsvPreview {
  const rows = rowsOf(text);
  const header = (rows.shift() ?? []).map((h) => h.toLowerCase());
  const col = (name: string) => header.indexOf(name);
  const missing = REQUIRED.filter((c) => col(c) < 0);
  const empty: CsvPreview = { rows: rows.length, moments: 0, seconds: 0, frameRate: null, players: { home: 0, away: 0 }, ballShare: 0, missing, clip: null };
  if (missing.length || !rows.length) return empty;

  const [ti, te, xi, yi, pi, ji, po] = ['time_s', 'team', 'x', 'y', 'player', 'jersey', 'position'].map(col);
  const times = new Map<number, string[][]>();
  for (const r of rows) {
    const t = parseFloat(r[ti]);
    if (!Number.isFinite(t)) continue;
    const key = Math.round(t * 1000) / 1000;
    if (!times.has(key)) times.set(key, []);
    times.get(key)!.push(r);
  }
  const keys = [...times.keys()].sort((a, b) => a - b);
  if (!keys.length) return empty;
  const steps = keys.slice(1, 200).map((k, i) => k - keys[i]).sort((a, b) => a - b);
  const step = steps.length ? steps[Math.floor(steps.length / 2)] : 0;
  const withBall = keys.filter((k) => times.get(k)!.some((r) => r[te]?.toLowerCase() === 'ball')).length;

  const first = times.get(keys[0])!;
  const players: Player[] = [];
  let ball: [number, number] | null = null;
  for (const r of first) {
    const team = r[te]?.toLowerCase();
    const [x, y] = toMetres(parseFloat(r[xi]), parseFloat(r[yi]), units);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    if (team === 'ball') { ball = [x, y]; continue; }
    if (team !== 'home' && team !== 'away') continue;
    const jersey = ji >= 0 ? parseInt(r[ji], 10) : NaN;
    players.push({ id: `${team}-${pi >= 0 ? r[pi] : players.length}`, team, name: pi >= 0 ? r[pi] : '', number: Number.isFinite(jersey) ? jersey : null,
      keeper: po >= 0 && /^(gk|goalkeeper|keeper)$/i.test(r[po] ?? ''), x, y });
  }
  const frame = { frame: 0, time_s: 0, ball, players, shapes: {} };
  const clip: ClipPayload = {
    meta: { clip_id: 'preview', title: 'Preview', focus_team: 'home', frame_rate: 1, teams: { home: { name: 'Home' }, away: { name: 'Away' } } },
    pitch: { length_m: 105, width_m: 68 }, frame_rate: 1, frames: [frame, { ...frame, frame: 1, time_s: 1 }],
    facts: null, explanation: null, has_video: false,
  };
  return {
    rows: rows.length, moments: keys.length, seconds: keys[keys.length - 1] - keys[0],
    frameRate: step > 0 ? Math.round(1 / step) : null,
    players: { home: players.filter((p) => p.team === 'home').length, away: players.filter((p) => p.team === 'away').length },
    ballShare: withBall / keys.length, missing, clip,
  };
}
