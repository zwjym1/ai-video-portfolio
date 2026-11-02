#!/usr/bin/env python3
"""从 BGM（最好是混音前的 BGM stem）实测拍点网格 → beat_grid.json（给 final_check.py / Remotion B(k) / mix 共用）。
  python3 tools/qc/beat_grid.py <bgm.wav> [--bpm 117] [--offset 0.29] [--dur 96.7] --out beat_grid.json
做法（首期 beat_table2.py 的通用版）：150Hz 低通起音 + 全频起音 → 与设计网格 ±50ms 匹配 → 线性拟合 offset+period。
不给 --bpm 时在 70–160 BPM 里找拍覆盖率最高的速度和首拍；匹配 <85% 拍会 WARN。网格到片尾漂移 >2 帧就说明 BPM 不对，必须用拟合值，不要用设计值。
"""
import argparse, json, numpy as np, librosa
from scipy.signal import butter, sosfilt
ap = argparse.ArgumentParser(); ap.add_argument('wav'); ap.add_argument('--bpm', type=float); ap.add_argument('--offset', type=float)
ap.add_argument('--dur', type=float); ap.add_argument('--out', required=True); ap.add_argument('--fps', type=float, default=30)
a = ap.parse_args()
y, sr = librosa.load(a.wav, sr=22050, mono=True)
dur = a.dur or len(y) / sr
hop = 64; lo = sosfilt(butter(2, 150, 'low', fs=sr, output='sos'), y)
pk = librosa.onset.onset_detect(onset_envelope=librosa.onset.onset_strength(y=lo, sr=sr, hop_length=hop), sr=sr, hop_length=hop, units='time', delta=0.05)
pk2 = librosa.onset.onset_detect(onset_envelope=librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop), sr=sr, hop_length=hop, units='time', delta=0.08)
def phase_of(on, p):
    ph = np.mod(on, p); bins = np.linspace(0, p, 101); h, _ = np.histogram(ph, bins); w = max(1, int(round(0.04 / p * 100)))
    hh = np.convolve(np.concatenate([h[-w:], h, h[:w]]), np.ones(2 * w + 1), 'valid'); j = int(np.argmax(hh)); c = bins[j] + p / 200
    m = np.abs((ph - c + p / 2) % p - p / 2) <= 0.04
    return float(np.angle(np.mean(np.exp(2j * np.pi * ph[m] / p))) % (2 * np.pi) / (2 * np.pi) * p) if m.any() else c
def coverage(on, b, dur):
    """网格上有多少拍在 ±40ms 内有鼓点起音（0–1）"""
    p = 60 / b; o = phase_of(on, p); g = o + p * np.arange(int((dur - o) / p) + 1); j = np.clip(np.searchsorted(on, g), 1, len(on) - 1)
    d = np.minimum(np.abs(on[j] - g), np.abs(on[j - 1] - g)); return float(np.mean(d <= 0.04)), o
if not a.bpm:
    # 不给 --bpm：70–160 BPM（0.05 步）里找「拍拍有鼓点」覆盖率最高的速度；覆盖率差 <2% 时取更快的（避免选到半速/⅔速），再 ±0.3 BPM 细搜。
    # （旧版用 librosa.beat.beat_track：EP01 BGM 上给出 117.44 BPM、相位落在反拍，只匹配 152/189 → 已弃用）
    on = np.sort(pk); res = [(coverage(on, b, dur), b) for b in np.arange(70, 160, 0.05)]
    top = max(r[0][0] for r in res); b0 = max(b for (c, _), b in res if c >= top - 0.02)
    fine = [(coverage(on, b, dur), b) for b in np.arange(b0 - 0.3, b0 + 0.3, 0.005)]; (cv, o1), b1 = max(fine, key=lambda r: r[0][0])
    a.bpm = b1; a.offset = a.offset if a.offset is not None else o1
    print(f'自动估速：{b1:.3f} BPM，首拍 {o1:.4f}s（低通起音 {len(pk)} 个，拍覆盖率 {cv:.0%}）')
per0 = 60 / a.bpm; off0 = a.offset or 0.0
allp = np.sort(np.concatenate([pk, pk2])); K = int((dur - off0) / per0) + 1; meas = {}
for k in range(K):
    d = allp - (off0 + k * per0); j = np.argmin(np.abs(d))
    if abs(d[j]) <= 0.05: meas[k] = float(allp[j])
ks = np.array(sorted(meas)); ts = np.array([meas[k] for k in ks]); off, per = np.polyfit(ks, ts, 1)[::-1]
for _ in range(2):  # 用拟合网格再匹配一遍、再拟合（消除设计值误差）
    m2 = {}
    for k in range(K):
        d = allp - (off + k * per); j = np.argmin(np.abs(d))
        if abs(d[j]) <= 0.05: m2[k] = float(allp[j])
    if len(m2) >= len(meas): meas = m2
    ks = np.array(sorted(meas)); ts = np.array([meas[k] for k in ks]); off, per = np.polyfit(ks, ts, 1)[::-1]
drift = abs((off0 + K * per0) - (off + K * per)) * a.fps
g = dict(offset=round(float(off), 4), period=round(float(per), 5), bpm=round(60 / per, 2), n=K, matched=f'{len(meas)}/{K}', source=a.wav,
         design=dict(offset=off0, period=round(per0, 5)), design_drift_frames_at_end=round(float(drift), 1),
         note='B(k)=offset+k*period；k%4==downbeat_mod 为小节第一拍（按曲子自查）')
g['ok'] = len(meas) >= 0.85 * K
if not g['ok']: print(f'WARN：只匹配到 {len(meas)}/{K} 拍（<85%），网格不可信：请用 --bpm/--offset 给设计值重跑，或换无鼓段更少的 BGM 段')
json.dump(g, open(a.out, 'w'), ensure_ascii=False, indent=1); print(json.dumps(g, ensure_ascii=False))
