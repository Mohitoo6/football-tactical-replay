// The intro: the penalty (keeper's view) plays full screen; on black, the logo reveals;
// then the site fades in. Plays once per visit, can be skipped, and respects reduced motion.
import { useEffect, useState } from 'react';
import LogoReveal from './LogoReveal';
import PhotoIntro from './PhotoIntro';
import VideoIntro from './VideoIntro';
import './intro.css';

const LOGO_TIME = 2600;             // ms the logo stays before the site appears


export default function Intro({ onDone }: { onDone: () => void }) {
  const [stage, setStage] = useState<'video' | 'logo' | 'out'>('video');
  // ?intro=photo shows the earlier two-photo intro, to compare the two
  const photo = new URLSearchParams(window.location.search).get('intro') === 'photo';

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
      {stage === 'video' && (photo ? <PhotoIntro onEnd={() => setStage('logo')} /> : <VideoIntro onEnd={() => setStage('logo')} />)}
      {stage !== 'video' && <LogoReveal />}
      <button type="button" className="intro-skip" onClick={finish}>Skip intro</button>
    </div>
  );
}
