// The landing page: a football-first scroll story built on a real clip and real photos.
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
import 'lenis/dist/lenis.css';
import Nav, { ArrowUpRight, Wordmark } from '../components/Nav';
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

/** Bullet lines of one section ("Coach's view" or "Key numbers") of the coach's explanation. */
function section(clip: ClipPayload | null, name: string, next?: string): string[] {
  const text = clip?.explanation?.text ?? '';
  let part = text.split(`**${name}**`)[1] ?? '';
  if (next) part = part.split(`**${next}**`)[0];
  return part.split('\n').map((l) => l.replace(/^\s*\*\s*/, '').trim()).filter(Boolean);
}

function Hero({ clip }: { clip: ClipPayload | null }) {
  const facts = section(clip, 'Key numbers');
  return (
    <section className="hero photo-band">
      <img className="photo hero-photo" src="/img/hero-pitch.webp" srcSet="/img/hero-pitch-1200.webp 1200w, /img/hero-pitch.webp 1920w" sizes="100vw" alt="" fetchPriority="high" />
      <div className="container hero-grid">
        <div className="hero-copy">
          <p className="eyebrow hero-in" style={{ animationDelay: '0.1s' }}>AI tactical analysis for football</p>
          <h1 className="headline hero-title hero-in" style={{ animationDelay: '0.2s' }}>
            Read any football<br />moment <em>like a coach.</em>
          </h1>
          <p className="lede hero-in" style={{ animationDelay: '0.35s' }}>
            Real tracking data, exact geometry, and an AI coach that only says what the numbers show.
          </p>
          <div className="hero-ctas hero-in" style={{ animationDelay: '0.5s' }}>
            <Link to="/app/clip/musiala-winner" className="btn btn-primary">Open a replay<span className="btn-arrow"><ArrowUpRight /></span></Link>
            <a href="#how" className="btn btn-ghost">See how it works</a>
          </div>
          <ul className="proof hero-in" style={{ animationDelay: '0.65s' }}>
            <li><strong>7</strong> real match clips</li>
            <li><strong>DFL</strong> open tracking data</li>
            <li><strong>0</strong> invented numbers</li>
          </ul>
        </div>
        <aside className="hero-card hero-in" style={{ animationDelay: '0.8s' }} aria-label="Live replay of a real goal">
          <div className="hero-card-head"><span>Live replay</span><span className="hero-card-tag"><span className="live-dot" />Real data</span></div>
          <div className="hero-card-body glass">
            <MiniReplay clip={clip} theme="grass" className="hero-card-canvas" label="Live replay of Musiala's 89th-minute winner, from real tracking data" />
            <div className="hero-card-meta">
              <p className="hero-card-title">{clip?.meta.title ?? 'Loading the clip…'}</p>
              <ul>{facts.slice(0, 1).map((f) => <li key={f}>{f}</li>)}</ul>
            </div>
          </div>
        </aside>
      </div>
      <a href="#how" className="scroll-cue" aria-label="Scroll to how it works"><span /></a>
    </section>
  );
}

const STEPS: { title: string; text: string; layers: Partial<Layers> }[] = [
  { title: 'Every player, 25 times a second.', text: 'We start from real positions: who stood where, frame by frame. Nothing is detected or guessed.', layers: { players: true, ball: true, shapes: false, lines: false } },
  { title: 'Geometry, not guesswork.', text: 'Team shapes, width, depth and the height of the back line are plain maths on those positions, and every function is tested.', layers: { players: true, ball: true, shapes: true, lines: true } },
  { title: 'A coach that stays grounded.', text: 'The AI only narrates the facts we computed. Every number it writes is checked against them before you see it.', layers: { players: true, ball: true, shapes: true, lines: false } },
];

