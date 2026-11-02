import json, os
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REG = json.load(open(f'{HERE}/registry.json'))
_c = {}


def _ld(p):
  if p not in _c:
    _c[p] = Image.open(f'{HERE}/{p}')
  return _c[p]


def frame(pose, mouth='X', blink=0):
  """Return RGB PIL image of pose with mouth (X/closed/open_s/open_l or A/E/O/S/L) and blink 0..2."""
  e = REG[pose]
  im = _ld(e['img']).convert('RGB').copy()
  # mouth first, eyes last: mouth ROI overlaps the lower eye rim, so eyes must win (no iris residue)
  if mouth not in ('X', 'closed', None, 'MBP'):
    # map volume aliases
    mk = mouth
    if mk not in e['mouth']:
      alt = {'small': 'open_s', 'large': 'open_l', '1': 'open_s', '2': 'open_l'}.get(str(mk), mk)
      mk = alt if alt in e['mouth'] else None
    if mk and mk in e['mouth']:
      p, x, y = e['mouth'][mk]
      im.paste(_ld(p), (x, y), _ld(p))
  if blink:
    key = str(blink)
    if key not in e['eye']:
      key = '2' if '2' in e['eye'] else next(iter(e['eye']))
    p, x, y = e['eye'][key]
    im.paste(_ld(p), (x, y), _ld(p))
  return im


def face_box(pose):
  M = np.array(REG[pose]['M'])
  c = M @ np.array([395, 612, 1])
  s = np.hypot(*M[:, 0])
  return c, s


def list_poses():
  return list(REG.keys())
