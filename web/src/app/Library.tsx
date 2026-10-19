// The match library: every clip (bundled and uploaded) as a card with a live preview of its real data.
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import AppLayout, { PageHeader } from './AppLayout';
import MiniReplay from '../components/MiniReplay';
import { ArrowUpRight } from '../components/Nav';
import { api, clockSeconds, type ClipSummary } from '../lib/api';
import type { ClipPayload } from '../lib/clip';

type Filter = 'all' | 'tracking' | 'video' | 'user';
const FILTERS: [Filter, string][] = [['all', 'All clips'], ['tracking', 'Match tracking'], ['video', 'Drone video'], ['user', 'Your uploads']];

function kind(c: ClipSummary): Filter {
  if (c.origin === 'user') return 'user';
  return c.data_kind === 'video' ? 'video' : 'tracking';
}
const KIND_LABEL: Record<Filter, string> = { all: '', tracking: 'Tracking data · DFL', video: 'Drone video · SoccerTrack', user: 'Your upload' };

function duration(c: ClipSummary): string {
  if (!c.start_clock || !c.end_clock) return '';
  return `${clockSeconds(c.end_clock) - clockSeconds(c.start_clock) + 1} s`;
}

/** One clip: the preview loads when the card scrolls into view and plays while hovered. */
function ClipCard({ clip, index }: { clip: ClipSummary; index: number }) {
  const ref = useRef<HTMLAnchorElement>(null);
  const [data, setData] = useState<ClipPayload | null>(null);
  const [hover, setHover] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { api.clip(clip.clip_id, 5).then(setData).catch(() => {}); io.disconnect(); }
    }, { rootMargin: '200px' });
    io.observe(el);
    return () => io.disconnect();
  }, [clip.clip_id]);
  // a still at the clip's goal (or its middle) until hovered
  const still = useMemo(() => {
    if (!data) return 0;
    const t0 = data.frames[0].time_s;
    const goal = data.meta.goals?.[0];
    return goal ? Math.max(0, goal.time_s - t0 - 1) : (data.frames[data.frames.length - 1].time_s - t0) / 2;
  }, [data]);
  const k = kind(clip);
  return (
    <Link to={`/app/clip/${clip.clip_id}`} ref={ref} className="clip-card reveal-up" style={{ animationDelay: `${index * 0.06}s` }}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} onFocus={() => setHover(true)} onBlur={() => setHover(false)}>
      <div className="clip-thumb">
        {data ? <MiniReplay clip={data} theme="grass" time={hover ? undefined : still} speed={1.5} className="clip-canvas" label={`Preview of ${clip.title}`} />
          : <div className="clip-canvas clip-skeleton" />}
        <span className="clip-kind">{KIND_LABEL[k]}</span>
        <span className="clip-play" aria-hidden="true"><ArrowUpRight /></span>
      </div>
      <div className="clip-body">
        <h2 className="clip-title">{clip.title}</h2>
        <p className="clip-teams">{clip.teams.home}<span className="vs">v</span>{clip.teams.away}</p>
        <div className="clip-meta">
          {clip.start_clock && <span className="mono">{clip.start_clock}–{clip.end_clock}</span>}
          {duration(clip) && <span>{duration(clip)}</span>}
          {clip.has_explanation && <span className="chip-ok">AI coach ✓</span>}
        </div>
      </div>
    </Link>
  );
}

export default function Library() {
  const [clips, setClips] = useState<ClipSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
  const [query, setQuery] = useState('');
  const navigate = useNavigate();
  useEffect(() => { api.clips().then(setClips).catch((e) => setError(e.message)); }, []);

  const shown = (clips ?? []).filter((c) => (filter === 'all' || kind(c) === filter)
    && `${c.title} ${c.teams.home} ${c.teams.away}`.toLowerCase().includes(query.trim().toLowerCase()));
  const count = (f: Filter) => (clips ?? []).filter((c) => f === 'all' || kind(c) === f).length;

  return (
    <AppLayout>
      <PageHeader eyebrow="Match library" photo="/img/stadium-night.webp"
        title={<>Every clip, <em>ready to read.</em></>}
        text="Bundesliga goals from open DFL tracking data, drone footage from SoccerTrack, and anything you upload.">
        <button type="button" className="btn btn-primary" onClick={() => navigate('/app/upload')}>New analysis<span className="btn-arrow"><ArrowUpRight /></span></button>
      </PageHeader>
      <section className="container library">
        <div className="toolbar">
          <div className="chips" role="tablist" aria-label="Filter clips">
            {FILTERS.map(([f, label]) => (
              <button key={f} type="button" role="tab" aria-selected={filter === f} className={`chip ${filter === f ? 'is-on' : ''}`} onClick={() => setFilter(f)}>
                {label}<span className="chip-count">{count(f)}</span>
              </button>
            ))}
          </div>
          <label className="search glass">
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" strokeWidth="1.6" /><path d="M11 11l3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
            <input type="search" placeholder="Search a team or player" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search clips" />
          </label>
        </div>
        {error && <div className="notice notice-error" role="alert"><strong>Can't load the clips.</strong> {error}</div>}
        {!clips && !error && <div className="clip-grid">{Array.from({ length: 6 }, (_, i) => <div key={i} className="clip-card clip-skeleton-card" />)}</div>}
        {clips && (
          <div className="clip-grid">
            {shown.map((c, i) => <ClipCard key={c.clip_id} clip={c} index={i} />)}
            {filter === 'user' && shown.length === 0 && (
              <div className="empty glass">
                <p className="empty-title">No uploads yet.</p>
                <p>Bring a CSV or Excel file of positions, a Metrica / SkillCorner / Sportec match, or a top-down drone video.</p>
                <Link to="/app/upload" className="btn btn-primary">Start a new analysis<span className="btn-arrow"><ArrowUpRight /></span></Link>
              </div>
            )}
          </div>
        )}
      </section>
    </AppLayout>
  );
}
