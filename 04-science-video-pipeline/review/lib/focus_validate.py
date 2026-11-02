#!/usr/bin/env python3
"""逐镜精审结果的假阳性自动校验 —— 拿 qoder 的说法去对客观检测（cutquality / objective / ASR）。

查的说法：
  闪帧/快闪（含「23 处快闪」这类计数）→ 对 cutquality 的 flash 事件；落在 motion_not_cut / transition 里 → 判「运动/转场，不是闪帧」
  没有字幕/字幕跟不上 → 对 ASR 字幕时间 + OCR 第 t 秒是否读到字幕文字
  画面与口播矛盾 → 对 cutquality 的 mismatch 事件（找不到只记「未证实」，不删）
  实拍/2D 割裂、风格断层 → 对 pingpong / 风格序列切换
  时间超出片长或超出本段 → 无效
兼容两种输入：旧 focus_review.py 的 {ok,result:{shots,personas,fixes}}，和 focus_run.py 的合并结果。
用法: python3 lib/focus_validate.py --focus out/x/focus/focus_a.json [--focus ...] --cutq out/x/cutquality.json \
        --objective out/x/objective.json --asr corpus/asr/x.json --out out/x/focus_validated.json
"""
import argparse, json, os, re

NUM = re.compile(r"\d+(?:\.\d+)?")
RX = {
    "flash": re.compile(r"快闪|闪帧|碎闪|连闪|闪烁|闪白|快切闪"),
    "nosub": re.compile(r"没有?字幕|无字幕|缺字幕|字幕(?:跟不上|缺失|没出|不见)|看不到字幕"),
    "mismatch": re.compile(r"矛盾|对不上|不符|不一致|出戏|货不对板|画面.{0,6}(?:口播|配音|字幕)|(?:口播|配音|字幕).{0,6}画面"),
    "style": re.compile(r"风格断层|割裂|实拍.{0,4}(?:动画|2D)|(?:动画|2D).{0,4}实拍|来回跳"),
}
COUNT = re.compile(r"(\d+)\s*(?:处|次|帧|下)\S{0,4}(?:快闪|闪)")


def trange(x, default=None):
    if x is None: return default
    if isinstance(x, (int, float)): return (float(x), float(x))
    v = [float(n) for n in NUM.findall(str(x))]
    if not v: return default
    return (min(v[:2]), max(v[:2]))


def overlap(r, a, b, tol):
    return r[0] - tol <= b and a <= r[1] + tol


