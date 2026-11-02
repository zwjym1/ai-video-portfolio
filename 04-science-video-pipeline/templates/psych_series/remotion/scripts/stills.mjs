import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';
import path from 'path';
const outDir = process.argv[2]; const times = process.argv.slice(3).map(Number);
const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts')});
const chromiumOptions = {gl: 'swangle'};
const comp = await selectComposition({serveUrl, id: process.env.COMP || 'Film', chromiumOptions});
for (const s of times) { const frame = Math.min(comp.durationInFrames - 1, Math.round(s * 30));
  await renderStill({composition: comp, serveUrl, output: `${outDir}/s_${s.toFixed(2)}.jpg`, imageFormat: 'jpeg', frame, chromiumOptions}); console.log('ok', s); }
