import { useState } from 'react';
import { Link, NavLink } from 'react-router';
import LogoMark from './LogoMark';
import './nav.css';

export function Wordmark() {
  return <span className="wordmark"><LogoMark size={30} />Vyuh</span>;
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
        <Link to="/" className="nav-home" aria-label="Vyuh home"><Wordmark /></Link>
        <nav className="nav-links" aria-label="Sections">
          {variant === 'site'
            ? links.map(([href, label]) => <a key={href} href={href} onClick={() => setOpen(false)}>{label}</a>)
            : <><Link to="/">Overview</Link><NavLink to="/app" end>Library</NavLink><NavLink to="/app/upload">New analysis</NavLink></>}
        </nav>
        <div className="nav-actions">
          {variant === 'site' && <Link to="/app" className="btn btn-primary nav-cta">Open app<span className="btn-arrow"><ArrowUpRight /></span></Link>}
          <button type="button" className="nav-menu" aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open} onClick={() => setOpen(!open)}>
            <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d={open ? 'M5 5l10 10M15 5L5 15' : 'M3 6h14M3 10h14M3 14h14'} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
          </button>
        </div>
      </div>
    </header>
  );
}
