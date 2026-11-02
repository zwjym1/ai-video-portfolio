#!/workspace/.venv-review/bin/python
"""对 corpus.json 里每条片子跑客观层（3 路并行）。用法: run_objective_corpus.py [id ...]"""
import json, subprocess, os, sys
from concurrent.futures import ThreadPoolExecutor
os.chdir(os.path.dirname(os.path.abspath(__file__)))
C = json.load(open('corpus/corpus.json'))['videos']
only = set(sys.argv[1:])
def run(v):
    cmd = ['/workspace/.venv-review/bin/python','lib/objective.py','--video',v['src'],'--asr',v['asr'],'--out',f"out/{v['id']}/objective.json"]
    for k in ('cover','facts','publish','beats'):
        if v.get(k): cmd += ['--'+k, v[k]]
    if v.get('ai'): cmd.append('--ai')
    r = subprocess.run(cmd, capture_output=True, text=True); return v['id'], r.returncode, (r.stdout+r.stderr)[-300:]
with ThreadPoolExecutor(3) as ex:
    for i, rc, msg in ex.map(run, [v for v in C if not only or v['id'] in only]): print(i, rc, msg.strip().splitlines()[-1] if msg.strip() else '', flush=True)
