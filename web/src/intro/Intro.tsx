// The intro screen: the 3D penalty, a black cover at the end, and a skip button.
// ?t=2.5 freezes the scene at that wall time (used to render and check single frames).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import IntroScene from './IntroScene';
import { WALL_END } from './timeline';

declare global {
  interface Window { __setTime?: (t: number) => void }
}

export default function Intro({ onDone }: { onDone: () => void }) {
  const frozen = useMemo(() => {
    const q = new URLSearchParams(window.location.search).get('t');
    return q === null ? null : parseFloat(q);
  }, []);
  const start = useRef(performance.now());
  const forced = useRef<number | null>(frozen);
  const [black, setBlack] = useState(0);

  useEffect(() => {
    window.__setTime = (t: number) => { forced.current = t; };
    return () => { delete window.__setTime; };
  }, []);

  const time = useCallback(() => forced.current ?? (performance.now() - start.current) / 1000, []);
  const onFrame = useCallback((b: number) => {
    setBlack((prev) => (Math.abs(prev - b) > 0.01 || (b === 1 && prev !== 1) ? b : prev));
    if (forced.current === null && time() > WALL_END) onDone();
  }, [onDone, time]);

  return (
    <div className="intro">
      <IntroScene time={time} onFrame={onFrame} />
      <div className="intro-black" style={{ opacity: black }} />
      {frozen === null && (
        <button type="button" className="intro-skip" onClick={onDone}>Skip intro</button>
      )}
    </div>
  );
}
