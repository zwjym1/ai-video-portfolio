#!/usr/bin/env python3
"""剪辑质量（edit quality）客观检测 —— 独立脚本，不改动任何旧产物，只写 out/<id>/cutquality.json。

扣分项（重点看 3 s 之后）：
  闪帧      真切点之间 ≤ 7 帧（30fps 下 ≤0.233 s）的碎镜头
  镜头内碎切 不在设计切点上的额外切点（给 --design-cuts 时）；否则为 1.5 s 内 ≥3 个切点的「碎切簇」
  实拍↔2D 来回跳 A-B-A（中间镜头 <2 s、风格与两侧都不同、两侧相同）
  明暗翻转  切点两侧平均亮度差 >35%，1.2 s 内又翻回去
  画面口播对不上 OCR 到的画面 f 值不在口播 ±1.5 s 内提到的 f 值里；UI 冲突词表（口播说「光圈」画面却是白平衡面板）
真切点 vs 快速运动：用 HSV 直方图相关性（运动时直方图几乎不变，切点时会断崖）区分，只有两者都跳才算切点。

用法：
  python3 lib/cutquality.py --video corpus/src/x.mp4 --out out/x/cutquality.json \
      [--proxy pc_proxy/x/proxy.mp4] [--asr corpus/asr/x.json] [--objective out/x/objective.json] \
      [--design-cuts ShotsV2.tsx|cuts.json] [--style-truth ShotsV2.tsx] [--rubric config/rubric.json]
  --proxy 给 PC 上 pc/pc_proxy.ps1 产出的 180x320 代理；缺省/不存在就在盒上直接解码原片（回退）。
"""
import argparse, json, os, re, subprocess, sys, math
import numpy as np

W, H, FPS = 144, 256, 30

DEFAULT_CFG = {
    "flash_max_frames": 7, "focus_from_s": 3.0,
    "cut_hist_d": 0.30, "cut_pix_d": 10.0, "cut_ratio": 3.0,
    "design_tol_s": 0.12, "cluster_win_s": 1.5, "cluster_n": 3,
    "pingpong_max_s": 2.0, "lumflip_rel": 0.35, "lumflip_back_s": 1.2,
    "fval_window": [-1.5, 1.0],
    "ui_conflicts": [
        {"vo": "光圈", "bad": "WH?I?TE.{0,3}B.{0,2}[AE]{1,2}L?.{0,2}ANCE|白平衡", "good": "APERTURE|[fƒF]\\s?/?\\s?\\d"}
    ],
    "penalty": {"flash": [8, 32], "intra": [2, 16], "cluster": [5, 25], "pingpong": [6, 24],
                 "lumflip": [3, 12], "mismatch": [8, 24], "style_switch_per_min_over": [12.0, 1.0, 10]},
    "pre3s_weight": 0.5,
}


def load_cfg(rubric):
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    if rubric and os.path.exists(rubric):
        r = json.load(open(rubric))
        for k, v in (r.get("edit_quality") or {}).get("detector", {}).items():
            cfg[k] = v
    return cfg


def decode(path, w=W, h=H, fps=FPS):
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={fps},scale={w}:{h}:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(raw) // (w * h * 3)
    return np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)


def hsv_hist(fr):
    x = fr.astype(np.float32) / 255.0
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    mx, mn = x.max(-1), x.min(-1); d = mx - mn + 1e-6
    hh = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) / 6.0
    s = np.where(mx > 0, (mx - mn) / (mx + 1e-6), 0); v = mx
    hi = np.clip((hh * 16).astype(int), 0, 15); si = np.clip((s * 4).astype(int), 0, 3); vi = np.clip((v * 8).astype(int), 0, 7)
    idx = (hi * 4 + si) * 8 + vi
    hist = np.bincount(idx.ravel(), minlength=512).astype(np.float64)
    return hist / hist.sum()


def corr(a, b):
    a = a - a.mean(); b = b - b.mean()
    return float((a * b).sum() / (math.sqrt((a * a).sum() * (b * b).sum()) + 1e-12))


