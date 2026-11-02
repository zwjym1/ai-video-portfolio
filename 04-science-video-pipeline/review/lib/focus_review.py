#!/workspace/.venv-review/bin/python
"""逐镜精审的 qoder-flash 调用（盒上跑）。用法: focus_review.py --prompt prompts/focus_cuts.md --ctx ctx.txt --img a.jpg --img b.jpg --out out.json"""
import argparse, json, os, re, shutil, subprocess, tempfile, time
ap = argparse.ArgumentParser(); ap.add_argument('--prompt'); ap.add_argument('--ctx'); ap.add_argument('--img', action='append'); ap.add_argument('--out'); ap.add_argument('--timeout', type=int, default=900)
a = ap.parse_args(); P = open(a.prompt).read().replace('{ctx}', open(a.ctx).read())
tmp = tempfile.mkdtemp(prefix='focus_'); names = []
for f in a.img: shutil.copy(f, tmp); names.append(os.path.basename(f))
cmd = [os.path.expanduser('~/.local/bin/qoder-flash'), '-p'] + sum((['--attachment', n] for n in names), []) + [P]
env = dict(os.environ, PATH=os.path.expanduser('~/.local/bin')+':'+os.environ['PATH']); t0 = time.time(); J = None; raw = err = ''
for _ in range(2):
    try: r = subprocess.run(cmd, cwd=tmp, env=env, capture_output=True, text=True, timeout=a.timeout); raw, err = r.stdout, r.stderr[-400:]
    except subprocess.TimeoutExpired: err = 'timeout'
    m = re.search(r'\{.*\}', raw, re.S)
    if m:
        try: J = json.loads(m.group(0)); break
        except json.JSONDecodeError: pass
shutil.rmtree(tmp, ignore_errors=True)
json.dump(dict(ok=J is not None, seconds=round(time.time()-t0, 1), result=J, raw=None if J else raw[-4000:], stderr=err), open(a.out, 'w'), ensure_ascii=False, indent=1)
print('focus', 'ok' if J else 'FAIL', a.out, round(time.time()-t0, 1))
