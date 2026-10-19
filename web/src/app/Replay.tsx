// The replay screen: the pitch with playback, a timeline of touches and goals, and a side panel with
// the AI coach (grounded, clickable clocks), the shape numbers over time, and the chain of events.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router';
import AppLayout from './AppLayout';
import MiniReplay, { type Layers } from '../components/MiniReplay';
import MetricCharts from './MetricCharts';
import CoachText from './CoachText';
import { api, clockSeconds, formatClock, ApiError } from '../lib/api';
import { duration as clipDuration, type ClipPayload, type Explanation, type Grounding, type Side } from '../lib/clip';
import { METRICS, events as clipEvents, metricSeries } from '../lib/replay';
import './replay.css';

type Tab = 'coach' | 'numbers' | 'events';
const SPEEDS = [0.5, 1, 2];
const LAYER_BUTTONS: [keyof Layers, string][] = [['shapes', 'Team shapes'], ['lines', 'Width & depth'], ['trail', 'Ball trail'], ['labels', 'Shirt numbers']];
const PITCH = { focus: '#3db4ff', other: '#ff8a3d' };   // the dot colours on the pitch

function metricLabel(key: string) {
  const m = METRICS.find((x) => x.key === key);
  return m ? { label: m.label, unit: m.unit } : { label: key, unit: '' };
}