def style_feats(fr):
    """实拍 vs 2D 示意动画（中间 12%–72% 画面，避开标题与字幕）：
    实拍有大量「柔和渐变」(梯度 2–8)；2D 动画多是纯平色块 + 硬边。
    返回 [zero(梯度<0.5 占比), weak(柔和渐变占比), edge(硬边占比)]。
    在 iPhone18Pro v2 的 36 个设计镜头（ShotsV2.tsx 的 REAL 真值）上留一法准确率 94%。"""
    hh = fr.shape[0]
    g = fr.astype(np.float32).mean(-1)[int(hh * .12): int(hh * .72)]
    gy, gx = np.gradient(g); mag = np.hypot(gx, gy)
    return [float((mag < 0.5).mean()), float(((mag > 2) & (mag < 8)).mean()), float((mag > 20).mean())]


def parse_design(path):
    if not path or not os.path.exists(path):
        return None, None
    s = open(path, encoding="utf-8").read()
    if path.endswith(".json"):
        j = json.load(open(path)); return j.get("cuts"), set(j.get("real", [])) if j.get("real") is not None else None
    m = re.search(r"CUTS\s*=\s*\[([^\]]*)\]", s)
    cuts = [float(x) for x in re.findall(r"[\d.]+", m.group(1))] if m else None
    m2 = re.search(r"REAL\s*=\s*new Set\(\[([^\]]*)\]\)", s)
    real = set(int(x) for x in re.findall(r"\d+", m2.group(1))) if m2 else None
    return cuts, real


def detect_cuts(F, cfg):
    sub = F[:, int(H * 0.06): int(H * 0.74)]
    hists = [hsv_hist(f) for f in sub]
    g = sub.astype(np.float32).mean(-1)
    dh = np.array([0.0] + [1 - corr(hists[i], hists[i - 1]) for i in range(1, len(F))])
    dp = np.array([0.0] + [float(np.abs(g[i] - g[i - 1]).mean()) for i in range(1, len(F))])
    cuts, motion = [], []
    for i in range(1, len(F)):
        lo, hi = max(1, i - 6), min(len(F), i + 7)
        nb = np.concatenate([dh[lo:i], dh[i + 1:hi]])
        base = float(np.median(nb)) if len(nb) else 0.0
        if dh[i] > cfg["cut_hist_d"] and dp[i] > cfg["cut_pix_d"] and dh[i] > cfg["cut_ratio"] * base:
            cuts.append(i)
        elif dp[i] > 18 and dh[i] < 0.15:
            motion.append(i)
    return cuts, motion, dh, dp


