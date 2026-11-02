#!/workspace/.venv-review/bin/python
"""稳健版逐镜精审：分段（默认 12 s）+ 每段少图 + 超时重试 + 换模型兜底 + 分段缓存 + 自动假阳性校验。
解决 25–62 s 一次塞太多图导致 qoder 超时 / other side closed 的问题。旧的 lib/focus_review.py 不动，照常可用。

用法：
  lib/focus_run.py --id iphone18pro_v2 --video corpus/src/iphone18pro_v2.mp4 [--from 3 --to 62] [--seg 12]
      [--asr corpus/asr/x.json] [--objective out/x/objective.json] [--cutq out/x/cutquality.json] [--design-cuts ShotsV2.tsx]
      [--bgm-note "雨日思绪 99BPM 偏抒情"] [--timeout 300] [--retries 3] [--parallel 2] [--models qoder-flash,qoder-flash-qwen] [--force] [--dry]
产物：out/<id>/focus_run/seg_<a>-<b>.json（每段，带 inputs_hash，命中缓存就跳过）、focus_run.json（合并）、focus_validated.json（校验）
"""
import argparse, concurrent.futures as cf, hashlib, json, os, re, shutil, signal, subprocess, sys, tempfile, time
from PIL import Image, ImageDraw
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.expanduser("~/.local/bin")


