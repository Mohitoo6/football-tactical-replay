import { lazy, Suspense } from 'react';
import { BrowserRouter, HashRouter, Route, Routes } from 'react-router';
import { STATIC } from './lib/api';
import Landing from './landing/Landing';
// the app screens load only when needed, so the landing page starts faster
const Library = lazy(() => import('./app/Library'));
const Replay = lazy(() => import('./app/Replay'));
const Upload = lazy(() => import('./app/Upload'));

// The online demo is a static site whose host serves only real files, so its pages live after a # (/#/app/...).
const Router = STATIC ? HashRouter : BrowserRouter;

export default function App() {
  return (
    <Router>
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
