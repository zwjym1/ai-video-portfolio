"""Host O gsprites-style mouth/blink patches from base vs locked edits."""
import os
import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
base_rgba = np.array(Image.open(f'{HERE}/base.png').convert('RGBA'))
base = base_rgba[..., :3].copy()
H, W = base.shape[:2]

# Mouth center ~395,612 (done_mouth.json); ROIs pad the diff bboxes.
MOUTH_ROI = (330, 566, 461, 678)
EYE_ROI = (265, 492, 533, 600)
# Face template for posekit alignment (eyes + midface + mouth).
FACE = (310, 490, 520, 680)


def _load_full(name):
  return np.array(Image.open(f'{HERE}/{name}.png').convert('RGB')).astype(np.float32)


def patch(name, roi, thr=10, grow=4, feath=2.0):
  g = _load_full(name)
  b = base.astype(np.float32)
  x0, y0, x1, y1 = roi
  d = np.abs(g - b).max(2)
  m = np.zeros((H, W), np.uint8)
  m[y0:y1, x0:x1] = (d[y0:y1, x0:x1] > thr).astype(np.uint8)
  m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
  m = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=grow)
  # colour-correct: low-freq diff on unchanged pixels
  diff = (g - b)
  w = ((d < thr) & (m == 0)).astype(np.float32)
  num = cv2.GaussianBlur(diff * w[..., None], (0, 0), 10)
  den = cv2.GaussianBlur(w, (0, 0), 10)[..., None] + 1e-3
  g = g - num / den
  a = cv2.GaussianBlur(m.astype(np.float32), (0, 0), feath)
  r = np.zeros((H, W), np.float32)
  r[y0:y1, x0:x1] = 1
  r = cv2.GaussianBlur(r, (0, 0), 3)
  a = a * r
  return np.clip(g, 0, 255), a[..., None]


# 3-level mouths for volume drive; map also to host_a-style keys for pose_api.
MOUTHS = {
  'X': None,  # closed = no paste
  'closed': None,
  'open_s': patch('mouth_open_s', MOUTH_ROI, thr=10, grow=3),
  'open_l': patch('mouth_open_l', MOUTH_ROI, thr=10, grow=3),
}
# aliases used by pose_api / volume levels
MOUTHS['S'] = MOUTHS['open_s']
MOUTHS['L'] = MOUTHS['open_l']
MOUTHS['A'] = MOUTHS['open_l']   # wide open ~ A
MOUTHS['E'] = MOUTHS['open_s']
MOUTHS['I'] = MOUTHS['open_s']
MOUTHS['O'] = MOUTHS['open_l']
MOUTHS['U'] = MOUTHS['open_s']
MOUTHS['N'] = MOUTHS['open_s']
MOUTHS['MBP'] = None  # closed
MOUTHS['F'] = MOUTHS['open_s']

def eye_patch(name, alpha):
  # blink_v2: face-edit eyes, ECC-aligned, pixel-locked; use the build alpha directly
  # (solid core over whole eye incl. highlights/lower lash) -> no diff-threshold residue.
  g = _load_full(name)
  a = np.array(Image.open(f'{HERE}/{alpha}.png').convert('L')).astype(np.float32) / 255
  return g, a[..., None]


EYES = {
  2: eye_patch('eyes_closed', 'eye_alpha_closed'),
  1: eye_patch('eyes_half', 'eye_alpha_half'),
}


def apply(img, p):
  if p is None:
    return img
  g, a = p
  return (g * a + img * (1 - a)).astype(np.uint8)


if __name__ == '__main__':
  for k, p in MOUTHS.items():
    if p is None:
      print(k, 'None')
    else:
      g, a = p
      x0, y0, x1, y1 = MOUTH_ROI
      print(k, 'alpha>', float((a[y0:y1, x0:x1, 0] > 0.5).sum()))
