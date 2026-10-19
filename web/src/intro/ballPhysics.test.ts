import { describe, expect, it } from 'vitest';
import { BALL, crossing, liftCoeff, simulate, solveShot, type Vec3 } from './ballPhysics';

const SPOT: Vec3 = [0, BALL.radius, -11];
const len = (v: Vec3) => Math.hypot(v[0], v[1], v[2]);

describe('ball physics', () => {
  it('without air, a dropped ball follows free fall', () => {
    const still = simulate([0, 10, 0], [0, 0, 0], [0, 0, 0], (s) => s.t >= 1);
    const end = still[still.length - 1];
    // drag is tiny at low speed, so after 1 s the drop is close to g/2 = 4.905 m
    expect(10 - end.p[1]).toBeGreaterThan(4.8);
    expect(10 - end.p[1]).toBeLessThan(4.905);
  });

  it('a 26 m/s penalty reaches the goal line in about 0.45 s and slows as drag predicts', () => {
    const flight = simulate(SPOT, [0, 1.6, 26], [0, 0, 0], (s) => s.p[2] > 0.5);
    const hit = crossing(flight, 0)!;
    expect(hit.t).toBeGreaterThan(0.42);
    expect(hit.t).toBeLessThan(0.47);
    // Drag alone gives v = v0 * exp(-k * Cd * distance), k = rho * A / (2 m): about 13.6% lost over 11 m.
    const k = (BALL.airDensity * Math.PI * BALL.radius ** 2) / (2 * BALL.mass);
    const expected = 1 - Math.exp(-k * BALL.dragCoeff * 11);
    const lost = 1 - len(hit.v) / len([0, 1.6, 26]);
    expect(Math.abs(lost - expected)).toBeLessThan(0.01);
  });

  it('no spin means no sideways curve', () => {
    const flight = simulate(SPOT, [0, 2, 25], [0, 0, 0], (s) => s.p[2] > 0);
    expect(Math.abs(flight[flight.length - 1].p[0])).toBeLessThan(1e-9);
  });

  it('side spin curves the ball (Magnus) the right way', () => {
    // spin about +y (anticlockwise seen from above) pushes a ball moving +z towards +x
    const flight = simulate(SPOT, [0, 2, 25], [0, 40, 0], (s) => s.p[2] > 0);
    expect(flight[flight.length - 1].p[0]).toBeGreaterThan(0.1);
    expect(liftCoeff(25, 40)).toBeGreaterThan(0);
  });

  it('the solver sends the ball through the catch point within 2 cm', () => {
    const target: Vec3 = [0.18, 1.45, -0.5];
    const shot = solveShot(SPOT, target, 26, [0, 25, -8]);
    expect(shot.miss).toBeLessThan(0.02);
    expect(len(shot.v0)).toBeCloseTo(26, 6);
  });
});
