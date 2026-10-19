import { describe, expect, it } from 'vitest';
import { coachBlocks, tokenize, valueAt } from './replay';

describe('replay helpers', () => {
  it('interpolates a metric between samples and keeps the ends', () => {
    const t = [0, 1, 2], v = [10, 20, null];
    expect(valueAt(t, v, 0.5)).toBe(15);
    expect(valueAt(t, v, -1)).toBe(10);
    expect(valueAt(t, v, 1.5)).toBe(20);   // a missing sample is not invented
  });

  it('finds clocks, numbers with units and formations in the coach text', () => {
    const tokens = tokenize("Bayern's back line pushed up from 42 metres at 87:57 to 72 metres, in a 4-1-4-1.");
    expect(tokens.filter((x) => x.kind === 'clock').map((x) => x.text)).toEqual(['87:57']);
    expect(tokens.filter((x) => x.kind === 'number').map((x) => x.text)).toEqual(['42 metres', '72 metres', '4-1-4-1']);
    expect(tokens.map((x) => x.text).join('')).toBe("Bayern's back line pushed up from 42 metres at 87:57 to 72 metres, in a 4-1-4-1.");
  });

  it('reads headings, bullets and paragraphs', () => {
    const blocks = coachBlocks('**What happened**  \nA line.\n* first\n* second');
    expect(blocks.map((b) => b.kind)).toEqual(['heading', 'paragraph', 'bullet', 'bullet']);
    expect(blocks[0].text).toBe('What happened');
  });
});
