#!/usr/bin/env python3
"""通用成片混音（自 EP-20261031-01 final/mix_film.py 抽出，参数全在 mix_config.json）。
人声 −16 / BGM −24 / 人声在时 BGM duck −5 dB / 总 −16 LUFS / alimiter 0.80（EP01 实测 TP −1.7 dBTP）。
音效（TICK/SUB/POP/LOWHIT）全部放在事件表 k 拍的 B(k)=offset+k·period 上，与画面同一份 film_events.json。
BGM 可在小节线拼接跳过无鼓段（splices：在成片第 at_k 拍处跳过原曲 skip_beats 拍，30ms 等功率交叉）。
输出：final/film_mix.wav（24bit）+ stem_vo/bgm/fx.wav；之后跑 tools/qc/beat_grid.py final/stem_bgm.wav 复核网格。"""
import sys, json, subprocess, numpy as np
from scipy.signal import butter, sosfilt
from scipy.io import wavfile
import pyloudnorm as pyln
CFG = json.load(open(sys.argv[1] if len(sys.argv) > 1 else 'audio/mix_config.json'))
R = 48000; DUR = CFG['dur']; OFF = CFG['bgm_in']; G = CFG['beat']; TG = CFG['targets']; OUT = CFG.get('out_dir', 'final')
def B(k): return G['offset'] + k * G['period']
rng = np.random.default_rng(1031)
def dec(f, ss=0, d=None):
    a = ['ffmpeg', '-v', 'error', '-ss', str(ss), '-i', f] + (['-t', str(d)] if d else []) + ['-ac', '2', '-ar', str(R), '-f', 'f32le', '-']
    return np.frombuffer(subprocess.run(a, capture_output=True, check=True).stdout, dtype=np.float32).reshape(-1, 2).astype(np.float64)
def tt(d): return np.arange(int(d * R)) / R
def env(d, a, tau): t = tt(d); return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / tau)
def lp(x, f, o=2): return sosfilt(butter(o, f, 'low', fs=R, output='sos'), x)
def hp(x, f, o=2): return sosfilt(butter(o, f, 'high', fs=R, output='sos'), x)
def glide(f0, f1, d, k=40): t = tt(d); f = f1 + (f0 - f1) * np.exp(-t * k); return np.sin(2 * np.pi * np.cumsum(f) / R)
def TICK(f=1760, d=0.08): t = tt(d); return np.sin(2 * np.pi * f * t) * env(d, 0.0005, 0.012) + 0.5 * hp(rng.standard_normal(len(t)), 3000) * env(d, 0.0003, 0.003)
def LOWHIT(f0=49, d=1.4):
    x = glide(f0 * 2.4, f0, d, 22) * env(d, 0.004, 0.45) + 0.2 * glide(f0 * 4.8, f0 * 2, d, 22) * env(d, 0.002, 0.2)
    n = lp(rng.standard_normal(int(d * R)), 700) * env(d, 0.001, 0.02) * 0.5
    return np.tanh(1.5 * (x + n))
def SUB(f=55, d=0.5): return np.tanh(2 * glide(f * 2, f, d, 30) * env(d, 0.003, 0.12))
def POP(d=0.12): return glide(600, 1400, d, -8) * env(d, 0.001, 0.03) * 0.8 + TICK(2200, d)
SFX = {'TICK': lambda e: TICK(e.get('f', 1760)), 'SUB': lambda e: SUB(e.get('f', 55)), 'POP': lambda e: POP(), 'LOWHIT': lambda e: LOWHIT(e.get('f', 49))}

N = int(DUR * R); meter = pyln.Meter(R)
vo = dec(CFG['vo']); vo = np.pad(vo[:N], ((0, max(0, N - len(vo[:N]))), (0, 0)))
# ---- BGM：按 splices 分段取原曲，段间 30ms 等功率交叉 ----
bg = np.zeros((N, 2)); xf = int(0.03 * R); song_t = OFF; film_t = 0.0; cuts = sorted(CFG.get('splices', []), key=lambda s: s['at_k'])
segs = []
for s in cuts:
    at = B(s['at_k']); segs.append((film_t, at, song_t)); song_t += (at - film_t) + s['skip_beats'] * G['period']; film_t = at
