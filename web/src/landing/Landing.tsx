// The landing page: an Apple-style scroll story about the product, built on a real clip.
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
import 'lenis/dist/lenis.css';
import Nav, { Wordmark } from '../components/Nav';
import MiniReplay, { type Layers } from '../components/MiniReplay';
import { useReveal } from '../components/useReveal';
import { loadClip, type ClipPayload } from '../lib/clip';
import './landing.css';

gsap.registerPlugin(ScrollTrigger);

const HERO_CLIP = '/data/musiala-winner.json';

/** Smooth scrolling (Lenis) driven by GSAP's ticker so ScrollTrigger stays in sync. */
function useSmoothScroll() {
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const lenis = new Lenis({ lerp: 0.1 });
    lenis.on('scroll', ScrollTrigger.update);
    const tick = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);
    return () => { gsap.ticker.remove(tick); lenis.destroy(); };
  }, []);
}

function coachLines(clip: ClipPayload | null): string[] {
  const text = clip?.explanation?.text ?? '';
  const part = text.split("**Coach's view**")[1]?.split('**Key numbers**')[0] ?? '';
  return part.split('\n').map((l) => l.replace(/^\s*\*\s*/, '').trim()).filter(Boolean);
}

function Hero({ clip }: { clip: ClipPayload | null }) {
  const shot = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = shot.current;
    if (!el) return;
    const tween = gsap.fromTo(el, { scale: 0.86, rotateX: 16, y: 40 }, {
      scale: 1, rotateX: 0, y: 0, ease: 'none',
      scrollTrigger: { trigger: el, start: 'top 95%', end: 'top 25%', scrub: true },
    });
    return () => { tween.scrollTrigger?.kill(); tween.kill(); };
  }, []);
  return (
    <section className="hero">
      <div className="container hero-copy">
        <p className="eyebrow hero-in" style={{ animationDelay: '0.1s' }}>Football tactical replay</p>
        <h1 className="headline hero-title hero-in" style={{ animationDelay: '0.2s' }}>
          Read any football moment<br /><span className="gradient-text">like a coach.</span>
        </h1>
        <p className="lede hero-in" style={{ animationDelay: '0.35s' }}>
          Real tracking data, exact geometry, and an AI coach that only says what the numbers show.
        </p>
        <div className="hero-ctas hero-in" style={{ animationDelay: '0.5s' }}>
          <Link to="/app/clip/musiala-winner" className="btn btn-primary">Open a replay</Link>
          <a href="#how" className="btn btn-ghost">See how it works</a>
        </div>
      </div>
      <div className="container hero-stage">
        <div className="hero-shot" ref={shot}>
          <MiniReplay clip={clip} className="hero-canvas" label="Live replay of Musiala's 89th-minute winner, from real tracking data" />
          <div className="hero-chip"><span className="live-dot" />Live · real DFL tracking data<span className="chip-title"> · {clip?.meta.title ?? 'loading'}</span></div>
        </div>
      </div>
    </section>
  );
}

const STEPS: { title: string; text: string; layers: Partial<Layers> }[] = [
  { title: 'Every player, 25 times a second.', text: 'We start from real positions: who stood where, frame by frame. Nothing is detected or guessed.', layers: { players: true, ball: true, shapes: false, lines: false } },
  { title: 'Geometry, not guesswork.', text: 'Team shapes, width, depth and the height of the back line are plain maths on those positions, and every function is tested.', layers: { players: true, ball: true, shapes: true, lines: true } },
  { title: 'A coach that stays grounded.', text: 'The AI only narrates the facts we computed. Every number it writes is checked against them before you see it.', layers: { players: true, ball: true, shapes: true, lines: false } },
];

