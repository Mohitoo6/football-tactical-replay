import { useState } from 'react';
import Intro from './intro/Intro';

export default function App() {
  const [introDone, setIntroDone] = useState(false);
  if (!introDone) return <Intro onDone={() => setIntroDone(true)} />;
  return (
    <main className="placeholder">
      <h1>TACTICAL REPLAY</h1>
      <p>Read any football moment like a coach</p>
    </main>
  );
}
