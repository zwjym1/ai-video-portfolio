// 拍点网格（全系列通用）。B(k)=offset+k·period 来自 tools/qc/beat_grid.py 实测（成片 BGM stem），不要手估。
// BM(k) = B(k) − lead_frames/fps：画面事件提前 1 帧，让「第一帧可见变化」落在拍上（EP01 返修 4 验证：落拍率 52.9% → 96.4%）。
import EP from '../episode.json';
export const FPS = 30;
export const DUR: number = (EP as any).dur;
export const FRAMES = Math.round(DUR * FPS);
const {offset, period, lead_frames} = (EP as any).beat;
export const BEAT: number = period;
export const B = (k: number) => offset + k * period;
export const BM = (k: number) => B(k) - lead_frames / FPS;
export const beatOf = (t: number) => Math.round((t - offset) / period);
// 事件表：events/film_events.json（id,k,desc,sfx,f,lvl），画面与混音共用同一份 → 音画同拍
export const makeEvents = (rows: {id: string; k: number}[]) => {
  const o: Record<string, number> = {}; rows.forEach(e => { o[e.id] = BM(e.k); });
  return new Proxy(o, {get: (x, p: string) => { if (!(p in x)) throw new Error('no event ' + p); return x[p]; }});
};