export default function Replay() {
  const { id = '' } = useParams();
  const [params] = useSearchParams();
  const [clip, setClip] = useState<ClipPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>(() => (['coach', 'numbers', 'events'].includes(params.get('tab') ?? '') ? params.get('tab') as Tab : 'coach'));
  const [copied, setCopied] = useState(false);
  const [layers, setLayers] = useState<Partial<Layers>>({ shapes: true, lines: false, trail: true, labels: true });
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [now, setNow] = useState(0);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [grounding, setGrounding] = useState<Grounding | null>(null);
  const [asking, setAsking] = useState<'idle' | 'busy' | string>('idle');
  const tRef = useRef(0);

  useEffect(() => {
    setClip(null); setError(null); tRef.current = 0; setNow(0);
    // a shared link (?t=18) opens paused at that moment; otherwise the clip plays from the start
    const at = parseFloat(params.get('t') ?? '');
    api.clip(id, 1).then((c) => {
      setClip(c); setExplanation(c.explanation); setGrounding(c.grounding ?? null);
      if (Number.isFinite(at)) { tRef.current = Math.max(0, Math.min(clipDuration(c), at)); setNow(tRef.current); } else setPlaying(true);
    })
      .catch((e: ApiError) => setError(e.status === 404 ? 'This clip does not exist.' : e.message));
  }, [id]);

  const total = clip ? clipDuration(clip) : 0;
  const startClock = clip?.meta.start_clock ? clockSeconds(clip.meta.start_clock) : null;
  const focus: Side = clip?.meta.focus_team ?? 'home';
  const other: Side = focus === 'home' ? 'away' : 'home';
  const names = clip ? { home: clip.meta.teams.home.name, away: clip.meta.teams.away.name } : { home: '', away: '' };
  const series = useMemo(() => (clip ? metricSeries(clip) : null), [clip]);
  const evts = useMemo(() => (clip ? clipEvents(clip) : []), [clip]);

  // the clock: advance while playing; the UI re-renders ~15 times a second, the pitch every frame
  useEffect(() => {
    if (!clip) return;
    let raf = 0, last = performance.now(), lastUi = 0;
    const loop = (ts: number) => {
      raf = requestAnimationFrame(loop);
      const dt = (ts - last) / 1000; last = ts;
      if (playing) {
        tRef.current += dt * speed;
        if (tRef.current >= total) { tRef.current = total; setPlaying(false); }
      }
      if (ts - lastUi > 66) { lastUi = ts; setNow(tRef.current); }
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [clip, playing, speed, total]);

  const seek = useCallback((t: number) => { tRef.current = Math.max(0, Math.min(total, t)); setNow(tRef.current); }, [total]);
  const seekClock = useCallback((clock: string) => { if (startClock != null) seek(clockSeconds(clock) - startClock); }, [seek, startClock]);
  const toggle = useCallback(() => {
    if (tRef.current >= total) seek(0);
    setPlaying((p) => !p);
  }, [seek, total]);

  // keyboard: space plays/pauses, arrows step 2 s
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'BUTTON') return;
      if (e.code === 'Space') { e.preventDefault(); toggle(); }
      if (e.code === 'ArrowRight') seek(tRef.current + 2);
      if (e.code === 'ArrowLeft') seek(tRef.current - 2);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [toggle, seek]);

  const share = async () => {
    const url = `${window.location.origin}/app/clip/${id}?t=${now.toFixed(1)}&tab=${tab}`;
    try { await navigator.clipboard.writeText(url); setCopied(true); window.setTimeout(() => setCopied(false), 1800); } catch { window.prompt('Copy this link', url); }
  };

  const ask = async () => {
    setAsking('busy');
    try {
      const r = await api.explain(id);
      setExplanation(r); setGrounding(r.grounding); setAsking('idle');
    } catch (e) {
      setAsking(e instanceof ApiError && e.status === 503 ? 'No free AI model is available right now. Try again in a minute.' : (e as Error).message);
    }
  };

  if (error) return <AppLayout><div className="container replay-error"><p className="eyebrow">Replay</p><h1 className="headline">{error}</h1><Link to="/app" className="btn btn-ghost">Back to the library</Link></div></AppLayout>;
  if (!clip || !series) return <AppLayout><div className="container replay-loading"><div className="spinner" /><p>Loading the clip…</p></div></AppLayout>;

  const goal = evts.find((e) => e.kind === 'goal' && now >= e.t && now < e.t + 3);
  const current = [...evts].reverse().find((e) => e.t <= now + 0.05);
  const factsTeams = clip.facts?.teams ?? [];
  const shapeOf = (name: string) => factsTeams.find((t) => t.name === name)?.shape_in_clip;
  // up to four changes of the focus team and two of the opponent
  const allChanges = clip.facts?.notable_changes ?? [];
  const changes = [...allChanges.filter((c) => c.team === names[focus]).slice(0, 4), ...allChanges.filter((c) => c.team !== names[focus]).slice(0, 2)];

  return (
    <AppLayout>
      <div className="container replay">
        <header className="match-head">
          <div>
            <nav className="crumbs" aria-label="Breadcrumb">
              <Link to="/app">Library</Link><span>/</span>
              <span className="kind-tag">{clip.meta.data_kind === 'video' ? 'Drone video · SoccerTrack' : clip.meta.data_kind === 'uploaded' ? 'Your upload' : 'Tracking data · DFL'}</span>
            </nav>
            <h1 className="headline match-title">{clip.meta.title}</h1>
            <div className="match-teams">
              <span><i style={{ background: PITCH.focus }} />{names[focus]}{shapeOf(names[focus]) && !shapeOf(names[focus])!.startsWith('n/a') && <em> · {shapeOf(names[focus])} in this clip</em>}</span>
              <span><i style={{ background: PITCH.other }} />{names[other]}{shapeOf(names[other]) && !shapeOf(names[other])!.startsWith('n/a') && <em> · {shapeOf(names[other])} in this clip</em>}</span>
            </div>
          </div>
          <div className="match-clock">
            <span className="mono">{startClock != null ? formatClock(startClock + now) : formatClock(now)}</span>
            <small>match clock</small>
          </div>
        </header>

        <div className="replay-grid">
          <section className="stage" aria-label="Replay">
            <div className="pitch-wrap">
              <MiniReplay clip={clip} theme="grass" layers={layers} timeSource={() => tRef.current} className="pitch-canvas" label={`Replay of ${clip.meta.title}`} />
              <div className="layer-pills" role="group" aria-label="Overlays">
                {LAYER_BUTTONS.map(([k, label]) => (
                  <button key={k} type="button" aria-pressed={!!layers[k]} className={`pill ${layers[k] ? 'is-on' : ''}`} onClick={() => setLayers({ ...layers, [k]: !layers[k] })}>{label}</button>
                ))}
              </div>
              {goal && <div className="goal-flash" role="status"><span>GOAL</span>{goal.player} · {goal.clock}</div>}
            </div>
            <div className="transport glass">
              <button type="button" className="play" onClick={toggle} aria-label={playing ? 'Pause' : 'Play'}>
                {playing ? <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><rect x="4" y="3" width="3.5" height="12" rx="1" fill="currentColor" /><rect x="10.5" y="3" width="3.5" height="12" rx="1" fill="currentColor" /></svg>
                  : <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path d="M5 3l10 6-10 6z" fill="currentColor" /></svg>}
              </button>
              <div className="scrub">
                <input type="range" min={0} max={total} step={0.01} value={now} aria-label="Position in the clip"
                  onChange={(e) => seek(parseFloat(e.target.value))} style={{ ['--p' as string]: `${(now / total) * 100}%` }} />
                <div className="marks" aria-hidden="true">
                  {evts.map((e, i) => (
                    <span key={i} className={`mark mark-${e.kind}`} style={{ left: `${(e.t / total) * 100}%`, background: e.kind === 'goal' ? undefined : (e.team === names[focus] ? PITCH.focus : PITCH.other) }} title={`${e.clock} ${e.player}`} />
                  ))}
                </div>
              </div>
              <span className="time mono">{formatClock(now)} / {formatClock(total)}</span>
              <div className="speeds" role="group" aria-label="Playback speed">
                {SPEEDS.map((s) => <button key={s} type="button" aria-pressed={speed === s} className={speed === s ? 'is-on' : ''} onClick={() => setSpeed(s)}>{s}×</button>)}
              </div>
            </div>
            <div className="below-stage">
              <p className="hint">Space to play or pause · ← → to step 2 s · click any time in the coach's text to jump there</p>
              <button type="button" className="link-btn" onClick={share}>{copied ? 'Link copied ✓' : 'Share this moment'}</button>
            </div>
          </section>

          <aside className="panel glass" aria-label="Analysis">
            <h2 className="sr-only">Analysis</h2>
            <div className="tabs" role="tablist">
              {([['coach', 'AI coach'], ['numbers', 'Numbers'], ['events', 'Events']] as [Tab, string][]).map(([k, label]) => (
                <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? 'is-on' : ''} onClick={() => setTab(k)}>{label}</button>
              ))}
            </div>
            <div className="panel-body">
              {tab === 'coach' && (explanation ? (
                <>
                  {grounding && (
                    <div className={`grounded ${grounding.passed ? 'ok' : 'warn'}`}>
                      <span className="grounded-icon" aria-hidden="true">{grounding.passed ? '✓' : '!'}</span>
                      <div>
                        <strong>{grounding.passed ? 'Grounded in the data' : 'Some statements need checking'}</strong>
                        <p>{grounding.passed ? `All ${grounding.numbers_checked} numbers, clocks and shapes in this text were found in the computed facts.` : grounding.problems.join('; ')}</p>
                      </div>
                    </div>
                  )}
                  <CoachText text={explanation.text} onClock={seekClock} />
                  <p className="model mono">{explanation.model ?? 'LLM'}{explanation.prompt_version ? ` · prompt ${explanation.prompt_version}` : ''} · written from the facts, never from the video</p>
                </>
              ) : (
                <div className="ask">
                  <p>The coach hasn't written about this clip yet. It reads only the computed facts, and every number it writes is checked.</p>
                  <button type="button" className="btn btn-primary" disabled={asking === 'busy'} onClick={ask}>{asking === 'busy' ? 'Writing…' : 'Ask the coach'}</button>
                  {asking !== 'idle' && asking !== 'busy' && <p className="ask-error" role="alert">{asking}</p>}
                </div>
              ))}
              {tab === 'numbers' && (
                <MetricCharts series={series} now={now} duration={total} startClock={startClock} focus={focus} names={names} onSeek={seek} />
              )}
              {tab === 'events' && (
                evts.length ? (
                  <ol className="events">
                    {evts.map((e, i) => (
                      <li key={i} className={`${e === current ? 'is-now' : ''} ${e.kind === 'goal' ? 'is-goal' : ''}`}>
                        <button type="button" onClick={() => seek(e.t)}>
                          <span className="mono">{e.clock}</span>
                          <i style={{ background: e.kind === 'goal' ? 'var(--ball)' : e.team === names[focus] ? PITCH.focus : PITCH.other }} />
                          <span className="ev-text">{e.kind === 'goal' ? <><strong>Goal</strong> · {e.player}</> : <>{e.player} <span className="dim">has the ball</span></>}</span>
                        </button>
                      </li>
                    ))}
                  </ol>
                ) : <p className="dim">No ball events in this clip.</p>
              )}
            </div>
          </aside>
        </div>

        {changes.length > 0 && (
          <section className="changes" aria-label="Key changes">
            <h2 className="changes-title">Key changes in this clip</h2>
            <div className="change-grid">
              {changes.map((c, i) => {
                const m = metricLabel(c.metric);
                const up = c.to > c.from;
                return (
                  <button key={i} type="button" className="change glass" onClick={() => seekClock(c.from_clock)}>
                    <span className="change-team"><i style={{ background: c.team === names[focus] ? PITCH.focus : PITCH.other }} />{c.team}</span>
                    <span className="change-metric">{m.label}</span>
                    <span className="change-value"><span className="mono">{c.from.toLocaleString('en')}</span><span className={`arrow ${up ? 'up' : 'down'}`}>{up ? '↑' : '↓'}</span><span className="mono">{c.to.toLocaleString('en')}</span> <small>{m.unit}</small></span>
                    <span className="change-clock mono">{c.from_clock} → {c.to_clock}</span>
                  </button>
                );
              })}
            </div>
          </section>
        )}
        {clip.meta.source && <p className="source">Source: {clip.meta.source}</p>}
      </div>
    </AppLayout>
  );
}
