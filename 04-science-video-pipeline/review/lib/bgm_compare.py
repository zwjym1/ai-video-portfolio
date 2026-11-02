#!/workspace/.venv-dy/bin/python
"""BGM 候选对比 + 粗混试听（盒上跑）。
用法: bgm_compare.py --vo vo.wav --sfx sfx.wav --video 成片.mp4 --cuts 0,2.9,... --out DIR --cur 现版.mp3:入点 --cand a.mp3 --cand b.mp3 ... [--meta chart_dir]
对每首：鼓点（打击声部 onset）、入点搜索（让设计切点 ±40ms 内对上鼓点最多）、开头 3s 能量、人声频段（1–4kHz）被压程度、歌词人声检测（whisper small）、调式/亮度；
按现版同一套混音参数（BGM 源统一 −12 LUFS → −13.9 dB，人声处 −8 dB，前 3s 不压，尾 1.5s 淡出，总 −16 LUFS / −1.5 dBTP）出试听 wav + 配画面 mp4。"""
import argparse, json, os, re, subprocess, numpy as np, soundfile as sf, librosa
ap = argparse.ArgumentParser()
for k in ('vo', 'sfx', 'video', 'cuts', 'out', 'cur', 'meta'): ap.add_argument('--' + k)
ap.add_argument('--cand', action='append', default=[]); ap.add_argument('--no-asr', action='store_true')
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True); SR = 48000
CUTS = [float(x) for x in a.cuts.split(',') if float(x) > 0]
def load(f, ss=0, dur=None, sr=SR):
    cmd = ['ffmpeg', '-v', 'error', '-ss', str(ss), '-i', f] + (['-t', str(dur)] if dur else []) + ['-ac', '1', '-ar', str(sr), '-f', 'f32le', '-']
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32).copy()
def _lj(e): return json.loads(re.findall(r'\{[^{}]*\}', e, re.S)[-1])
def lufs_of(x, sr=SR):
    sf.write('/tmp/_l.wav', x, sr, subtype='FLOAT')
    e = subprocess.run(['ffmpeg', '-hide_banner', '-i', '/tmp/_l.wav', '-af', 'loudnorm=print_format=json', '-f', 'null', '-'], capture_output=True, text=True).stderr
    return float(_lj(e)['input_i'])
vo = load(a.vo); sfx = load(a.sfx); N = len(vo); TOTAL = N / SR; sfx = np.pad(sfx, (0, max(0, N - len(sfx))))[:N]
# 人声活动（10ms 帧）
hop = 480; fr = N // hop; env = np.sqrt(np.convolve(vo[:fr * hop].reshape(fr, hop).__pow__(2).mean(1), np.ones(15) / 15, 'same'))
vact = env > 10 ** (-40 / 20)
def band(x, lo=1000, hi=4000, n=2048):
    S = np.abs(librosa.stft(x, n_fft=n, hop_length=hop)) ** 2; f = librosa.fft_frequencies(sr=SR, n_fft=n)
    return S[(f >= lo) & (f < hi)].sum(0)
VB = band(vo)
asr = None
def lyrics(f, ss):
    global asr
    if a.no_asr: return None
    from faster_whisper import WhisperModel
    if asr is None: os.environ.setdefault('HF_HUB_OFFLINE', '1'); asr = WhisperModel('small', device='cpu', compute_type='int8', cpu_threads=8)
    x = load(f, ss, TOTAL, 16000); segs, info = asr.transcribe(x, vad_filter=True, beam_size=1)
    segs = [s for s in segs if s.no_speech_prob < 0.5 and s.avg_logprob > -1.0]
    txt = ''.join(s.text for s in segs); return dict(lang=info.language, sec=round(sum(s.end - s.start for s in segs), 1), sample=txt[:60])
