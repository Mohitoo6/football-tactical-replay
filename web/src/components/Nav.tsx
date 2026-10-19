import { Link, NavLink } from 'react-router';
import './nav.css';

export function Wordmark() {
  return (
    <span className="wordmark">
      <svg width="26" height="17" viewBox="0 0 30 20" aria-hidden="true"><rect x="1" y="1" width="28" height="18" rx="2" fill="none" stroke="currentColor" strokeWidth="1.6" /><line x1="15" y1="1" x2="15" y2="19" stroke="currentColor" strokeWidth="1.6" /><circle cx="15" cy="10" r="2.2" fill="var(--mint)" /></svg>
      TACTICAL REPLAY
    </span>
  );
}

export default function Nav({ variant = 'site' }: { variant?: 'site' | 'app' }) {
  return (
    <header className="nav">
      <div className="nav-inner container">
        <Link to="/" aria-label="Tactical Replay home"><Wordmark /></Link>
        {variant === 'site' ? (
          <nav className="nav-links" aria-label="Sections">
            <a href="#how">How it works</a>
            <a href="#inputs">Your data</a>
            <a href="#accuracy">Accuracy</a>
            <Link to="/app" className="nav-cta">Open app</Link>
          </nav>
        ) : (
          <nav className="nav-links" aria-label="App">
            <NavLink to="/app" end>Library</NavLink>
            <NavLink to="/app/upload">New analysis</NavLink>
          </nav>
        )}
      </div>
    </header>
  );
}
