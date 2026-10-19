// Flight of a football: gravity, air drag and Magnus lift from spin.
// World axes (metres): x to the keeper's right, y up, z towards the keeper.
// The keeper stands on the goal line (z = 0); the penalty spot is at z = -11.

export type Vec3 = [number, number, number];

export const BALL = {
  mass: 0.43,      // kg (FIFA: 410-450 g)
  radius: 0.11,    // m (size 5: 68-70 cm circumference)
  airDensity: 1.2, // kg/m^3
  dragCoeff: 0.25, // fast shots are past the "drag crisis", so Cd is low
  gravity: 9.81,
};

const AREA = Math.PI * BALL.radius * BALL.radius;

export interface Sample {
  t: number;  // seconds since the kick
  p: Vec3;    // position
  v: Vec3;    // velocity
}

const add = (a: Vec3, b: Vec3, s = 1): Vec3 => [a[0] + b[0] * s, a[1] + b[1] * s, a[2] + b[2] * s];
const len = (a: Vec3) => Math.hypot(a[0], a[1], a[2]);
const cross = (a: Vec3, b: Vec3): Vec3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];

/** Lift coefficient from the spin parameter S = r*w/|v| (Sawicki et al. model). */
export function liftCoeff(speed: number, spinRate: number): number {
  if (speed === 0 || spinRate === 0) return 0;
  const s = (BALL.radius * spinRate) / speed;
  return 1 / (2 + 1 / s);
}

/** Acceleration of the ball for velocity v and spin vector w (rad/s). */
export function acceleration(v: Vec3, spin: Vec3): Vec3 {
  const speed = len(v);
  const k = (0.5 * BALL.airDensity * AREA) / BALL.mass;
  let a: Vec3 = [0, -BALL.gravity, 0];
  a = add(a, v, -k * BALL.dragCoeff * speed);
  const w = len(spin);
  if (w > 0 && speed > 0) {
    const side = cross(spin, v);          // direction of the Magnus force
    const sideLen = len(side);
    if (sideLen > 0) a = add(a, side, (k * liftCoeff(speed, w) * speed * speed) / sideLen);
  }
  return a;
}

/** Integrate the flight with fixed RK4 steps until stop() is true or maxT passes. */
export function simulate(p0: Vec3, v0: Vec3, spin: Vec3, stop: (s: Sample) => boolean, maxT = 3, dt = 1 / 240): Sample[] {
  const out: Sample[] = [{ t: 0, p: p0, v: v0 }];
  let p = p0, v = v0, t = 0;
  while (t < maxT) {
    const a1 = acceleration(v, spin);
    const v2 = add(v, a1, dt / 2), a2 = acceleration(v2, spin);
    const v3 = add(v, a2, dt / 2), a3 = acceleration(v3, spin);
    const v4 = add(v, a3, dt), a4 = acceleration(v4, spin);
    p = add(p, add(add(v, add(v2, v3), 2), v4), dt / 6);
    v = add(v, add(add(a1, add(a2, a3), 2), a4), dt / 6);
    t += dt;
    const s = { t, p, v };
    out.push(s);
    if (stop(s)) break;
  }
  return out;
}

/** Position and velocity where the ball crosses the plane z = zPlane (linear between steps). */
export function crossing(samples: Sample[], zPlane: number): Sample | null {
  for (let i = 1; i < samples.length; i++) {
    const a = samples[i - 1], b = samples[i];
    if (a.p[2] < zPlane && b.p[2] >= zPlane) {
      const w = (zPlane - a.p[2]) / (b.p[2] - a.p[2]);
      const mix = (x: Vec3, y: Vec3): Vec3 => [x[0] + (y[0] - x[0]) * w, x[1] + (y[1] - x[1]) * w, x[2] + (y[2] - x[2]) * w];
      return { t: a.t + (b.t - a.t) * w, p: mix(a.p, b.p), v: mix(a.v, b.v) };
    }
  }
  return null;
}

/**
 * Find the launch velocity (at a fixed speed) that sends the ball through `target`.
 * Shooting method: aim, fly, measure the miss at the target's plane, move the aim point, repeat.
 */
export function solveShot(p0: Vec3, target: Vec3, speed: number, spin: Vec3): { v0: Vec3; flight: Sample[]; miss: number } {
  let aim: Vec3 = [...target];
  let best = { v0: [0, 0, 0] as Vec3, flight: [] as Sample[], miss: Infinity };
  for (let i = 0; i < 40; i++) {
    const d: Vec3 = [aim[0] - p0[0], aim[1] - p0[1], aim[2] - p0[2]];
    const v0: Vec3 = [d[0] / len(d) * speed, d[1] / len(d) * speed, d[2] / len(d) * speed];
    const flight = simulate(p0, v0, spin, (s) => s.p[2] > target[2] + 0.5);
    const hit = crossing(flight, target[2]);
    if (!hit) break;
    const ex = target[0] - hit.p[0], ey = target[1] - hit.p[1];
    const miss = Math.hypot(ex, ey);
    if (miss < best.miss) best = { v0, flight, miss };
    if (miss < 0.0005) break;
    aim = [aim[0] + ex, aim[1] + ey, aim[2]];
  }
  return best;
}

/** Ball state at time t after the kick, linearly interpolated from the samples. */
export function stateAt(samples: Sample[], t: number): Sample {
  if (t <= 0) return samples[0];
  const last = samples[samples.length - 1];
  if (t >= last.t) return last;
  const i = Math.min(samples.length - 1, Math.max(1, Math.ceil(t / (samples[1].t - samples[0].t))));
  const a = samples[i - 1], b = samples[i];
  const w = (t - a.t) / (b.t - a.t);
  const mix = (x: Vec3, y: Vec3): Vec3 => [x[0] + (y[0] - x[0]) * w, x[1] + (y[1] - x[1]) * w, x[2] + (y[2] - x[2]) * w];
  return { t, p: mix(a.p, b.p), v: mix(a.v, b.v) };
}
