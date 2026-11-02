#!/workspace/.venv-dy/bin/python
"""BGM 契合度（科技揭秘「哇」向）—— 只读音频，写 out/<id>/bgmfit.json。结论属「特征推断」，需人耳确认。

只有成片混音时：避开人声频段（300–4000 Hz）看 BGM —— 鼓点清晰度（低频/高频打击能量占比）、速度、
开头 3 s 能量、切点踩强拍（±40 ms，对比随机基线）、调式（无人声空隙里的色度，低置信）。
给了 --bgm-stem / --vo-stem 时（如 sfx/mix_meta.json 能还原），还算人声频段信噪比（遮挡人声）。

用法：
  python3 lib/bgmfit.py --video corpus/src/x.mp4 --out out/x/bgmfit.json [--audio pc_proxy/x/audio.flac]
        [--asr corpus/asr/x.json] [--objective out/x/objective.json] [--bgm-stem bgm.wav --vo-stem vo.wav] [--rubric config/rubric.json]
"""
import argparse, json, os, subprocess, sys
import numpy as np

SR = 22050
TARGET = {"tempo": [108, 140], "tempo_soft": [90, 160], "perc_good": 0.35, "perc_bad": 0.15,
          "first3_good_db": 0.0, "first3_bad_db": -6.0, "lift_good": 1.6, "snr_good": 18.0, "snr_bad": 12.0,
          "weights": {"tempo": 0.2, "drums": 0.25, "first3": 0.2, "hits": 0.2, "mode": 0.05, "mask": 0.1}}


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def lin(x, lo, hi):
    return float(np.clip((x - lo) / (hi - lo), 0, 1)) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video"); ap.add_argument("--audio"); ap.add_argument("--out", required=True)
    ap.add_argument("--asr"); ap.add_argument("--objective"); ap.add_argument("--cuts", help="逗号分隔切点秒，缺省读 objective.json")
    ap.add_argument("--bgm-stem"); ap.add_argument("--vo-stem")
    ap.add_argument("--rubric", default=os.path.join(os.path.dirname(__file__), "..", "config", "rubric.json"))
    a = ap.parse_args()
    import librosa
    T = json.loads(json.dumps(TARGET))
    if a.rubric and os.path.exists(a.rubric):
        T.update((json.load(open(a.rubric)).get("bgm_fit") or {}).get("target", {}))
    src = a.audio if a.audio and os.path.exists(a.audio) else (a.bgm_stem or a.video)
    y = load(src); dur = len(y) / SR
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512)); fr = librosa.fft_frequencies(sr=SR, n_fft=2048)
    keep = (fr < 300) | (fr > 4000)            # 避开人声频段
    Sk = S * keep[:, None]
    H, P = librosa.decompose.hpss(Sk)
    perc = float((P ** 2).sum() / ((H ** 2).sum() + (P ** 2).sum() + 1e-9))
    low = S[fr < 200]
    rms_low = np.sqrt((low ** 2).mean(0)) + 1e-9
    tt = librosa.frames_to_time(np.arange(S.shape[1]), sr=SR, hop_length=512)
    music_db = 20 * np.log10(np.sqrt((Sk ** 2).mean(0)) + 1e-9)
    has_bgm = True
    obj = json.load(open(a.objective)) if a.objective and os.path.exists(a.objective) else {}
    bp = obj.get("bgm_presence") or {}
    if bp and bp.get("gap_db") is not None and bp["gap_db"] < -45:
        has_bgm = False
    first3 = float(np.median(music_db[tt < 3]) - np.median(music_db[tt >= 3])) if (tt < 3).any() else 0.0
    oenv = librosa.onset.onset_strength(S=librosa.amplitude_to_db(P + 1e-9), sr=SR, hop_length=512)
    tempo = float(np.atleast_1d((getattr(librosa.feature, "tempo", None) or librosa.beat.tempo)(onset_envelope=oenv, sr=SR, hop_length=512))[0])
    if tempo < 75: tempo *= 2
    thr = np.percentile(oenv, 90)
    pk = librosa.util.peak_pick(oenv, pre_max=3, post_max=3, pre_avg=5, post_avg=5, delta=0.0, wait=4)
    strong = tt[pk[oenv[pk] >= thr]] if len(pk) else np.array([])
    if a.cuts:
        cuts = [float(x) for x in a.cuts.split(",") if x]
    else:
        cuts = (obj.get("cuts") or {}).get("times", [])
    cuts = [c for c in cuts if 0.3 < c < dur - 0.3]
    hits = sum(1 for c in cuts if len(strong) and np.min(np.abs(strong - c)) <= 0.04)
    dens = len(strong) / max(dur, 1e-6)
    chance = dens * 0.08 * len(cuts)
    lift = hits / chance if chance > 0 else 0.0
    # 调式：无人声空隙的色度（低置信）
    mode, mode_conf = None, 0.0
    try:
        asr = json.load(open(a.asr)) if a.asr and os.path.exists(a.asr) else []
        m = np.ones_like(tt, bool)
        for s in asr:
            m &= ~((tt >= s["a"] - 0.05) & (tt <= s["b"] + 0.05))
        C = librosa.feature.chroma_stft(S=H ** 2, sr=SR)
        c = C[:, m].mean(1) if m.sum() > 20 else C.mean(1)
        maj = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        mnr = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
        cm = [np.corrcoef(c, np.roll(maj, k))[0, 1] for k in range(12)]; cn = [np.corrcoef(c, np.roll(mnr, k))[0, 1] for k in range(12)]
        mode = "major" if max(cm) >= max(cn) else "minor"; mode_conf = float(abs(max(cm) - max(cn)))
    except Exception:
        pass
    snr = None
    if a.bgm_stem and a.vo_stem and os.path.exists(a.bgm_stem) and os.path.exists(a.vo_stem):
        b = load(a.bgm_stem); v = load(a.vo_stem); n = min(len(b), len(v))
        def band(x):
            X = np.abs(librosa.stft(x[:n], n_fft=2048, hop_length=512)); return (X[(fr >= 1000) & (fr <= 4000)] ** 2).sum(0)
        eb, ev = band(b), band(v); act = ev > np.percentile(ev, 60)
        snr = float(np.median(10 * np.log10(ev[act] / (eb[act] + 1e-12)))) if act.any() else None
    sc = {}
    lo, hi = T["tempo"]; slo, shi = T["tempo_soft"]
    sc["tempo"] = 100.0 if lo <= tempo <= hi else (lin(tempo, slo, lo) if tempo < lo else 100 - lin(tempo, hi, shi))
    sc["drums"] = lin(perc, T["perc_bad"], T["perc_good"])
    sc["first3"] = lin(first3, T["first3_bad_db"], T["first3_good_db"])
    sc["hits"] = lin(lift, 0.8, T["lift_good"]) if cuts else 50.0
    sc["mode"] = 70.0 if mode is None else (100.0 if mode == "major" else 40.0)
    sc["mask"] = 70.0 if snr is None else lin(snr, T["snr_bad"], T["snr_good"])
    Wt = T["weights"]
    score = sum(Wt[k] * sc[k] for k in Wt) / sum(Wt.values())
    if not has_bgm:
        score = 30.0
    R = {"version": 1, "source": src, "decoded_from": "proxy" if src == a.audio else "original", "has_bgm": has_bgm,
         "tempo_bpm": round(tempo, 1), "perc_ratio_nonspeech": round(perc, 3), "first3s_rel_db": round(first3, 2),
         "strong_onsets_per_s": round(dens, 2), "cut_hits_40ms": hits, "cut_hits_chance": round(chance, 2), "hit_lift": round(lift, 2),
         "mode": mode, "mode_conf": round(mode_conf, 3), "speech_band_snr_db": None if snr is None else round(snr, 1),
         "subscores": {k: round(v, 1) for k, v in sc.items()}, "score": round(score, 1),
         "note": "特征推断（避开人声频段），情绪/版权需人耳确认；目标=科技揭秘「哇」：利落鼓点、前 3 s 有能量、踩切点、不压人声"}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(R, open(a.out, "w"), ensure_ascii=False, indent=1)
    if not os.environ.get("CQ_QUIET"):
        print(json.dumps({k: R[k] for k in ("score", "subscores", "tempo_bpm", "first3s_rel_db", "hit_lift")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
