// Renders the two-shot photo intro on one canvas, from a single clock.
// ?t=3.1 freezes it at that wall time; window.__setTime(t) does the same (for frame checks).
import { useEffect, useRef } from 'react';
import { CUT, FADE_IN, IMAGE, T_BLACK, ballAt, droplets, flightTime, rng } from './penalty';

declare global { interface Window { __setTime?: (t: number) => void } }

const SRC = { shot1: '/intro/shot1.jpg', shot2: '/intro/shot2-clean.jpg', ball: '/intro/ball.webp' };
const clamp = (v: number) => Math.max(0, Math.min(1, v));
const smooth = (v: number) => { v = clamp(v); return v * v * (3 - 2 * v); };

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((ok, fail) => { const i = new Image(); i.onload = () => ok(i); i.onerror = fail; i.src = src; });
}

/** A copy of an image blurred once, used to fake depth of field cheaply. */
function blurred(img: HTMLImageElement, px: number): HTMLCanvasElement {
  const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
  const g = c.getContext('2d')!; g.filter = `blur(${px}px)`; g.drawImage(img, 0, 0);
  return c;
}

function grainTile(): HTMLCanvasElement {
  const c = document.createElement('canvas'); c.width = c.height = 192;
  const g = c.getContext('2d')!; const d = g.createImageData(192, 192); const r = rng(3);
  for (let i = 0; i < d.data.length; i += 4) { const v = r() * 255; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255; }
  g.putImageData(d, 0, 0);
  return c;
}

// rain streaks and crowd camera flashes, placed once
const RAIN = (() => { const r = rng(11); return Array.from({ length: 260 }, () => ({ x: r() * 1700 - 50, y: r() * 900, speed: 900 + r() * 700, len: 14 + r() * 26, a: 0.12 + r() * 0.28 })); })();
const FLASHES = (() => { const r = rng(5); return Array.from({ length: 46 }, () => ({ x: r() * 1600, y: 170 + r() * 280, phase: r() * 3, size: 1.2 + r() * 2.4 })); })();

