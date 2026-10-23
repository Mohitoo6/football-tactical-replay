// New analysis: pick a source, give the file(s), see a preview and the quality report, open the replay.
// Coordinate data is the main way in; a top-down drone video is processed as a background job.
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import AppLayout, { PageHeader } from './AppLayout';
import MiniReplay from '../components/MiniReplay';
import { ArrowUpRight } from '../components/Nav';
import { api, ApiError, STATIC, STATIC_NOTE, urls, type Job, type Report, type UploadResult } from '../lib/api';
import { previewCsv, type CsvPreview, type Units } from '../lib/csvPreview';
import type { ClipPayload } from '../lib/clip';
import './upload.css';

type Provider = 'metrica' | 'skillcorner' | 'sportec' | 'tracab' | 'secondspectrum' | 'hawkeye';
type Source = 'template' | Provider | 'drone';

const SOURCES: { key: Source; title: string; text: string; tag: string; icon: string }[] = [
  { key: 'template', title: 'Tracking file', text: 'CSV or Excel in our template: time, team, player, x, y.', tag: 'Recommended', icon: '▦' },
  { key: 'metrica', title: 'Metrica Sports', text: 'Two CSV files: the home team and the away team.', tag: 'Provider', icon: 'M' },
  { key: 'skillcorner', title: 'SkillCorner', text: 'Match JSON with the tracking JSONL.', tag: 'Provider', icon: 'S' },
  { key: 'sportec', title: 'Sportec / DFL', text: 'Match information XML with the positions XML.', tag: 'Provider', icon: 'D' },
  { key: 'tracab', title: 'TRACAB', text: 'Metadata XML or JSON with the tracking .dat or JSON.', tag: 'Provider', icon: 'T' },
  { key: 'secondspectrum', title: 'Second Spectrum', text: 'Metadata XML or JSON with the tracking JSONL.', tag: 'Provider', icon: '2' },
  { key: 'hawkeye', title: 'Hawk-Eye', text: 'The ball and player files of the minutes you want.', tag: 'Provider', icon: 'H' },
  { key: 'drone', title: 'Drone video', text: 'A still, top-down video of the whole pitch, up to 2 minutes.', tag: 'Experimental', icon: '◉' },
];

const PROVIDER_FILES: Record<Provider, [string, string]> = {
  metrica: ['Home team CSV', 'Away team CSV'],
  skillcorner: ['Match JSON (metadata)', 'Tracking JSONL'],
  sportec: ['Match information XML', 'Positions XML'],
  tracab: ['Metadata (XML or JSON)', 'Tracking data (.dat or JSON)'],
  secondspectrum: ['Metadata (XML or JSON)', 'Tracking JSONL'],
  hawkeye: ['Ball files (…samples.ball)', 'Player files (…samples.centroids)'],
};
// Hawk-Eye writes one file per minute: a window can need two or three of each.
const MULTI_FILE: Source[] = ['hawkeye'];

const CHECKS_AHEAD = [
  ['Frame rate', '5–60 moments per second'],
  ['Clip length', '3–120 seconds'],
  ['Players per team', 'at least 7'],
  ['Positions on the pitch', 'at most 2% more than 5 m outside'],
  ['Ball present', 'in at least half of the moments (warning only)'],
  ['Goalkeepers', 'given for both teams (warning only)'],
];

function StaticNote({ drone = false }: { drone?: boolean }) {
  return (
    <p className="static-note">{STATIC_NOTE}{' '}
      <a href="https://github.com/Mohitoo6/football-tactical-replay#run-it" target="_blank" rel="noreferrer">Three commands, in the README</a>.
      {drone && <> Two drone clips are already processed: <Link to="/app/clip/drone-0600-0630">open one</Link> to see the result beside the original video.</>}
    </p>
  );
}

