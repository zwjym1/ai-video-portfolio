#!/workspace/.venv-review/bin/python
"""客观检测层：只看文件、不联网、不登录。
用法: objective.py --video V --asr asr.json --out out/<id>/objective.json
       [--cover 封面.png] [--facts facts.md] [--publish 发布文案.md] [--nobgm 无BGM版.mp4] [--beats beat_map.json] [--ai]
"""
import argparse, json, os, re, subprocess, sys, math
import numpy as np, cv2

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)

def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def probe(v):
    r = sh(['ffprobe','-v','error','-show_entries','format=duration:stream=width,height,r_frame_rate,codec_type','-of','json',v])
    j = json.loads(r.stdout); d = float(j['format']['duration'])
    vs = [s for s in j['streams'] if s['codec_type']=='video'][0]
    return d, int(vs['width']), int(vs['height'])

def frames(v, fps, w=270, h=480, t0=0, dur=None):
    cmd = ['ffmpeg','-v','error','-ss',str(t0)] + (['-t',str(dur)] if dur else []) + ['-i',v,'-vf',f'fps={fps},scale={w}:{h}','-f','rawvideo','-pix_fmt','rgb24','-']
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw)//(w*h*3)
    return np.frombuffer(raw[:n*w*h*3], np.uint8).reshape(n, h, w, 3)

def frame_at(v, t, w=540, h=960):
    f = frames(v, 1, w, h, t0=t, dur=0.5)
    return f[0] if len(f) else None

# ---------- 1 首帧主体 ----------
def spectral_saliency(gray):
    g = cv2.resize(gray, (64, 114)).astype(np.float32)
    F = np.fft.fft2(g); A = np.log(np.abs(F)+1e-6); P = np.angle(F)
    R = A - cv2.blur(A, (3,3))
    S = np.abs(np.fft.ifft2(np.exp(R+1j*P)))**2
    S = cv2.GaussianBlur(S, (9,9), 2.5); S = (S-S.min())/(S.max()-S.min()+1e-9)
    return cv2.resize(S, (gray.shape[1], gray.shape[0]))

def frame0_metrics(f):
    gray = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY)
    lum = float(gray.mean()/255)
    S = spectral_saliency(gray)
    m = (S > max(0.35, np.percentile(S, 85))).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    area = float(st[1:,4].max()/m.size) if n > 1 else 0.0
    if n > 1:
        k = 1+int(np.argmax(st[1:,4])); mass_in = float(S[lab==k].sum()/S.sum())
    else: mass_in = 0.0
    edges = cv2.Canny(gray, 80, 160); ed = float(edges.mean()/255)
    rg = f[...,0].astype(float)-f[...,1]; yb = 0.5*(f[...,0].astype(float)+f[...,1])-f[...,2]
    colorful = float(np.sqrt(rg.std()**2+yb.std()**2)+0.3*np.sqrt(rg.mean()**2+yb.mean()**2))
    # 主体中心对比：显著区平均亮度 vs 背景
    if n > 1:
        fg = gray[lab==k].mean(); bg = gray[lab!=k].mean(); c = abs(float(fg-bg))/255
    else: c = 0.0
    return dict(luminance=round(lum,3), salient_blob_area=round(area,3), salient_mass_in_blob=round(mass_in,3),
                subject_bg_contrast=round(c,3), edge_density=round(ed,3), colorfulness=round(colorful,1))

# ---------- 2 剪辑与画面变化 ----------
def cuts(v, thr=0.10, min_gap=0.4):
    """画面切换点：ffmpeg scene 分数 ≥thr（含硬切与大幅转场），间隔≥min_gap 去抖。"""
    tmp = f'/tmp/_sc_{os.getpid()}.txt'
    sh(['ffmpeg','-v','error','-i',v,'-vf',f"scale=180:320,select='gte(scene,0)',metadata=print:file={tmp}",'-an','-f','null','-'])
    txt = open(tmp).read(); os.remove(tmp)
    ts = [float(x) for x in re.findall(r'pts_time:([\d.]+)', txt)]; sc = [float(x) for x in re.findall(r'scene_score=([\d.]+)', txt)]
    out = []
    for t, s_ in zip(ts, sc):
        if s_ >= thr and (not out or t-out[-1] >= min_gap): out.append(round(t,2))
    return out

