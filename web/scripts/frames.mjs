// Render intro frames at fixed times with the installed Chrome (GPU on).
// usage: node scripts/frames.mjs OUTDIR t1 t2 ...   (needs `npm run dev` running)
import puppeteer from 'puppeteer-core';
import { mkdirSync } from 'node:fs';

const [out, ...times] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
  args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--window-size=1600,900'],
  defaultViewport: { width: 1600, height: 900, deviceScaleFactor: 1 },
});
const page = await browser.newPage();
page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') console.log('[page]', m.type(), m.text()); });
page.on('pageerror', (e) => console.log('[page error]', e.message));
await page.goto(`http://localhost:5173/?t=${times[0]}`, { waitUntil: 'networkidle0' });
await page.waitForFunction(() => typeof window.__setTime === 'function', { timeout: 20000 });
const frames = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
for (const t of times) {
  await page.evaluate((x) => window.__setTime(x), parseFloat(t));
  await frames(); await frames();
  await page.screenshot({ path: `${out}/t${t}.png` });
}
console.log('renderer:', await page.evaluate(() => {
  const gl = document.createElement('canvas').getContext('webgl2');
  const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
  return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : String(!!gl);
}));
await browser.close();