segs.append((film_t, DUR, song_t))
for i, (f0, f1, s0) in enumerate(segs):
    pre = xf / R if i > 0 else 0
    x = dec(CFG['bgm'], max(0, s0 - pre), f1 - f0 + pre + 0.05)
    a = int(f0 * R) - (xf if i > 0 else 0); n = min(len(x), N - a)
    if i > 0:
        r = np.linspace(0, 1, xf)[:, None]; bg[a:a + xf] = bg[a:a + xf] * np.sqrt(1 - r) + x[:xf] * np.sqrt(r); bg[a + xf:a + n] = x[xf:n]
    else:
        bg[a:a + n] = x[:n]
vo *= 10 ** ((TG['vo'] - meter.integrated_loudness(vo)) / 20)
bg *= 10 ** ((TG['bgm'] - meter.integrated_loudness(bg)) / 20)
def lpzone(bg, k0, k1, fc, amt, xs):
    a0, a1 = int(B(k0) * R), int(B(k1) * R); x2 = max(1, int(xs * R))
    mf = np.stack([lp(bg[:, c], fc, 4) for c in range(2)], 1) * 10 ** (-2 / 20)
    w = np.zeros(N); w[a0:a1] = amt; w[a0:a0 + x2] = np.linspace(0, amt, x2); w[a1 - x2:a1] = np.linspace(amt, 0, x2)
    return bg * (1 - w)[:, None] + mf * w[:, None]
for z in CFG.get('lp_zones', []): bg = lpzone(bg, z['k0'], z['k1'], z['fc'], z['amt'], z['xs'])
# ---- duck：人声能量 > −42 dB 视为在说话，attack 60ms / release 300ms ----
m = vo.mean(1); ww = int(0.02 * R); rms = np.sqrt(np.convolve(m ** 2, np.ones(ww) / ww, 'same')); act = (20 * np.log10(rms + 1e-9) > -42).astype(float)
g = np.zeros(N); a_at = 1 - np.exp(-1 / (0.06 * R)); a_rel = 1 - np.exp(-1 / (0.30 * R)); y = 0.0
for i in range(N): y += (act[i] - y) * (a_at if act[i] > y else a_rel); g[i] = y
fade = np.ones(N)
if CFG.get('fade_k') is not None: fs = int(B(CFG['fade_k']) * R); fade[fs:] = np.linspace(1, 0, N - fs) ** 1.6
bg *= (10 ** (TG['duck_db'] * g / 20) * fade)[:, None]
# ---- 音效：同一份事件表，放在 B(k) ----
def kw(x): w = int(0.15 * R); c = np.convolve(x ** 2, np.ones(w) / w, 'valid') if len(x) > w else np.array([np.mean(x ** 2)]); return 10 * np.log10(c.max() + 1e-12)
ref = kw(vo.mean(1)); fx = np.zeros(N); used = 0
for e in json.load(open(CFG['events'])):
    if not e.get('sfx'): continue
    x = hp(SFX[e['sfx']](e), 40); x = x * 10 ** ((ref + e.get('lvl', -17) - kw(x)) / 20)
    i = int(round(B(e['k']) * R)); n = min(len(x), N - i); fx[i:i + n] += x[:n]; used += 1
mix = vo + bg + fx[:, None]; mix *= 10 ** ((TG['mix'] - meter.integrated_loudness(mix)) / 20)
wavfile.write(f'{OUT}/film_mix_pre.wav', R, mix.astype(np.float32))
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f'{OUT}/film_mix_pre.wav', '-af', f"alimiter=limit={TG['limit']}:attack=2:release=80:level=disabled",
                '-ar', '48000', '-c:a', 'pcm_s24le', f'{OUT}/film_mix.wav'], check=True)
for nm, arr in [('vo', vo), ('bgm', bg), ('fx', np.stack([fx, fx], 1))]: wavfile.write(f'{OUT}/stem_{nm}.wav', R, arr.astype(np.float32))
print('混音前自测（不是最终实测，最终以 final_check.py 量成片为准）：vo', round(meter.integrated_loudness(vo), 2), 'bgm(duck后)', round(meter.integrated_loudness(bg), 2), '音效', used, '个', 'BGM 段', len(segs))
