// Play the intro in real time: report the frame rate and take screenshots at given seconds.
// usage: node scripts/play.mjs OUTDIR   (needs `npm run dev` running)
import puppeteer from 'puppeteer-core';
const out = process.argv[2];
const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true,
  args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'], defaultViewport: { width: 1600, height: 900 } });
const page = await browser.newPage();
page.on('pageerror', (e) => console.log('[page error]', e.message));
await page.goto('http://localhost:5173/?intro=1', { waitUntil: 'networkidle0' });
const t0 = Date.now();
// frames per second while the intro plays (counted with requestAnimationFrame over 1.5 s)
const fps = await page.evaluate(() => new Promise((r) => { let n = 0; const s = performance.now(); const f = () => { n++; if (performance.now() - s < 1500) requestAnimationFrame(f); else r(n / 1.5); }; requestAnimationFrame(f); }));
console.log('fps during shot 1:', fps.toFixed(1));
for (const at of [4.45, 4.6, 5.2, 6.0, 7.2]) {
  const wait = at * 1000 - (Date.now() - t0); if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  await page.screenshot({ path: `${out}/rt${at}.png` });
}
await browser.close();
