#!/usr/bin/env python3
"""成片一键自检（2026-10-30 首期「你被设计了吗 01」复盘后新增）。

输入：成片 mp4 + srt + 节拍网格（beat_grid.json，由 tools/qc/beat_grid.py 从 BGM stem 实测生成）
输出：PASS/FAIL 表（终端 + <out>/qc_report.md + qc_report.json）；任一 FAIL 退出码 1。

  python3 tools/qc/final_check.py --video 成片.mp4 --srt 成片.srt --grid beat_grid.json \
      [--script script/v2_approved.md] [--claims claims.json] [--dur 95 105] [--out review/qc_final]

检查项（阈值全部来自 config/workflow_spec.md §10 与 production_config §字幕）：
  字幕   每卡单行（srt 文本无换行 + 抽帧看字幕带只有 1 行字）、显示长度 ≤16 字、句末不带 ，。、；：（？！可留）、
         无两句合卡（卡内无断句标点/CJK 间空格；给了 --script 时每卡必须落在逐字稿的同一个分句里）、第 0 帧有字幕、卡不重叠
  响度   integrated −16±0.5 LUFS、true peak ≤ −1.0 dBTP（ffmpeg ebur128）
  画面   硬切数（同一口径：270px 灰度，直方图 Bhattacharyya>0.30 且 变化面积>35%）=0、
         任意 2 帧整屏平均亮度跳变 ≤17、闪白（亮度 3 帧内升 ≥12 且 0.6s 内回落 ≥12，或 ≥45% 像素近白且持续 <0.6s）=0
  拍点   非字幕运动起点（90×160 灰度帧差、字幕带置零、阈 0.25、前 4 帧静止）距最近拍点 ≤2 帧的占比 ≥85%
  时长   在 --dur 区间内；规格 1080×1920 / 30fps
  自报   --claims 里执行者自报的数字与实测逐项比对（不符即 FAIL）——回报只许引用本报告里的数。
"""
import argparse, json, re, subprocess, sys, os, hashlib, datetime
import numpy as np, cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'scripts', 'subs'))
try:
    import oneline  # 复用同一套切句/显示长度规则
except Exception:
    oneline = None

END_BAD = '，。、；：,.;:'
INNER_BAD = '，。？！；：、,?!;:…'
MAXC = 16

def nchar(s):
    return len(re.sub(r'\s', '', s))  # 规则口径：去空格后的字符数（含标点/引号，最严）

def vis_len(s):
    return sum(0.55 if re.match(r'[0-9.a-zA-Z%–-]', ch) else 1 for ch in s)

def parse_srt(p):
    txt = open(p, encoding='utf-8-sig').read().replace('\r', '')
    out = []
    for blk in re.split(r'\n\s*\n', txt.strip()):
        L = blk.split('\n')
        if len(L) < 3 or '-->' not in L[1]: continue
        def ts(x):
            h, m, s = x.strip().replace(',', '.').split(':'); return int(h) * 3600 + int(m) * 60 + float(s)
        a, b = L[1].split('-->')
        out.append(dict(i=int(L[0]), a=ts(a), b=ts(b), lines=L[2:], text='\n'.join(L[2:])))
    return out

def norm(s):
    return re.sub(r'[\s，。？！；：、…,.?!;:「」“”"\'《》()（）—-]', '', s).lower()

def script_clauses(p):
    sents = []
    for line in open(p, encoding='utf-8'):
        m = re.match(r'^\s*\d+[.．、]\s*(.+?)\s*$', line)
        if m: sents.append(m.group(1))
    cl = []
    for s in sents:
        parts = oneline.clauses(s) if oneline else re.split(r'(?<=[，。？！；：、])', s)
        cl += [norm(x) for x in parts if norm(x)]
    return cl

