import { useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';
import Intro, { shouldPlayIntro } from './intro/Intro';
import Landing from './landing/Landing';
import AppPlaceholder from './app/AppPlaceholder';

export default function App() {
  // ?intro=1 forces the intro (for review); otherwise it plays once per visit
  const force = new URLSearchParams(window.location.search).has('intro');
  const [intro, setIntro] = useState(() => window.location.pathname === '/' && (force || shouldPlayIntro()));
  return (
    <BrowserRouter>
      {intro && <Intro onDone={() => setIntro(false)} />}
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/app/*" element={<AppPlaceholder />} />
      </Routes>
    </BrowserRouter>
  );
}
