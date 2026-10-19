// The photo intro's timeline and camera, as pure functions of wall time t (seconds).
// Shot 1: the keeper's view, the striker waits. Cut on the strike. Shot 2: the ball flies from his
// boot to the lens along a computed flight, projected into the photo with a pinhole camera.
import { BALL, simulate, solveShot, stateAt, type Vec3 } from './ballPhysics';

// --- camera fitted to shot 2 (1600 x 900), see public/intro/camera.json -------------------------
export const IMAGE = { w: 1600, h: 900 };
export const CAM = {
  f: 1504,            // focal length in pixels (striker: 242 px tall for ~1.85 m at ~11.5 m)
  cx: 800,            // principal point x (image centre)
  horizonY: 595,      // where the far end of the pitch meets the stands
  height: 0.29,       // camera height above the grass (m): the keeper is down low
};

/** World point (x right, y up, z towards the keeper; camera at z = 0) to image pixels and radius. */
export function project(p: Vec3, radius = BALL.radius): { x: number; y: number; r: number; depth: number } {
  const depth = -p[2];
  return {
    x: CAM.cx + (CAM.f * p[0]) / depth,
    y: CAM.horizonY - (CAM.f * (p[1] - CAM.height)) / depth,
    r: (CAM.f * radius) / depth,
    depth,
  };
}

/** The image pixel (u, v) at distance `depth` in front of the camera, as a world point. */
export function unproject(u: number, v: number, depth: number): Vec3 {
  return [((u - CAM.cx) * depth) / CAM.f, CAM.height + ((CAM.horizonY - v) * depth) / CAM.f, -depth];
}

// The ball starts on the grass just in front of the striker's feet and is struck straight at the
// keeper's face: it reaches the lens (0.15 m away) at the centre of the frame, where it fills the view.
export const KICK_FROM: Vec3 = [-1.52, BALL.radius, -11.3];
export const LENS_DEPTH = 0.15;
export const AT_LENS: Vec3 = unproject(805, 430, LENS_DEPTH);
export const SPEED = 27;            // m/s, about 97 km/h
export const SPIN: Vec3 = [28, -5, 0]; // topspin with a little side spin (rad/s)
export const SHOT = solveShot(KICK_FROM, AT_LENS, SPEED, SPIN);
/** The computed flight, from the boot until the ball is at the lens. */
// small steps (0.25 ms, under 1 cm) so the last sample lands right at the lens, where 1 cm matters
export const FLIGHT = simulate(KICK_FROM, SHOT.v0, SPIN, (s) => -s.p[2] <= LENS_DEPTH, 2, 1 / 4000);

// --- timeline -----------------------------------------------------------------------------------
export const FADE_IN = 0.35;
export const CUT = 2.45;             // wall time of the cut from shot 1 to shot 2
const SLOW = 0.18;                   // slow-motion speed during the flight

/** Scene time of the flight (seconds since the kick) for wall time t; slows to SLOW after the cut. */
export function flightTime(t: number): number {
  const w = t - CUT;
  if (w <= 0) return 0;
  const ramp0 = 0.05, ramp1 = 0.16;  // full speed for a blink, then ease into slow motion
  if (w < ramp0) return w;
  if (w < ramp1) {
    const x = (w - ramp0) / (ramp1 - ramp0);
    return ramp0 + (ramp1 - ramp0) * (x - (1 - SLOW) * x * x / 2);
  }
  const atRamp = ramp0 + (ramp1 - ramp0) * (1 - (1 - SLOW) / 2);
  return atRamp + (w - ramp1) * SLOW;
}

export const FLIGHT_END = FLIGHT[FLIGHT.length - 1].t;
/** Wall time when the ball reaches the lens (and the screen goes black). */
export const T_BLACK = (() => { let t = CUT; while (flightTime(t) < FLIGHT_END) t += 0.001; return t; })();

export function ballAt(t: number) {
  const s = stateAt(FLIGHT, flightTime(t));
  return { ...s, screen: project(s.p) };
}

/** A tiny deterministic random generator, so every frame renders the same way every time. */
export function rng(seed: number) {
  let s = seed >>> 0 || 1;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}

export interface Droplet { x: number; y: number; r: number; alpha: number; dx: number; dy: number }

/** Water flung off the spinning ball: born on its surface, flying outwards, drawn in perspective. */
export function droplets(t: number): Droplet[] {
  const now = flightTime(t);
  if (now <= 0) return [];
  const out: Droplet[] = [];
  const rand = rng(7);
  for (let i = 0; i < 220; i++) {
    const born = i * 0.002, life = 0.06 + rand() * 0.08;
    const a = rand() * Math.PI * 2, b = rand() * 2 - 1, speed = 0.8 + rand() * 2.2;
    const dir: Vec3 = [Math.sqrt(1 - b * b) * Math.cos(a), b, Math.sqrt(1 - b * b) * Math.sin(a)];
    const age = now - born;
    if (age < 0 || age > life || born > FLIGHT_END) continue;
    const at = stateAt(FLIGHT, born);
    const p: Vec3 = [
      at.p[0] + dir[0] * BALL.radius + (at.v[0] * 0.92 + dir[0] * speed) * age,
      at.p[1] + dir[1] * BALL.radius + (at.v[1] * 0.92 + dir[1] * speed) * age - 4.9 * age * age,
      at.p[2] + dir[2] * BALL.radius + (at.v[2] * 0.92 + dir[2] * speed) * age,
    ];
    if (-p[2] < 0.15) continue;
    // drops are 1-2.5 mm; the streak is how far one moves in one displayed frame of slow motion
    const s = project(p, 0.001 + rand() * 0.0015);
    const step = 0.0025;
    const prev = project([p[0] - (at.v[0] * 0.92 + dir[0] * speed) * step, p[1] - (at.v[1] * 0.92 + dir[1] * speed) * step, p[2] - (at.v[2] * 0.92 + dir[2] * speed) * step]);
    let dx = s.x - prev.x, dy = s.y - prev.y;
    const len = Math.hypot(dx, dy), cap = 12;
    if (len > cap) { dx *= cap / len; dy *= cap / len; }
    out.push({ x: s.x, y: s.y, r: Math.min(3, Math.max(0.5, s.r)), alpha: 0.7 * (1 - age / life), dx, dy });
  }
  return out;
}
