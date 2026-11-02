#!/workspace/.venv-review/bin/python
"""校准：用有真实数据的视频，算各分数与真实 2 秒跳出率的 Spearman，并做留一法(LOO)权重网格。
用法: calibrate.py [--metric bounce2s] [--write-rubric]   → out/calibration.json / calibration.md
真实数据来源: corpus/corpus.json 的 real 字段 + ledger/actuals.csv（用户截图录入）。"""
import json, os, csv, itertools, argparse, subprocess, copy
import numpy as np
from scipy.stats import spearmanr
ROOT = os.path.dirname(os.path.abspath(__file__)); PY = '/workspace/.venv-review/bin/python'
sys_path = os.path.join(ROOT, 'lib'); import sys; sys.path.insert(0, sys_path); import merge as M

def actuals(metric):
    A = {e['id']: (e.get('real') or {}).get(metric) for e in json.load(open(os.path.join(ROOT, 'corpus/corpus.json')))['videos']}
    p = os.path.join(ROOT, 'ledger/actuals.csv')
    if os.path.exists(p):
        for r in csv.DictReader(open(p)):
            if r.get(metric): A[r['id']] = float(r[metric])
    return {k: v for k, v in A.items() if v is not None}

def feats(id_, R, runs):
    O = json.load(open(os.path.join(ROOT, f'out/{id_}/objective.json'))); S = M.load_subj(id_, runs)
    m = M.subj_scores(S, R['persona_weights']); h, b, HO, BO = M.obj_scores(O, R, m)
    return dict(HO=HO, BO=BO, SH=m['S_hook'] if m else None, SB=m['S_body'] if m else None, SV=m['S_value'] if m else None,
                stay2=m['stay2'] if m else None, swipe=m['swipe_med'] if m else None, **{'h_'+k: v for k, v in h.items()}, **{'b_'+k: v for k, v in b.items()})

def rho(x, y):
    ok = [(a, b) for a, b in zip(x, y) if a is not None]
    if len(ok) < 4: return None, None
    r, p = spearmanr(*zip(*ok)); return round(float(r), 3), round(float(p), 3)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--metric', default='bounce2s'); ap.add_argument('--runs', default='r1,r2')
    a = ap.parse_args(); R = json.load(open(os.path.join(ROOT, 'config/rubric.json'))); A = actuals(a.metric)
    ids = [i for i in A if os.path.exists(os.path.join(ROOT, f'out/{i}/objective.json'))]
    F = {i: feats(i, R, a.runs.split(',')) for i in ids}; y = [1-A[i] for i in ids]  # 用 2 秒留存(=1-跳出)，ρ>0 表示分越高越好
    single = {k: rho([F[i][k] for i in ids], y) for k in F[ids[0]]}
    per_run = {}
    for r in a.runs.split(','):
        G = {i: feats(i, R, [r]) for i in ids}
        per_run[r] = {k: rho([G[i][k] for i in ids], y)[0] for k in ('SH', 'stay2', 'swipe', 'h_frame0_probe', 'HO')}
    # 钩子分 = w*HO + (1-w)*SH；网格 + 留一
    grid = [0, .25, .5, .75, 1]
    def hook(i, w): return w*F[i]['HO'] + (1-w)*(F[i]['SH'] if F[i]['SH'] is not None else F[i]['HO'])
    full = {w: rho([hook(i, w) for i in ids], y)[0] for w in grid}
    loo_pred = {}
    for out in ids:
        tr = [i for i in ids if i != out]
        best = max(grid, key=lambda w: (np.nan_to_num(spearmanr([hook(i, w) for i in tr], [1-A[i] for i in tr])[0], nan=-9), -abs(w-.5)))
        xs = np.array([hook(i, best) for i in tr]); ys = np.array([A[i] for i in tr]); k, b0 = np.polyfit(xs, ys, 1)
        loo_pred[out] = dict(w=best, pred=round(float(k*hook(out, best)+b0), 3), actual=A[out])
    loo_rho = rho([loo_pred[i]['pred'] for i in ids], [A[i] for i in ids])  # 预测跳出 vs 真实跳出，ρ>0 好
    mae = float(np.mean([abs(loo_pred[i]['pred']-loo_pred[i]['actual']) for i in ids]))
    wb = max(grid, key=lambda w: (np.nan_to_num(full[w], nan=-9), -abs(w-.5)))
    yb = np.array([A[i] for i in ids]); xs = np.array([hook(i, wb) for i in ids]); k, b0 = np.polyfit(xs, yb, 1); resid = float(np.std(yb-(k*xs+b0), ddof=2))
    res = dict(metric=a.metric, n=len(ids), ids=ids, actual=A, spearman_single=single, spearman_per_run=per_run, hook_weight_grid=full,
               best_obj_weight=wb, loo=loo_pred, loo_spearman=loo_rho, loo_mae=round(mae, 3), fit=dict(slope=k, intercept=b0, resid_sd=resid),
               critical_rho_p05=dict(one_tailed=0.714, two_tailed=0.786), features={i: {k: (None if v is None else round(v, 2)) for k, v in F[i].items()} for i in ids})
    json.dump(res, open(os.path.join(ROOT, 'out/calibration.json'), 'w'), ensure_ascii=False, indent=1)
    L = [f"# 校准报告（{a.metric}，n={len(ids)}）", "", "单项 Spearman ρ（分数 vs 真实 2 秒留存=1-跳出；ρ>0 = 分越高留得越住）；n=7 时 p<0.05 需 |ρ|≥0.786（双尾）", "", "| 指标 | ρ | p |", "|---|---|---|"]
    for k, (r, p) in sorted(single.items(), key=lambda kv: (kv[1][0] is None or kv[1][0] != kv[1][0], -(kv[1][0] or 0))): L.append(f"| {k} | {r} | {p} |")
    L += ["", f"钩子分客观权重网格: {full}；全量最优 w_obj={wb}", f"留一法（每次用其余 6 条选权重+线性拟合，预测被留出那条的跳出率）：预测 vs 真实 ρ={loo_rho[0]} (p={loo_rho[1]})，MAE={mae:.3f}", "", "| id | 真实 | 留一预测 | 选中 w_obj |", "|---|---|---|---|"]
    L += [f"| {i} | {loo_pred[i]['actual']} | {loo_pred[i]['pred']} | {loo_pred[i]['w']} |" for i in ids]
    L += ["", f"各轮主观稳定性: {per_run}"]
    open(os.path.join(ROOT, 'out/calibration.md'), 'w').write('\n'.join(L)); print('\n'.join(L))

if __name__ == '__main__': main()
