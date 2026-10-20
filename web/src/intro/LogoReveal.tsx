// The end of the intro: the ball becomes the centre of the Vyuh mark, its three rings draw around it,
// then the name rises with व्यूह beneath it and the tagline. Pure SVG + CSS, crisp at any size.
import { RINGS } from '../components/LogoMark';
import './logo-reveal.css';

export default function LogoReveal() {
  return (
    <div className="logo-reveal" role="img" aria-label="Vyuh. Read any football moment like a coach.">
      <svg className="lr-mark" viewBox="0 0 64 64" aria-hidden="true">
        <g fill="none" stroke="var(--mint)" strokeLinecap="round">
          {RINGS.map((r, i) => <path key={r.d} className="lr-ring" d={r.d} strokeWidth={r.width} opacity={r.opacity} pathLength={1} style={{ animationDelay: `${0.15 + i * 0.18}s` }} />)}
        </g>
        <circle className="lr-spot" cx="32" cy="32" r="4.2" fill="#fff" />
      </svg>
      <div className="lr-title-mask"><h1 className="lr-title">VYUH</h1></div>
      <p className="lr-native" lang="sa">व्यूह</p>
      <p className="lr-tagline">Read any football moment like a coach</p>
    </div>
  );
}
