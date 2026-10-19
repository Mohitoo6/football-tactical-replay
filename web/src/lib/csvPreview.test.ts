import { describe, expect, it } from 'vitest';
import { previewCsv } from './csvPreview';

const CSV = `time_s,team,player,jersey,position,x,y
0.00,home,Keeper Home,1,GK,-48.5,0.3
0.00,home,Player 4,4,,-30.2,-12.0
0.00,away,Keeper Away,1,GK,49.0,-1.2
0.00,ball,,,,-28.0,5.5
0.04,home,Keeper Home,1,GK,-48.5,0.3
0.04,home,Player 4,4,,-30.1,-12.1
0.04,away,Keeper Away,1,GK,49.0,-1.2
0.08,home,Keeper Home,1,GK,-48.5,0.3
`;

describe('CSV preview', () => {
  it('counts moments, the frame rate, players and ball rows', () => {
    const p = previewCsv(CSV, 'metres');
    expect(p.missing).toEqual([]);
    expect(p.moments).toBe(3);
    expect(p.frameRate).toBe(25);
    expect(p.players).toEqual({ home: 2, away: 1 });
    expect(p.ballShare).toBeCloseTo(1 / 3, 6);
    expect(p.clip!.frames[0].players.find((x) => x.keeper && x.team === 'home')!.x).toBe(-48.5);
  });

  it('converts corner metres and 0-1 coordinates to centre metres', () => {
    const corner = previewCsv('time_s,team,x,y\n0,home,52.5,34\n', 'metres_corner');
    expect(corner.clip!.frames[0].players[0]).toMatchObject({ x: 0, y: 0 });
    const norm = previewCsv('time_s,team,x,y\n0,away,1,0\n', 'normalised');
    expect(norm.clip!.frames[0].players[0]).toMatchObject({ x: 52.5, y: -34 });
  });

  it('names the missing columns instead of guessing', () => {
    expect(previewCsv('time,side,px,py\n0,home,1,2\n', 'metres').missing).toEqual(['time_s', 'team', 'x', 'y']);
  });
});
