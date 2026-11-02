#!/usr/bin/env python3
"""Host O pose-swap sample: hard pose cuts + sprite-talk bottom-anchored bob/sway on whichever pose is showing
+ pose_api mouths (3-level volume) + scheduled blinks (half-closed-closed-half, blink_v2 face-edit eyes)."""
import os, sys, json, subprocess
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/workspace/oss/sprite-talk"); sys.path.insert(0, os.path.join(HERE, "..", "poses_kit")); sys.path.insert(0, HERE)
from sprite_talk.warp import BodyWarp
from sprite_talk.curves import GENERIC_LOOP, bob_series
from sprite_talk.mouth import audio_rms, audio_duration, mouth_levels
from sprite_talk.blink import blink_schedule
import pose_api as P
from drive_host_o_sample import make_bg

FPS, W, H = 30, 1920, 1080
PIV, DY_GAIN, AMP = 0.355, 0.75, 1.0
VO = "/workspace/science-studio/hosts/host_d/ai_talking/inputs/vo_intro.mp3"
OUT = os.path.join(HERE, "host_o_posekit_swap_sample.mp4")
SCHED = [(0.0, 2.2, 'pose_talk_idle'), (2.2, 4.5, 'pose_talk_point'), (4.5, 6.5, 'pose_think'),
         (6.5, 8.5, 'pose_talk_point'), (8.5, 10.0, 'pose_react_surprise'), (10.0, 99.0, 'pose_peace')]
LV = {0: 'X', 1: 'open_s', 2: 'open_l'}

def pose_at(t):
    return next(p for a, b, p in SCHED if a <= t < b)

def main():
    dur = audio_duration(VO); n = int(round(dur * FPS))
    lvl, env = mouth_levels(audio_rms(VO, FPS, dur), n, FPS, None)
    talking = env > 0.08
    ux, uy = bob_series(n, 1.0, GENERIC_LOOP, FPS, AMP, DY_GAIN, talking)  # per unit head height; phase continuous across cuts
    blinks = blink_schedule(n, FPS, seed=7)
    alpha = {p: np.array(Image.open(os.path.join(HERE, '..', 'poses_kit', P.REG[p]['img'])).convert('RGBA'))[..., 3] for p in P.list_poses()}
    warps = {p: BodyWarp.for_sprite(np.dstack([np.zeros(alpha[p].shape + (3,), np.uint8), alpha[p]]), piv_ratio=PIV) for p in alpha}
    bg = np.array(make_bg().convert('RGB')).astype(np.float32)
    X0 = W - 770 - 80
    proc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                             "-i", "-", "-i", VO, "-t", f"{dur:.3f}", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                             "-c:a", "aac", "-b:a", "128k", "-shortest", OUT], stdin=subprocess.PIPE)
    log = []
    for f in range(n):
        p = pose_at(f / FPS); wp = warps[p]; hh = wp.head_height
        rgb = np.array(P.frame(p, LV[int(lvl[f])], blinks.get(f, 0)))
        im = wp(np.dstack([rgb, alpha[p]]), ux[f] * hh, uy[f] * hh)
        a = im[..., 3:4].astype(np.float32) / 255
        fr = bg.copy(); reg = fr[:, X0:X0 + 770]
        fr[:, X0:X0 + 770] = im[..., :3] * a + reg * (1 - a)
        proc.stdin.write(fr.astype(np.uint8).tobytes())
        log.append((p, round(float(ux[f] * hh), 2), round(float(uy[f] * hh), 2), blinks.get(f, 0)))
    proc.stdin.close(); proc.wait()
    meta = dict(mp4=OUT, vo=VO, dur=dur, n_frames=n, schedule=SCHED,
                method='posekit patches via pose_api; hard pose cuts; sprite-talk BodyWarp bottom-anchored bob/sway per frame on current pose; blink_v2 eyes',
                sway=dict(curve='sprite_talk GENERIC_LOOP', piv_ratio=PIV, dy_gain=DY_GAIN, amp=AMP, amp_scale='x per-pose head height (BodyWarp.head_height)',
                          head_px={p: round(w.head_height, 1) for p, w in warps.items()},
                          max_dx_px=round(max(abs(l[1]) for l in log), 2), max_dy_px=round(max(abs(l[2]) for l in log), 2)),
                blink_frames={str(k): v for k, v in sorted(blinks.items())}, frac_open=round(float((lvl > 0).mean()), 3))
    json.dump(meta, open(os.path.join(HERE, 'pose_swap_meta.json'), 'w'), indent=1)
    print(json.dumps(meta['sway']), 'blinks', sorted(blinks.items()))

if __name__ == '__main__':
    main()