function HowItWorks({ clip }: { clip: ClipPayload | null }) {
  const el = useRef<HTMLElement>(null);
  const [step, setStep] = useState(0);
  const lines = section(clip, "Coach's view", 'Key numbers');
  useEffect(() => {
    const node = el.current;
    if (!node) return;
    const st = ScrollTrigger.create({
      trigger: node, start: 'top top', end: 'bottom bottom',
      onUpdate: (self) => setStep(Math.min(STEPS.length - 1, Math.floor(self.progress * STEPS.length))),
    });
    return () => st.kill();
  }, []);
  return (
    <section id="how" className="how" ref={el}>
      <div className="how-sticky photo-band">
        <img className="photo how-photo" src="/img/stadium-crowd.webp" alt="" loading="lazy" />
        <div className="container how-head">
          <h2 className="eyebrow">How it works</h2>
        </div>
        <div className="container how-grid">
          <div className="how-visual">
            <MiniReplay clip={clip} theme="grass" layers={STEPS[step].layers} className="how-canvas" />
            <div className={`coach-card glass ${step === 2 ? 'is-on' : ''}`} aria-hidden={step !== 2}>
              <p className="coach-label"><span className="live-dot" />AI coach · grounded</p>
              <p className="coach-text">{lines[0] ?? ''}</p>
            </div>
          </div>
          <ol className="how-steps">
            {STEPS.map((s, i) => (
              <li key={s.title} className={`glass ${i === step ? 'is-active' : ''}`}>
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
      <h2 className="headline section-title reveal">Two ways in.<br /><em className="dim">One analysis out.</em></h2>
      <div className="input-grid">
        <article className="input-card reveal">
          <div className="input-visual photo-band" aria-hidden="true">
            <img className="photo" src="/img/players-action.webp" alt="" loading="lazy" />
            <table className="mono data-table glass">
              <tbody>
                {[['0.00', 'away', 'Kimmich', '−4.1', '−11.3'], ['0.00', 'home', 'Chabot', '12.5', '−7.9'], ['0.04', 'away', 'Musiala', '21.7', '13.3'], ['0.04', 'ball', '', '27.7', '−26.8']].map((r, i) => (
                  <tr key={i} style={{ animationDelay: `${i * 0.15}s` }}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>
                ))}
              </tbody>
            </table>
            <div className="data-dots glass">{at(0).map((p, i) => <span key={p.id} style={{ ...pos(p), animationDelay: `${0.6 + i * 0.04}s`, background: p.team === focus ? 'var(--team-a)' : 'var(--team-b)' }} />)}</div>
          </div>
          <p className="input-tag">Main way in</p>
          <h3>Coordinate data</h3>
          <p>A CSV or Excel file in our template, or files from Metrica, SkillCorner or Sportec. We check it and turn it into a replay.</p>
        </article>
        <article className="input-card reveal" style={{ transitionDelay: '0.12s' }}>
          <div className="input-visual drone-visual" aria-hidden="true">
            <img className="photo" src="/img/aerial-pitch.webp" alt="" loading="lazy" />
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
    <section id="accuracy" className="accuracy">
      <div className="container">
        <p className="eyebrow reveal">Accuracy</p>
        <h2 className="headline section-title reveal">Measured,<br /><em className="dim">not guessed.</em></h2>
        <div className="stat-grid">
          {stats.map((s, i) => (
            <div className="stat glass reveal" key={s.label} style={{ transitionDelay: `${i * 0.08}s` }}>
              <p className="stat-value"><CountUp to={s.value} decimals={s.decimals} suffix={s.suffix} /></p>
              <p className="stat-label">{s.label}</p>
            </div>
          ))}
        </div>
        <p className="footnote reveal">
          Drone numbers are medians over 13 SoccerTrack segments against GNSS ground truth. On 6 segments we never tuned on: 96.9% found and 0.44 m.
        </p>
      </div>
    </section>
  );
}

function CoachQuote({ clip }: { clip: ClipPayload | null }) {
  const lines = section(clip, "Coach's view", 'Key numbers');
  return (
    <section id="coach" className="quote photo-band">
      <img className="photo" src="/img/stadium-night.webp" alt="" loading="lazy" />
      <div className="container">
        <p className="eyebrow reveal">The AI coach</p>
        <blockquote className="quote-text reveal">“{lines[1] ?? lines[0] ?? ''}”</blockquote>
        <p className="quote-meta reveal">Musiala's winner, Köln v Bayern · every number checked against the computed facts</p>
      </div>
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
        <section className="final photo-band">
          <img className="photo" src="/img/players-action.webp" alt="" loading="lazy" />
          <div className="container final-inner">
            <h2 className="headline final-title reveal">See it on a <em>real goal.</em></h2>
            <Link to="/app/clip/musiala-winner" className="btn btn-primary reveal">Open the replay<span className="btn-arrow"><ArrowUpRight /></span></Link>
          </div>
        </section>
      </main>
      <footer className="footer">
        <div className="container footer-grid">
          <div><Wordmark /><p className="footer-small">Built by Mohit (AI, app, video) and Rohit (data, geometry).</p></div>
          <div className="footer-small">
            <p>Tracking data: DFL / Bassek et al., Scientific Data 2025 (CC BY 4.0); Metrica Sports sample data; SoccerTrack.</p>
            <p>Photos: Paul McWilliam, Willian Justen de Vasconcellos, James Kirkup, jebin ephrimraj and Mark mc neill on Unsplash.</p>
            <p>An AI Engineer portfolio project.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