def sub_checks(subs, clauses, line_counts):
    rows = []
    multi = [s for s in subs if len(s['lines']) > 1]
    rows.append(('字幕·SRT 每卡单行', not multi, f'{len(subs)} 卡，多行 {len(multi)}' + (f'：#{multi[0]["i"]}' if multi else '')))
    if line_counts is not None:
        bad = [(i, n) for i, n in line_counts.items() if n > 1]
        rows.append(('字幕·抽帧实看单行', not bad, f'抽 {len(line_counts)} 卡，看到多行 {len(bad)}' + (f'：#{bad[:5]}' if bad else '')))
    long_ = [(s['i'], s['text'], nchar(s['text'])) for s in subs if nchar(s['text']) > MAXC]
    mx = max((nchar(s['text']) for s in subs), default=0); mv = max((vis_len(s['text']) for s in subs), default=0)
    rows.append(('字幕·每卡 ≤16 字', not long_, f'最长 {mx} 字（去空格字符数；按显示宽度 {mv:.1f}）' + (f'；超长 {long_[:3]}' if long_ else '')))
    endp = [(s['i'], s['text']) for s in subs if s['text'].strip() and s['text'].strip()[-1] in END_BAD]
    rows.append(('字幕·句末无标点', not endp, f'带句末标点 {len(endp)}' + (f'：{endp[:3]}' if endp else '')))
    merged = []
    for s in subs:
        t = s['text'].strip()
        core = t.rstrip(END_BAD + '？！?!')
        if any(ch in INNER_BAD for ch in core) or re.search(r'[\u4e00-\u9fff]\s+[\u4e00-\u9fff]', core):
            merged.append((s['i'], t, '卡内有断句标点/空格'))
        elif clauses is not None:
            n = norm(t)
            if n and not any(n in c for c in clauses): merged.append((s['i'], t, '跨逐字稿分句或稿中没有'))
    rows.append(('字幕·无两句合卡', not merged, f'疑似合卡 {len(merged)}' + (f'：{merged[:3]}' if merged else '') + ('（已对逐字稿分句逐卡核对）' if clauses is not None else '（未给 --script，只查标点）')))
    first = subs[0]['a'] if subs else 99
    rows.append(('字幕·第 0 帧有字幕', first <= 0.05, f'首卡起点 {first:.2f}s'))
    ov = [(a['i'], b['i']) for a, b in zip(subs, subs[1:]) if b['a'] < a['b'] - 0.01]
    rows.append(('字幕·卡间不重叠', not ov, f'重叠 {len(ov)}'))
    return rows

def loudness(video):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', video, '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True).stderr
    summ = r[r.rfind('Summary:'):]
    I = float(re.search(r'I:\s+(-?[\d.]+) LUFS', summ).group(1))
    LRA = float(re.search(r'LRA:\s+(-?[\d.]+) LU', summ).group(1))
    TP = float(re.search(r'Peak:\s+(-?[\d.inf]+) dBFS', summ).group(1))
    return I, TP, LRA

