#!/workspace/.venv-review/bin/python
"""0–2s 开头提示（单独打分、单独报告，不一票否决、不拦放行）：只看前 2 秒的「路人划走测试」（qoder-flash-qwen 默认；盲审，临时目录只放一张图）。
规则：第一帧/前 2 秒必须是异常画面或抛出问题，不能是铺垫、空镜或标题卡；对 0–2s 单独做路人划走测试。
用法: gate02.py --video 成片.mp4 [--asr asr.json] --out out/<id>/gate02.json [--model qwen|flash] [--runs 2] [--dry]
判定：每轮都要 frame0_type 属于「异常画面/抛出问题」类 且 (anomaly_by_2s 或 question_by_2s) 且 swipe_by_2s=false 才算过；
多轮取最严（任一轮不过 → 不过）；score=各轮均分（首帧类型 40 + 2 秒内异常/问题 30 + 不划走 30）。--dry 只出拼图不调模型。
merge.py 读 gate02.json，只在返修单里单列「0–2s 开头提示」，不进否决/必改，不改结论。"""
import argparse, json, os, re, shutil, subprocess, tempfile, time
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
OKT = ('异常画面', '抛出问题')
ap = argparse.ArgumentParser(); ap.add_argument('--video', required=True); ap.add_argument('--asr'); ap.add_argument('--out', required=True)
ap.add_argument('--model', default='qwen'); ap.add_argument('--runs', type=int, default=2); ap.add_argument('--timeout', type=int, default=300); ap.add_argument('--dry', action='store_true')
a = ap.parse_args(); od = os.path.dirname(os.path.abspath(a.out)); os.makedirs(od, exist_ok=True)
FONT = next((p for p in ['/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'] if os.path.exists(p)), None)
ims = []
for t in (0.0, 0.5, 1.0, 1.5, 2.0):
    p = os.path.join(tempfile.gettempdir(), f'_g02_{os.getpid()}.jpg')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t:.3f}', '-i', a.video, '-frames:v', '1', '-vf', 'scale=300:-2', p], check=True)
    im = Image.open(p).convert('RGB'); os.remove(p); d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, 30) if FONT else ImageFont.load_default(); d.rectangle([0, 0, im.width, 38], fill=(0, 0, 0)); d.text((6, 2), f'{t:.1f}s', fill=(255, 255, 0), font=f); ims.append(im)
w, h = ims[0].size; sheet = Image.new('RGB', (5*w, h)); [sheet.paste(im, (i*w, 0)) for i, im in enumerate(ims)]
sp = os.path.join(od, os.path.splitext(os.path.basename(a.out))[0] + '_0_2s.jpg'); sheet.save(sp, quality=88)
tr = ''
if a.asr and os.path.exists(a.asr):
    tr = '\n'.join(f"[{s['a']:.1f}-{s['b']:.1f}] {s['text']}" for s in json.load(open(a.asr)) if s['a'] < 2.0)
P = open(os.path.join(ROOT, 'prompts/gate_0_2s.md')).read().replace('{transcript_0_2}', tr or '（前 2 秒无口播）')
if a.dry: print('gate02 dry：只出拼图', sp); raise SystemExit
exe = os.path.expanduser('~/.local/bin/' + ('qoder-flash' if a.model == 'flash' else 'qoder-flash-qwen'))
env = dict(os.environ, PATH=os.path.expanduser('~/.local/bin') + ':' + os.environ['PATH'])
R = []; t0 = time.time()
for i in range(a.runs):
    tmp = tempfile.mkdtemp(prefix='g02_'); shutil.copy(sp, os.path.join(tmp, 'gate_0_2s.jpg')); J = None; raw = ''
    for attempt in range(2):
        try: raw = subprocess.run([exe, '-p', '--attachment', 'gate_0_2s.jpg', P], cwd=tmp, env=env, capture_output=True, text=True, timeout=a.timeout).stdout
        except subprocess.TimeoutExpired: raw = ''
        m = re.search(r'\{.*\}', raw, re.S)
        try: J = json.loads(m.group(0)) if m else None
        except json.JSONDecodeError: J = None
        if J: break
    shutil.rmtree(tmp, ignore_errors=True)
    if J:
        t_ok = any(k in str(J.get('frame0_type', '')) for k in OKT); aq = bool(J.get('anomaly_by_2s') or J.get('question_by_2s')); stay = not J.get('swipe_by_2s')
        J['score'] = 40*t_ok + 30*aq + 30*stay          # 首帧类型 40 + 2 秒内有异常/问题 30 + 路人 2 秒不划走 30
        J['pass'] = t_ok and aq and stay
    R.append(J or {'error': raw[-500:]})
ok = [r for r in R if 'pass' in r]
out = dict(ok=bool(ok), model=os.path.basename(exe), seconds=round(time.time()-t0, 1), runs=R, sheet=sp,
           passed=(all(r['pass'] for r in ok) if ok else None), score=(round(sum(r['score'] for r in ok)/len(ok)) if ok else None), role='提示项：单独打分、单独报告，不一票否决、不拦放行',
           rule='第一帧/前 2 秒必须是异常画面或抛出问题，不能是铺垫、空镜或标题卡；对0–2s单独做路人划走测试')
json.dump(out, open(a.out, 'w'), ensure_ascii=False, indent=1)
print('gate02(提示)', out['score'], '通过' if out['passed'] else ('未通过' if out['passed'] is False else '模型失败'), a.out, out['seconds'], 's')
