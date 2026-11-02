// 封面（9:16 1080×1920 + 4:3 1440×1080），文字从 episode.json 读。
// 版式规矩（spec §7 / §10.5）：9:16 所有文字落在 y240–1680（避开抖音顶部状态栏和底部按钮区；EP01 封面文字顶 250）；
// 4:3 文字靠左 x70–750、视觉主体靠右；两版共用同一视觉组件 <Visual/>，每期只替换 Visual。
import React from 'react';
import {AbsoluteFill} from 'remotion';
import EP from './episode.json';
import {SANS, rgba} from './common/motion';
const CV = (EP as any).cover;
export const COVER_SAFE = {tall: {y0: 240, y1: 1680}, wide: {x0: 70, x1: 750}};
const Visual: React.FC<{tall: boolean}> = ({tall}) => // ← 每期替换：产品塔/券面/价格卡等主视觉
  <div style={{position: 'absolute', left: tall ? 190 : 820, top: tall ? 1000 : 300, width: tall ? 700 : 520, height: tall ? 520 : 560, borderRadius: 24,
    border: `4px dashed ${CV.accent}`, opacity: 0.6}} />;
export const Cover: React.FC<{w: number; h: number}> = ({w, h}) => {
  const tall = h > w; const acc = CV.accent;
  return <AbsoluteFill style={{background: 'radial-gradient(ellipse 80% 60% at 50% 55%, #1B2740 0%, #0E1420 50%, #06080C 100%)', overflow: 'hidden'}}>
    <Visual tall={tall} />
    <div style={{position: 'absolute', left: tall ? 0 : 70, right: tall ? 0 : undefined, top: tall ? 250 : 190, textAlign: tall ? 'center' : 'left', fontFamily: SANS, fontWeight: 800,
      fontSize: tall ? 40 : 34, color: 'rgba(255,255,255,0.85)', letterSpacing: 3}}>{CV.kicker}</div>
    <div style={{position: 'absolute', left: tall ? 0 : 70, width: tall ? w : 680, top: tall ? 300 : 260, textAlign: tall ? 'center' : 'left', fontFamily: SANS, fontWeight: 900, color: '#fff',
      lineHeight: 1.1, textShadow: '0 6px 0 rgba(0,0,0,0.6)'}}>
      <div style={{fontSize: tall ? 196 : 140, color: acc, letterSpacing: -4, textShadow: `0 0 40px ${rgba(acc, 0.45)}, 0 6px 0 rgba(0,0,0,0.6)`}}>{CV.big}</div>
      <div style={{fontSize: tall ? 128 : 96, marginTop: 10}}>{CV.line2}</div>
      <div style={{fontSize: tall ? 46 : 38, marginTop: 34, color: '#CFE0FA', fontWeight: 800}}>{CV.sub}</div>
    </div>
  </AbsoluteFill>;
};