def probe(video):
    j = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height,r_frame_rate,duration:format=duration', '-of', 'json', video], capture_output=True, text=True).stdout)
    v = [s for s in j['streams'] if s['codec_type'] == 'video'][0]
    n, d = v['r_frame_rate'].split('/')
    global VDUR, NPKT
    VDUR = float(v.get('duration') or j['format']['duration'])
    NPKT = int(json.loads(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v', '-count_packets', '-show_entries', 'stream=nb_read_packets', '-of', 'json', video], capture_output=True, text=True).stdout)['streams'][0]['nb_read_packets'])
    return float(j['format']['duration']), int(v['width']), int(v['height']), float(n) / float(d), any(s['codec_type'] == 'audio' for s in j['streams'])

def count_text_lines(band):
    """字幕带里的白字（白填充+黑描边）有几行：近白像素的行投影聚类。"""
    m = (band.min(axis=2) > 200)
    rows = m.sum(axis=1) >= 6
    lines, run, gap = 0, 0, 99
    for r in rows:
        if r: run += 1; gap = 0
        else:
            gap += 1
            if run and gap > 10:
                if run >= 18: lines += 1
                run = 0
    if run >= 18: lines += 1
    return lines

def video_pass(video, fps, subs, sub_band=(1520, 1760), samp_band=(1530, 1800)):
    cap = cv2.VideoCapture(video)
    want = {}
    for s in subs:  # 每卡在显示区间中点抽一帧看字幕行数
        want.setdefault(int(round((s['a'] + s['b']) / 2 * fps)), s['i'])
    prev90 = prevW = ph = None; d90 = []; L = []; E = []; A = []; Hh = []; white = []; lc = {}
    i = 0
    while True:
        ok, fr = cap.read()
        if not ok: break
        H, Wd = fr.shape[:2]
        g90 = cv2.cvtColor(cv2.resize(fr, (90, 160), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(float)
        g90[int(160 * sub_band[0] / 1920):int(160 * sub_band[1] / 1920)] = 0
        if prev90 is not None: d90.append(np.abs(g90 - prev90).mean())
        prev90 = g90
        gW = cv2.cvtColor(cv2.resize(fr, (270, int(round(270 * H / Wd))), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        L.append(float(gW.mean())); white.append(float((gW > 230).mean()))
        hist = cv2.calcHist([gW], [0], None, [32], [0, 256]); cv2.normalize(hist, hist)
        if prevW is not None:
            dd = cv2.absdiff(gW, prevW); E.append(float(dd.mean())); A.append(float((dd > 12).mean()))
            Hh.append(float(cv2.compareHist(ph, hist, cv2.HISTCMP_BHATTACHARYYA)))
        prevW, ph = gW, hist
        if i in want:
            y0, y1 = int(samp_band[0] * H / 1920), int(samp_band[1] * H / 1920)
            lc[want[i]] = count_text_lines(fr[y0:y1, int(0.04 * Wd):int(0.96 * Wd)])
        i += 1
    return dict(n=i, d90=np.array(d90), L=np.array(L), E=np.array(E), A=np.array(A), H=np.array(Hh), white=np.array(white), lines=lc)

def onsets(d, fps, thr=0.25, quiet=4):
    on = []; below = quiet
    for i, x in enumerate(d):
        if x > thr and below >= quiet: on.append((i + 1) / fps)
        below = below + 1 if x <= thr else 0
    return on

def flashes(L, white, fps):
    ev = []
    n = len(L); win = int(0.6 * fps)
    for i in range(n - 3):
        if L[i + 3] - L[i] >= 12 or L[i + 1] - L[i] >= 12:
            pk = i + int(np.argmax(L[i:i + 4])); seg = L[pk:pk + win]
            if len(seg) and L[pk] - seg.min() >= 12 and (not ev or (i / fps) - ev[-1] > 0.5): ev.append(round(i / fps, 2))
    w = white > 0.45; i = 0
    while i < n:
        if w[i]:
            j = i
            while j < n and w[j]: j += 1
            if (j - i) < 0.6 * fps and (not ev or abs(i / fps - ev[-1]) > 0.5): ev.append(round(i / fps, 2))
            i = j
        else: i += 1
    return sorted(ev)

def load_grid(p, dur):
    g = json.load(open(p))
    if 'beats' in g: return np.array(g['beats']), g
    off, per = g['offset'], g['period']; n = g.get('n') or int((dur - off) / per) + 2
    return off + per * np.arange(n), g

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--video', required=True); ap.add_argument('--srt', help='不给则跳过字幕项（只用于验证画面/拍点检测器）'); ap.add_argument('--grid', required=True)
    ap.add_argument('--script'); ap.add_argument('--claims'); ap.add_argument('--dur', nargs=2, type=float, default=[95, 105])
    ap.add_argument('--hit-target', type=float, default=0.85); ap.add_argument('--tol-frames', type=float, default=2)
    ap.add_argument('--sub-band', nargs=2, type=int, default=[1530, 1800], help='抽帧数字幕行数的 y 区间（1920 高坐标；模板字幕容器 top=1560 高 140）')
    ap.add_argument('--out'); ap.add_argument('--no-frame-subs', action='store_true', help='跳过抽帧看字幕行数')
    a = ap.parse_args()
    t0 = datetime.datetime.now()
    dur, W, H, fps, has_a = probe(a.video)
    subs = parse_srt(a.srt) if a.srt else []
    clauses = script_clauses(a.script) if a.script else None
    vp = video_pass(a.video, fps, [] if a.no_frame_subs else subs, samp_band=tuple(a.sub_band))
    rows = sub_checks(subs, clauses, None if a.no_frame_subs else vp['lines']) if a.srt else [('字幕（未给 --srt，跳过）', True, '—')]
    I, TP, LRA = loudness(a.video)
    rows.append(('响度·整体 −16 LUFS（±0.5）', abs(I + 16) <= 0.5, f'{I:.1f} LUFS（LRA {LRA:.1f} LU）'))
    rows.append(('响度·真峰 ≤ −1 dBTP', TP <= -1.0, f'{TP:.1f} dBTP'))
    cut = (vp['H'] > 0.30) & (vp['A'] > 0.35); cut_t = []
    for k in np.where(cut)[0]:  # 连续几帧都判切的只算 1 次（0.2s 内合并）
        tk = round(float(k + 1) / fps, 2)
        if not cut_t or tk - cut_t[-1] > 0.2: cut_t.append(tk)
    rows.append(('画面·硬切 = 0', len(cut_t) == 0, f'{len(cut_t)} 次' + (f'：{cut_t[:8]}s' if cut_t else '')))
    L = vp['L']; j2 = np.abs(L[2:] - L[:-2]); jm = float(j2.max()) if len(j2) else 0; jt = round((int(np.argmax(j2)) + 2) / fps, 2) if len(j2) else 0
    rows.append(('画面·2 帧亮度跳变 ≤17', jm <= 17, f'最大 {jm:.1f}（{jt}s）'))
    fl = flashes(L, vp['white'], fps)
    rows.append(('画面·闪白 = 0', not fl, f'{len(fl)} 次' + (f'：{fl[:8]}s' if fl else '')))
    still = float((vp['E'] < 0.3).mean()); whole = int(((vp['A'] > 0.5) & ~cut).sum())
    rows.append(('画面·静止帧 ≥65%（参考）', still >= 0.65, f'{still*100:.1f}%；整屏大变化帧 {whole}'))
    beats, g = load_grid(a.grid, dur)
    on = onsets(vp['d90'], fps); tol = a.tol_frames / fps + 1e-6
    dist = np.array([np.min(np.abs(beats - o)) for o in on]) if on else np.array([])
    hit = float((dist <= tol).mean()) if len(dist) else 0.0
    miss = [round(float(o), 2) for o, d in zip(on, dist) if d > tol]
    rows.append((f'拍点·动效起点命中 ≥{a.hit_target*100:.0f}%', hit >= a.hit_target, f'{int((dist<=tol).sum())}/{len(on)} = {hit*100:.1f}%（±{a.tol_frames:g} 帧；网格 {g.get("offset","list")}+k·{g.get("period","")}）' + (f'；未命中起点 {miss[:10]}s' if miss else '')))
    rows.append((f'时长 {a.dur[0]:g}–{a.dur[1]:g}s', a.dur[0] <= dur <= a.dur[1], f'{dur:.2f}s（视频流 {VDUR:.2f}s，音画差 {abs(dur-VDUR)*fps:.0f} 帧，参考）'))
    rows.append(('规格 1080×1920 / 30fps / 有音轨', (W, H) == (1080, 1920) and abs(fps - 30) < 0.01 and has_a and vp['n'] == NPKT, f'{W}×{H} {fps:g}fps 音轨={has_a}；完整解码 {vp["n"]}/{NPKT} 帧'))
    meas = dict(lufs=round(I, 2), tp=round(TP, 2), lra=round(LRA, 2), cuts=len(cut_t), max_luma_jump=round(jm, 2), flashes=len(fl), beat_hit=round(hit, 4),
                n_onsets=len(on), duration=round(dur, 2), n_subs=len(subs), max_sub_len=max((nchar(s['text']) for s in subs), default=0), still_ratio=round(still, 4))
    if a.claims:
        cl = json.load(open(a.claims)); tolm = dict(lufs=0.15, tp=0.15, lra=0.3, max_luma_jump=1.0, beat_hit=0.02, duration=0.05, still_ratio=0.02, max_sub_len=0.01)
        for k, v in cl.items():
            if k not in meas: rows.append((f'自报·{k}', False, f'自报 {v}，本脚本不测此项——不得作为实测回报')); continue
            ok = abs(float(v) - float(meas[k])) <= tolm.get(k, 0)
            rows.append((f'自报·{k}', ok, f'自报 {v} / 实测 {meas[k]}'))
    sha = hashlib.sha256(open(a.video, 'rb').read()).hexdigest()
    nfail = sum(not ok for _, ok, _ in rows)
    md = [f'# 成片自检报告（tools/qc/final_check.py）', '',
          f'- 成片：`{a.video}`（sha256 {sha[:12]}…）', f'- 字幕：`{a.srt}`；节拍网格：`{a.grid}`' + (f'；逐字稿：`{a.script}`' if a.script else ''),
          f'- 运行：{t0:%Y-%m-%d %H:%M}（UTC+8），耗时 {(datetime.datetime.now()-t0).total_seconds():.0f}s', f'- **结论：{"全部 PASS" if not nfail else f"{nfail} 项 FAIL"}**', '',
          '| 检查项 | 结果 | 实测 |', '|---|---|---|'] + [f'| {n} | {"PASS" if ok else "**FAIL**"} | {d} |' for n, ok, d in rows]
    print('\n'.join(md))
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        open(os.path.join(a.out, 'qc_report.md'), 'w').write('\n'.join(md) + '\n')
        json.dump(dict(video=a.video, sha256=sha, measured=meas, rows=[dict(item=n, pass_=bool(ok), detail=d) for n, ok, d in rows],
                       onsets=on, missed_onsets=miss, cuts=cut_t, flashes=fl, sub_lines=vp['lines']), open(os.path.join(a.out, 'qc_report.json'), 'w'), ensure_ascii=False, indent=1)
    sys.exit(1 if nfail else 0)

if __name__ == '__main__':
    main()
