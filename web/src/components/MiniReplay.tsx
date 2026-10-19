// A live replay of a real clip on a canvas: pitch, players, the ball, and team shapes.
// Used as the landing page's product shot and in the scroll story (layers switch on as you scroll).
import { useEffect, useRef } from 'react';
import { duration, hull, sampleAt, type ClipPayload, type Side } from '../lib/clip';

export interface Layers { players: boolean; shapes: boolean; lines: boolean; ball: boolean }
const ALL: Layers = { players: true, shapes: true, lines: false, ball: true };

const COLOURS: Record<'focus' | 'other', string> = { focus: '#4cc3ff', other: '#ff8a3d' };

interface Props {
  clip: ClipPayload | null;
  layers?: Partial<Layers>;
  speed?: number;
  /** Controlled time in seconds; when given, the replay does not run its own clock. */
  time?: number;
  className?: string;
  label?: string;
}

export default function MiniReplay({ clip, layers, speed = 1, time, className, label }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const opts = useRef<Layers>({ ...ALL, ...layers });
  const controlled = useRef<number | undefined>(time);
  opts.current = { ...ALL, ...layers };
  controlled.current = time;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !clip) return;
    const ctx = canvas.getContext('2d')!;
    const total = duration(clip);
    const focus: Side = clip.meta.focus_team;
    let raf = 0, start = performance.now(), visible = true;
    const fade = { shapes: 0, lines: 0, ball: 0, players: 0 };

    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; });
    io.observe(canvas);

    const draw = (now: number) => {
      raf = requestAnimationFrame(draw);
      if (!visible) return;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = canvas.clientWidth, h = canvas.clientHeight;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      // fit the 105 x 68 m pitch with a margin
      const pad = Math.min(w, h) * 0.06;
      const scale = Math.min((w - 2 * pad) / 105, (h - 2 * pad) / 68);
      const ox = w / 2, oy = h / 2;
      const X = (x: number) => ox + x * scale, Y = (y: number) => oy - y * scale;

      // layers fade in and out smoothly instead of popping
      for (const k of Object.keys(fade) as (keyof Layers)[]) fade[k] += ((opts.current[k] ? 1 : 0) - fade[k]) * 0.08;

      // pitch markings
      ctx.strokeStyle = 'rgba(242,245,247,0.16)'; ctx.lineWidth = 1;
      ctx.strokeRect(X(-52.5), Y(34), 105 * scale, 68 * scale);
      ctx.beginPath(); ctx.moveTo(X(0), Y(34)); ctx.lineTo(X(0), Y(-34)); ctx.stroke();
      ctx.beginPath(); ctx.arc(X(0), Y(0), 9.15 * scale, 0, Math.PI * 2); ctx.stroke();
      for (const s of [-1, 1]) {
        ctx.strokeRect(s < 0 ? X(-52.5) : X(52.5 - 16.5), Y(20.16), 16.5 * scale, 40.32 * scale);
        ctx.strokeRect(s < 0 ? X(-52.5) : X(52.5 - 5.5), Y(9.16), 5.5 * scale, 18.32 * scale);
      }

      const t = controlled.current ?? (((now - start) / 1000) * speed) % total;
      const s = sampleAt(clip, t);
      const colour = (team: Side) => (team === focus ? COLOURS.focus : COLOURS.other);

      // team shapes from the blended positions (outfield players only)
      if (fade.shapes > 0.01) {
        for (const team of ['home', 'away'] as Side[]) {
          const pts = s.players.filter((p) => p.team === team && !p.keeper).map((p) => [p.x, p.y] as [number, number]);
          const poly = hull(pts);
          if (poly.length < 3) continue;
          ctx.beginPath();
          poly.forEach(([x, y], i) => (i ? ctx.lineTo(X(x), Y(y)) : ctx.moveTo(X(x), Y(y))));
          ctx.closePath();
          ctx.globalAlpha = 0.14 * fade.shapes; ctx.fillStyle = colour(team); ctx.fill();
          ctx.globalAlpha = 0.85 * fade.shapes; ctx.strokeStyle = colour(team); ctx.lineWidth = 1.5; ctx.stroke();
          if (fade.lines > 0.01) {
            // width and depth of the focus team's shape
            if (team === focus) {
              const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
              const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
              ctx.globalAlpha = 0.9 * fade.lines; ctx.setLineDash([4, 5]); ctx.strokeStyle = '#7ff0c6'; ctx.lineWidth = 1.2;
              ctx.beginPath(); ctx.moveTo(X(x0), Y(y0) + 14); ctx.lineTo(X(x1), Y(y0) + 14); ctx.stroke();
              ctx.beginPath(); ctx.moveTo(X(x1) + 14, Y(y0)); ctx.lineTo(X(x1) + 14, Y(y1)); ctx.stroke();
              ctx.setLineDash([]);
              ctx.fillStyle = '#7ff0c6'; ctx.font = '600 11px JetBrains Mono, monospace';
              ctx.fillText(`width ${(y1 - y0).toFixed(0)} m`, X(x1) + 20, Y((y0 + y1) / 2));
              ctx.fillText(`depth ${(x1 - x0).toFixed(0)} m`, X((x0 + x1) / 2) - 30, Y(y0) + 28);
            }
          }
          ctx.globalAlpha = 1;
        }
      }

      // players
      const r = Math.max(3.5, scale * 0.9);
      ctx.globalAlpha = fade.players;
      for (const p of s.players) {
        ctx.beginPath(); ctx.arc(X(p.x), Y(p.y), r, 0, Math.PI * 2);
        ctx.fillStyle = colour(p.team);
        ctx.shadowColor = colour(p.team); ctx.shadowBlur = 10;
        ctx.fill();
        ctx.shadowBlur = 0;
        if (p.keeper) { ctx.lineWidth = 1.5; ctx.strokeStyle = '#f2f5f7'; ctx.stroke(); }
      }
      ctx.globalAlpha = 1;

      // ball
      if (s.ball && fade.ball > 0.01) {
        ctx.globalAlpha = fade.ball;
        ctx.beginPath(); ctx.arc(X(s.ball[0]), Y(s.ball[1]), r * 0.7, 0, Math.PI * 2);
        ctx.fillStyle = '#ffe14d'; ctx.shadowColor = '#ffe14d'; ctx.shadowBlur = 16; ctx.fill(); ctx.shadowBlur = 0;
        ctx.globalAlpha = 1;
      }
    };
    raf = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(raf); io.disconnect(); start = 0; };
  }, [clip, speed]);

  return <canvas ref={canvasRef} className={className} role="img" aria-label={label ?? 'Live replay of a real football clip'} />;
}
