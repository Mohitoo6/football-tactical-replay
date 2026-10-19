import { describe, expect, it } from 'vitest';
import { CATCH, SHOT, SPOT, T_BLACK, T_CATCH, T_KICK, WALL_BLACK, WALL_END, frameAt, sceneTime } from './timeline';

describe('intro timeline', () => {
  it('the shot is solved through the catch point', () => {
    expect(SHOT.miss).toBeLessThan(0.02);
    console.log('kick', T_KICK, 'catch', T_CATCH.toFixed(3), 'black', T_BLACK.toFixed(3), 'wall black', WALL_BLACK.toFixed(2), 'wall end', WALL_END.toFixed(2));
  });

  it('scene time only moves forward, and slows down during the flight', () => {
    let prev = -1;
    for (let t = 0; t < WALL_END; t += 0.01) { const s = sceneTime(t); expect(s).toBeGreaterThanOrEqual(prev); prev = s; }
    const before = sceneTime(1.01) - sceneTime(1.0);
    const flight = sceneTime((WALL_BLACK + T_KICK) / 2 + 0.01) - sceneTime((WALL_BLACK + T_KICK) / 2);
    expect(flight).toBeLessThan(before * 0.5);
  });

  it('the ball waits on the spot, meets the hands, then ends at the face before the screen is black', () => {
    expect(frameAt(1).ball).toEqual(SPOT);
    const atCatch = frameAt(0);
    expect(atCatch.black).toBe(0);
    // find the wall time of the catch and check the ball is at the hands there
    let t = 0; while (sceneTime(t) < T_CATCH) t += 0.001;
    const f = frameAt(t);
    expect(Math.hypot(f.ball[0] - CATCH[0], f.ball[1] - CATCH[1], f.ball[2] - CATCH[2])).toBeLessThan(0.05);
    expect(frameAt(WALL_END).black).toBe(1);
  });
});
