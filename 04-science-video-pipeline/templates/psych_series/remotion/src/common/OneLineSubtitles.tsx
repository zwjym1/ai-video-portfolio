// 一句一字幕（全局通用 Remotion 组件）。数据由 science-studio/scripts/subs/oneline.py 生成（--out-ts）。
// 规则：一屏只显示一句、单行、不换行、不拼接；字号按句长自动缩放到安全宽度内。
import React from 'react';
export type Sub = {text: string; a: number; b: number; show_a: number; show_b: number};
const vlen = (x: string) => [...x].reduce((n, c) => n + (/[0-9.a-zA-Z%–-]/.test(c) ? 0.55 : 1), 0);
export const OneLineSubtitles: React.FC<{t: number; subs: Sub[]; fontFamily: string; top?: number; width?: number; maxFont?: number; zIndex?: number}> =
  ({t, subs, fontFamily, top = 1600, width = 1080, maxFont = 80, zIndex = 80}) => {
  const s = subs.find((x) => t >= x.show_a && t < x.show_b);
  if (!s) return null;
  const safe = width - 120;
  const fs = Math.min(maxFont, Math.floor(safe / Math.max(1, vlen(s.text))));
  const p = Math.min(1, Math.max(0, (t - s.show_a) / 0.1));
  const pop = s.show_a <= 0 ? 1 : 1 - Math.pow(1 - p, 3);
  return (
    <div data-zone="subtitle" style={{position: 'absolute', left: 0, width, top, height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex}}>
      <div style={{fontFamily, fontWeight: 700, fontSize: fs, lineHeight: 1.1, color: '#fff', WebkitTextStroke: `${Math.round(fs / 7)}px #000`, paintOrder: 'stroke fill',
        whiteSpace: 'nowrap', transform: `scale(${0.9 + 0.1 * pop})`, opacity: 0.35 + 0.65 * pop, textShadow: '0 4px 10px rgba(0,0,0,.6)'}}>{s.text}</div>
    </div>
  );
};
