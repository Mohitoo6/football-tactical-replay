import { lazy, Suspense, useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';
import { shouldPlayIntro } from './intro/shouldPlay';
import Landing from './landing/Landing';
// the intro and the app screens load only when needed, so the landing page starts faster
const Intro = lazy(() => import('./intro/Intro'));
const Library = lazy(() => import('./app/Library'));
const Replay = lazy(() => import('./app/Replay'));
const Upload = lazy(() => import('./app/Upload'));

export default function App() {
  // ?intro=1 forces the intro (for review), ?intro=0 skips it; otherwise it plays once per visit
  const param = new URLSearchParams(window.location.search).get('intro');
  const [intro, setIntro] = useState(() => window.location.pathname === '/' && param !== '0' && (param === '1' || param === 'photo' || shouldPlayIntro()));
  return (
    <BrowserRouter>
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
    </BrowserRouter>
  );
}