def mismatch(asr, objective, cfg):
    out = []
    if not asr or not objective:
        return out
    segs = [s for s in asr if s.get("text")]
    fre = re.compile(r"(?:[fƒF]\s*/?\s*)(\d(?:\.\d{1,2})?)")
    def vo_text(t, a, b):
        return " ".join(s["text"] for s in segs if s["b"] >= t + a and s["a"] <= t + b)
    def is_sub(frag, t):
        import difflib
        for s in segs:
            if s["b"] >= t - 2 and s["a"] <= t + 2:
                if frag in s["text"] or difflib.SequenceMatcher(None, frag, s["text"]).ratio() > 0.6:
                    return True
        return False
    for e in objective.get("ocr_timeline", []):
        t = float(e["t"]); frags = [x.strip() for x in e.get("text", "").split("|") if x.strip()]
        pic = [f for f in frags if not is_sub(f, t) and not re.match(r"^(画面|样张|示意|素材|来源)", f)]
        vt = vo_text(t, *cfg["fval_window"])
        vo_f = set(float(x) for x in fre.findall(vt))
        ui = re.search(cfg.get("ui_tokens", "APERTURE|AUTO|AWB|ISO|EV\\b"), " ".join(pic))
        pic_f = set(float(x) for f in pic for x in fre.findall(f)) if ui else set()
        if vo_f and pic_f and not (pic_f & vo_f):
            out.append({"t": t, "kind": "f值不符", "vo": sorted(vo_f), "pic": sorted(pic_f), "frags": pic[:6]})
            continue
        vnow = vo_text(t, -0.5, 0.5)
        for rule in cfg["ui_conflicts"]:
            if rule["vo"] in vnow:
                ptxt = " ".join(pic)
                if re.search(rule["bad"], ptxt) and not re.search(rule["good"], ptxt):
                    out.append({"t": t, "kind": "UI冲突", "vo": vnow, "pic": pic[:6]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--proxy"); ap.add_argument("--asr"); ap.add_argument("--objective")
    ap.add_argument("--design-cuts"); ap.add_argument("--style-truth"); ap.add_argument("--rubric", default=os.path.join(os.path.dirname(__file__), "..", "config", "rubric.json"))
    ap.add_argument("--style-model", default=os.path.join(os.path.dirname(__file__), "..", "config", "style_model.json"))
    a = ap.parse_args()
    cfg = load_cfg(a.rubric)
    src = a.proxy if a.proxy and os.path.exists(a.proxy) else a.video
    F = decode(src); n = len(F); dur = n / FPS
    cuts, motion, dh, dp = detect_cuts(F, cfg)
    ct = [c / FPS for c in cuts]
    bounds = [0] + cuts + [n]
    shots = []
    for k in range(len(bounds) - 1):
        a0, b0 = bounds[k], bounds[k + 1]
        mid = F[(a0 + b0) // 2]
        shots.append({"i": k, "a": round(a0 / FPS, 3), "b": round(b0 / FPS, 3), "frames": b0 - a0,
                      "luma": round(float(F[a0:b0:3].mean()), 1), "feat": [round(x, 4) for x in style_feats(mid)]})
    design, real = parse_design(a.design_cuts)
    _, truth = parse_design(a.style_truth) if a.style_truth else (None, None)
    # 风格分类：优先用标定好的 style_model.json（逻辑回归），没有就用经验阈值
    wmod = None
    if os.path.exists(a.style_model):
        wmod = json.load(open(a.style_model))
    def p2d(f):
        if wmod:
            z = wmod["b"] + sum(w * (x - m) / s for w, x, m, s in zip(wmod["w"], f, wmod["mu"], wmod["sd"]))
            return 1 / (1 + math.exp(-z))
        return 0.0 if f[1] > 0.13 else 1.0
    for s in shots:
        s["p2d"] = round(p2d(s["feat"]), 3); s["style"] = "2D" if s["p2d"] >= 0.5 else "实拍"
    # 风格序列：给了设计切点就按设计镜头算（避免碎镜头干扰），否则按检测镜头
    if design:
        dsh = []
        dd = design + [dur]
        for k in range(len(design)):
            ss = [s for s in shots if s["a"] < dd[k + 1] and s["b"] > dd[k]]
            ts = np.linspace(dd[k] + 0.1, max(dd[k] + 0.1, dd[k + 1] - 0.1), 3)
            f = list(np.median([style_feats(F[min(n - 1, int(t * FPS))]) for t in ts], 0)); p = p2d(f)
            dsh.append({"i": k, "a": dd[k], "b": dd[k + 1], "style": "2D" if p >= 0.5 else "实拍", "p2d": round(p, 3), "feat": [round(x, 4) for x in f]})
        seq = dsh
    else:
        seq = [s for s in shots if s["frames"] > cfg["flash_max_frames"]]
    style_check = None
    if truth is not None and design:
        ok = sum((s["style"] == "实拍") == (s["i"] in truth) for s in seq)
        style_check = {"n": len(seq), "correct": ok, "acc": round(ok / len(seq), 3),
                       "wrong": [s["i"] for s in seq if (s["style"] == "实拍") != (s["i"] in truth)]}
    ev = {"flash": [], "intra": [], "cluster": [], "pingpong": [], "lumflip": [], "mismatch": [], "motion_not_cut": []}
    fm = cfg["flash_max_frames"]
    def is_transition(s):
        """碎镜头若每帧都≈ 前一镜末帧 A、后一镜首帧 B、常量（闪白/压黑）的线性组合，就是叠化/闪白转场，不算闪帧。"""
        a0, b0 = int(round(s["a"] * FPS)), int(round(s["b"] * FPS))
        if a0 < 1 or b0 >= n: return False
        A = F[a0 - 1].astype(np.float32).ravel(); B = F[b0].astype(np.float32).ravel()
        X = np.stack([A, B, np.full_like(A, 255.0)], 1)
        ref = float(np.abs(A - B).mean()) + 1e-6
        # 擦除/划变：每个像素要么像 A 要么像 B
        def wipe_ok(j):
            M = F[j].astype(np.float32).ravel(); dA = np.abs(M - A); dB = np.abs(M - B)
            fa = float(((dA < 12) & (dB > 30)).mean()); fb = float(((dB < 12) & (dA > 30)).mean())
            return float(np.minimum(dA, dB).mean()) < 0.3 * ref and fa > 0.1 and fb > 0.1
        if all(wipe_ok(j) for j in range(a0, b0)): return "wipe"
        # 同一画面的冲击闪白/压暗特效：前后两帧几乎同一画面，中间帧≈ A 的整体增益+偏移
        if ref < 14:
            ok = True
            for j in range(a0, b0):
                M = F[j].astype(np.float32).ravel(); Xa = np.stack([A, np.ones_like(A)], 1)
                c, *_ = np.linalg.lstsq(Xa, M, rcond=None)
                if float(np.abs(Xa @ c - M).mean()) > 18: ok = False; break
            if ok: return "impact_flash"
        cs = []
        for j in range(a0, b0):
            M = F[j].astype(np.float32).ravel()
            c, *_ = np.linalg.lstsq(X, M, rcond=None)
            if float(np.abs(X @ c - M).mean()) > 0.35 * ref: return False
            cs.append(c)
        # 真过渡：第一帧还带着前一镜（A 系数 ≥0.15）、最后一帧已带后一镜（B 系数 ≥0.15）；
        # 一上来就是「变暗/变色的 B」（如 v2 4.567 s 的 3 帧暗红头）= 硬切闪帧，不算过渡
        return "dissolve" if (cs[0][0] >= 0.15 and cs[-1][1] >= 0.15) else False
    ev["transition"] = []
    for s in shots:
        if s["frames"] <= fm and s["a"] > 0.05 and s["b"] < dur - 0.05:
            kind = is_transition(s)
            if kind:
                ev["transition"].append({"t": s["a"], "to": s["b"], "frames": s["frames"], "kind": kind}); continue
            if ev["flash"] and s["a"] - ev["flash"][-1]["to"] <= 0.5:   # 连在一起的碎镜头合并成一处
                ev["flash"][-1]["to"] = s["b"]; ev["flash"][-1]["frames"] += s["frames"]; ev["flash"][-1]["n"] += 1
            else:
                ev["flash"].append({"t": s["a"], "to": s["b"], "frames": s["frames"], "n": 1})
    def in_flash(t):
        return any(f["t"] - 0.01 <= t <= f["to"] + 0.01 for f in ev["flash"])
    if design:
        for t in ct:
            if min(abs(t - d) for d in design) > cfg["design_tol_s"] and not in_flash(t):   # 已记为闪帧的不重复扣
                ev["intra"].append({"t": round(t, 3)})
    else:
        tr = ev["transition"]
        ct = [t for t in ct if not any(x["t"] - 0.01 < t <= x["to"] + 0.01 for x in tr)]   # 过渡段只算一个切点
        i = 0
        while i < len(ct):
            j = i
            while j + 1 < len(ct) and ct[j + 1] - ct[i] <= cfg["cluster_win_s"]:
                j += 1
            if j - i + 1 >= cfg["cluster_n"] and not any(f["t"] - 0.2 <= ct[j] and ct[i] <= f["to"] + 0.2 for f in ev["flash"]):
                ev["cluster"].append({"t": round(ct[i], 3), "to": round(ct[j], 3), "n": j - i + 1}); i = j + 1
            else:
                i += 1
    for k in range(1, len(seq) - 1):
        A, B, C = seq[k - 1], seq[k], seq[k + 1]
        if A["style"] == C["style"] != B["style"] and (B["b"] - B["a"]) < cfg["pingpong_max_s"]:
            ev["pingpong"].append({"t": round(B["a"], 3), "to": round(B["b"], 3), "pattern": f'{A["style"]}-{B["style"]}-{C["style"]}'})
    switches = sum(seq[k]["style"] != seq[k - 1]["style"] for k in range(1, len(seq)))
    L = [s for s in shots if s["frames"] > 2]
    for k in range(1, len(L) - 1):
        l0, l1, l2 = L[k - 1]["luma"], L[k]["luma"], L[k + 1]["luma"]
        if abs(l1 - l0) / max(l0, l1, 1) > cfg["lumflip_rel"] and abs(l2 - l1) / max(l1, l2, 1) > cfg["lumflip_rel"] \
           and (l1 - l0) * (l2 - l1) < 0 and (L[k]["b"] - L[k]["a"]) <= cfg["lumflip_back_s"] and not in_flash(L[k]["a"]):
            ev["lumflip"].append({"t": L[k]["a"], "to": L[k]["b"], "luma": [l0, l1, l2]})
    asr = json.load(open(a.asr)) if a.asr and os.path.exists(a.asr) else None
    obj = json.load(open(a.objective)) if a.objective and os.path.exists(a.objective) else None
    mm = []
    for e in mismatch(asr, obj, cfg):          # 连续秒合并成一处
        if mm and e["t"] - mm[-1]["to"] <= 1.01 and e["kind"] == mm[-1]["kind"]:
            mm[-1]["to"] = e["t"]
        else:
            e["to"] = e["t"]; mm.append(e)
    ev["mismatch"] = mm
    # 运动段（帧差大但直方图稳定）——给假阳性校验器用：这些时刻的「快闪」多半是运动不是切点
    seg = []
    for m in motion:
        t = m / FPS
        if seg and t - seg[-1][1] <= 0.2:
            seg[-1][1] = t
        else:
            seg.append([t, t])
    ev["motion_not_cut"] = [{"t": round(x, 3), "to": round(y, 3)} for x, y in seg if y - x >= 0.1]
    P, f3 = cfg["penalty"], cfg["focus_from_s"]
    def pen(kind, items):
        per, cap = P[kind]
        tot = sum(per * (1 + 0.25 * (it.get("n", 1) - 1)) * (1.0 if it["t"] >= f3 else cfg["pre3s_weight"]) for it in items)
        return min(cap, tot)
    ded = {k: round(pen(k, ev[k]), 2) for k in ("flash", "intra", "cluster", "pingpong", "lumflip", "mismatch")}
    spm = switches / max(dur / 60, 1e-6)
    thr, per, cap = P["style_switch_per_min_over"]
    ded["style_switch"] = round(min(cap, (spm - thr) * per), 2) if spm > thr else 0.0
    score = max(0.0, 100 - sum(ded.values()))
    after3 = {k: sum(1 for it in ev[k] if it["t"] >= f3) for k in ("flash", "intra", "cluster", "pingpong", "lumflip", "mismatch")}
    R = {"version": 1, "video": a.video, "decoded_from": "proxy" if src != a.video else "original", "duration_s": round(dur, 2),
         "n_cuts_detected": len(cuts), "cuts_detected": [round(t, 3) for t in ct], "design_cuts": design,
         "shots_per_10s": round(len(shots) / dur * 10, 2), "style_switches": switches, "style_switch_per_min": round(spm, 2),
         "style_seq": [{"i": s["i"], "a": round(s["a"], 2), "style": s["style"], "p2d": s["p2d"]} for s in seq],
         "style_check": style_check, "events": ev, "after3s_counts": after3, "deductions": ded, "score": round(score, 1)}
    if design:
        hit = sum(1 for d in design[1:] if any(abs(d - t) <= cfg["design_tol_s"] for t in ct))
        R["design_recall"] = round(hit / max(1, len(design) - 1), 3)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(R, open(a.out, "w"), ensure_ascii=False, indent=1)
    if not os.environ.get("CQ_QUIET"):
        print(json.dumps({k: R[k] for k in ("score", "deductions", "after3s_counts", "n_cuts_detected", "style_switches", "style_check", "design_recall") if k in R}, ensure_ascii=False))
    return R


if __name__ == "__main__":
    main()
