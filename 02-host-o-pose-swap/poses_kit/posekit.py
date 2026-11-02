# Derive viseme mouth + blink patches for every Host O pose from approved base patches (gsprites) via face alignment.
import os, sys, json
import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
cwd = os.getcwd()
os.chdir(HERE)
sys.path.insert(0, HERE)
import gsprites as G
os.chdir(cwd)

FACE = G.FACE  # (310,490,520,680)


def align(pose, face=None, srch=None):
  b = cv2.cvtColor(G.base, cv2.COLOR_RGB2GRAY)
  p = cv2.cvtColor(pose, cv2.COLOR_RGB2GRAY)
  x0, y0, x1, y1 = face or FACE
  cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
  best = (-1,)

  def tryit(s, rot):
    R = cv2.getRotationMatrix2D((cx, cy), rot, 1.0)
    rb = cv2.warpAffine(b, R, (b.shape[1], b.shape[0]))
    t = cv2.resize(rb[y0:y1, x0:x1], None, fx=s, fy=s)
    if t.shape[0] >= p.shape[0] or t.shape[1] >= p.shape[1] or t.shape[0] < 20:
      return (-1,)
    pp = p if srch is None else p[srch[1]:srch[3], srch[0]:srch[2]]
    if t.shape[0] >= pp.shape[0] or t.shape[1] >= pp.shape[1]:
      return (-1,)
    r = cv2.matchTemplate(pp, t, cv2.TM_CCOEFF_NORMED)
    _, mv, _, ml = cv2.minMaxLoc(r)
    if srch:
      ml = (ml[0] + srch[0], ml[1] + srch[1])
    return (mv, s, rot, ml)

  for s in np.arange(0.7, 1.31, 0.04):
    for rot in (-8, -4, 0, 4, 8):
      r = tryit(s, rot)
      best = max(best, r, key=lambda z: z[0])
  for s in np.arange(best[1] - 0.04, best[1] + 0.041, 0.01):
    for rot in np.arange(best[2] - 3, best[2] + 3.1, 1):
      r = tryit(s, rot)
      best = max(best, r, key=lambda z: z[0])
  sc, s, rot, (mx, my) = best
  R = np.vstack([cv2.getRotationMatrix2D((cx, cy), rot, 1.0), [0, 0, 1]])
  S = np.array([[s, 0, mx - s * x0], [0, s, my - s * y0], [0, 0, 1]])
  return float(sc), (S @ R)[:2].astype(np.float32)


def warp_patch(pose, patch, M, roi):
  g, a = patch
  H, W = pose.shape[:2]
  gw = cv2.warpAffine(g, M, (W, H), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
  aw = cv2.warpAffine(a[..., 0], M, (W, H), flags=cv2.INTER_LINEAR)
  bw = cv2.warpAffine(G.base.astype(np.float32), M, (W, H), flags=cv2.INTER_LINEAR)
  # colour transfer: pose vs warped base, low-freq, weighted near patch
  x0, y0, x1, y1 = roi
  R = np.zeros((G.H, G.W), np.float32)
  R[max(0, y0 - 30):min(G.H, y1 + 30), max(0, x0 - 40):min(G.W, x1 + 40)] = 1
  Rw = cv2.warpAffine(R, M, (W, H)) > 0.5
  d = pose.astype(np.float32) - bw
  ok = Rw & (np.abs(d).max(2) < 40)
  off = np.median(d[ok], 0) if ok.sum() > 50 else 0
  gw = np.clip(gw + off, 0, 255)
  ys, xs = np.where(aw > 0.01)
  if len(xs) == 0:
    return np.zeros((1, 1, 4), np.uint8), (0, 0)
  X0, Y0, X1, Y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
  rgba = np.dstack([gw[Y0:Y1, X0:X1], aw[Y0:Y1, X0:X1] * 255]).astype(np.uint8)
  return rgba, (int(X0), int(Y0))


# Per-pose overrides if needed (empty for now; all front-ish).
OVR = {}

POSES = [
  'pose_talk_idle',
  'pose_talk_point',
  'pose_think',
  'pose_peace',
  'pose_react_surprise',
]

# Mouth keys to materialize as patches (skip None/closed).
MOUTH_KEYS = ['open_s', 'open_l', 'S', 'L', 'A', 'E', 'O']


if __name__ == '__main__':
  reg = {}
  poses = sys.argv[1:] or POSES
  for pn in poses:
    path = f'{HERE}/{pn}.png'
    pose = np.array(Image.open(path).convert('RGB'))
    sc, M = align(pose, **OVR.get(pn, {}))
    od = f'{HERE}/patches/{pn}'
    os.makedirs(od, exist_ok=True)
    ent = {'img': f'{pn}.png', 'match': round(sc, 3), 'M': M.tolist(), 'mouth': {}, 'eye': {}}
    # unique patches only once physically; aliases share files
    written = {}
    for k in MOUTH_KEYS:
      p = G.MOUTHS.get(k)
      if p is None:
        continue
      # dedupe by id of underlying array
      key_id = id(p[0])
      if key_id not in written:
        r, o = warp_patch(pose, p, M, G.MOUTH_ROI)
        fn = f'm_{k}.png'
        Image.fromarray(r).save(f'{od}/{fn}')
        written[key_id] = (f'patches/{pn}/{fn}', *o)
      ent['mouth'][k] = list(written[key_id])
    # also store open_s/open_l canonical names if aliased
    for k in ('open_s', 'open_l'):
      if k not in ent['mouth'] and G.MOUTHS.get(k) is not None:
        r, o = warp_patch(pose, G.MOUTHS[k], M, G.MOUTH_ROI)
        Image.fromarray(r).save(f'{od}/m_{k}.png')
        ent['mouth'][k] = [f'patches/{pn}/m_{k}.png', *o]
    for k, p in G.EYES.items():
      r, o = warp_patch(pose, p, M, G.EYE_ROI)
      Image.fromarray(r).save(f'{od}/e_{k}.png')
      ent['eye'][str(k)] = [f'patches/{pn}/e_{k}.png', *o]
    reg[pn] = ent
    print(pn, round(sc, 3), np.round(M, 3).tolist())
  fn = f'{HERE}/registry.json'
  old = json.load(open(fn)) if os.path.exists(fn) else {}
  old.update(reg)
  json.dump(old, open(fn, 'w'), indent=1)
  print('WROTE', fn, 'poses', list(reg))