def visual_change(F, fps):
    g = F.mean(axis=3).astype(np.float32)
    d = np.abs(np.diff(g, axis=0)).mean(axis=(1,2))  # 相邻帧平均像素差
    per_s = [float(d[i:i+fps].mean()) for i in range(0, len(d), fps)]
    active = [x > 6 for x in per_s]
    # 最长静止段（像素差<2.5 连续秒数）
    longest = cur = 0
    for x in per_s:
        cur = cur+1 if x < 2.5 else 0; longest = max(longest, cur)
    return dict(pixel_change_active_share=round(float(np.mean(active)),3), longest_static_s=int(longest),
                mean_diff=round(float(np.mean(per_s)),2), per_second=[round(x,1) for x in per_s])

# ---------- 3 OCR 字幕可读性 / 合规角标 ----------
_ocr = None
def ocr(img):
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    res, _ = _ocr(img[..., ::-1].copy())
    out = []
    for box, txt, sc in (res or []):
        sc = float(sc)
        if sc < 0.6: continue
        b = np.array(box); x0,y0 = b.min(0); x1,y1 = b.max(0)
        out.append(dict(t=txt, x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1), s=float(sc)))
    return out

def wcag(img, b):
    crop = cv2.cvtColor(img[int(b['y0']):int(b['y1']), int(b['x0']):int(b['x1'])], cv2.COLOR_RGB2GRAY)
    if crop.size < 20: return None
    t,_ = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    a = crop[crop>t]; c = crop[crop<=t]
    if len(a)==0 or len(c)==0: return None
    L = lambda v: (lambda s: s/12.92 if s<=0.03928 else ((s+0.055)/1.055)**2.4)(v/255)
    l1, l2 = L(np.percentile(a,80)), L(np.percentile(c,20))
    return (max(l1,l2)+0.05)/(min(l1,l2)+0.05)

def subtitle_metrics(v, dur, W=540, H=960):
    F = frames(v, 1, W, H)
    heights, cpl, contrast, unsafe, with_text, texts = [], [], [], 0, 0, []
    main_h, top_hidden = [], []
    nbox = 0
    for i, f in enumerate(F):
        bs = ocr(f)
        texts.append(dict(t=i, text=' | '.join(b['t'] for b in bs)))
        if not bs: continue
        with_text += 1
        low = [b['y1']-b['y0'] for b in bs if b['y0'] > 0.5*H and len(re.findall(r'[\u4e00-\u9fff]', b['t'])) >= 2]
        if low: main_h.append(max(low)/H)
        for b in bs:
            hz = len(re.findall(r'[\u4e00-\u9fff]', b['t']))
            if hz < 2: continue
            nbox += 1
            heights.append((b['y1']-b['y0'])/H); cpl.append(len(b['t']))
            c = wcag(f, b); contrast.append(c) if c else None
            # 抖音界面遮挡区（经验值，未核）：底部 8%（进度条/导航）、右侧 14%（点赞/评论按钮列，竖向 45%-85%）、顶部 6%（推荐/关注 tab）
            if b['y1'] > 0.92*H or (b['x1'] > 0.86*W and 0.45*H < b['y0'] < 0.85*H): unsafe += 1
            if b['y1'] < 0.06*H: top_hidden.append(b['t'])
    med = lambda x: round(float(np.median(x)),4) if x else None
    return dict(text_frame_share=round(with_text/max(1,len(F)),3), median_text_height_frac=med(heights),
                p10_text_height_frac=round(float(np.percentile(heights,10)),4) if heights else None,
                median_chars_per_line=med(cpl), max_chars_per_line=int(max(cpl)) if cpl else None,
                median_contrast=round(float(np.median(contrast)),2) if contrast else None,
                low_contrast_share=round(float(np.mean([c<3 for c in contrast])),3) if contrast else None,
                unsafe_zone_share=round(unsafe/max(1,nbox),3),
                main_subtitle_height_frac=med(main_h), top6pct_texts=sorted(set(top_hidden))[:5]), texts

# ---------- 4 响度 ----------
def loud(v, t0=None, dur=None):
    cmd = ['ffmpeg','-v','info'] + (['-ss',str(t0),'-t',str(dur)] if dur else []) + ['-i',v,'-af','ebur128=peak=true','-f','null','-']
    e = sh(cmd).stderr; tail = e[e.rfind('Summary'):]
    g = lambda k: (lambda m: float(m.group(1)) if m else None)(re.search(k+r':\s+(-?[\d.]+|-inf)', tail))
    return dict(I_LUFS=g('I'), LRA=g('LRA'), TP_dBTP=g('Peak'))