function FileDrop({ label, accept, files, onFiles, multiple = false }:
  { label: string; accept: string; files: File[]; onFiles: (f: File[]) => void; multiple?: boolean }) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const take = (list: FileList | null | undefined) => {
    const picked = Array.from(list ?? []);
    if (picked.length) onFiles(multiple ? picked : picked.slice(0, 1));
  };
  const file = files[0];
  const bytes = files.reduce((sum, f) => sum + f.size, 0);
  return (
    <div className={`drop ${over ? 'is-over' : ''} ${file ? 'has-file' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files); }}>
      <input ref={input} type="file" accept={accept} multiple={multiple} className="sr-only" aria-label={label} onChange={(e) => take(e.target.files)} />
      {file ? (
        <div className="drop-file">
          <span className="drop-icon">✓</span>
          <span><strong>{files.length > 1 ? `${files.length} files` : file.name}</strong><small>{(bytes / 1024 / 1024).toFixed(bytes > 1e6 ? 1 : 2)} MB</small></span>
          <button type="button" className="link-btn" onClick={() => input.current?.click()}>Change</button>
        </div>
      ) : (
        <button type="button" className="drop-empty" onClick={() => input.current?.click()}>
          <span className="drop-icon">↑</span>
          <span><strong>{label}</strong><small>{multiple ? 'Drop them here, or click to choose (several allowed)' : 'Drop it here, or click to choose'}</small></span>
        </button>
      )}
    </div>
  );
}

function ReportView({ report }: { report: Report }) {
  const title = { ok: 'All checks passed', warning: 'Accepted, with warnings', rejected: 'Not accepted' }[report.status] ?? report.status;
  return (
    <div className={`report report-${report.status}`}>
      <p className="report-title">{title}</p>
      <ul>
        {report.checks.map((c, i) => (
          <li key={c.name} style={{ animationDelay: `${i * 0.08}s` }} className={c.passed ? 'pass' : c.blocking ? 'fail' : 'warn'}>
            <span className="report-mark" aria-hidden="true">{c.passed ? '✓' : c.blocking ? '✕' : '!'}</span>
            <span className="report-name">{c.name}</span>
            <span className="report-value mono">{c.value}</span>
            <span className="report-need">needs {c.requirement}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Result({ result }: { result: UploadResult }) {
  const [clip, setClip] = useState<ClipPayload | null>(null);
  useEffect(() => { if (result.clip_id) api.clip(result.clip_id, 5).then(setClip).catch(() => {}); }, [result.clip_id]);
  return (
    <div className="result">
      <ReportView report={result.report} />
      {result.clip_id && (
        <div className="result-clip glass">
          {clip ? <MiniReplay clip={clip} theme="grass" className="result-canvas" label="Preview of the new clip" /> : <div className="result-canvas clip-skeleton" />}
          <div className="result-actions">
            <p>Your clip is ready. On the replay you can ask the AI coach to explain it.</p>
            <Link to={`/app/clip/${result.clip_id}`} className="btn btn-primary">Open the replay<span className="btn-arrow"><ArrowUpRight /></span></Link>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Upload() {
  const [source, setSource] = useState<Source | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [filesB, setFilesB] = useState<File[]>([]);
  const file = files[0] ?? null;
  const [units, setUnits] = useState<Units>('metres');
  const [title, setTitle] = useState('');
  const [home, setHome] = useState('Home');
  const [away, setAway] = useState('Away');
  const [focus, setFocus] = useState<'home' | 'away'>('home');
  const [period, setPeriod] = useState(1);
  const [window_, setWindow] = useState<[string, string]>(['0', '30']);  // text, so a box can be emptied while typing
  const [preview, setPreview] = useState<CsvPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [droneOk, setDroneOk] = useState<boolean | null>(null);
  const jobId = useRef<string | null>(null);

  useEffect(() => { api.health().then((h) => setDroneOk(h.drone_video)).catch(() => setDroneOk(null)); }, []);

  // read a CSV in the browser for an instant preview (Excel files are read by the server)
  useEffect(() => {
    if (source !== 'template' || !file || !/\.csv$/i.test(file.name) || file.size > 40e6) { setPreview(null); return; }
    file.text().then((t) => setPreview(previewCsv(t, units)));
  }, [file, units, source]);

  // follow a drone job until it ends
  useEffect(() => {
    if (!job || job.state !== 'running' || !jobId.current) return;
    const id = window.setTimeout(() => api.job(jobId.current!).then(setJob).catch((e) => setError(e.message)), 1200);
    return () => window.clearTimeout(id);
  }, [job]);

  const reset = (s: Source | null) => { setSource(s); setFiles([]); setFilesB([]); setPreview(null); setResult(null); setJob(null); setError(null); };

  const tryExample = async () => {
    const res = await fetch(urls.example);
    if (!res.ok) { setError('The example file is served by the analysis server; is it running?'); return; }
    const blob = await res.blob();
    setFiles([new File([blob], 'example_musiala_winner.csv', { type: 'text/csv' })]);
    setTitle("Musiala's winner (example file)"); setHome('1. FC Köln'); setAway('FC Bayern München'); setFocus('away'); setUnits('metres');
  };

  const submit = async () => {
    if (!source || !file) return;
    setBusy(true); setError(null); setResult(null);
    const form = new FormData();
    try {
      if (source === 'template') {
        form.append('file', file); form.append('title', title || file.name); form.append('units', units);
        form.append('focus_team', focus); form.append('home_name', home); form.append('away_name', away);
        setResult(await api.uploadTracking(form));
      } else if (source === 'drone') {
        form.append('file', file); form.append('title', title || file.name);
        const { job_id } = await api.uploadDrone(form);
        jobId.current = job_id;
        setJob({ state: 'running', progress: 0, message: 'uploaded, starting', clip_id: null, report: null });
      } else {
        if (!filesB.length) return;
        form.append('provider', source);
        files.forEach((f) => form.append('file_a', f)); filesB.forEach((f) => form.append('file_b', f));
        form.append('period', String(period)); form.append('start_s', String(parseFloat(window_[0]) || 0)); form.append('end_s', String(parseFloat(window_[1]) || 0));
        form.append('title', title || `${SOURCES.find((s) => s.key === source)!.title} clip`); form.append('focus_team', focus);
        setResult(await api.uploadProvider(form));
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong while uploading.');
    } finally { setBusy(false); }
  };

  const ready = !!file && (source === 'template' || source === 'drone' || filesB.length > 0);
  const meta = SOURCES.find((s) => s.key === source);

  return (
    <AppLayout>
      <PageHeader eyebrow="New analysis" photo="/img/aerial-pitch.webp"
        title={<>Bring your own <em>moment.</em></>}
        text="Coordinate data from any provider, or a top-down drone video. We check it first, then build the same replay, numbers and coach for it." />
      <section className="container upload">
        {!source && (
          <div className="chooser glass">
            <h2 className="chooser-head">Where does your clip come from?</h2>
            {STATIC && <StaticNote />}
            {SOURCES.map((s, i) => (
              <button key={s.key} type="button" className="choice" style={{ animationDelay: `${i * 0.06}s` }} onClick={() => reset(s.key)}
                disabled={s.key === 'drone' && droneOk === false && !STATIC}>
                <span className="choice-icon">{s.icon}</span>
                <span className="choice-text"><strong>{s.title}</strong><small>{s.key === 'drone' && droneOk === false && !STATIC ? 'Needs the video tools on the server (uv sync --group video).' : s.text}</small></span>
                <span className={`choice-tag ${s.tag === 'Recommended' ? 'is-rec' : ''}`}>{s.tag}</span>
                <span className="choice-arrow" aria-hidden="true"><ArrowUpRight /></span>
              </button>
            ))}
            <p className="chooser-foot">No file yet? <a href={urls.template}>Download the template</a> or <a href={urls.example}>a full example</a>.</p>
          </div>
        )}

        {source && meta && (
          <div className="flow">
            <div className="flow-head">
              <button type="button" className="link-btn" onClick={() => reset(null)}>← All sources</button>
              <h2>{meta.title}</h2>
            </div>
            {!result && !job && (
              <div className="flow-grid">
                <div className="form glass">
                  <FileDrop label={source === 'drone' ? 'Your drone video (MP4/MOV)' : source === 'template' ? 'Your CSV or Excel file' : PROVIDER_FILES[source][0]}
                    accept={source === 'drone' ? 'video/*' : source === 'template' ? '.csv,.xlsx,.xls' : '*'} files={files} onFiles={setFiles}
                    multiple={MULTI_FILE.includes(source)} />
                  {source !== 'template' && source !== 'drone' &&
                    <FileDrop label={PROVIDER_FILES[source][1]} accept="*" files={filesB} onFiles={setFilesB} multiple={MULTI_FILE.includes(source)} />}
                  {source === 'template' && !file && <button type="button" className="link-btn" onClick={tryExample}>Try it with our example file (Musiala's winner)</button>}
                  <label className="field"><span>Title</span><input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Our second goal vs City" /></label>
                  {source !== 'drone' && (
                    <>
                      {source === 'template' && (
                        <div className="field-row">
                          <label className="field"><span>Home team</span><input value={home} onChange={(e) => setHome(e.target.value)} /></label>
                          <label className="field"><span>Away team</span><input value={away} onChange={(e) => setAway(e.target.value)} /></label>
                        </div>
                      )}
                      <div className="field"><span>Which team's move is this?</span>
                        <div className="segmented" role="group" aria-label="Focus team">
                          {(['home', 'away'] as const).map((s) => <button key={s} type="button" aria-pressed={focus === s} className={focus === s ? 'is-on' : ''} onClick={() => setFocus(s)}>{source === 'template' ? (s === 'home' ? home : away) : s === 'home' ? 'Home' : 'Away'}</button>)}
                        </div>
                      </div>
                      {source === 'template' && (
                        <div className="field"><span>Coordinates</span>
                          <div className="segmented" role="group" aria-label="Coordinate units">
                            {([['metres', 'Metres, centre = 0'], ['metres_corner', 'Metres from a corner'], ['normalised', '0 to 1']] as [Units, string][]).map(([u, l]) => (
                              <button key={u} type="button" aria-pressed={units === u} className={units === u ? 'is-on' : ''} onClick={() => setUnits(u)}>{l}</button>
                            ))}
                          </div>
                        </div>
                      )}
                      {source !== 'template' && (
                        <div className="field-row">
                          <label className="field"><span>Half</span><select value={period} onChange={(e) => setPeriod(parseInt(e.target.value, 10))}><option value={1}>First</option><option value={2}>Second</option></select></label>
                          <label className="field"><span>From (s into the half)</span><input type="number" min={0} value={window_[0]} onChange={(e) => setWindow([e.target.value, window_[1]])} /></label>
                          <label className="field"><span>To (max 120 s later)</span><input type="number" min={0} value={window_[1]} onChange={(e) => setWindow([window_[0], e.target.value])} /></label>
                        </div>
                      )}
                    </>
                  )}
                  {error && <p className="form-error" role="alert">{error}</p>}
                  {STATIC && <StaticNote drone={source === 'drone'} />}
                  <button type="button" className="btn btn-primary submit" disabled={!ready || busy || STATIC} onClick={submit}>
                    {busy ? 'Checking…' : source === 'drone' ? 'Upload and process' : 'Check and build the replay'}<span className="btn-arrow"><ArrowUpRight /></span>
                  </button>
                </div>

                <aside className="side glass">
                  {source === 'template' && preview && !preview.missing.length ? (
                    <>
                      <p className="side-title">Preview of your first moment</p>
                      <MiniReplay clip={preview.clip} theme="grass" time={0} className="side-canvas" label="Your first moment on the pitch" />
                      <div className="badges mono">
                        <span>{preview.frameRate ?? '–'} fps</span><span>{preview.seconds.toFixed(1)} s</span>
                        <span>{preview.players.home} v {preview.players.away}</span><span>ball in {Math.round(preview.ballShare * 100)}%</span>
                      </div>
                      <p className="side-note">Players in the wrong place? Change the coordinate units: the preview updates.</p>
                    </>
                  ) : source === 'template' && preview?.missing.length ? (
                    <div className="side-warn"><p className="side-title">These columns are missing</p><p className="mono">{preview.missing.join(', ')}</p><p>Our template starts with: time_s, team, player, jersey, position, x, y.</p></div>
                  ) : source === 'drone' ? (
                    <>
                      <p className="side-title">What the video needs</p>
                      <ul className="needs">
                        <li>A still camera, high above the pitch, looking down</li>
                        <li>The whole pitch and its painted lines in view</li>
                        <li>At least 10 pixels per metre (1080p or better for a full pitch)</li>
                        <li>3 seconds to 2 minutes long</li>
                      </ul>
                      <p className="side-note">Footage we can't read well is refused with the reason, rather than guessed.</p>
                    </>
                  ) : (
                    <>
                      <p className="side-title">What we check first</p>
                      <ul className="needs">{CHECKS_AHEAD.map(([n, r]) => <li key={n}><strong>{n}</strong> · {r}</li>)}</ul>
                      <p className="side-note">If a check fails we tell you exactly why, and nothing is guessed.</p>
                    </>
                  )}
                </aside>
              </div>
            )}

            {job && (
              job.state === 'running' ? (
                <div className="processing photo-band">
                  <img className="photo" src="/img/aerial-pitch.webp" alt="" />
                  <div className="scanline" aria-hidden="true" />
                  <div className="processing-card glass" role="status">
                    <p className="side-title">Reading your video</p>
                    <div className="bar"><span style={{ width: `${Math.round(job.progress * 100)}%` }} /></div>
                    <p className="mono processing-msg">{Math.round(job.progress * 100)}% · {job.message}</p>
                  </div>
                </div>
              ) : job.state === 'failed' ? (
                <p className="form-error" role="alert">The video could not be processed: {job.message}</p>
              ) : (
                job.report && <Result result={{ clip_id: job.clip_id, report: job.report }} />
              )
            )}
            {result && <Result result={result} />}
          </div>
        )}
      </section>
    </AppLayout>
  );
}
