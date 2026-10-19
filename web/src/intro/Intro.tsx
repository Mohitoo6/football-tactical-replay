// The intro: the penalty video (keeper's view) plays full screen; on black, the logo reveals;
// then the site fades in. Plays once per visit, can be skipped, and respects reduced motion.
import { useEffect, useRef, useState } from 'react';
import LogoReveal from './LogoReveal';
import './intro.css';

const VIDEO = '/intro/intro.mp4';   // rendered by the intro lab (Part A); until then only the logo plays
const LOGO_TIME = 2600;             // ms the logo stays before the site appears

export function shouldPlayIntro(): boolean {
  try {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
    return sessionStorage.getItem('intro-seen') !== '1';
  } catch { return true; }
}

export default function Intro({ onDone }: { onDone: () => void }) {
  const [stage, setStage] = useState<'video' | 'logo' | 'out'>('video');
  const videoRef = useRef<HTMLVideoElement>(null);

  const finish = () => {
    try { sessionStorage.setItem('intro-seen', '1'); } catch { /* private mode */ }
    setStage('out');
    window.setTimeout(onDone, 700);
  };

  useEffect(() => {
    if (stage !== 'logo') return;
    const id = window.setTimeout(finish, LOGO_TIME);
    return () => window.clearTimeout(id);
  }, [stage]);

  return (
    <div className={`intro intro-${stage}`}>
      {stage === 'video' && (
        <video ref={videoRef} className="intro-video" src={VIDEO} autoPlay muted playsInline
          onEnded={() => setStage('logo')} onError={() => setStage('logo')} />
      )}
      {stage !== 'video' && <LogoReveal />}
      <button type="button" className="intro-skip" onClick={finish}>Skip intro</button>
    </div>
  );
}
