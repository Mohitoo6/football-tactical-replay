// The AI coach's explanation: headings, bullets, highlighted numbers and clickable match clocks.
import { memo } from 'react';
import { coachBlocks, tokenize } from '../lib/replay';

function Line({ text, onClock }: { text: string; onClock: (clock: string) => void }) {
  return (
    <>
      {tokenize(text).map((tok, i) => {
        if (tok.kind === 'clock') return <button key={i} type="button" className="clock-chip mono" onClick={() => onClock(tok.text)} title={`Jump to ${tok.text}`}>{tok.text}</button>;
        if (tok.kind === 'number') return <mark key={i} className="num">{tok.text}</mark>;
        return <span key={i}>{tok.text}</span>;
      })}
    </>
  );
}

export default memo(function CoachText({ text, onClock }: { text: string; onClock: (clock: string) => void }) {
  const blocks = coachBlocks(text);
  const out: React.ReactNode[] = [];
  let bullets: string[] = [];
  const flush = () => {
    if (bullets.length) out.push(<ul key={`u${out.length}`}>{bullets.map((b, i) => <li key={i}><Line text={b} onClock={onClock} /></li>)}</ul>);
    bullets = [];
  };
  blocks.forEach((b, i) => {
    if (b.kind === 'bullet') { bullets.push(b.text); return; }
    flush();
    out.push(b.kind === 'heading' ? <h3 key={i}>{b.text}</h3> : <p key={i}><Line text={b.text} onClock={onClock} /></p>);
  });
  flush();
  return <div className="coach-text-body">{out}</div>;
});
