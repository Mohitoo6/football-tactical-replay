// The intro film: a silhouette takes a penalty and the ball flies into the screen until it is black.
// Made with Google Gemini (Veo), cut at the black frame, sound and Gemini's end card removed (see public/intro/CREDITS.md).
import { useRef, useState } from 'react';

export default function VideoIntro({ onEnd }: { onEnd: () => void }) {
  const ref = useRef<HTMLVideoElement>(null);
  const [shown, setShown] = useState(false);
  return (
    <>
      <video ref={ref} className={`intro-film ${shown ? 'is-shown' : ''}`} src="/intro/penalty.mp4" autoPlay muted playsInline preload="auto"
        onPlaying={() => setShown(true)} onEnded={onEnd} onError={onEnd}
        aria-label="A silhouetted player takes a penalty; the ball flies at you until the screen goes black" />
      <p className="intro-label">AI-generated intro · Google Gemini</p>
    </>
  );
}
