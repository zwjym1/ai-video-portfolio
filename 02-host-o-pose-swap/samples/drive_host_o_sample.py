#!/usr/bin/env python3
"""Host O landscape talk sample: Aning-extract bob (dy x0.75) + 3-level volume mouth + blink.

Reuses:
  - sprite_talk BodyWarp / mouth_levels / blink_schedule / audio_rms
  - morning/visemes._aning_replica_bob_series for Aning-extract feel
Does NOT invent new art; drives existing host_o_star_sleep sprites.
"""
from __future__ import annotations
import os, sys, subprocess, json
import numpy as np
import cv2
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SPRITES = os.path.normpath(os.path.join(HERE, "..", "sprites"))
sys.path.insert(0, "/workspace/oss/sprite-talk")
sys.path.insert(0, "/workspace/science-studio/episodes/ai_hands_ep01_mcp/trial/morning")

from sprite_talk.warp import BodyWarp
from sprite_talk.mouth import audio_rms, audio_duration, mouth_levels
from sprite_talk.blink import blink_schedule
from visemes import _aning_replica_bob_series

FPS = 30
W, H = 1920, 1080
DY_GAIN = 0.75  # Aning-art internal calibration: comfortable vs raw extract
BG = (14, 14, 17)
VO = "/workspace/science-studio/hosts/host_d/ai_talking/inputs/vo_intro.mp3"
OUT_MP4 = os.path.join(HERE, "host_o_talk_landscape_sample.mp4")
OUT_PREV = os.path.join(HERE, "host_o_talk_preview.jpg")
LEVEL_KEY = {0: "closed", 1: "small", 2: "large"}


def load_sprites():
    base = np.array(Image.open(os.path.join(SPRITES, "base.png")).convert("RGBA"))
    mouths = {
        "closed": base.copy(),  # mouth_closed == base
        "small": np.array(Image.open(os.path.join(SPRITES, "mouth_open_s.png")).convert("RGBA")),
        "large": np.array(Image.open(os.path.join(SPRITES, "mouth_open_l.png")).convert("RGBA")),
    }
    eyes_closed = np.array(Image.open(os.path.join(SPRITES, "eyes_closed.png")).convert("RGBA"))
    # feathered eye patch from diff vs base
    d = np.abs(eyes_closed.astype(np.int16) - base.astype(np.int16)).max(2)
    m = (d > 12).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    m = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=2)
    # restrict to eye ROI
    roi = np.zeros_like(m)
    roi[500:595, 270:530] = 1
    m = m * roi
    a = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 1.6)[..., None]
    eye_patch = (eyes_closed.astype(np.float32), a)
    return mouths, eye_patch, base


def apply_eyes(img, eye_patch):
    g, a = eye_patch
    out = img.copy()
    out[..., :3] = (g[..., :3] * a + out[..., :3] * (1 - a)).astype(np.uint8)
    return out


def compose_frame(mouths, eye_patch, mouth_key, blink_state):
    img = mouths[mouth_key].copy()
    if blink_state >= 1:  # no half-lid sprite: treat half+closed as closed
        img = apply_eyes(img, eye_patch)
    return img


def aning_bob_px(n, fps, talking, host_h, host_h_ref, dy_gain=DY_GAIN):
    """Loop Aning extract curve; gate by talking; dy *= dy_gain; scale by height ratio."""
    bob, _, _, meta = _aning_replica_bob_series(n, fps)
    ref = float(meta.get("host_h_ref") or host_h_ref)
    sc = host_h / ref
    # ease talking envelope
    tk = np.asarray(talking, float)[:n]
    k = np.ones(13) / 13.0
    env = np.clip(np.convolve(tk, k, "same"), 0, 1)
    dx = np.zeros(n, np.float32)
    dy = np.zeros(n, np.float32)
    for f in range(n):
        bx, by = bob[f]
        g = env[f]
        dx[f] = bx * sc * g
        dy[f] = by * sc * dy_gain * g
    return dx, dy, meta


def place_host(canvas, rgba, anchor="br"):
    """Half-body sitting: bottom-anchored, right third of landscape."""
    hi = Image.fromarray(rgba)
    # keep native 770x1080; if taller than canvas, scale down
    sc = min(1.0, (H - 20) / hi.height)
    if sc < 1.0:
        hi = hi.resize((int(hi.width * sc), int(hi.height * sc)), Image.LANCZOS)
    x = W - hi.width - 80
    y = H - hi.height
    canvas.alpha_composite(hi, (x, y))
    return canvas


