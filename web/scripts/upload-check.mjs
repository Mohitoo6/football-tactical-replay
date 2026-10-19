// Walk through the upload flow with the example file and take screenshots (for design review).
// usage: node scripts/upload-check.mjs OUTDIR   (needs `npm run dev` and the API running)
import puppeteer from 'puppeteer-core';
import { mkdirSync } from 'node:fs';

const out = process.argv[2];
mkdirSync(out, { recursive: true });
const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true,
  args: ['--use-angle=metal', '--enable-gpu'], defaultViewport: { width: 1440, height: 900 } });
const page = await browser.newPage();
page.on('pageerror', (e) => console.log('[page error]', e.message));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const clickText = (text) => page.evaluate((t) => { const b = [...document.querySelectorAll('button')].find((x) => x.textContent.includes(t)); b?.click(); return !!b; }, text);
await page.goto('http://localhost:5173/app/upload', { waitUntil: 'networkidle0' });
await wait(1200); await page.screenshot({ path: `${out}/1-chooser.png` });
console.log('tracking file:', await clickText('Tracking file'));
await wait(600); console.log('example:', await clickText('Try it with our example file'));
await wait(2500); await page.evaluate(() => window.scrollTo(0, 260)); await wait(600);
await page.screenshot({ path: `${out}/2-preview.png` });
console.log('submit:', await clickText('Check and build the replay'));
await wait(9000); await page.evaluate(() => window.scrollTo(0, 260)); await wait(1200);
await page.screenshot({ path: `${out}/3-result.png` });
const link = await page.evaluate(() => document.querySelector('.result-actions a')?.getAttribute('href'));
console.log('result link:', link);
await browser.close();
