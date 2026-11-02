#!/usr/bin/env python3
"""Host O pose-swap with host-A v4 (approved) talk motion, ported via sprite_talk.presets.aning_v4.
Hard pose cuts (poses_v2 + poses_kit pose_api.frame: mouth first, eyes last), v5 mouths, blink_v2 blinks.
Motion: one global curve (phase/gate continuous across cuts), amplitude = A v4 x (O head height / A head height)."""
import os, sys, json, subprocess
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = ["/workspace/oss/sprite-talk", os.path.join(HERE, "..", "poses_kit"), HERE, os.path.join(HERE, "v4motion")]
from sprite_talk.mouth import audio_rms, audio_duration, mouth_levels
from sprite_talk.blink import blink_schedule
from sprite_talk.presets import ANING_V4, aning_v4_series, LinearPinWarp
import pose_api as P
from drive_host_o_sample import make_bg
from geom import o_geom, A_HH

FPS, W, H = 30, 1920, 1080
VO = "/workspace/science-studio/hosts/host_d/ai_talking/inputs/vo_intro.mp3"
OUT = os.path.join(HERE, "host_o_swap_v4motion.mp4")
SCHED = [(0.0, 2.2, 'pose_talk_idle'), (2.2, 4.5, 'pose_talk_point'), (4.5, 6.5, 'pose_think'),
         (6.5, 8.5, 'pose_talk_point'), (8.5, 10.0, 'pose_react_surprise'), (10.0, 99.0, 'pose_peace')]
LV = {0: 'X', 1: 'open_s', 2: 'open_l'}
X0 = W - 770 - 80
pose_at = lambda t: next(p for a, b, p in SCHED if a <= t < b)

def main():
    dur = audio_duration(VO); n = int(round(dur * FPS))
    lvl, env = mouth_levels(audio_rms(VO, FPS, dur), n, FPS, None)
    G = {p: o_geom(p) for p in P.list_poses()}
    HH = float(np.mean([g['hh'] for g in G.values()]))           # one amplitude -> continuous across cuts
    dx, dy, gate = aning_v4_series(n, HH, env > 0.08, FPS)
    blinks = blink_schedule(n, FPS, seed=7)
    alpha = {p: G[p]['rgba'][..., 3] for p in G}
    warps = {p: LinearPinWarp(alpha[p].shape, G[p]['chin'] - ANING_V4['rigid_above_chin'] * G[p]['hh'], 1079.0) for p in G}
    bg = np.array(make_bg().convert('RGB')).astype(np.float32)
    proc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                             "-i", "-", "-i", VO, "-t", f"{dur:.3f}", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                             "-c:a", "aac", "-b:a", "128k", "-shortest", OUT], stdin=subprocess.PIPE)
    for f in range(n):
        p = pose_at(f / FPS)
        rgb = np.array(P.frame(p, LV[int(lvl[f])], blinks.get(f, 0)))
        im = warps[p](np.dstack([rgb, alpha[p]]), dx[f], dy[f])
        a = im[..., 3:4].astype(np.float32) / 255
        fr = bg.copy(); reg = fr[:, X0:X0 + 770]
        fr[:, X0:X0 + 770] = im[..., :3] * a + reg * (1 - a)
        proc.stdin.write(fr.astype(np.uint8).tobytes())
    proc.stdin.close(); proc.wait()
    meta = dict(mp4=OUT, vo=VO, dur=dur, n_frames=n, schedule=SCHED, preset='aning_v4', head_hh_px=round(HH, 1),
                scale_vs_hostA=round(HH / A_HH, 4), AX_px=round(ANING_V4['ax'] * HH, 2), AY_px=round(ANING_V4['ay'] * HH, 2),
                rigid_y={p: round(w.rigid_y, 1) for p, w in warps.items()}, pin_y=1079,
                blink_frames=sorted(int(k) for k, v in blinks.items() if v == 2), frac_open=round(float((lvl > 0).mean()), 3))
    np.save(os.path.join(HERE, 'v4motion', 'o_v4_curve.npy'), np.stack([dx, dy, gate]))
    json.dump(meta, open(os.path.join(HERE, 'swap_v4motion_meta.json'), 'w'), indent=1)
    print(json.dumps(meta))

if __name__ == '__main__':
    main()