KEYS = 'C C# D D# E F F# G G# A A# B'.split()
MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]); MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
def analyze(f, fixed_in=None):
    y = load(f, sr=22050); dur = len(y) / 22050
    yh, yp = librosa.effects.hpss(y)
    on = librosa.onset.onset_detect(y=yp, sr=22050, units='time', backtrack=False)
    st = librosa.onset.onset_strength(y=yp, sr=22050); ot = librosa.times_like(st, sr=22050)
    thr = np.percentile(st, 80); strong = np.array([t for t in on if st[min(len(st) - 1, np.searchsorted(ot, t))] >= thr])
    tempo, bt = librosa.beat.beat_track(y=y, sr=22050, units='time'); tempo = float(np.atleast_1d(tempo)[0])
    def hits(s):
        return sum(1 for c in CUTS if len(strong) and np.min(np.abs(strong - (s + c))) <= 0.04)
    rms = librosa.feature.rms(y=y)[0]; rt = librosa.times_like(rms, sr=22050); gl = np.median(rms) + 1e-9
    def e3(s): m = (rt >= s) & (rt < s + 3); return float(20 * np.log10(rms[m].mean() / gl + 1e-9)) if m.any() else -99
    if fixed_in is not None: ins = fixed_in; loop = dur < fixed_in + TOTAL
    else:
        cand = [b for b in bt if b + TOTAL <= dur] or [0.0]; loop = dur < TOTAL
        sc = [(hits(s) + 2 * (e3(s) > -1.5), s) for s in cand]; ins = max(sc)[1]
    ch = librosa.feature.chroma_cqt(y=yh, sr=22050).mean(1)
    best = max([(np.corrcoef(np.roll(MAJ, k), ch)[0, 1], KEYS[k] + ' 大调') for k in range(12)] + [(np.corrcoef(np.roll(MIN, k), ch)[0, 1], KEYS[k] + ' 小调') for k in range(12)])
    seg = (rt >= ins) & (rt < ins + TOTAL)
    return dict(file=f, dur=round(dur, 1), tempo=round(tempo, 1), in_point=round(float(ins), 2), loops=bool(loop),
                cut_hits=hits(ins), cut_total=len(CUTS), first3s_rel_db=round(e3(ins), 1),
                first3s_vs_rest_db=round(e3(ins) - float(20 * np.log10(rms[seg].mean() / gl + 1e-9)), 1),
                perc_ratio=round(float(np.sum(yp ** 2) / (np.sum(y ** 2) + 1e-9)), 2),
                drum_hits_per_s=round(float(np.sum((strong >= ins) & (strong < ins + TOTAL)) / TOTAL), 2),
                centroid_hz=int(np.mean(librosa.feature.spectral_centroid(y=y[int(ins * 22050):int((ins + TOTAL) * 22050)], sr=22050))), key=best[1], key_r=round(float(best[0]), 2))
def mix(f, ins, tag):
    b = load(f, ins, TOTAL + 0.5)
    if len(b) < N: b = np.tile(b, int(np.ceil(N / len(b))) + 1)
    b = b[:N]; b *= 10 ** ((-12.0 - lufs_of(b)) / 20); g = 10 ** (-13.9 / 20)
    t = np.arange(fr) / 100; duck = np.where(vact, -8.0, 0.0); duck[t < 3] = 0; cur = 0.0; d = np.zeros(fr)
    for i in range(fr):
        cur += (duck[i] - cur) * ((1 - np.exp(-1 / 6)) if duck[i] < cur else (1 - np.exp(-1 / 30))); d[i] = cur
    gain = np.repeat(10 ** (d / 20), hop); gain = np.pad(gain, (0, N - len(gain)), 'edge')
    fade = np.clip((TOTAL - np.arange(N) / SR) / 1.5, 0, 1); bg = b * g * gain * fade
    BB = band(bg); m = vact[:min(len(BB), len(vact))]; snr = 10 * np.log10((VB[:len(m)][m] + 1e-12) / (BB[:len(m)][m] + 1e-12))
    x = vo + sfx + bg; w = f'{a.out}/{tag}.wav'; sf.write('/tmp/_pre.wav', x, SR, subtype='FLOAT')
    e = subprocess.run(['ffmpeg', '-hide_banner', '-i', '/tmp/_pre.wav', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'], capture_output=True, text=True).stderr
    L = _lj(e); af = f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={L['input_i']}:measured_TP={L['input_tp']}:measured_LRA={L['input_lra']}:measured_thresh={L['input_thresh']}:offset={L['target_offset']}:linear=true"
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', '/tmp/_pre.wav', '-af', af, '-ar', str(SR), '-ac', '2', '-c:a', 'pcm_s16le', '-t', str(TOTAL), w], check=True)
    mp4 = f'{a.out}/{tag}_配画面.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', a.video, '-i', w, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', mp4], check=True)
    return dict(wav=w, mp4=mp4, speech_band_snr_db_p10=round(float(np.percentile(snr, 10)), 1), speech_band_snr_db_med=round(float(np.median(snr)), 1))
meta = {}
if a.meta:
    for j in os.listdir(a.meta):
        if j.endswith('.json') and not j.endswith('strong_beat.json') and j[:2].isdigit():
            d = json.load(open(os.path.join(a.meta, j))); meta[os.path.basename(d.get('file', ''))] = d
R = []
cf, ci = a.cur.rsplit(':', 1)
for k, (f, fixed) in enumerate([(cf, float(ci))] + [((c.rsplit(':',1)[0], float(c.rsplit(':',1)[1])) if re.search(r':[0-9.]+$', c) else (c, None)) for c in a.cand]):
    A = analyze(f, fixed); m = meta.get(os.path.basename(f), {})
    A.update(title=m.get('title', os.path.basename(f)), author=m.get('author'), rank=m.get('rank'), heat=m.get('heat'), user_count=m.get('user_count'), music_id=m.get('music_id'))
    tag = ('00_现版_' if k == 0 else f'{k:02d}_') + re.sub(r'[\\/:*?"<>|\s()（）]+', '_', A['title'])[:24]
    A['lyrics'] = lyrics(f, A['in_point']); A.update(mix(f, A['in_point'], tag)); R.append(A); print(json.dumps(A, ensure_ascii=False))
json.dump(R, open(f'{a.out}/compare.json', 'w'), ensure_ascii=False, indent=1)