def audio_onsets(v, sr=22050):
    raw = subprocess.run(['ffmpeg','-v','error','-i',v,'-ac','1','-ar',str(sr),'-f','f32le','-'], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32); hop = 512; win = 2048
    n = 1 + (len(x)-win)//hop
    idx = np.arange(win)[None,:] + hop*np.arange(n)[:,None]
    X = np.abs(np.fft.rfft(x[idx]*np.hanning(win), axis=1))
    X = np.log1p(10*X); flux = np.maximum(0, np.diff(X, axis=0)).sum(1)
    flux = (flux-flux.mean())/(flux.std()+1e-9)
    t = (np.arange(len(flux))+1)*hop/sr
    # 峰值：局部最大且 > 1.2σ，间隔≥0.15s
    pk = []
    for i in range(3, len(flux)-3):
        if flux[i] > 1.2 and flux[i] == flux[i-3:i+4].max():
            if not pk or t[i]-pk[-1] > 0.15: pk.append(float(t[i]))
    rms = np.sqrt((x[idx]**2).mean(1)); return pk, t, rms

def beat_sync(cut_t, onsets, dur, tol=0.08):
    if not cut_t or not onsets: return dict(cuts=len(cut_t), aligned_share=None, chance=None, lift=None)
    on = np.array(onsets)
    al = [np.min(np.abs(on-c)) <= tol for c in cut_t]
    # 随机基线：同样数量的随机时刻命中率（蒙特卡洛）
    rng = np.random.default_rng(0); R = rng.uniform(0, dur, (2000, len(cut_t)))
    ch = float(np.mean(np.min(np.abs(R[...,None]-on[None,None,:]), axis=2) <= tol))
    sh_ = float(np.mean(al)); return dict(cuts=len(cut_t), aligned_share=round(sh_,3), chance=round(ch,3), lift=round(sh_/ch,2) if ch else None)

# ---------- 5 文本层：开头信息点 / 语速 / 术语 / 新信息间隔 / 结尾 ----------
import jieba, jieba.posseg as pseg
jieba.setLogLevel(60)
def load_list(p):
    return set(l.strip() for l in open(p) if l.strip() and not l.startswith('#')) if os.path.exists(p) else set()
TERMS = load_list(os.path.join(ROOT,'config/lexicon_terms.txt')); PLAIN = load_list(os.path.join(ROOT,'config/lexicon_plain.txt'))
for w in TERMS|PLAIN: jieba.add_word(w, freq=5, tag='n')
CONTRAST = ['不是','居然','竟然','反而','却','其实','没想到','为什么','凭什么','怎么','原来','真相','根本','偏偏','只用','比','会长出','越','反倒']
ANALOGY = ['就像','像是','好比','相当于','就好比','类似','想象','像一','像个','像把','像你']
CTA = ['关注','点赞','收藏一下','下期','三连','评论区告诉','记得']
HZ = re.compile(r'[\u4e00-\u9fffA-Za-z0-9]')

def words_before(asr, T):
    out = []
    for s in asr:
        ws = s.get('words') or [[s['text'], s['a'], s['b']]]
        for w, a, b in ws:
            if a < T: out.append(w)
    return ''.join(out)

def concrete(text):
    nouns, nums = [], []
    for w, p in pseg.cut(text):
        if re.fullmatch(r'[\d.]+|[一二三四五六七八九十百千万两几]+[倍个块天年秒次毫度%]?', w) or p == 'm': nums.append(w)
        elif p in ('n','nr','ns','nz','eng','nt') and len(w) >= 2 or w in TERMS or w in PLAIN: nouns.append(w)
    return nouns, nums

def is_term(w, p):
    if w in PLAIN: return False
    if w in TERMS: return True
    if len(w) < 2 or not re.search(r'[\u4e00-\u9fff]', w): return bool(re.fullmatch(r'f/\d|[A-Z]{2,}', w))
    f = jieba.dt.FREQ.get(w, 0)
    return p in ('n','nz') and 0 < f < 120 and len(w) >= 3

