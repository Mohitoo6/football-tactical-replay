// One clock for the whole intro. Wall time t (seconds since start) maps to scene time s,
// which runs slower around the shot (slow motion). Every moving thing is a pure function
// of s, so any frame can be rendered exactly (for the MP4 export and for checking).
import { BALL, solveShot, stateAt, type Vec3 } from './ballPhysics';

export const SPOT: Vec3 = [0, BALL.radius, -11];
export const EYE: Vec3 = [0, 1.38, 0.25];          // keeper crouched in the ready stance, just off the line
export const CATCH: Vec3 = [0.1, 1.26, -0.5];      // where the hands meet the ball, in front of the face
export const FACE: Vec3 = [0.0, 1.36, 0.08];       // the keeper pulls the ball in until it fills the view

export const T_RUN = 1.2;      // kicker starts the run-up
export const T_KICK = 2.9;     // boot meets ball (scene time)
const SHOT_SPEED = 26;         // m/s, about 94 km/h: a firm, typical penalty
// Spin (rad/s): +x is topspin for a ball moving towards +z (w x v points down), +y curves it to +x.
export const SPIN: Vec3 = [30, 4, 0];

export const SHOT = solveShot(SPOT, CATCH, SHOT_SPEED, SPIN);
export const FLIGHT_TIME = SHOT.flight[SHOT.flight.length - 1].t;
const hit = SHOT.flight.find((q) => q.p[2] >= CATCH[2]) ?? SHOT.flight[SHOT.flight.length - 1];
export const T_CATCH = T_KICK + hit.t;
export const PULL = 0.5;       // seconds (scene) to pull the ball into the face
export const T_BLACK = T_CATCH + PULL;

const clamp = (v: number) => Math.max(0, Math.min(1, v));
export const smooth = (v: number) => { v = clamp(v); return v * v * (3 - 2 * v); };
const mix = (a: number, b: number, w: number) => a + (b - a) * w;

/** Playback speed at scene time s: normal, then slow motion while the ball flies, normal after the catch. */
function timeScale(s: number): number {
  const slow = 0.2;
  if (s < T_KICK + 0.05) return 1;
  if (s < T_KICK + 0.16) return mix(1, slow, smooth((s - T_KICK - 0.05) / 0.11));
  if (s < T_CATCH - 0.02) return slow;
  if (s < T_CATCH + 0.06) return mix(slow, 0.7, smooth((s - T_CATCH + 0.02) / 0.08));
  return 0.7;
}

// Integrate ds/dt = timeScale(s) once, then look up s for any wall time t.
const STEP = 1 / 1000;
const TABLE: number[] = (() => {
  const out = [0];
  let s = 0;
  while (s < T_BLACK + 2) { s += timeScale(s) * STEP; out.push(s); }
  return out;
})();
export const WALL_BLACK = TABLE.findIndex((s) => s >= T_BLACK) * STEP;
export const WALL_END = WALL_BLACK + 0.35;

export function sceneTime(t: number): number {
  const i = t / STEP;
  if (i <= 0) return 0;
  if (i >= TABLE.length - 1) return TABLE[TABLE.length - 1];
  const a = Math.floor(i);
  return mix(TABLE[a], TABLE[a + 1], i - a);
}

export interface Frame {
  s: number;
  ball: Vec3;
  ballSpin: number;   // radians turned about the spin axis
  kicker: Vec3;       // stand-in position (slice 1)
  black: number;      // 0..1 cover
  look: Vec3;         // where the keeper looks
  shake: number;      // camera shake amount at the catch
}

const RUN_START: Vec3 = [-1.9, 0, -15.3];   // about 30 degrees off the line of the shot, 4.5 m back
const PLANT: Vec3 = [-0.3, 0, -11.2];       // plant foot beside the ball

export function frameAt(t: number): Frame {
  const s = sceneTime(t);
  let ball: Vec3 = SPOT;
  if (s >= T_KICK && s < T_CATCH) ball = stateAt(SHOT.flight, s - T_KICK).p;
  else if (s >= T_CATCH) {
    const w = smooth((s - T_CATCH) / PULL);
    ball = [mix(CATCH[0], FACE[0], w), mix(CATCH[1], FACE[1], w), mix(CATCH[2], FACE[2], w)];
  }
  const run = smooth((s - T_RUN) / (T_KICK - T_RUN));
  const kicker: Vec3 = [mix(RUN_START[0], PLANT[0], run), 0, mix(RUN_START[2], PLANT[2], run)];
  const flying = s >= T_KICK && s < T_CATCH;
  const ballSpin = flying ? (s - T_KICK) * 30 : 0;
  // The keeper watches the kicker, then tracks the ball in.
  const track = smooth((s - T_KICK) / 0.3);
  const look: Vec3 = [mix(SPOT[0] * 0.5, ball[0], track * 0.6), mix(1.0, ball[1], track * 0.6), mix(-11, ball[2] - 2, track * 0.6)];
  const shake = s >= T_CATCH ? Math.exp(-(s - T_CATCH) * 14) : 0;
  return { s, ball, ballSpin, kicker, black: smooth((t - WALL_BLACK + 0.12) / 0.12), look, shake };
}