def make_bg():
    img = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img)
    for y in range(14, H, 30):
        for x in range(14, W, 30):
            d.ellipse((x - 1.6, y - 1.6, x + 1.6, y + 1.6), fill=(36, 36, 44, 255))
    return img


def contact_sheet(frames_rgb, path, cols=4):
    # pick evenly spaced frames
    idxs = [int(i * (len(frames_rgb) - 1) / (cols - 1)) for i in range(cols)]
    thumbs = []
    tw, th = 480, 270
    for i in idxs:
        im = Image.fromarray(frames_rgb[i]).resize((tw, th), Image.LANCZOS)
        thumbs.append(im)
    sheet = Image.new("RGB", (tw * cols, th), (10, 10, 12))
    for i, t in enumerate(thumbs):
        sheet.paste(t, (i * tw, 0))
    sheet.save(path, quality=90)
    return path


def main():
    mouths, eye_patch, base = load_sprites()
    warp = BodyWarp.for_sprite(base, piv_ratio=0.355)
    host_h = float(warp.bot - warp.top + 1)
    dur = min(audio_duration(VO), 15.0)
    # prefer full VO if ~6-15s
    n = int(round(dur * FPS))
    rms = audio_rms(VO, FPS, dur)
    lvl, env = mouth_levels(rms, n, FPS, align=None)
    talking = env > 0.08
    _, _, _, meta = _aning_replica_bob_series(n, FPS)
    dx, dy, meta = aning_bob_px(n, FPS, talking, host_h, float(meta.get("host_h_ref", 828)))
    blinks = blink_schedule(n, FPS, seed=7)

    print(json.dumps({
        "vo": VO, "dur": round(dur, 3), "frames": n,
        "dy_gain": DY_GAIN, "host_h": round(host_h, 1),
        "host_h_ref": meta.get("host_h_ref"),
        "piv": round(warp.piv, 1), "frac_open": round(float((lvl > 0).mean()), 3),
        "blinks": len([1 for v in blinks.values() if v == 2]),
    }, ensure_ascii=False), flush=True)

    bg0 = make_bg()
    preview_bufs = []
    preview_at = set(int(t * FPS) for t in (0.5, 2.0, 4.5, 7.0, 9.5) if int(t * FPS) < n)

    enc = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", VO,
        "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-shortest",
        OUT_MP4,
    ]
    p = subprocess.Popen(enc, stdin=subprocess.PIPE)
    for f in range(n):
        mk = LEVEL_KEY[int(lvl[f])]
        sp = compose_frame(mouths, eye_patch, mk, blinks.get(f, 0))
        warped = warp(sp, float(dx[f]), float(dy[f]))
        canvas = bg0.copy()
        place_host(canvas, warped)
        rgb = np.array(canvas.convert("RGB"))
        p.stdin.write(np.ascontiguousarray(rgb).tobytes())
        if f in preview_at:
            preview_bufs.append(rgb.copy())
        if f % 60 == 0:
            print(f"frame {f}/{n}", flush=True)
    p.stdin.close()
    rc = p.wait()
    if rc:
        raise SystemExit(f"ffmpeg failed rc={rc}")

    if len(preview_bufs) < 4:
        # fallback: grab by re-seeking isn't possible; pad from last
        while len(preview_bufs) < 4:
            preview_bufs.append(preview_bufs[-1] if preview_bufs else np.zeros((H, W, 3), np.uint8))
    contact_sheet(preview_bufs[:4], OUT_PREV, cols=4)

    # note mouth sprite quality
    note = {
        "mp4": OUT_MP4,
        "preview": OUT_PREV,
        "script": os.path.abspath(__file__),
        "bob": f"Aning-extract ×{DY_GAIN} dy_gain, height-scaled to host_h={host_h:.0f}",
        "vo": VO,
    }
    with open(os.path.join(HERE, "sample_meta.json"), "w") as f:
        json.dump(note, f, ensure_ascii=False, indent=2)
    print("DONE", json.dumps(note, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
