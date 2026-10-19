// Textures made in code: the match ball (our own panel design) and the mown grass.
import * as THREE from 'three';

const PHI = (1 + Math.sqrt(5)) / 2;
type V = [number, number, number];
const norm = (v: V): V => { const l = Math.hypot(v[0], v[1], v[2]); return [v[0] / l, v[1] / l, v[2] / l]; };
const dot = (a: V, b: V) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const smoothstep = (a: number, b: number, x: number) => { const t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const mixRGB = (a: number[], b: number[], w: number) => [a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w, a[2] + (b[2] - a[2]) * w];

/** Panel centres of a classic 32-panel ball: 12 pentagons (icosahedron vertices) and 20 hexagons (its face centres). */
function panelCentres(): { pent: V[]; hex: V[] } {
  const raw: V[] = [];
  for (const a of [-1, 1]) for (const b of [-1, 1]) raw.push([0, a, b * PHI], [a, b * PHI, 0], [b * PHI, 0, a]);
  const hex: V[] = [];
  for (let i = 0; i < 12; i++) for (let j = i + 1; j < 12; j++) for (let k = j + 1; k < 12; k++) {
    const d = (p: V, q: V) => Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
    if ([d(raw[i], raw[j]), d(raw[j], raw[k]), d(raw[i], raw[k])].every((x) => Math.abs(x - 2) < 1e-6)) {
      hex.push(norm([raw[i][0] + raw[j][0] + raw[k][0], raw[i][1] + raw[j][1] + raw[k][1], raw[i][2] + raw[j][2] + raw[k][2]]));
    }
  }
  return { pent: raw.map(norm), hex };
}

/** Equirectangular colour and bump maps for the ball. */
export function ballTextures(width = 1024): { map: THREE.Texture; bump: THREE.Texture } {
  const h = width / 2;
  const { pent, hex } = panelCentres();
  const colour = document.createElement('canvas'); colour.width = width; colour.height = h;
  const bump = document.createElement('canvas'); bump.width = width; bump.height = h;
  const ci = colour.getContext('2d')!.createImageData(width, h);
  const bi = bump.getContext('2d')!.createImageData(width, h);
  for (let y = 0; y < h; y++) {
    const lat = Math.PI / 2 - (y + 0.5) / h * Math.PI;
    for (let x = 0; x < width; x++) {
      const lon = (x + 0.5) / width * 2 * Math.PI - Math.PI;
      // three.js SphereGeometry: u runs with -x/+z, v from +y down
      const n: V = [-Math.cos(lat) * Math.cos(lon), Math.sin(lat), Math.cos(lat) * Math.sin(lon)];
      // Nearest panel centre decides the panel; the gap to the second nearest is the distance to its edge.
      let best = -2, second = -2, isPent = false;
      for (const c of pent) { const d = dot(n, c); if (d > best) { second = best; best = d; isPent = true; } else if (d > second) second = d; }
      for (const c of hex) { const d = dot(n, c); if (d > best) { second = best; best = d; isPent = false; } else if (d > second) second = d; }
      const gap = best - second;
      const band = (lo: number, hi: number, soft: number) => Math.min(smoothstep(lo - soft, lo + soft, gap), 1 - smoothstep(hi - soft, hi + soft, gap));
      let col = isPent ? [14, 32, 52] : [242, 244, 246];                     // navy pentagons, white hexagons
      if (isPent) col = mixRGB(col, [127, 240, 198], band(0.03, 0.042, 0.002)); // mint ring that follows the pentagon
      const seam = 1 - smoothstep(0.004, 0.011, gap);                          // stitched seam, anti-aliased
      col = mixRGB(col, [col[0] * 0.45, col[1] * 0.45, col[2] * 0.45], seam);
      const i = (y * width + x) * 4;
      ci.data[i] = col[0]; ci.data[i + 1] = col[1]; ci.data[i + 2] = col[2]; ci.data[i + 3] = 255;
      bi.data[i] = bi.data[i + 1] = bi.data[i + 2] = 255 - 215 * seam; bi.data[i + 3] = 255;
    }
  }
  colour.getContext('2d')!.putImageData(ci, 0, 0);
  bump.getContext('2d')!.putImageData(bi, 0, 0);
  const map = new THREE.CanvasTexture(colour); map.colorSpace = THREE.SRGBColorSpace; map.anisotropy = 8;
  const bumpTex = new THREE.CanvasTexture(bump);
  return { map, bump: bumpTex };
}

/** Grass: alternating mown stripes (light/dark) with fine noise, tiled along the pitch length. */
export function grassTexture(): THREE.Texture {
  const w = 512, h = 1024;
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const ctx = c.getContext('2d')!;
  const img = ctx.createImageData(w, h);
  let seed = 7;
  const rand = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  for (let y = 0; y < h; y++) {
    const band = Math.floor(y / (h / 2)) % 2;      // two stripes per tile
    for (let x = 0; x < w; x++) {
      const n = rand() * 0.22 + 0.89;
      const base = band ? [34, 92, 44] : [44, 112, 54];
      const i = (y * w + x) * 4;
      img.data[i] = base[0] * n; img.data[i + 1] = base[1] * n; img.data[i + 2] = base[2] * n; img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = 16;
  return t;
}
