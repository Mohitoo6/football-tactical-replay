// The end of the intro: the ball becomes the mint centre spot, the pitch draws around it,
// then the name rises and the tagline fades in. Pure SVG + CSS, crisp at any size.
import './logo-reveal.css';

export default function LogoReveal() {
  return (
    <div className="logo-reveal" role="img" aria-label="Vyuh. Read any football moment like a coach.">
      <svg className="lr-mark" viewBox="0 0 160 104" aria-hidden="true">
        <g fill="none" stroke="var(--mint)" strokeWidth="2.4" strokeLinecap="round">
          <rect className="lr-outline" x="4" y="3" width="152" height="98" rx="3" pathLength="1" />
          <path className="lr-inner" d="M80 3 V101" pathLength="1" />
          <circle className="lr-inner" cx="80" cy="52" r="17" pathLength="1" />
          <path className="lr-inner" d="M4 32 H22 V72 H4 M156 32 H138 V72 H156" pathLength="1" />
        </g>
        <circle className="lr-spot" cx="80" cy="52" r="6" fill="var(--mint)" />
      </svg>
      <div className="lr-title-mask"><h1 className="lr-title">VYUH</h1></div>
      <p className="lr-native" lang="sa">व्यूह</p>
      <p className="lr-tagline">Read any football moment like a coach</p>
    </div>
  );
}
