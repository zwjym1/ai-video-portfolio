#!/workspace/.venv-review/bin/python
"""生成给 qoder-flash 看的两张图：
  hook_3s.jpg   —— 第 0 帧大图 + 0.25/0.5/1/1.5/2/2.5/3s 七格（看「1 秒内认不认得出」）
  contact.jpg   —— 全片均匀 16 格，每格标时间
用法: sheets.py <video> <outdir> [--frames-dir PC抽好的帧目录]
有 --frames-dir（PC 上 pc/pc_frames.ps1 抽的帧）就直接拼，没有就在盒上用 ffmpeg 现抽（回退）。"""
import sys, os, subprocess, json
from PIL import Image, ImageDraw, ImageFont
v, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
FD = sys.argv[sys.argv.index('--frames-dir')+1] if '--frames-dir' in sys.argv else None
dur = float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',v],capture_output=True,text=True).stdout)
SRC = 'box-ffmpeg'
FONT = next((p for p in ['/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc','/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc','/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc','/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc'] if os.path.exists(p)), None)
def grab(t, w, kind='c'):
    global SRC
    if FD:
        q = os.path.join(FD, f'{kind}_{t:.3f}.jpg')
        if os.path.exists(q): SRC = 'pc-frames'; return Image.open(q).convert('RGB').resize((w, int(round(Image.open(q).height*w/Image.open(q).width))))
    p = f'/tmp/_sh_{os.getpid()}.jpg'
    subprocess.run(['ffmpeg','-v','error','-y','-ss',f'{t:.3f}','-i',v,'-frames:v','1','-vf',f'scale={w}:-2',p])
    im = Image.open(p).convert('RGB'); os.remove(p); return im
def label(im, txt):
    d = ImageDraw.Draw(im); f = ImageFont.truetype(FONT, max(16, im.width//10)) if FONT else ImageFont.load_default()
    d.rectangle([0,0,im.width, f.size+8], fill=(0,0,0)); d.text((6,2), txt, fill=(255,255,0), font=f); return im
# hook sheet
big = label(grab(0.0, 540, 'h'), '0.00s 第一帧')
ts = [0.25,0.5,1.0,1.5,2.0,2.5,3.0]; small = [label(grab(t, 260, 'h'), f'{t:.2f}s') for t in ts]
sw, shh = small[0].size; cols = 4
H = max(big.height, 2*shh); W = big.width + cols*sw
canvas = Image.new('RGB', (W, H), (30,30,30)); canvas.paste(big, (0,0))
for i, im in enumerate(small): canvas.paste(im, (big.width + (i%cols)*sw, (i//cols)*shh))
canvas.save(os.path.join(out,'hook_3s.jpg'), quality=88)
# contact sheet 16 格
n = 16; tt = [dur*(i+0.5)/n for i in range(n)]; ims = [label(grab(t, 240), f'{t:.1f}s') for t in tt]
w, h = ims[0].size; cs = Image.new('RGB', (8*w, 2*h)); [cs.paste(im, ((i%8)*w, (i//8)*h)) for i, im in enumerate(ims)]
cs.save(os.path.join(out,'contact.jpg'), quality=85)
json.dump(dict(frames_source=SRC, duration=dur, hook_ts=[0]+ts, contact_ts=[round(t,1) for t in tt]), open(os.path.join(out,'sheets.json'),'w'))
print('sheets ok', out)