def text_metrics(asr, dur):
    full = ''.join(s['text'] for s in asr)
    chars = len(HZ.findall(full)); speech = sum(s['b']-s['a'] for s in asr)
    first_voice = min((w[1] for s in asr for w in (s.get('words') or []) ), default=(asr[0]['a'] if asr else None))
    t3 = words_before(asr, 3.0); n3, m3 = concrete(t3)
    contrast3 = [c for c in CONTRAST if c in t3]
    # 术语
    terms, seen = [], set()
    for s in asr:
        for w, p in pseg.cut(s['text']):
            if is_term(w, p) and w not in seen:
                seen.add(w); terms.append(dict(term=w, t=s['a']))
    for tr in terms:  # 术语出现前后 ±1 句内是否有类比
        i = next(k for k,s in enumerate(asr) if s['a']==tr['t'])
        ctx = ''.join(asr[j]['text'] for j in range(max(0,i-1), min(len(asr),i+2)))
        tr['analogy_nearby'] = any(a in ctx for a in ANALOGY)
    # 新信息间隔
    seen_n, info_t = set(), []
    for s in asr:
        n, m = concrete(s['text']); new = [x for x in n+m if x not in seen_n]
        if new: info_t.append(s['a']); seen_n |= set(new)
    gaps = np.diff([0.0]+info_t+[dur]) if info_t else [dur]
    tail = ''.join(s['text'] for s in asr if s['a'] > dur-8)
    return dict(chars=chars, speech_s=round(speech,1), cps_speech=round(chars/max(1,speech),2), cps_duration=round(chars/dur,2),
                first_voice_s=round(first_voice,2) if first_voice is not None else None,
                first3s_text=t3, first3s_nouns=sorted(set(n3)), first3s_numbers=m3, first3s_contrast=contrast3,
                first3s_info_points=len(set(n3))+min(2,len(m3))+(1 if contrast3 else 0),
                terms=terms, term_count=len(terms), terms_per_min=round(len(terms)/dur*60,2),
                first_term_s=terms[0]['t'] if terms else None,
                term_analogy_share=round(np.mean([t['analogy_nearby'] for t in terms]),2) if terms else None,
                new_info_events=len(info_t), new_info_mean_gap_s=round(float(np.mean(gaps)),2), new_info_max_gap_s=round(float(np.max(gaps)),2),
                ending_text=tail, ending_cta=[c for c in CTA if c in tail], ending_question=('？' in tail or '?' in tail or '吗' in tail[-6:]))

# ---------- 6 事实出处 ----------
CN = dict(zip('零一二两三四五六七八九十', [0,1,2,2,3,4,5,6,7,8,9,10]))
def numbers_in(text):
    out = set(re.findall(r'\d+(?:\.\d+)?', text))
    for m in re.findall(r'[一二两三四五六七八九十]+(?=[倍个片块天年秒次条根层度])', text):
        v = CN.get(m) if len(m)==1 else (10+CN.get(m[1],0) if m[0]=='十' else CN.get(m[0],0)*10+(CN.get(m[2],0) if len(m)>2 else 0))
        if v is not None: out.add(str(v))
    return out

def fact_metrics(asr, facts_path, ocr_texts):
    claims = numbers_in(''.join(s['text'] for s in asr))  # 只核口播数字（OCR 噪声大，屏幕数字另列）
    claims = {c for c in claims if c not in ('0','1','2','3')} or claims
    if not facts_path or not os.path.exists(facts_path):
        return dict(facts_file=None, numeric_claims=sorted(claims), sourced=[], unsourced=sorted(claims), source_urls=0, coverage=0.0)
    ft = open(facts_path).read(); urls = len(set(re.findall(r'https?://[^\s)>\]]+', ft)))
    fnum = numbers_in(ft); ok = sorted(c for c in claims if c in fnum); bad = sorted(c for c in claims if c not in fnum)
    return dict(facts_file=facts_path, numeric_claims=sorted(claims), sourced=ok, unsourced=bad, source_urls=urls,
                coverage=round(len(ok)/max(1,len(claims)),2))

# ---------- 7 合规 ----------
REAL = ['实拍','样张','真机拍摄','现场拍摄','原片直出','官方样片']
def compliance(asr, ocr_texts, publish, ai_flag):
    spoken = ''.join(s['text'] for s in asr); scr = ' '.join(o['text'] for o in ocr_texts)
    pub = open(publish).read() if publish and os.path.exists(publish) else ''
    label = bool(re.search(r'AI\s*(生成|示意|合成)|艺术示意|示意图|画面为示意', scr))
    declared = bool(re.search(r'内容由AI生成|AI\s*生成', pub))
    neg = lambda t, w: re.search(r'(非|不是|并非|不代表)[^。，,]{0,6}'+w, t)
    claims_real = sorted(set(w for w in REAL for t in (spoken, scr) if w in t and not neg(t, w)))
    attributed = bool(re.search(r'(实拍|来源|素材)[:：]?\s*\S+.*(CC\s*BY|\d{4}|官方|Newsroom)', scr))
    risk = bool(claims_real) and (ai_flag or not attributed)
    return dict(ai_content=ai_flag, in_video_ai_label=label, publish_declares_ai=declared if pub else None,
                publish_file=publish if pub else None, claims_real_footage=claims_real, real_footage_attributed=attributed,
                impersonation_risk=risk)

