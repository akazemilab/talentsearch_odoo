// Minimal WOFF2 encoder: null transforms for every table, one brotli stream. Enough for a browser to load the font.
const fs = require('fs'), zlib = require('zlib');
const [,, src, dst] = process.argv;
const ttf = fs.readFileSync(src);
const numTables = ttf.readUInt16BE(4);
const flavor = ttf.readUInt32BE(0);
const tables = [];
for (let i = 0; i < numTables; i++) {
  const o = 12 + 16 * i;
  tables.push({ tag: ttf.toString('latin1', o, o + 4), off: ttf.readUInt32BE(o + 8), len: ttf.readUInt32BE(o + 12) });
}
// keep sfnt order but WOFF2 wants glyf before loca and loca right after glyf when both present (decoder expectation)
const b128 = n => { const out = []; do { out.unshift(n & 0x7f); n = Math.floor(n / 128); } while (n > 0); for (let i = 0; i < out.length - 1; i++) out[i] |= 0x80; return Buffer.from(out); };
const dir = [], chunks = [];
let totalSfnt = 12 + 16 * numTables;
for (const t of tables) {
  const data = ttf.subarray(t.off, t.off + t.len);
  const transformVersion = (t.tag === 'glyf' || t.tag === 'loca') ? 3 : 0;   // 3 = null transform for glyf/loca, 0 = none for others
  const flags = 63 | (transformVersion << 6);                                  // 63 = arbitrary tag follows
  dir.push(Buffer.from([flags]), Buffer.from(t.tag, 'latin1'), b128(t.len));
  chunks.push(data);
  totalSfnt += (t.len + 3) & ~3;
}
const raw = Buffer.concat(chunks);
const comp = zlib.brotliCompressSync(raw, { params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 11, [zlib.constants.BROTLI_PARAM_SIZE_HINT]: raw.length, [zlib.constants.BROTLI_PARAM_LGWIN]: 24 } });
const dirBuf = Buffer.concat(dir);
let len = 48 + dirBuf.length + comp.length;
const pad = (4 - (len % 4)) % 4; len += pad;
const h = Buffer.alloc(48);
h.write('wOF2', 0, 'latin1'); h.writeUInt32BE(flavor, 4); h.writeUInt32BE(len, 8); h.writeUInt16BE(numTables, 12); h.writeUInt16BE(0, 14);
h.writeUInt32BE(totalSfnt, 16); h.writeUInt32BE(comp.length, 20); h.writeUInt16BE(1, 24); h.writeUInt16BE(0, 26);
h.writeUInt32BE(0, 28); h.writeUInt32BE(0, 32); h.writeUInt32BE(0, 36); h.writeUInt32BE(0, 40); h.writeUInt32BE(0, 44);
fs.writeFileSync(dst, Buffer.concat([h, dirBuf, comp, Buffer.alloc(pad)]));
console.log(dst, ttf.length, '->', len);
