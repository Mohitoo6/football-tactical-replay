import { useState } from 'react';
import { Link, NavLink } from 'react-router';
import './nav.css';

export function BallIcon({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="14.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M16 9.5l5.6 4.1-2.1 6.6h-7l-2.1-6.6z" fill="currentColor" />
      <path d="M16 9.5V2M21.6 13.6l7-2.3M19.5 20.2l4.3 6M12.5 20.2l-4.3 6M10.4 13.6l-7-2.3" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export function Wordmark() {
  return <span className="wordmark"><BallIcon />Tactical Replay</span>;
}

export function ArrowUpRight() {
  return <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 11.5l7-7M5.5 4.5h6v6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

export default function Nav({ variant = 'site' }: { variant?: 'site' | 'app' }) {
  const [open, setOpen] = useState(false);
  const links = variant === 'site'
    ? [['#how', 'How it works'], ['#inputs', 'Your data'], ['#accuracy', 'Accuracy'], ['#coach', 'AI coach']]
    : [];
  return (
    <header className="nav">
      <div className={`nav-pill glass ${open ? 'is-open' : ''}`}>
        <Link to="/" className="nav-home" aria-label="Tactical Replay home"><Wordmark /></Link>
        <nav className="nav-links" aria-label="Sections">
          {variant === 'site'
            ? links.map(([href, label]) => <a key={href} href={href} onClick={() => setOpen(false)}>{label}</a>)
            : <><NavLink to="/app" end>Library</NavLink><NavLink to="/app/upload">New analysis</NavLink></>}
        </nav>
        <div className="nav-actions">
          <Link to="/app" className="btn btn-primary nav-cta">Open app<span className="btn-arrow"><ArrowUpRight /></span></Link>
          <button type="button" className="nav-menu" aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open} onClick={() => setOpen(!open)}>
            <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d={open ? 'M5 5l10 10M15 5L5 15' : 'M3 6h14M3 10h14M3 14h14'} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
          </button>
        </div>
      </div>
    </header>
  );
}
