// 丝滑运动工具（spec §10.4）：只给「先快后慢、无过冲」的缓动；禁止闪白、回弹、整屏推近、硬切。
// 场景切换只用 xfade（≥0.5s 交叉淡化）或共享元素形变；final_check.py 会量 2 帧亮度跳变（≤17）和硬切数（=0）。
import {interpolate, Easing} from 'remotion';
export const OUT = Easing.out(Easing.cubic);
export const SOFT = Easing.out(Easing.quad); // 第一帧即可见变化 → 起点落拍更准
export const lerp = (t: number, a: number, b: number, v0: number, v1: number, e = OUT) =>
  interpolate(t, [a, b], [v0, v1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: e});
export const fadeIn = (t: number, at: number, d = 0.3) => lerp(t, at, at + d, 0, 1, SOFT);
export const fadeOut = (t: number, at: number, d = 0.4) => lerp(t, at, at + d, 1, 0, SOFT);
export const win = (t: number, on: number, off = 1e9, din = 0.35, dout = 0.45) => Math.min(fadeIn(t, on, din), fadeOut(t, off, dout));
// 场景交叉淡化：返回 [a 的不透明度, b 的不透明度]，d 不得小于 0.5s
export const xfade = (t: number, at: number, d = 0.6) => { const m = lerp(t, at, at + Math.max(0.5, d), 0, 1, Easing.inOut(Easing.quad)); return [1 - m, m]; };
export const rgba = (hex: string, a: number) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };
export const SANS = '"Noto Sans CJK SC", "Noto Sans SC", sans-serif';
export const C = {bg0: '#06080C', bg1: '#182235', glass: '#8FB6EA', gold: '#F2B544', red: '#E5483B', white: '#F5F5F5', grey: '#8A93A3', dim: '#6F7A8C'};
// 9:16 安全区：主体 x150–855；正文/标注 y240–1480；字幕带 y1560–1700（OneLineSubtitles top=1560）
export const SAFE = {x0: 150, x1: 855, y0: 240, y1: 1480, subTop: 1560};
