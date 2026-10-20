// Generate the SPARK desktop icon (multi-resolution .ico) with no native deps.
// Single source of truth for the app mark used by the .lnk, the Electron window
// and packaging. Run: npm run icon
// Output: public/spark.ico (and public/spark.png).
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const PUBLIC = join(ROOT, 'public');

// SPARK cockpit palette (see src/index.css + tailwind.config.js).
const BG = [11, 18, 32];
const RING = [6, 182, 212];
const RING_DIM = [22, 78, 99];
const BOLT = [34, 211, 238];
const GOLD = [212, 175, 55];

const SIZE = 256;
const SCALE = 4; // supersample factor for smooth edges

function inPolygon(px, py, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    const intersect = (yi > py) !== (yj > py) &&
      px < ((xj - xi) * (py - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

const BOLT_POLY = [
  [146, 44], [96, 136], [128, 136], [108, 212],
  [168, 112], [134, 112], [156, 44],
];

function renderPixels(size) {
  const s = size;
  const scale = s / SIZE;
  const r = 48 * scale; // tile corner radius
  const ringPad = 22 * scale;
  const ringDimW = 10 * scale;
  const innerPad = 40 * scale;
  const ringW = 4 * scale;
  const cx = 128 * scale, cy = 150 * scale, coreR = 14 * scale;
  const bolt = BOLT_POLY.map(([x, y]) => [x * scale, y * scale]);

  const buf = Buffer.alloc(s * s * 4);
  for (let y = 0; y < s; y++) {
    for (let x = 0; x < s; x++) {
      // rounded-rect mask
      const dx = Math.max(r - Math.min(x + 0.5, s - x - 0.5), 0);
      const dy = Math.max(r - Math.min(y + 0.5, s - y - 0.5), 0);
      const outside = Math.hypot(dx, dy) > r;
      if (outside) continue; // transparent
      let color = BG;

      const dCenter = Math.hypot(x + 0.5 - s / 2, y + 0.5 - s / 2);
      const outer = s / 2 - ringPad;
      const inner = s / 2 - innerPad;
      if (Math.abs(dCenter - outer) <= ringDimW / 2) color = RING_DIM;
      else if (Math.abs(dCenter - inner) <= ringW / 2) color = RING;

      if (inPolygon(x + 0.5, y + 0.5, bolt)) color = BOLT;
      if (Math.hypot(x + 0.5 - cx, y + 0.5 - cy) <= coreR) color = GOLD;

      const o = (y * s + x) * 4;
      buf[o] = color[0]; buf[o + 1] = color[1]; buf[o + 2] = color[2]; buf[o + 3] = 255;
    }
  }
  return buf;
}

// --- Minimal PNG encoder (RGBA, no dependencies) ---
import { deflateSync } from 'node:zlib';

function crc32(buf) {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return (~c) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const t = Buffer.from(type, 'ascii');
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([t, data])), 0);
  return Buffer.concat([len, t, data, crc]);
}

function encodePng(size) {
  const pixels = renderPixels(size);
  const raw = Buffer.alloc(size * (size * 4 + 1));
  for (let y = 0; y < size; y++) {
    raw[y * (size * 4 + 1)] = 0; // filter: none
    pixels.copy(raw, y * (size * 4 + 1) + 1, y * size * 4, (y + 1) * size * 4);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8;   // bit depth
  ihdr[9] = 6;   // color type RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

// --- ICO container: embed PNG images (Vista+ format) ---
function encodeIco(sizes) {
  const images = sizes.map((s) => ({ size: s, data: encodePng(s) }));
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);            // type: icon
  header.writeUInt16LE(images.length, 4);
  const dir = Buffer.alloc(16 * images.length);
  let offset = 6 + 16 * images.length;
  images.forEach((img, i) => {
    const e = i * 16;
    dir[e] = img.size >= 256 ? 0 : img.size;
    dir[e + 1] = img.size >= 256 ? 0 : img.size;
    dir[e + 2] = 0; // palette
    dir[e + 3] = 0;
    dir.writeUInt16LE(1, e + 4);   // color planes
    dir.writeUInt16LE(32, e + 6);  // bits per pixel
    dir.writeUInt32LE(img.data.length, e + 8);
    dir.writeUInt32LE(offset, e + 12);
    offset += img.data.length;
  });
  return Buffer.concat([header, dir, ...images.map((i) => i.data)]);
}

mkdirSync(PUBLIC, { recursive: true });
const sizes = [16, 24, 32, 48, 64, 128, 256];
writeFileSync(join(PUBLIC, 'spark.png'), encodePng(256));
writeFileSync(join(PUBLIC, 'spark.ico'), encodeIco(sizes));
console.log(`Wrote public/spark.png and public/spark.ico (${sizes.join(', ')})`);
