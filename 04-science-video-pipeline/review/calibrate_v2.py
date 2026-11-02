#!/workspace/.venv-review/bin/python
"""v2 校准：v1 公式 vs v2 公式（+剪辑质量 +BGM 契合）对真实 2 秒跳出率的 Spearman，留一法，v1/v2 能否拉开。旧 calibrate.py 不动。
用法: calibrate_v2.py [--metric bounce2s] [--runs r1,r2]  → out/calibration_v2.json / calibration_v2.md
注意：n=7，单尾 p<0.05 需 ρ≥0.714、双尾 ≥0.786；网格选权重的留一结果才算「泛化」，全量 ρ 只是拟合。"""
import json, os, sys, subprocess, itertools, argparse
import numpy as np
from scipy.stats import spearmanr
ROOT = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(ROOT, 'lib')); import calibrate as C1
PY = sys.executable

def merged(i, legacy, runs):
    cmd = [PY, os.path.join(ROOT, 'lib', 'merge.py'), '--id', i, '--quiet', '--runs', runs] + (['--legacy'] if legacy else [])
    subprocess.run(cmd, check=True); return json.load(open(os.path.join(ROOT, f'out/{i}/verdict.json')))

def rho(x, y):
    ok = [(a, b) for a, b in zip(x, y) if a is not None]
    if len(ok) < 4: return [None, None]
    r, p = spearmanr(*zip(*ok)); return [round(float(r), 3), round(float(p), 3)]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--metric', default='bounce2s'); ap.add_argument('--runs', default='r1,r2'); a = ap.parse_args()
    A = C1.actuals(a.metric); corpus = {e['id']: e for e in json.load(open(os.path.join(ROOT, 'corpus/corpus.json')))['videos']}
    allids = list(corpus)
    V1 = {i: merged(i, True, a.runs) for i in allids}
    V2 = {i: merged(i, False, a.runs) for i in allids}      # 最后留下的 verdict.json 是 v2
    ids = [i for i in allids if i in A]
    y = [1 - A[i] for i in ids]                                # 2 秒留存，ρ>0 = 分越高越留得住
    F = {}
    for i in allids:
        v1, v2 = V1[i], V2[i]
        F[i] = dict(total_v1=v1['total'], total_v2=v2['total'], hook=v2['hook'], body=v2['body'], value=v2['value'], edit=v2.get('edit'),
                    edit_obj=(v2.get('edit_detail') or {}).get('edit_obj'), bgm_fit=(v2.get('bgm_fit') or {}).get('score'),
                    hook_obj=v2['hook_obj'], body_obj=v2['body_obj'], stay2=(v2.get('subj') or {}).get('stay2'),
                    in_vertical=1.0 if corpus[i].get('vertical') == 'tech' else 0.0)
    single = {k: rho([F[i][k] for i in ids], y) for k in F[ids[0]]}
    # 留一：在 6 条上网格选 total 权重（hook/body/edit/value），看被留出那条的排名
    grid = [w for w in itertools.product([.3, .4, .5], [.15, .25, .35], [0, .1, .2, .3], [.05, .15, .25]) if abs(sum(w) - 1) < 1e-9]
    def tot(i, w): f = F[i]; return w[0]*f['hook'] + w[1]*f['body'] + w[2]*(f['edit'] if f['edit'] is not None else f['body']) + w[3]*(f['value'] if f['value'] is not None else f['body'])
    loo = {}
    for out in ids:
        tr = [i for i in ids if i != out]
        best = max(grid, key=lambda w: (np.nan_to_num(spearmanr([tot(i, w) for i in tr], [1 - A[i] for i in tr])[0], nan=-9), -abs(w[2] - .2)))
        xs = np.array([tot(i, best) for i in tr]); ys = np.array([A[i] for i in tr]); k, b0 = np.polyfit(xs, ys, 1)
        loo[out] = dict(w=best, score=round(tot(out, best), 1), pred_bounce=round(float(k*tot(out, best) + b0), 3), actual=A[out])
    loo_rho = rho([-loo[i]['pred_bounce'] for i in ids], y)
    # 垂类匹配（知赏给的选题标签）作为独立因子：总分 + 不在垂类扣 Δ
    vert = {d: rho([F[i]['total_v2'] - (0 if F[i]['in_vertical'] else d) for i in ids], y) for d in (0, 5, 10, 15)}
    sep = {k: round(F['iphone18pro'][k] - F['iphone18pro_v2'][k], 1) for k in ('total_v1', 'total_v2', 'edit', 'edit_obj', 'bgm_fit') if F['iphone18pro'][k] is not None and F['iphone18pro_v2'][k] is not None}
    rank_real = sorted(ids, key=lambda i: A[i]); rank_v2 = sorted(ids, key=lambda i: -F[i]['total_v2']); rank_v1 = sorted(ids, key=lambda i: -F[i]['total_v1'])
    res = dict(metric=a.metric, n=len(ids), ids=ids, actual=A, features=F, spearman_single=single, loo=loo, loo_spearman=loo_rho,
               vertical_penalty=vert, v1_minus_v2=sep, rank_real=rank_real, rank_total_v1=rank_v1, rank_total_v2=rank_v2,
               critical_rho_p05=dict(one_tailed=0.714, two_tailed=0.786))
    json.dump(res, open(os.path.join(ROOT, 'out/calibration_v2.json'), 'w'), ensure_ascii=False, indent=1)
    L = [f"# 校准 v2（{a.metric}，n={len(ids)}；ρ>0 = 分越高 2 秒留存越高；n=7 单尾 p<.05 需 ρ≥0.714）", "", "| 指标 | ρ | p |", "|---|---|---|"]
    L += [f"| {k} | {r} | {p} |" for k, (r, p) in sorted(single.items(), key=lambda kv: -(kv[1][0] if kv[1][0] is not None else -9))]
    L += ["", f"真实排名（跳出低→高）：{' > '.join(rank_real)}", f"v1 总分排名：{' > '.join(rank_v1)}", f"v2 总分排名：{' > '.join(rank_v2)}",
          "", f"留一（6 条网格选权重 → 预测第 7 条）：ρ={loo_rho[0]} (p={loo_rho[1]})", "", "| id | 真实跳出 | 留一分 | 预测跳出 | 选中权重 h/b/e/v |", "|---|---|---|---|---|"]
    L += [f"| {i} | {loo[i]['actual']} | {loo[i]['score']} | {loo[i]['pred_bounce']} | {loo[i]['w']} |" for i in ids]
    L += ["", f"垂类匹配扣分 Δ → ρ：{vert}", f"iPhone18Pro v1 − v2：{sep}"]
    open(os.path.join(ROOT, 'out/calibration_v2.md'), 'w').write('\n'.join(L)); print('\n'.join(L))

if __name__ == '__main__': main()
