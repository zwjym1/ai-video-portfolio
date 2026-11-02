#!/workspace/.venv-review/bin/python
"""逐镜精审（某一时段）：帧差找片内快闪、主体位置跳动、切点对鼓点/句首、字幕/署名遮挡，并出拼图给 qoder 看。
用法: shotreview.py <video> <outdir> --from 3 --to 27 [--cuts 0,2.9,...] [--beats beat_map.json] [--asr asr.json] [--dense 4.4-9.2:10,14-23.2:4]"""
import sys, os, json, argparse, subprocess, numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont
ap = argparse.ArgumentParser(); ap.add_argument('video'); ap.add_argument('out'); ap.add_argument('--from', dest='t0', type=float, default=3); ap.add_argument('--to', dest='t1', type=float, default=27)
ap.add_argument('--cuts'); ap.add_argument('--beats'); ap.add_argument('--asr'); ap.add_argument('--dense', default='')
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'; fnt = lambda s: ImageFont.truetype(FONT, s)
FPS = 30
def read(t0, t1, w=270):
    cmd = ['ffmpeg', '-v', 'error', '-ss', f'{t0:.3f}', '-t', f'{t1-t0:.3f}', '-i', a.video, '-vf', f'fps={FPS},scale={w}:-2', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    raw = subprocess.run(cmd, capture_output=True).stdout; h = int(round(1920*w/1080/2)*2); n = len(raw)//(w*h*3)
    return np.frombuffer(raw[:n*w*h*3], np.uint8).reshape(n, h, w, 3), h
fr, H = read(a.t0, a.t1); ts = a.t0 + np.arange(len(fr))/FPS
g = fr.mean(3).astype(np.float32); d = np.r_[0, np.abs(np.diff(g, axis=0)).mean((1, 2))]
# 字幕带(下 25%)和角标带(上 8%)不计入画面变化
gm = g[:, int(.08*H):int(.75*H)]; dm = np.r_[0, np.abs(np.diff(gm, axis=0)).mean((1, 2))]
cuts = [float(x) for x in a.cuts.split(',')] if a.cuts else None
beats = json.load(open(a.beats))['onsets_video_s'] if a.beats else []
asr = json.load(open(a.asr)) if a.asr else []
starts = [s['a'] for s in asr]
# 片内快闪：不在设计切点 ±2 帧的帧差尖峰（> 中位数×4 且 > 12）
med = np.median(dm[dm > 0]); thr = max(12, 4*med)
spikes = [round(float(t), 3) for t, x in zip(ts, dm) if x > thr]
def near(t, L, tol): return min((abs(t-x) for x in L), default=9) <= tol
intra = [t for t in spikes if not (cuts and near(t, cuts, 2.5/FPS))]
# 主体位置：显著性重心（谱残差），每镜首/末帧
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from objective import spectral_saliency
def cen(img):
    m = spectral_saliency(cv2.cvtColor(img[int(.08*H):int(.75*H)], cv2.COLOR_RGB2GRAY)); m = cv2.resize(m, (img.shape[1], int(.75*H)-int(.08*H)))
    m = (255*(m-m.min())/(np.ptp(m)+1e-9)).astype(np.uint8)
    _, b = cv2.threshold(m, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU); ys, xs = np.nonzero(b)
    return (float(xs.mean()/img.shape[1]), float((ys.mean()+.08*H)/H)) if len(xs) else (0.5, 0.5)
fi = lambda t: int(np.clip(round((t-a.t0)*FPS), 0, len(fr)-1))
shots = []
C = [c for c in (cuts or []) if a.t0-3 <= c < a.t1] 
for i, c in enumerate(C):
    e = C[i+1] if i+1 < len(C) else a.t1
    s0, s1 = max(c, a.t0), min(e, a.t1)
    if s1 - s0 < 0.1: continue
    seg = dm[fi(s0)+2:fi(s1)-1]; inn = [t for t in intra if s0 < t < s1]
    shots.append(dict(i=i+1, a=round(c, 2), b=round(e, 2), dur=round(e-c, 2), first=cen(fr[fi(s0)+1]), last=cen(fr[fi(s1)-2]),
                      motion=round(float(seg.mean()), 1) if len(seg) else None, intra_flashes=inn,
                      on_beat=near(c, beats, 0.04), beat_off_ms=round(min((abs(c-x) for x in beats), default=9)*1000),
                      on_sentence=near(c, starts, 0.15), sent_off_ms=round(min((abs(c-x) for x in starts), default=9)*1000)))
for k in range(1, len(shots)):
    p, q = shots[k-1]['last'], shots[k]['first']; shots[k]['jump_from_prev'] = round(float(np.hypot(p[0]-q[0], p[1]-q[1])), 3)
for s in shots: s['first'] = [round(x, 2) for x in s['first']]; s['last'] = [round(x, 2) for x in s['last']]
json.dump(dict(range=[a.t0, a.t1], fps=FPS, flash_thr=round(float(thr), 1), spikes=spikes, intra_flashes=intra, shots=shots), open(os.path.join(a.out, 'shots.json'), 'w'), ensure_ascii=False, indent=1)
sub_at = lambda t: next((s['text'] for s in asr if s['a'] <= t < s['b']+.05), '')
def sheet(items, cols, w, name, title):
    rows = (len(items)+cols-1)//cols; hh = int(w*1920/1080); pad = 34
    S = Image.new('RGB', (cols*w, 60+rows*(hh+pad)), (18, 18, 18)); D = ImageDraw.Draw(S); D.text((8, 10), title, font=fnt(30), fill=(255, 220, 120))
    for k, (t, lab) in enumerate(items):
        im = Image.fromarray(fr[fi(t)]).resize((w, hh)); x, y = (k % cols)*w, 60+(k//cols)*(hh+pad); S.paste(im, (x, y+pad))
        D.text((x+4, y+2), lab, font=fnt(20), fill=(255, 255, 255))
    S.save(os.path.join(a.out, name), quality=88); return name
out = []
# 1 每镜 首/中/末
it = []
for s in shots:
    s0, s1 = max(s['a'], a.t0), min(s['b'], a.t1)
    for tag, t in (('首', s0+1/FPS), ('中', (s0+s1)/2), ('末', s1-2/FPS)): it.append((t, f"#{s['i']}{tag} {t:.2f}s"))
out.append(sheet(it, 9, 150, 'shots_first_mid_last.jpg', f'逐镜 首/中/末 帧 {a.t0}-{a.t1}s（#=镜号）'))
# 2 切点前后对
it = []
for s in shots[1:]:
    it += [(s['a']-2/FPS, f"切{s['a']:.2f}前"), (s['a']+1/FPS, f"切{s['a']:.2f}后")]
out.append(sheet(it, 10, 140, 'cut_pairs.jpg', '每个切点前一帧 / 后一帧（看构图与主体跳动、风格衔接）'))
# 3 密集段
for spec in filter(None, a.dense.split(',')):
    rg, f = spec.split(':'); x0, x1 = map(float, rg.split('-')); f = float(f)
    tt = np.arange(x0, x1, 1/f); it = [(t, f"{t:.2f}s{' ⚡' if near(t, intra, .5/f) else ''}") for t in tt]
    out.append(sheet(it, 10, 130, f'dense_{x0:g}-{x1:g}s_{f:g}fps.jpg', f'{x0}-{x1}s 每 {1/f:.2f}s 一帧（⚡=片内快闪）'))
# 4 帧差曲线
W_, H_ = 1600, 360; P = Image.new('RGB', (W_, H_), (18, 18, 18)); D = ImageDraw.Draw(P)
X = lambda t: 40+(t-a.t0)/(a.t1-a.t0)*(W_-60); mx = max(dm.max(), thr*1.2)
for b in beats:
    if a.t0 <= b <= a.t1: D.line([(X(b), 40), (X(b), H_-30)], fill=(60, 60, 110))
for c in (cuts or []):
    if a.t0 <= c <= a.t1: D.line([(X(c), 30), (X(c), H_-30)], fill=(200, 80, 80), width=2)
D.line([(X(t), H_-30-x/mx*(H_-80)) for t, x in zip(ts, dm)], fill=(120, 220, 255), width=2)
D.line([(40, H_-30-thr/mx*(H_-80)), (W_-20, H_-30-thr/mx*(H_-80))], fill=(255, 200, 0))
for t in range(int(a.t0), int(a.t1)+1): D.text((X(t)-8, H_-26), str(t), font=fnt(18), fill=(200, 200, 200))
D.text((40, 6), '帧间差（蓝）/ 设计切点（红）/ BGM 鼓点（紫）/ 快闪阈值（黄）', font=fnt(22), fill=(255, 255, 255)); P.save(os.path.join(a.out, 'framediff.png')); out.append('framediff.png')
print(json.dumps(dict(sheets=out, intra=intra, n_shots=len(shots)), ensure_ascii=False))
