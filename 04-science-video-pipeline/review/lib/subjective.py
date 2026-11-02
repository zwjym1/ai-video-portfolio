#!/workspace/.venv-review/bin/python
"""主观层：qoder-flash 多角色盲审。
用法: subjective.py --sheets out/<id>/sheets --asr asr.json --out out/<id>/subjective_r1.json [--title 标题] [--model flash|qwen]
- 在只放了两张图的临时目录里调用，避免模型读到项目里的真实数据（盲审）。
- 只用 qoder-flash（DeepSeek-Flash max，撞限自动回退 Qwen3.8-Flash）或 qoder-flash-qwen；不改全局默认模型。"""
import argparse, json, os, re, shutil, subprocess, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
ap = argparse.ArgumentParser()
for k in ('sheets','asr','out','title'): ap.add_argument('--'+k)
ap.add_argument('--model', default='flash'); ap.add_argument('--timeout', type=int, default=600)
a = ap.parse_args()
S = json.load(open(a.asr)); meta = json.load(open(os.path.join(a.sheets,'sheets.json')))
tr = '\n'.join(f"[{s['a']:.1f}-{s['b']:.1f}] {s['text']}" for s in S)
P = open(os.path.join(ROOT,'prompts/persona_review.md')).read().replace('{duration}', f"{meta['duration']:.1f}") \
    .replace('{title_hint}', a.title or '（无）').replace('{transcript}', tr)
tmp = tempfile.mkdtemp(prefix='blind_')
for f in ('hook_3s.jpg','contact.jpg'): shutil.copy(os.path.join(a.sheets,f), tmp)
exe = os.path.expanduser('~/.local/bin/' + ('qoder-flash' if a.model=='flash' else 'qoder-flash-qwen'))
env = dict(os.environ, PATH=os.path.expanduser('~/.local/bin')+':'+os.environ['PATH'])
t0 = time.time(); raw = ''; err = ''
for attempt in range(2):
    try:
        r = subprocess.run([exe,'-p','--attachment','hook_3s.jpg','--attachment','contact.jpg',P], cwd=tmp, env=env,
                           capture_output=True, text=True, timeout=a.timeout)
        raw, err = r.stdout, r.stderr[-500:]
    except subprocess.TimeoutExpired: raw, err = '', 'timeout'
    m = re.search(r'\{.*\}', raw, re.S)
    if m:
        try: J = json.loads(m.group(0)); break
        except json.JSONDecodeError: J = None
    else: J = None
shutil.rmtree(tmp, ignore_errors=True)
os.makedirs(os.path.dirname(a.out), exist_ok=True)
used = 'Qwen3.8-Flash' if (a.model!='flash' or '撞限' in err or 'Qwen' in err) else 'DeepSeek-Flash(max)'
out = dict(ok=J is not None, model=used, seconds=round(time.time()-t0,1), result=J, raw=None if J else raw[-3000:], stderr=err[-300:])
json.dump(out, open(a.out,'w'), ensure_ascii=False, indent=1)
print('subjective', 'ok' if J else 'FAIL', a.out, out['seconds'], 's', used)
