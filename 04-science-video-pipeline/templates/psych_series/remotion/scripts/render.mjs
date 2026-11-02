import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';
import path from 'path';
const out = process.argv[2];
const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts')});
const chromiumOptions = {gl: 'swangle'};
const comp = await selectComposition({serveUrl, id: process.env.COMP || 'Film', chromiumOptions});
let last = -1; const t0 = Date.now();
await renderMedia({composition: comp, serveUrl, codec: 'h264', crf: 16, pixelFormat: 'yuv420p', imageFormat: 'jpeg', jpegQuality: 95, muted: true,
  outputLocation: out, chromiumOptions, concurrency: 6,
  onProgress: ({progress}) => { const p = Math.floor(progress * 100); if (p >= last + 10) { last = p; console.log(`progress ${p}% ${((Date.now() - t0) / 1000).toFixed(0)}s`); } }});
console.log('DONE', ((Date.now() - t0) / 1000).toFixed(0), 's');
