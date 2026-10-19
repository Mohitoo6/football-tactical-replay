// Check that the original video and the replay clock stay together: play, read both, seek, read both.
// usage: node scripts/sync-check.mjs CLIP_ID OUTDIR   (needs `npm run dev` and the API running)
import puppeteer from 'puppeteer-core';
import { mkdirSync } from 'node:fs';

const [clipId, out] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true,
  args: ['--use-angle=metal', '--enable-gpu', '--autoplay-policy=no-user-gesture-required'], defaultViewport: { width: 1440, height: 1400 } });
const page = await browser.newPage();
page.on('pageerror', (e) => console.log('[page error]', e.message));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const read = () => page.evaluate(() => {
  const v = document.querySelector('.source-video');
  const [m, s] = document.querySelector('.time').textContent.split('/')[0].trim().split(':').map(Number);
  const exact = +(+document.querySelector('.scrub input').value).toFixed(2);
  return { video: v ? +v.currentTime.toFixed(2) : null, clock: m * 60 + s, exact, gap: v ? +(v.currentTime - exact).toFixed(3) : null, paused: v?.paused };
});
await page.goto(`http://localhost:5173/app/clip/${clipId}`, { waitUntil: 'networkidle0' });
await wait(6000);
console.log('after 6 s of play:', await read());
await page.screenshot({ path: `${out}/playing.png` });
await page.keyboard.press('Space');                       // pause
await page.evaluate(() => { const r = document.querySelector('.scrub input'); const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(r, '20'); r.dispatchEvent(new Event('input', { bubbles: true })); });
await wait(1500);
console.log('paused, seeked to 20 s:', await read());
await page.screenshot({ path: `${out}/seeked.png` });
await browser.close();
