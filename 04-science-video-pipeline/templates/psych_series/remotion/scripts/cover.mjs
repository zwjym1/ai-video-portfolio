import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';
import path from 'path';
const outDir = process.argv[2] || '../deliver';
const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts')});
const chromiumOptions = {gl: 'swangle'};
for (const [id, out] of [['Cover916', `${outDir}/cover_9x16.png`], ['Cover43', `${outDir}/cover_4x3.png`]]) {
  const comp = await selectComposition({serveUrl, id, chromiumOptions});
  await renderStill({composition: comp, serveUrl, output: out, imageFormat: 'png', frame: 0, chromiumOptions}); console.log('ok', out);
}
