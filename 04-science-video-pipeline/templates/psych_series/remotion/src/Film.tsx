// 成片骨架：固定机位，一个舞台，场景之间用 xfade/共享元素形变；所有动作起点 = T.<事件id>（= BM(k)）。
// 字幕只用 OneLineSubtitles + subs_oneline.ts（scripts/subs/oneline.py --out-ts 生成），不要自写多行字幕。
import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import EVJ from './film_events.json';
import {OneLineSubtitles} from './common/OneLineSubtitles';
import {SUBS} from './subs_oneline';
import {FPS, makeEvents} from './common/beats';
import {C, SANS, SAFE, lerp, xfade} from './common/motion';  // 另有 fadeIn/fadeOut/win 可用
const T = makeEvents(EVJ as any[]);

export const Film: React.FC = () => {
  const t = useCurrentFrame() / FPS;
  const [a, b] = xfade(t, T.scene2);
  return <AbsoluteFill style={{background: `radial-gradient(ellipse 80% 60% at 50% 45%, ${C.bg1} 0%, ${C.bg0} 100%)`, overflow: 'hidden'}}>
    {/* 场景 1：0 秒钩子（真实产品图 + 大字），第 0 帧就有画面和第一句字幕 */}
    <div style={{position: 'absolute', inset: 0, opacity: a}}>
      <Img src={staticFile('real/placeholder.png')} style={{position: 'absolute', left: SAFE.x0, width: SAFE.x1 - SAFE.x0, top: 420}} />  {/* 第 0 帧必须已可见：不要给钩子做淡入 */}
      <div style={{position: 'absolute', left: 0, right: 0, top: SAFE.y0 + 40, textAlign: 'center', fontFamily: SANS, fontWeight: 900, fontSize: 120, color: C.gold,
        transform: `translateY(${lerp(t, T.title, T.title + 0.4, 24, 0)}px)`}}>钩子大字</div>
    </div>
    {/* 场景 2：机制演示 */}
    <div style={{position: 'absolute', inset: 0, opacity: b}} />
    <OneLineSubtitles t={t} subs={SUBS} fontFamily={SANS} top={SAFE.subTop} />
  </AbsoluteFill>;
};