def grab(video, t, w):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", video, "-frames:v", "1", "-vf", f"scale={w}:-2", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
    from io import BytesIO
    return Image.open(BytesIO(raw)).convert("RGB") if raw else Image.new("RGB", (w, w * 16 // 9))


def label(im, s):
    d = ImageDraw.Draw(im); d.rectangle([0, 0, 8 * len(s) + 6, 16], fill=(0, 0, 0)); d.text((3, 2), s, fill=(255, 255, 0)); return im


def tile(ims, cols):
    w, h = ims[0].size; rows = (len(ims) + cols - 1) // cols
    out = Image.new("RGB", (w * cols, h * rows), (30, 30, 30))
    for k, im in enumerate(ims): out.paste(im, ((k % cols) * w, (k // cols) * h))
    return out


def run_qoder(model, prompt, imgs, timeout):
    tmp = tempfile.mkdtemp(prefix="fseg_"); names = []
    for f in imgs: shutil.copy(f, tmp); names.append(os.path.basename(f))
    cmd = [os.path.join(BIN, model), "-p"] + sum((["--attachment", n] for n in names), []) + [prompt]
    env = dict(os.environ, PATH=BIN + ":" + os.environ["PATH"])
    p = subprocess.Popen(cmd, cwd=tmp, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)   # 连子进程（qoderclicn）一起杀，避免孤儿进程占住 qoder
        p.communicate(); out, err = "", "timeout"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    J = None
    for m in sorted(re.finditer(r"\{.*\}", out or "", re.S), key=lambda m: -len(m.group(0)))[:1]:
        try: J = json.loads(m.group(0))
        except json.JSONDecodeError:
            try: J = json.loads(re.sub(r",\s*([}\]])", r"\1", m.group(0)))
            except json.JSONDecodeError: J = None
    return J, (out or "")[-3000:], (err or "")[-400:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True); ap.add_argument("--video", required=True)
    ap.add_argument("--from", dest="t0", type=float, default=3.0); ap.add_argument("--to", dest="t1", type=float)
    ap.add_argument("--seg", type=float, default=12.0); ap.add_argument("--asr"); ap.add_argument("--objective"); ap.add_argument("--cutq"); ap.add_argument("--design-cuts")
    ap.add_argument("--bgm-note", default=""); ap.add_argument("--prompt", default=os.path.join(ROOT, "prompts", "focus_seg.md"))
    ap.add_argument("--timeout", type=int, default=300); ap.add_argument("--retries", type=int, default=3); ap.add_argument("--parallel", type=int, default=2)
    ap.add_argument("--models", default="qoder-flash,qoder-flash-qwen"); ap.add_argument("--force", action="store_true"); ap.add_argument("--dry", action="store_true")
    ap.add_argument("--out-dir")
    a = ap.parse_args()
    od = a.out_dir or os.path.join(ROOT, "out", a.id, "focus_run"); os.makedirs(od, exist_ok=True)
    cutq_p = a.cutq or os.path.join(ROOT, "out", a.id, "cutquality.json"); obj_p = a.objective or os.path.join(ROOT, "out", a.id, "objective.json")
    CQ = json.load(open(cutq_p)) if os.path.exists(cutq_p) else {}
    A = json.load(open(a.asr)) if a.asr and os.path.exists(a.asr) else []
    dur = CQ.get("duration_s") or float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.video], capture_output=True, text=True).stdout)
    t1 = min(a.t1 or dur, dur)
    cuts = None
    if a.design_cuts and os.path.exists(a.design_cuts):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import cutquality as C
        cuts, _ = C.parse_design(a.design_cuts)
    if not cuts:
        tr = CQ.get("events", {}).get("transition", [])
        cuts = [0.0] + [t for t in CQ.get("cuts_detected", []) if not any(x["t"] - 0.01 < t <= x["to"] + 0.01 for x in tr)]
    bounds = cuts + [dur]
    # 分段：尽量在切点处断开，每段 ≤ seg 秒
    segs, s = [], a.t0
    while s < t1 - 0.5:
        e = min(t1, s + a.seg)
        if e < t1:
            cand = [c for c in cuts if s + a.seg * 0.6 <= c <= e]
            if cand: e = cand[-1]
        segs.append((round(s, 2), round(e, 2))); s = e
    SS = sorted(CQ.get("style_seq", []), key=lambda x: x["a"])
    def style_at(t):
        cur = "?"
        for x in SS:
            if x["a"] <= t: cur = x["style"]
        return cur
    P = open(a.prompt, encoding="utf-8").read()
    jobs = []
    for (sa, sb) in segs:
        tag = f"{sa:05.1f}-{sb:05.1f}"; d = os.path.join(od, f"seg_{tag}"); os.makedirs(d, exist_ok=True)
        sh = [(k, bounds[k], bounds[k + 1]) for k in range(len(cuts)) if bounds[k + 1] > sa and bounds[k] < sb]
        ims = []
        for k, x, y in sh:
            for t in (x + 0.05, (x + y) / 2, y - 0.05):
                ims.append(label(grab(a.video, max(sa, min(sb, t)), 180), f"#{k+1} {t:.1f}s"))
        tile(ims, 6).save(os.path.join(d, "shots.jpg"), quality=82)
        step = 0.25 if sb - sa <= 8 else 0.5
        ts = [sa + i * step for i in range(int((sb - sa) / step) + 1)]
        tile([label(grab(a.video, t, 135), f"{t:.2f}") for t in ts], 8).save(os.path.join(d, "dense.jpg"), quality=80)
        ev = CQ.get("events", {})
        def inn(x): return x.get("to", x["t"]) >= sa - 0.2 and x["t"] <= sb + 0.2
        lines = ["镜头表（#镜号 起-止 | 风格[脚本分类]）:"] + [f"#{k+1} {x:.2f}-{y:.2f} | {style_at((x + y) / 2)}" for k, x, y in sh]
        lines.append("口播字幕（这些句子画面上都有字幕）:")
        lines += [f"  {s_['a']:.2f}-{s_['b']:.2f} {s_['text']}" for s_ in A if s_["b"] > sa and s_["a"] < sb]
        lines.append("脚本检测（30fps，HSV 直方图区分切点与运动）:")
        lines.append("  真闪帧: " + ("; ".join(f'{x["t"]:.2f}-{x["to"]:.2f}s {x["frames"]}帧' for x in ev.get("flash", []) if inn(x)) or "无"))
        lines.append("  快速运动(不是切点、不是闪帧): " + ("; ".join(f'{x["t"]:.2f}-{x["to"]:.2f}s' for x in ev.get("motion_not_cut", []) if inn(x)) or "无"))
        lines.append("  叠化/划变/冲击闪白(转场，不算闪帧): " + ("; ".join(f'{x["t"]:.2f}s {x.get("kind","")}' for x in ev.get("transition", []) if inn(x)) or "无"))
        lines.append("  实拍↔2D 来回跳: " + ("; ".join(f'{x["t"]:.2f}-{x["to"]:.2f}s {x["pattern"]}' for x in ev.get("pingpong", []) if inn(x)) or "无"))
        lines.append("  画面读数与口播不符: " + ("; ".join(f'{x["t"]:.0f}s {x["kind"]} 口播{x["vo"]} 画面{x["pic"]}' for x in ev.get("mismatch", []) if inn(x)) or "无"))
        if a.bgm_note: lines.append("BGM: " + a.bgm_note)
        ctx = "\n".join(lines)
        prompt = P.replace("{ctx}", ctx).replace("{a}", f"{sa:g}").replace("{b}", f"{sb:g}").replace("{step}", f"{step:g}")
        open(os.path.join(d, "ctx.txt"), "w").write(ctx)
        imgs = [os.path.join(d, "shots.jpg"), os.path.join(d, "dense.jpg")]
        h = hashlib.sha256((prompt + "".join(hashlib.sha256(open(f, "rb").read()).hexdigest() for f in imgs)).encode()).hexdigest()[:16]
        jobs.append(dict(seg=(sa, sb), dir=d, prompt=prompt, imgs=imgs, hash=h, out=os.path.join(od, f"seg_{tag}.json")))
    if a.dry:
        print(json.dumps([{"seg": j["seg"], "dir": j["dir"]} for j in jobs], ensure_ascii=False)); return
    models = a.models.split(",")
    def work(j):
        if not a.force and os.path.exists(j["out"]):
            old = json.load(open(j["out"]))
            if old.get("ok") and old.get("inputs_hash") == j["hash"]:
                return {**old, "cached": True}
        t0 = time.time(); tries = []
        for k in range(a.retries):
            model = models[0] if k < max(1, a.retries - 1) else models[-1]   # 最后一次换兜底模型
            J, raw, err = run_qoder(model, j["prompt"], j["imgs"], a.timeout)
            tries.append({"model": model, "ok": J is not None, "err": err[:200], "s": round(time.time() - t0, 1)})
            if J is not None:
                R = dict(ok=True, seg=j["seg"], model=model, seconds=round(time.time() - t0, 1), tries=tries, inputs_hash=j["hash"], result=J)
                json.dump(R, open(j["out"], "w"), ensure_ascii=False, indent=1); return R
            time.sleep(min(60, 10 * 2 ** k))
        R = dict(ok=False, seg=j["seg"], seconds=round(time.time() - t0, 1), tries=tries, inputs_hash=j["hash"], raw=raw[-2000:])
        json.dump(R, open(j["out"], "w"), ensure_ascii=False, indent=1); return R
    with cf.ThreadPoolExecutor(max_workers=max(1, a.parallel)) as ex:
        res = list(ex.map(work, jobs))
    for r in res: print("seg", r["seg"], "ok" if r["ok"] else "FAIL", r.get("model"), r.get("seconds"), "cached" if r.get("cached") else "", flush=True)
    good = [r for r in res if r["ok"]]
    tot = sum(r["seg"][1] - r["seg"][0] for r in good) or 1
    score = round(sum((r["result"].get("segment_score") or 0) * (r["seg"][1] - r["seg"][0]) for r in good) / tot, 1) if good else None
    M = {"version": 1, "id": a.id, "range": [a.t0, t1], "n_segments": len(res), "ok_segments": len(good),
         "failed": [r["seg"] for r in res if not r["ok"]], "focus_score": score,
         "segment_scores": [{"seg": r["seg"], "score": r["result"].get("segment_score"), "bgm": r["result"].get("bgm")} for r in good],
         "result": {"segments": [r["result"] | {"segment": list(r["seg"])} for r in good]}}
    mp = os.path.join(os.path.dirname(od), "focus_run.json"); json.dump(M, open(mp, "w"), ensure_ascii=False, indent=1)
    vp = os.path.join(os.path.dirname(od), "focus_validated.json")
    cmd = [sys.executable if os.path.exists(sys.executable) else "python3", os.path.join(ROOT, "lib", "focus_validate.py"), "--focus", mp, "--cutq", cutq_p, "--objective", obj_p, "--out", vp]
    if a.asr: cmd += ["--asr", a.asr]
    subprocess.run(cmd)
    print("focus_score", score, "->", mp, vp)


if __name__ == "__main__":
    main()
