import { lazy, Suspense, useState } from 'react';
import { BrowserRouter, HashRouter, Route, Routes } from 'react-router';
import { STATIC } from './lib/api';
import { shouldPlayIntro } from './intro/shouldPlay';
import Landing from './landing/Landing';
// the intro and the app screens load only when needed, so the landing page starts faster
const Intro = lazy(() => import('./intro/Intro'));
const Library = lazy(() => import('./app/Library'));
const Replay = lazy(() => import('./app/Replay'));
const Upload = lazy(() => import('./app/Upload'));

// The online demo is a static site whose host serves only real files, so its pages live after a # (/#/app/...).
const Router = STATIC ? HashRouter : BrowserRouter;
const atHome = () => STATIC ? ['', '#', '#/'].includes(window.location.hash) : window.location.pathname === '/';

export default function App() {
  // ?intro=1 forces the intro (for review), ?intro=0 skips it; otherwise it plays once per visit
  const param = new URLSearchParams(window.location.search).get('intro');
  const [intro, setIntro] = useState(() => atHome() && param !== '0' && (param === '1' || shouldPlayIntro()));
  return (
    <Router>
      {intro && <Suspense fallback={<div style={{ position: "fixed", inset: 0, zIndex: 100, background: "#000" }} />}><Intro onDone={() => setIntro(false)} /></Suspense>}
      <Suspense fallback={null}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/app" element={<Library />} />
        <Route path="/app/clip/:id" element={<Replay />} />
        <Route path="/app/upload" element={<Upload />} />
        <Route path="*" element={<Library />} />
      </Routes>
      </Suspense>
    </Router>
  );
}
