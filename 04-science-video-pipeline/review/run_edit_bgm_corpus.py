#!/usr/bin/env python3
"""对整个语料跑 剪辑质量(cutquality) + BGM 契合(bgmfit)。PC 代理优先（pc/proxy/<id>/proxy.mp4、audio.flac），没有就盒上解码原片。
用法: python3 run_edit_bgm_corpus.py [--proxy-dir pc/proxy] [--ids a,b] [--design]   # --design: 有设计切点(corpus 的 design_cuts_from)时一并用
"""
import argparse, json, os, subprocess, sys, time
PYA = "/workspace/.venv-dy/bin/python" if os.path.exists("/workspace/.venv-dy/bin/python") else sys.executable  # bgmfit 需要 librosa
ROOT = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument("--proxy-dir", default=os.path.join(ROOT, "pc", "proxy")); ap.add_argument("--ids"); ap.add_argument("--design", action="store_true"); ap.add_argument("--only", choices=["cut", "bgm"])
a = ap.parse_args()
C = json.load(open(os.path.join(ROOT, "corpus", "corpus.json")))
ids = a.ids.split(",") if a.ids else None
for v in C["videos"]:
    if ids and v["id"] not in ids: continue
    i = v["id"]; od = os.path.join(ROOT, "out", i); os.makedirs(od, exist_ok=True)
    px = os.path.join(a.proxy_dir, i, "proxy.mp4"); pa = os.path.join(a.proxy_dir, i, "audio.flac")
    src = os.path.join(ROOT, v["src"]); asr = os.path.join(ROOT, v["asr"]); obj = os.path.join(od, "objective.json")
    t0 = time.time()
    cmd = [sys.executable, os.path.join(ROOT, "lib", "cutquality.py"), "--video", src, "--out", os.path.join(od, "cutquality.json"), "--asr", asr, "--objective", obj]
    if os.path.exists(px): cmd += ["--proxy", px]
    if a.design and v.get("design_cuts_from"): cmd += ["--design-cuts", os.path.join(ROOT, v["design_cuts_from"]), "--style-truth", os.path.join(ROOT, v["design_cuts_from"])]
    r1 = subprocess.run(cmd, capture_output=True, text=True) if a.only != "bgm" else subprocess.CompletedProcess(cmd, 0, "skip", "")
    cmd = [PYA, os.path.join(ROOT, "lib", "bgmfit.py"), "--video", src, "--out", os.path.join(od, "bgmfit.json"), "--asr", asr, "--objective", obj]
    if os.path.exists(pa): cmd += ["--audio", pa]
    r2 = subprocess.run(cmd, capture_output=True, text=True) if a.only != "cut" else subprocess.CompletedProcess(cmd, 0, "skip", "")
    print(i, "proxy" if os.path.exists(px) else "box", f"{time.time()-t0:.1f}s", "| cut:", (r1.stdout or r1.stderr[-300:]).strip()[:200], "| bgm:", (r2.stdout or r2.stderr[-300:]).strip()[:160], flush=True)