function HowItWorks({ clip }: { clip: ClipPayload | null }) {
  const section = useRef<HTMLElement>(null);
  const [step, setStep] = useState(0);
  const lines = coachLines(clip);
  useEffect(() => {
    const el = section.current;
    if (!el) return;
    const st = ScrollTrigger.create({
      trigger: el, start: 'top top', end: 'bottom bottom',
      onUpdate: (self) => setStep(Math.min(STEPS.length - 1, Math.floor(self.progress * STEPS.length))),
    });
    return () => st.kill();
  }, []);
  return (
    <section id="how" className="how" ref={section}>
      <div className="how-sticky">
        <div className="container how-grid">
          <div className="how-visual">
            <MiniReplay clip={clip} layers={STEPS[step].layers} className="how-canvas" />
            <div className={`coach-card ${step === 2 ? 'is-on' : ''}`} aria-hidden={step !== 2}>
              <p className="coach-label"><span className="live-dot" />AI coach · grounded</p>
              <p className="coach-text">{lines[0] ?? ''}</p>
            </div>
          </div>
          <ol className="how-steps">
            {STEPS.map((s, i) => (
              <li key={s.title} className={i === step ? 'is-active' : ''}>
                <span className="how-num mono">0{i + 1}</span>
                <h3>{s.title}</h3>
                <p>{s.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

function Inputs({ clip }: { clip: ClipPayload | null }) {
  // real positions from the clip: the first frame for the data card, a later one for the drone card
  const at = (k: number) => clip?.frames[Math.min(clip.frames.length - 1, k)]?.players ?? [];
  const pos = (p: { x: number; y: number }) => ({ left: `${((p.x + 52.5) / 105) * 100}%`, top: `${((34 - p.y) / 68) * 100}%` });
  const focus = clip?.meta.focus_team;
  return (
    <section id="inputs" className="inputs container">
      <p className="eyebrow reveal">Your data</p>
      <h2 className="headline section-title reveal">Two ways in.<br /><span className="dim">One analysis out.</span></h2>
      <div className="input-grid">
        <article className="input-card reveal">
          <div className="input-visual data-visual" aria-hidden="true">
            <table className="mono">
              <tbody>
                {[['0.00', 'away', 'Kimmich', '−4.1', '−11.3'], ['0.00', 'home', 'Chabot', '12.5', '−7.9'], ['0.04', 'away', 'Musiala', '21.7', '13.3'], ['0.04', 'ball', '', '27.7', '−26.8']].map((r, i) => (
                  <tr key={i} style={{ animationDelay: `${i * 0.15}s` }}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>
                ))}
              </tbody>
            </table>
            <div className="data-dots">{at(0).map((p, i) => <span key={p.id} style={{ ...pos(p), animationDelay: `${0.6 + i * 0.04}s`, background: p.team === focus ? 'var(--team-a)' : 'var(--team-b)' }} />)}</div>
          </div>
          <p className="input-tag">Main way in</p>
          <h3>Coordinate data</h3>
          <p>A CSV or Excel file in our template, or files from Metrica, SkillCorner or Sportec. We check it and turn it into a replay.</p>
        </article>
        <article className="input-card reveal" style={{ transitionDelay: '0.12s' }}>
          <div className="input-visual drone-visual" aria-hidden="true">
            <div className="drone-lines" />
            <div className="drone-scan" />
            <div className="drone-pitch">{at(60).map((p, i) => <span key={p.id} className="drone-ring" style={{ ...pos(p), animationDelay: `${0.8 + i * 0.06}s`, borderColor: p.team === focus ? 'var(--team-a)' : 'var(--team-b)' }} />)}</div>
          </div>
          <p className="input-tag">Also works</p>
          <h3>Drone video</h3>
          <p>A still, top-down video of the whole pitch. We calibrate from the painted lines, find and follow every player, and refuse footage we cannot read well.</p>
        </article>
      </div>
    </section>
  );
}

function CountUp({ to, decimals = 0, suffix = '' }: { to: number; decimals?: number; suffix?: string }) {
  const el = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const node = el.current;
    if (!node) return;
    const obj = { v: 0 };
    const tween = gsap.to(obj, {
      v: to, duration: 1.6, ease: 'power3.out',
      scrollTrigger: { trigger: node, start: 'top 85%', once: true },
      onUpdate: () => { node.textContent = obj.v.toFixed(decimals) + suffix; },
    });
    return () => { tween.scrollTrigger?.kill(); tween.kill(); };
  }, [to, decimals, suffix]);
  return <span ref={el}>{(0).toFixed(decimals) + suffix}</span>;
}

function Accuracy() {
  const stats = [
    { value: 98.6, decimals: 1, suffix: '%', label: 'of players found in drone video' },
    { value: 0.35, decimals: 2, suffix: ' m', label: 'median position error' },
    { value: 97.4, decimals: 1, suffix: '%', label: 'of identities kept through the clip' },
    { value: 118, decimals: 0, suffix: '', label: 'automated tests' },
  ];
  return (
    <section id="accuracy" className="accuracy container">
      <p className="eyebrow reveal">Accuracy</p>
      <h2 className="headline section-title reveal">Measured,<br /><span className="dim">not guessed.</span></h2>
      <div className="stat-grid">
        {stats.map((s, i) => (
          <div className="stat reveal" key={s.label} style={{ transitionDelay: `${i * 0.08}s` }}>
            <p className="stat-value mono"><CountUp to={s.value} decimals={s.decimals} suffix={s.suffix} /></p>
            <p className="stat-label">{s.label}</p>
          </div>
        ))}
      </div>
      <p className="footnote reveal">
        Drone numbers are medians over 13 SoccerTrack segments against GNSS ground truth. On 6 segments we never tuned on: 96.9% found and 0.44 m.
      </p>
    </section>
  );
}

function CoachQuote({ clip }: { clip: ClipPayload | null }) {
  const lines = coachLines(clip);
  return (
    <section className="quote container">
      <p className="eyebrow reveal">The AI coach</p>
      <blockquote className="quote-text reveal">“{lines[1] ?? lines[0] ?? ''}”</blockquote>
      <p className="quote-meta reveal mono">Musiala's winner · every number checked against the computed facts</p>
    </section>
  );
}

export default function Landing() {
  const [clip, setClip] = useState<ClipPayload | null>(null);
  const page = useRef<HTMLDivElement>(null);
  useSmoothScroll();
  useReveal(page);
  useEffect(() => { loadClip(HERO_CLIP).then(setClip).catch(() => setClip(null)); }, []);
  useEffect(() => { ScrollTrigger.refresh(); }, [clip]);
  return (
    <div className="landing" ref={page}>
      <Nav />
      <main>
        <Hero clip={clip} />
        <HowItWorks clip={clip} />
        <Inputs clip={clip} />
        <Accuracy />
        <CoachQuote clip={clip} />
        <section className="final container">
          <h2 className="headline final-title reveal">See it on a real goal.</h2>
          <Link to="/app/clip/musiala-winner" className="btn btn-primary reveal">Open the replay</Link>
        </section>
      </main>
      <footer className="footer">
        <div className="container footer-grid">
          <div><Wordmark /><p className="footer-small">Built by Mohit (AI, app, video) and Rohit (data, geometry).</p></div>
          <div className="footer-small">
            <p>Tracking data: DFL / Bassek et al., Scientific Data 2025 (CC BY 4.0); Metrica Sports sample data; SoccerTrack.</p>
            <p>An AI Engineer portfolio project.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
