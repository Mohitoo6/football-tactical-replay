// The frame around every app screen: the glass nav, the page, a slim footer.
import type { ReactNode } from 'react';
import Nav from '../components/Nav';
import './app.css';

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="app">
      <Nav variant="app" />
      <main className="app-main">{children}</main>
      <footer className="app-footer container">
        <span>Tracking data: DFL (CC BY 4.0), SoccerTrack. Every number shown is computed from positions; the AI only explains them.</span>
      </footer>
    </div>
  );
}

/** A page header on a photo band: eyebrow, title, a line of text and actions. */
export function PageHeader({ eyebrow, title, text, photo, children }: { eyebrow: string; title: ReactNode; text?: ReactNode; photo: string; children?: ReactNode }) {
  return (
    <header className="page-head photo-band">
      <img className="photo" src={photo} alt="" />
      <div className="container page-head-inner">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h1 className="headline page-title">{title}</h1>
          {text && <p className="lede page-text">{text}</p>}
        </div>
        {children && <div className="page-actions">{children}</div>}
      </div>
    </header>
  );
}
