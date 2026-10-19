import { describe, expect, it } from 'vitest';
import { CUT, FLIGHT, KICK_FROM, SHOT, T_BLACK, ballAt, flightTime, project, unproject } from './penalty';

describe('photo intro camera and flight', () => {
  it('projection and unprojection agree', () => {
    const p = unproject(959, 320, 0.51);
    const s = project(p);
    expect(s.x).toBeCloseTo(959, 6);
    expect(s.y).toBeCloseTo(320, 6);
  });

  it('the ball starts on the grass in front of the striker in the photo', () => {
    const s = project(KICK_FROM);
    // the striker's plant foot is at about (550, 632) and his boot at (607, 547)
    expect(Math.abs(s.x - 597)).toBeLessThan(25);
    expect(Math.abs(s.y - 620)).toBeLessThan(25);
    expect(s.r).toBeGreaterThan(10);
    expect(s.r).toBeLessThan(20);
  });

  it('the computed flight ends at the lens, centred, and covers the whole 1600 x 900 frame', () => {
    expect(SHOT.miss).toBeLessThan(0.01);
    const end = project(FLIGHT[FLIGHT.length - 1].p);
    expect(Math.abs(end.x - 805)).toBeLessThan(20);
    expect(Math.abs(end.y - 430)).toBeLessThan(20);
    const farthestCorner = Math.max(...[[0, 0], [1600, 0], [0, 900], [1600, 900]].map(([x, y]) => Math.hypot(x - end.x, y - end.y)));
    expect(end.r).toBeGreaterThan(farthestCorner);
  });

  it('slow motion: the flight only starts at the cut and runs slower than real time', () => {
    expect(flightTime(CUT - 0.5)).toBe(0);
    const a = flightTime(CUT + 1), b = flightTime(CUT + 1.1);
    expect(b - a).toBeCloseTo(0.018, 4);
    expect(T_BLACK - CUT).toBeGreaterThan(1.5);
    expect(T_BLACK - CUT).toBeLessThan(3);
    expect(ballAt(T_BLACK).screen.r).toBeGreaterThan(1000);
  });
});
