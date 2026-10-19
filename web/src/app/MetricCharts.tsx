// Small multiples: one line chart per shape metric, both teams, a playhead synced to the replay.
// Hover shows a crosshair with both values; click seeks the replay. A table view lists the same numbers.
import { memo, useMemo, useState } from 'react';
import { METRICS, valueAt, type Metric, type Series } from '../lib/replay';
import type { Side } from '../lib/clip';
import { formatClock } from '../lib/api';

export const CHART_COLOURS: Record<'focus' | 'other', string> = { focus: '#1f93d8', other: '#e8681e' };  // validated on the dark green surface

interface Props {
  series: Series;
  now: number;
  duration: number;
  startClock: number | null;
  focus: Side;
  names: Record<Side, string>;
  onSeek: (t: number) => void;
}

const W = 300, H = 92, PAD = { l: 36, r: 10, t: 8, b: 18 };

function fmt(v: number | null, unit: string) {
  if (v == null) return '–';
  return `${unit === 'm²' ? Math.round(v).toLocaleString('en') : v.toFixed(0)} ${unit}`;
}

const Chart = memo(function Chart({ metric, series, now, duration, startClock, focus, names, onSeek }: Props & { metric: (typeof METRICS)[number] }) {
  const [hover, setHover] = useState<number | null>(null);
  const sides: Side[] = [focus, focus === 'home' ? 'away' : 'home'];
  const all = sides.flatMap((s) => series.values[s][metric.key]).filter((v): v is number => v != null);
  const lo = Math.min(...all), hi = Math.max(...all);
  const pad = (hi - lo) * 0.12 || 1;
  const y0 = lo - pad, y1 = hi + pad;
  const X = (t: number) => PAD.l + (t / duration) * (W - PAD.l - PAD.r);
  const Y = (v: number) => PAD.t + (1 - (v - y0) / (y1 - y0)) * (H - PAD.t - PAD.b);
  const path = (side: Side) => {
    let d = '', pen = false;
    series.t.forEach((t, i) => {
      const v = series.values[side][metric.key][i];
      if (v == null) { pen = false; return; }
      d += `${pen ? 'L' : 'M'}${X(t).toFixed(1)} ${Y(v).toFixed(1)}`;
      pen = true;
    });
    return d;
  };
  const at = hover ?? now;
  const colour = (s: Side) => (s === focus ? CHART_COLOURS.focus : CHART_COLOURS.other);
  const clock = (t: number) => (startClock == null ? formatClock(t) : formatClock(startClock + t));
  const fromEvent = (e: React.MouseEvent<SVGRectElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const t = ((e.clientX - box.left) / box.width) * duration;
    return Math.max(0, Math.min(duration, t));
  };
  return (
    <figure className="mchart">
      <figcaption className="mchart-head">
        <span className="mchart-title" title={metric.help}>{metric.label}</span>
        <span className="mchart-values">
          {sides.map((s) => <span key={s}><i style={{ background: colour(s) }} />{fmt(valueAt(series.t, series.values[s][metric.key], at), metric.unit)}</span>)}
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="mchart-svg" role="img"
        aria-label={`${metric.label} of ${names[sides[0]]} and ${names[sides[1]]} over the clip`}>
        {[y0 + pad, y1 - pad].map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={Y(v)} y2={Y(v)} className="mchart-grid" />
            <text x={PAD.l - 6} y={Y(v) + 3} className="mchart-axis" textAnchor="end">{Math.round(v).toLocaleString('en')}</text>
          </g>
        ))}
        <text x={PAD.l} y={H - 4} className="mchart-axis">{clock(0)}</text>
        <text x={W - PAD.r} y={H - 4} className="mchart-axis" textAnchor="end">{clock(duration)}</text>
        {sides.map((s) => <path key={s} d={path(s)} fill="none" stroke={colour(s)} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />)}
        <line x1={X(now)} x2={X(now)} y1={PAD.t} y2={H - PAD.b} className="mchart-playhead" />
        {hover != null && <line x1={X(hover)} x2={X(hover)} y1={PAD.t} y2={H - PAD.b} className="mchart-cross" />}
        {sides.map((s) => {
          const v = valueAt(series.t, series.values[s][metric.key], at);
          return v == null ? null : <circle key={s} cx={X(at)} cy={Y(v)} r={4} fill={colour(s)} stroke="#10281b" strokeWidth={2} />;
        })}
        <rect x={PAD.l} y={0} width={W - PAD.l - PAD.r} height={H} fill="transparent" style={{ cursor: 'pointer' }}
          onMouseMove={(e) => setHover(fromEvent(e))} onMouseLeave={() => setHover(null)} onClick={(e) => onSeek(fromEvent(e))} />
      </svg>
      {hover != null && <p className="mchart-tip mono">{clock(hover)}</p>}
    </figure>
  );
});

export default function MetricCharts(props: Props) {
  const [table, setTable] = useState(false);
  const { series, focus, names, startClock } = props;
  const sides: Side[] = [focus, focus === 'home' ? 'away' : 'home'];
  const rows = useMemo(() => {
    const out: { t: number; v: Record<Side, Record<Metric, number | null>> }[] = [];
    for (let t = 0; t <= props.duration + 0.01; t += 2) {
      const v = {} as Record<Side, Record<Metric, number | null>>;
      for (const s of sides) { v[s] = {} as Record<Metric, number | null>; for (const m of METRICS) v[s][m.key] = valueAt(series.t, series.values[s][m.key], t); }
      out.push({ t, v });
    }
    return out;
  }, [series, props.duration, focus]);
  return (
    <div className="mcharts">
      <div className="mcharts-top">
        <ul className="legend">
          {sides.map((s) => <li key={s}><i style={{ background: s === focus ? CHART_COLOURS.focus : CHART_COLOURS.other }} />{names[s]}</li>)}
        </ul>
        <button type="button" className="link-btn" onClick={() => setTable(!table)}>{table ? 'Show charts' : 'Show as table'}</button>
      </div>
      {table ? (
        <div className="mtable-wrap">
          <table className="mtable">
            <thead><tr><th>Time</th>{METRICS.map((m) => <th key={m.key} colSpan={2}>{m.label} ({m.unit})</th>)}</tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.t}>
                  <td className="mono">{startClock == null ? formatClock(r.t) : formatClock(startClock + r.t)}</td>
                  {METRICS.map((m) => sides.map((s) => <td key={m.key + s} className="mono">{r.v[s][m.key] == null ? '–' : Math.round(r.v[s][m.key]!)}</td>))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mtable-note">Each metric has two columns: {names[sides[0]]} first, then {names[sides[1]]}.</p>
        </div>
      ) : (
        <div className="mcharts-grid">{METRICS.map((m) => <Chart key={m.key} metric={m} {...props} />)}</div>
      )}
    </div>
  );
}
