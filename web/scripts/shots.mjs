// Screenshots of a page at several scroll positions (for design review).
// usage: node scripts/shots.mjs URL OUTDIR WIDTHxHEIGHT y1 y2 ...   (y in viewport heights, e.g. 0 1 2.5)
import puppeteer from 'puppeteer-core';
import { mkdirSync } from 'node:fs';

const [url, out, size, ...ys] = process.argv.slice(2);
const [width, height] = size.split('x').map(Number);
mkdirSync(out, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
  args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'],
  defaultViewport: { width, height, deviceScaleFactor: 1 },
});
const page = await browser.newPage();
page.on('pageerror', (e) => console.log('[page error]', e.message));
page.on('console', (m) => { if (m.type() === 'error') console.log('[console]', m.text()); });
await page.evaluateOnNewDocument(() => { try { sessionStorage.setItem('intro-seen', '1'); } catch {} });
await page.goto(url, { waitUntil: 'networkidle0' });
await new Promise((r) => setTimeout(r, 1800));
for (const y of ys) {
  await page.evaluate((v) => window.scrollTo(0, v * window.innerHeight), parseFloat(y));
  await new Promise((r) => setTimeout(r, 1600));
  await page.screenshot({ path: `${out}/${width}-y${y}.png` });
}
await browser.close();