def claims_of(J, src):
    out = []
    R = J.get("result", J) if isinstance(J, dict) else {}
    segs = R.get("segments") or [R]
    for S in segs:
        seg = trange(S.get("segment")) if S.get("segment") else None
        for s in S.get("shots", []) or []:
            txt = " ".join(str(s.get(k, "")) for k in ("rhythm", "note", "occlusion", "verdict"))
            for it in s.get("issues", []) or []:
                txt += " " + str(it.get("type", "")) + " " + str(it.get("note", ""))
            out.append({"src": src, "where": f"shot#{s.get('no', s.get('i', '?'))}", "t": trange(s.get("t"), seg), "text": txt,
                        "flags": {"flash": s.get("flash") is True, "style": s.get("style_jump") is True,
                                  "mismatch": isinstance(s.get("match"), (int, float)) and s.get("match") <= 2}, "seg": seg})
        for f in S.get("fixes", []) or []:
            out.append({"src": src, "where": "fix", "t": trange(f.get("t"), seg), "text": f"{f.get('action','')} {f.get('why','')}", "flags": {}, "seg": seg,
                        "priority": f.get("priority")})
        for p in S.get("personas", []) or []:
            out.append({"src": src, "where": f"persona:{p.get('id')}", "t": trange(p.get("swipe_at_s"), seg), "text": str(p.get("why", "")), "flags": {}, "seg": seg})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--focus", action="append", required=True); ap.add_argument("--cutq"); ap.add_argument("--objective"); ap.add_argument("--asr")
    ap.add_argument("--out", required=True); ap.add_argument("--duration", type=float)
    a = ap.parse_args()
    CQ = json.load(open(a.cutq)) if a.cutq and os.path.exists(a.cutq) else {}
    O = json.load(open(a.objective)) if a.objective and os.path.exists(a.objective) else {}
    A = json.load(open(a.asr)) if a.asr and os.path.exists(a.asr) else []
    dur = a.duration or CQ.get("duration_s") or O.get("duration_s") or 1e9
    ev = CQ.get("events", {})
    flashes, motion, trans = ev.get("flash", []), ev.get("motion_not_cut", []), ev.get("transition", [])
    mism, pp = ev.get("mismatch", []), ev.get("pingpong", [])
    seq = CQ.get("style_seq", [])
    switches = [seq[k]["a"] for k in range(1, len(seq)) if seq[k]["style"] != seq[k - 1]["style"]]
    ocr = {int(e["t"]): e.get("text", "") for e in O.get("ocr_timeline", [])}
    def sub_present(r):
        hit_asr = [s for s in A if s.get("b", 0) >= r[0] - 0.3 and s.get("a", 0) <= r[1] + 0.3]
        if not hit_asr: return None, "这段没有口播，本来就无字幕"
        seen = 0
        for s in hit_asr:
            core = re.sub(r"[\s，。？！,.?!]", "", s["text"])[:4]
            for t in range(int(s["a"]), int(s["b"]) + 1):
                if core and core in re.sub(r"\s", "", ocr.get(t, "")): seen += 1; break
        if seen: return True, f"ASR 有 {len(hit_asr)} 句、OCR 在画面里读到其中 {seen} 句的字幕文字"
        return (True if (O.get("subtitles") or {}).get("text_frame_share", 0) > 0.9 else None), "OCR 未逐句对上，但全片 90% 以上帧有字幕"
    res = []
    for path in a.focus:
        J = json.load(open(path))
        for c in claims_of(J, os.path.basename(path)):
            r, txt = c["t"], c["text"]
            if r is None: continue
            checks = []
            if r[0] > dur + 0.5 or (c["seg"] and not overlap(c["seg"], r[0], r[1], 1.0)):
                checks.append(("time", "invalid", f"时间 {r} 超出片长/本段"))
            if c["flags"].get("flash") or RX["flash"].search(txt):
                fl = [f for f in flashes if overlap(r, f["t"], f["to"], 0.4)]
                mo = [m for m in motion if overlap(r, m["t"], m["to"], 0.4)]
                tr = [x for x in trans if overlap(r, x["t"], x["to"], 0.4)]
                m = COUNT.search(txt); claimed = int(m.group(1)) if m else None
                if fl:
                    fl = [f for f in fl if overlap(r, f["t"], f["to"], 0.0)] or fl
                    nfr = sum(f["frames"] for f in fl)
                    st = "confirmed" if not claimed or claimed <= max(3, nfr) * 1.5 else "overstated"
                    checks.append(("flash", st, f"实测 {len(fl)} 处闪帧（共 {nfr} 帧：" + "、".join(f'{f["t"]:.2f}–{f["to"]:.2f}s' for f in fl) + "）" + (f"；说的 {claimed} 处是把运动也算进去了" if st == "overstated" else "")))
                elif mo or tr:
                    checks.append(("flash", "false_positive", "不是闪帧：" + ("、".join(f'{x["t"]:.2f}–{x["to"]:.2f}s 快速运动' for x in mo) + " " + "、".join(f'{x["t"]:.2f}s {x.get("kind","转场")}' for x in tr)).strip()))
                elif CQ:
                    checks.append(("flash", "false_positive", "该时段未检出闪帧（30fps 直方图切点检测）"))
            if RX["nosub"].search(txt):
                p, why = sub_present(r)
                checks.append(("nosub", "false_positive" if p else "unverified", why))
            if c["flags"].get("mismatch") or RX["mismatch"].search(txt):
                mm = [x for x in mism if overlap(r, x["t"], x.get("to", x["t"]), 1.5)]
                checks.append(("mismatch", "confirmed" if mm else "unverified", ("脚本也查到：" + "；".join(f'{x["t"]:.0f}s {x["kind"]}' for x in mm)) if mm else "脚本没查到对应的 f 值/UI 冲突，需人看"))
            if c["flags"].get("style") or RX["style"].search(txt):
                ok = [x for x in pp if overlap(r, x["t"], x["to"], 0.5)] or [t for t in switches if r[0] - 0.5 <= t <= r[1] + 0.5]
                checks.append(("style", "confirmed" if ok else "unverified", "风格分类器在此处有实拍↔2D 切换" if ok else "风格分类器没看到切换"))
            if checks:
                res.append({**{k: c[k] for k in ("src", "where", "text")}, "t": r, "checks": [{"type": t, "status": s, "evidence": e} for t, s, e in checks]})
    n = sum(len(x["checks"]) for x in res)
    fp = sum(1 for x in res for c in x["checks"] if c["status"] in ("false_positive", "invalid"))
    ov = sum(1 for x in res for c in x["checks"] if c["status"] == "overstated")
    conf = sum(1 for x in res for c in x["checks"] if c["status"] == "confirmed")
    R = {"version": 1, "inputs": a.focus, "n_checks": n, "confirmed": conf, "false_positive": fp, "overstated": ov,
         "unverified": n - fp - ov - conf, "precision_est": round(conf / max(1, conf + fp), 3), "claims": res,
         "rule": "false_positive/invalid 的说法不进返修单、不扣分；overstated 按实测数改写；unverified 保留但标「需人看」"}
    json.dump(R, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: R[k] for k in ("n_checks", "confirmed", "false_positive", "overstated", "unverified", "precision_est")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