export default function PhotoIntro({ onEnd }: { onEnd: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const endRef = useRef(onEnd);
  endRef.current = onEnd;

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext('2d')!;
    const frozen = new URLSearchParams(window.location.search).get('t');
    let forced: number | null = frozen === null ? null : parseFloat(frozen);
    window.__setTime = (t: number) => { forced = t; };
    let raf = 0, start = 0, ended = false, cancelled = false;

    Promise.all([loadImage(SRC.shot1), loadImage(SRC.shot2), loadImage(SRC.ball)]).then(([shot1, shot2, ball]) => {
      if (cancelled) return;
      const shot2Soft = blurred(shot2, 5);
      const grain = grainTile();
      start = performance.now();

      const frame = () => {
        raf = requestAnimationFrame(frame);
        const t = forced ?? (performance.now() - start) / 1000;
        const dpr = Math.min(2, window.devicePixelRatio || 1);
        const W = canvas.clientWidth, H = canvas.clientHeight;
        if (canvas.width !== Math.round(W * dpr)) { canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr); }
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.fillStyle = '#000'; ctx.fillRect(0, 0, canvas.width, canvas.height);

        // "cover" fit of the 1600 x 900 photos, plus a slow push-in towards a focus point
        const cover = Math.max(W / IMAGE.w, H / IMAGE.h) * dpr;
        const place = (zoom: number, fx: number, fy: number, swayX = 0, swayY = 0) => {
          const s = cover * zoom;
          const ox = canvas.width / 2 - fx * s + (fx - IMAGE.w / 2) * cover + swayX * cover;
          const oy = canvas.height / 2 - fy * s + (fy - IMAGE.h / 2) * cover + swayY * cover;
          ctx.setTransform(s, 0, 0, s, ox, oy);
        };

        if (t >= T_BLACK) {
          if (!ended && forced === null && t > T_BLACK + 0.12) { ended = true; endRef.current(); }
          return;
        }

        let rainSpeed = 1;
        if (t < CUT) {
          // Shot 1: the wait. Push in on the striker; the keeper breathes.
          const p = smooth(t / CUT);
          place(1 + 0.08 * p, 800, 380, Math.sin(t * 1.3) * 3, Math.sin(t * 2.1) * 2);
          ctx.drawImage(shot1, 0, 0);
          for (const f of FLASHES) {
            const k = ((t * 0.9 + f.phase) % 3);
            const a = k < 0.12 ? 1 - k / 0.12 : 0;
            if (a <= 0) continue;
            const g = ctx.createRadialGradient(f.x, f.y, 0, f.x, f.y, f.size * 5);
            g.addColorStop(0, `rgba(255,255,255,${0.9 * a})`); g.addColorStop(1, 'rgba(255,255,255,0)');
            ctx.fillStyle = g; ctx.fillRect(f.x - f.size * 5, f.y - f.size * 5, f.size * 10, f.size * 10);
          }
        } else {
          // Shot 2: the ball, in slow motion, straight at the keeper.
          const b = ballAt(t);
          const w = t - CUT;
          place(1 + 0.04 * smooth(w / 2.2), 900, 380);
          ctx.drawImage(shot2, 0, 0);
          ctx.globalAlpha = 0.85 * smooth((5 - b.screen.depth) / 4);   // focus pulls to the ball
          ctx.drawImage(shot2Soft, 0, 0);
          ctx.globalAlpha = 1;
          rainSpeed = 0.18;

          // ghost copies a moment behind the ball read as motion blur
          const s = flightTime(t);
          for (let k = 3; k >= 1; k--) {
            const g = ballAt(t - k * 0.02);
            if (flightTime(t - k * 0.02) <= 0) continue;
            ctx.globalAlpha = 0.12 * (4 - k);
            ctx.drawImage(ball, g.screen.x - g.screen.r, g.screen.y - g.screen.r, g.screen.r * 2, g.screen.r * 2);
          }
          ctx.globalAlpha = 1;
          ctx.save();
          ctx.translate(b.screen.x, b.screen.y);
          ctx.rotate(-s * 5);                                  // the spin, seen from the front
          ctx.shadowColor = 'rgba(0,0,0,0.55)'; ctx.shadowBlur = b.screen.r * 0.25;
          ctx.drawImage(ball, -b.screen.r, -b.screen.r, b.screen.r * 2, b.screen.r * 2);
          ctx.restore();

          for (const d of droplets(t)) {
            ctx.globalAlpha = d.alpha;
            ctx.strokeStyle = '#eef6ff'; ctx.lineCap = 'round'; ctx.lineWidth = d.r * 1.6;
            ctx.beginPath(); ctx.moveTo(d.x - d.dx, d.y - d.dy); ctx.lineTo(d.x, d.y); ctx.stroke();
          }
          ctx.globalAlpha = 1;
        }

        // rain, in screen space over both shots (slow motion slows it too)
        ctx.setTransform(cover, 0, 0, cover, canvas.width / 2 - (IMAGE.w / 2) * cover, canvas.height / 2 - (IMAGE.h / 2) * cover);
        const clock = t < CUT ? t : CUT + (t - CUT) * rainSpeed;
        ctx.lineCap = 'round';
        for (const r of RAIN) {
          const y = ((r.y + r.speed * clock) % 960) - 30;
          const x = r.x - (y - r.y) * 0.08;
          ctx.strokeStyle = `rgba(220,235,255,${r.a})`; ctx.lineWidth = 1.1;
          ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - r.len * 0.08, y + r.len * (t < CUT ? 1 : 0.35)); ctx.stroke();
        }

        // film finish: vignette, grain, fade in, and the white flash of the cut
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        const v = ctx.createRadialGradient(canvas.width / 2, canvas.height / 2, canvas.height * 0.35, canvas.width / 2, canvas.height / 2, canvas.width * 0.75);
        v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,0.55)');
        ctx.fillStyle = v; ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.globalAlpha = 0.07; ctx.globalCompositeOperation = 'overlay';
        ctx.fillStyle = ctx.createPattern(grain, 'repeat')!;
        ctx.translate((t * 997) % 192, (t * 613) % 192);
        ctx.fillRect(-192, -192, canvas.width + 384, canvas.height + 384);
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = 1;
        const black = 1 - smooth(t / FADE_IN);
        const flash = t >= CUT ? 1 - clamp((t - CUT) / 0.09) : 0;
        if (black > 0) { ctx.fillStyle = `rgba(0,0,0,${black})`; ctx.fillRect(0, 0, canvas.width, canvas.height); }
        if (flash > 0) { ctx.fillStyle = `rgba(255,255,255,${0.45 * flash})`; ctx.fillRect(0, 0, canvas.width, canvas.height); }
      };
      frame();
    }).catch(() => endRef.current());

    return () => { cancelled = true; cancelAnimationFrame(raf); delete window.__setTime; };
  }, []);

  return <canvas ref={canvasRef} className="intro-canvas" role="img" aria-label="A penalty seen through the goalkeeper's eyes: the striker shoots and the ball flies straight at you" />;
}
