#!/workspace/.venv-review/bin/python
"""发布后闭环台账（不登录任何平台：真实数据只来自用户发来的后台截图，人工/看图录入）。
  ledger.py predict <id>                       发布前：把 verdict.json 的分数和预测跳出率写进 ledger/predictions.csv
  ledger.py actual <id> --bounce2s 0.25 [--stay5s .. --completion .. --avg_watch_s .. --plays .. --likes .. --comments .. --shares .. --saves .. --follows .. --hours 24 --shot 截图路径]
                                               发布后：录入截图里的数字到 ledger/actuals.csv（同一条可多次录入不同时点，校准用最新一次）
  ledger.py report                             预测 vs 真实对照表；新增真实数据≥5 条时提示跑 calibrate.py"""
import sys, os, csv, json, argparse, datetime
ROOT = os.path.dirname(os.path.abspath(__file__)); LD = os.path.join(ROOT, 'ledger')
PF = ['id', 'predicted_at', 'rubric_version', 'verdict', 'total', 'hook', 'body', 'value', 'pred_bounce2s', 'pred_bounce2s_lo', 'pred_bounce2s_hi', 'persona_stay5', 'persona_finish', 'persona_share']
AF = ['id', 'captured_at', 'hours_after_publish', 'plays', 'bounce2s', 'stay5s', 'completion', 'avg_watch_s', 'likes', 'comments', 'shares', 'saves', 'follows', 'shot']
def app(fn, fields, row):
    p = os.path.join(LD, fn); new = not os.path.exists(p); os.makedirs(LD, exist_ok=True)
    with open(p, 'a', newline='') as f:
        w = csv.DictWriter(f, fields); new and w.writeheader(); w.writerow(row)
def rows(fn):
    p = os.path.join(LD, fn); return list(csv.DictReader(open(p))) if os.path.exists(p) else []
def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest='cmd', required=True)
    p1 = sp.add_parser('predict'); p1.add_argument('id')
    p2 = sp.add_parser('actual'); p2.add_argument('id'); p2.add_argument('--hours', type=float)
    for k in AF[3:-1]: p2.add_argument('--'+k, type=float)
    p2.add_argument('--shot'); sp.add_parser('report'); a = ap.parse_args()
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    if a.cmd == 'predict':
        V = json.load(open(os.path.join(ROOT, f'out/{a.id}/verdict.json'))); C = json.load(open(os.path.join(ROOT, 'out/calibration.json')))
        R = json.load(open(os.path.join(ROOT, 'config/rubric.json'))); fit = C['fit']; key = C.get('predict_from', 'hook')
        x = V[key]; pb = fit['slope']*x + fit['intercept']; sd = fit['resid_sd']; s = V.get('subj') or {}
        app('predictions.csv', PF, dict(id=a.id, predicted_at=now, rubric_version=R.get('version', 'v0'), verdict=V['verdict'], total=V['total'], hook=V['hook'], body=V['body'], value=V['value'],
            pred_bounce2s=round(pb, 3), pred_bounce2s_lo=round(pb-1.64*sd, 3), pred_bounce2s_hi=round(pb+1.64*sd, 3), persona_stay5=s.get('stay5'), persona_finish=s.get('finish'), persona_share=s.get('share')))
        print(f'{a.id}: 预测 2 秒跳出 {pb:.1%}（90% 区间 {pb-1.64*sd:.1%}–{pb+1.64*sd:.1%}，基于 n={C["n"]} 条的粗拟合）')
    elif a.cmd == 'actual':
        r = dict(id=a.id, captured_at=now, hours_after_publish=a.hours, shot=a.shot, **{k: getattr(a, k) for k in AF[3:-1]})
        for k in ('bounce2s', 'stay5s', 'completion'):
            if r[k] is not None and r[k] > 1: r[k] = r[k]/100  # 允许直接填百分数
        app('actuals.csv', AF, r); print('已录入', r)
    else:
        P = {r['id']: r for r in rows('predictions.csv')}; A = {}
        for r in rows('actuals.csv'): A[r['id']] = r
        print('| id | 结论 | 预测2s跳出 | 真实2s跳出 | 真实完播 | 分享 | 偏差 |\n|---|---|---|---|---|---|---|')
        for i in sorted(set(P) | set(A)):
            p, r = P.get(i, {}), A.get(i, {}); d = ''
            if p.get('pred_bounce2s') and r.get('bounce2s'): d = f"{float(r['bounce2s'])-float(p['pred_bounce2s']):+.1%}"
            print(f"| {i} | {p.get('verdict','')} | {p.get('pred_bounce2s','')} | {r.get('bounce2s','')} | {r.get('completion','')} | {r.get('shares','')} | {d} |")
        C = json.load(open(os.path.join(ROOT, 'out/calibration.json'))) if os.path.exists(os.path.join(ROOT, 'out/calibration.json')) else {'ids': []}
        new = [i for i in A if i not in C['ids'] and A[i].get('bounce2s')]
        print(f'\n校准后新增真实数据 {len(new)} 条' + ('（≥5，该跑 calibrate.py 并考虑改 rubric）' if len(new) >= 5 else ''))
if __name__ == '__main__': main()