# ---------- 8 封面 vs 首帧 ----------
def cover_match(cover, f0):
    if not cover or not os.path.exists(cover): return dict(cover=None)
    c = cv2.cvtColor(cv2.imread(cover), cv2.COLOR_BGR2RGB)
    h, w = f0.shape[:2]; c = cv2.resize(c, (w, h))
    a = cv2.resize(cv2.cvtColor(c, cv2.COLOR_RGB2GRAY), (90,160)).astype(float); b = cv2.resize(cv2.cvtColor(f0, cv2.COLOR_RGB2GRAY), (90,160)).astype(float)
    corr = float(np.corrcoef(a.ravel(), b.ravel())[0,1])
    def dh(g):
        g = cv2.resize(g.astype(np.uint8), (9,8)); return (g[:,1:] > g[:,:-1]).ravel()
    ham = int((dh(a) != dh(b)).sum())
    hs = [cv2.calcHist([x], [0,1,2], None, [8,8,8], [0,256]*3) for x in (c, f0)]
    hist = float(cv2.compareHist(cv2.normalize(hs[0],None), cv2.normalize(hs[1],None), cv2.HISTCMP_CORREL))
    return dict(cover=cover, gray_corr=round(corr,3), dhash_hamming=ham, color_hist_corr=round(hist,3))

def main():
    ap = argparse.ArgumentParser()
    for k in ('video','asr','out','cover','facts','publish','nobgm','beats'): ap.add_argument('--'+k)
    ap.add_argument('--ai', action='store_true'); ap.add_argument('--skip-ocr', action='store_true')
    a = ap.parse_args(); os.makedirs(os.path.dirname(a.out), exist_ok=True)
    dur, W, H = probe(a.video); asr = json.load(open(a.asr)) if a.asr and os.path.exists(a.asr) else []
    R = dict(video=a.video, duration_s=round(dur,2), resolution=f'{W}x{H}')
    f0 = frame_at(a.video, 0.0); R['frame0'] = frame0_metrics(f0)
    R['frame0_ocr'] = [b['t'] for b in ocr(f0)]
    F = frames(a.video, 2); R['visual'] = visual_change(F, 2)
    F3 = frames(a.video, 4, dur=3.0); R['visual_first3s'] = dict(mean_diff=round(float(np.abs(np.diff(F3.mean(3).astype(np.float32),axis=0)).mean()),2))
    ct = cuts(a.video); R['cuts'] = dict(n=len(ct), per_10s=round(len(ct)/dur*10,2), times=ct,
        max_gap_s=round(float(np.max(np.diff([0]+ct+[dur]))),2), first3s=len([c for c in ct if c<3]))
    if a.skip_ocr: sub, texts = {}, []
    else: sub, texts = subtitle_metrics(a.video, dur)
    R['subtitles'] = sub
    R['first3s_ocr'] = sorted(set(x for t in texts if t['t'] < 3 for x in t['text'].split(' | ') if x))
    R['loudness'] = dict(full=loud(a.video), first3s=loud(a.video, 0, 3))
    on, _, rms = audio_onsets(a.nobgm and False or a.video)
    if a.beats and os.path.exists(a.beats):
        bm = json.load(open(a.beats)); on_b = bm.get('onsets_video_s') or on; src = 'beat_map.json'
    else: on_b, src = on, 'mix_spectral_flux'
    R['beat_sync'] = dict(onset_source=src, **beat_sync(ct, on_b, dur))
    # BGM 是否存在：语音间隙里的能量
    if asr:
        hop_t = 512/22050; tt = np.arange(len(rms))*hop_t
        sp = np.zeros(len(rms), bool)
        for s in asr: sp |= (tt >= s['a']-0.1) & (tt <= s['b']+0.1)
        gap = rms[~sp]; spk = rms[sp]
        db = lambda x: float(20*np.log10(np.median(x)+1e-9)) if len(x) else None
        R['bgm_presence'] = dict(gap_db=round(db(gap),1) if len(gap) else None, speech_db=round(db(spk),1) if len(spk) else None,
                                 gap_share=round(float((~sp).mean()),3))
    R['text'] = text_metrics(asr, dur) if asr else {}
    R['facts'] = fact_metrics(asr, a.facts, texts)
    R['compliance'] = compliance(asr, texts, a.publish, a.ai)
    R['cover_match'] = cover_match(a.cover, f0)
    R['ocr_timeline'] = texts
    json.dump(R, open(a.out,'w'), ensure_ascii=False, indent=1); print('objective ok', a.out)

if __name__ == '__main__': main()
