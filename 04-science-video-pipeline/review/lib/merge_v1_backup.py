#!/workspace/.venv-review/bin/python
"""合并客观层 + 主观层 → 分数、一票否决、结论、返修单。
用法: merge.py --id <id> [--rubric config/rubric.json] [--runs r1,r2]  → out/<id>/verdict.json + 返修单.md"""
import argparse, json, os, re, statistics as st
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)

def pl(x, pts):
    if x is None: return None
    xs, ys = zip(*pts); return float(np.interp(x, xs, ys))

def load_subj(id_, runs):
    out = []
    for r in runs:
        p = os.path.join(ROOT, f'out/{id_}/subjective_{r}.json')
        if os.path.exists(p):
            J = json.load(open(p))
            if J.get('ok') and J.get('result'): out.append(J['result'])
    return out

def subj_scores(S, PW):
    """多轮主观结果取平均；返回 0-100 的 hook/body/value + 预测比例。"""
    if not S: return None
    agg = []
    for R in S:
        P = {p['id']: p for p in R.get('personas', [])}
        w = {k: v for k, v in PW.items() if k in P}; tw = sum(w.values()) or 1
        wm = lambda f: sum(w[k]*f(P[k]) for k in w)/tw
        sc = lambda dim: wm(lambda p: (p['scores'].get(dim, 3)-1)/4*100)
        f0 = R.get('frame0', {}) or {}
        agg.append(dict(
            stay2=wm(lambda p: float(bool(p.get('stay_2s')))), stay5=wm(lambda p: float(bool(p.get('stay_5s')))),
            finish=wm(lambda p: float(bool(p.get('finish')))), share=wm(lambda p: float(bool(p.get('share')))),
            save=wm(lambda p: float(bool(p.get('save')))),
            swipe_med=st.median([p['swipe_at_s'] if p.get('swipe_at_s') is not None else 999 for p in P.values()]),
            hook=sc('hook'), clarity=sc('clarity'), novelty=sc('novelty'), payoff=sc('payoff'), visual=sc('visual'), emotion=sc('emotion'),
            f0_rec=bool(f0.get('recognizable')), f0_conf=float(f0.get('confidence') or 0), f0_subject=f0.get('subject')))
    m = {k: (float(np.mean([a[k] for a in agg])) if isinstance(agg[0][k], (int, float, bool)) else agg[0][k]) for k in agg[0]}
    m['S_hook'] = 0.5*m['stay2']*100 + 0.5*m['hook']
    m['S_body'] = 0.3*m['clarity'] + 0.25*m['visual'] + 0.2*m['emotion'] + 0.25*m['finish']*100
    m['S_value'] = 0.35*m['payoff'] + 0.25*m['novelty'] + 0.25*m['share']*100 + 0.15*m['save']*100
    m['runs'] = len(agg)
    if len(agg) > 1: m['run_spread_hook'] = round(abs(agg[0]['hook']-agg[1]['hook']), 1); m['run_spread_stay2'] = round(abs(agg[0]['stay2']-agg[1]['stay2']), 2)
    return m

def obj_scores(O, R, m):
    T = O.get('text', {}); sub = O.get('subtitles', {}); L = O['loudness']['full']; H = R['hook_obj']; B = R['body_obj']
    f0 = (m['f0_conf']*100 if m and m['f0_rec'] else (m['f0_conf']*30 if m else 50)) - (20 if O['frame0']['luminance'] < 0.10 else 0)
    info = min(5, T.get('first3s_info_points', 0))
    ft = T.get('first_term_s'); h = dict(
        frame0_probe=max(0, f0), first_voice_s=pl(T.get('first_voice_s', 2), H['first_voice_s']['map']),
        info3=pl(info, H['info3']['map']), no_term_10s=100.0 if ft is None else pl(ft, H['no_term_10s']['map']),
        visual3=pl(O['visual_first3s']['mean_diff'], H['visual3']['map']))
    I, TP = L.get('I_LUFS'), L.get('TP_dBTP')
    loud = 100 - (0 if I is None or -17 <= I <= -13 else 15*min(abs(I+17), abs(I+13))) - (30 if TP is not None and TP > -1 else 0)
    bs = O['beat_sync']; bgm = (O.get('bgm_presence') or {}).get('gap_db')
    beat = 50.0 if (bgm is not None and bgm < -60) or bs.get('lift') is None else pl(bs['lift'], B['beat_sync']['map'])
    cm = O.get('cover_match', {})
    cov = 60.0 if not cm.get('cover') else (100.0 if cm['color_hist_corr'] >= 0.8 and cm['gray_corr'] >= 0.4 else 60.0 if cm['color_hist_corr'] >= 0.8 else 30.0)
    b = dict(cps=pl(T.get('cps_speech'), B['cps']['map']), terms_per_min=pl(T.get('terms_per_min'), B['terms_per_min']['map']),
             info_max_gap=pl(T.get('new_info_max_gap_s'), B['info_max_gap']['map']), static_s=pl(O['visual']['longest_static_s'], B['static_s']['map']),
             sub_height=pl(sub.get('main_subtitle_height_frac') or sub.get('median_text_height_frac'), B['sub_height']['map']),
             sub_contrast=pl(sub.get('median_contrast'), B['sub_contrast']['map']), loudness=max(0, loud), beat_sync=beat, cover=cov)
    wsum = lambda d, W: sum((d[k] if d[k] is not None else 50)*W[k]['w'] for k in d)/sum(W[k]['w'] for k in d)
    return h, b, wsum(h, H), wsum(b, B)

def bigrams(t):
    t = re.sub(r'[^\u4e00-\u9fffA-Za-z0-9./]', '', t); return {t[i:i+2] for i in range(len(t)-1)}

def fact_covered(claim, facts_rows, facts_nums):
    nums = set(re.findall(r'\d+(?:\.\d+)?', claim))
    if nums and nums <= facts_nums: return True
    cb = bigrams(claim)
    return bool(cb) and max((len(cb & bigrams(r))/len(cb) for r in facts_rows), default=0) >= 0.30  # 粗匹配，返修单里人工复核

def vetoes(O, S, facts_nums, facts_rows=(), ai_kind='visual'):
    V, MUST = [], []
    C = O['compliance']; F = O['facts']; T = O.get('text', {}); L = O['loudness']['full']
    if ai_kind == 'voice':
        if C['publish_declares_ai'] is False: V.append('配音为 AI 合成，但发布声明里没写「内容由AI生成」')
        if not C['in_video_ai_label']: MUST.append('配音为 AI 合成，片内没有文字提示：发布时勾「内容由AI生成」平台会加标识；稳妥起见片尾署名行加「配音为 AI 合成」（《人工智能生成合成内容标识办法》对合成人声也要求显式标识）')
        C = dict(C, impersonation_risk=False)
    else:
        if C['ai_content'] and not C['in_video_ai_label']: V.append('AI 生成画面但片内没有「AI 生成/示意」角标')
        if C['ai_content'] and C['publish_declares_ai'] is False: V.append('AI 生成内容，发布文案/声明里没写「内容由AI生成」')
    if C.get('impersonation_risk'): V.append(f"出现「{'/'.join(C['claims_real_footage'])}」字样但无出处或片子含 AI 画面（冒充实拍风险）")
    if F['facts_file'] is None: MUST.append('没有事实表（facts.md）：口播里的数字无法核对出处')
    elif F['coverage'] < 0.8: MUST.append(f"口播数字 {F['unsourced']} 在事实表里找不到（覆盖率 {F['coverage']:.0%}，ASR 误识别也可能导致，需人工复核）")
    I, TP = L.get('I_LUFS'), L.get('TP_dBTP')
    if I is not None and not -20 <= I <= -10: V.append(f'整体响度 {I} LUFS 超出 -20..-10')
    if TP is not None and TP > -1: MUST.append(f'真峰值 {TP} dBTP > -1（可能削波），母带加 -1 dBTP 限幅')
    if T.get('ending_cta'): MUST.append(f"结尾在求互动/关注（{T['ending_cta']}），与账号偏好「结尾自然、不求关注」冲突")
    for R in S:
        for fl in R.get('fact_flags', []) or []:
            covered = fact_covered(fl.get('claim', ''), facts_rows, facts_nums)
            try: t = float(str(fl.get('t')).split('-')[0])
            except ValueError: t = -1
            near = ' '.join(x['text'] for x in O.get('ocr_timeline', []) if abs(x['t']-t) <= 2)
            if covered and re.search(r'来源|出处|伪造|发布会|字样', fl.get('issue', '')) and '来源' in near:
                MUST.append(f"{fl.get('t')}s 片内已有出处字样（OCR：{re.search(r'来源[^|]*', near).group(0).strip()[:40]}），但评审团看错/当成伪造 → 出处字放大、加底、停留≥2 秒"); continue
            tag = f"{fl.get('t')}s「{fl.get('claim','')[:30]}」：{fl.get('issue','')[:80]}"
            if fl.get('severity') == 'high' and not covered: V.append('懂行者硬伤（事实表未覆盖）：' + tag)
            elif fl.get('severity') in ('high', 'mid'):
                MUST.append(('事实已核但观众会质疑 → 画面上把出处写大写清：' if covered else '懂行者质疑，需核实：') + tag)
    ocr = ' '.join(x['text'] for x in O.get('ocr_timeline', []))
    third = re.findall(r'(?:画面|样张|素材)[:：]\s*([A-Za-z\u4e00-\u9fff ·]{2,20})', ocr)
    third = [re.split(r'[·（(]|iPhone|iphone', t)[0].strip() for t in third]
    if third: MUST.append(f"用了第三方素材（片内署名：{'、'.join(sorted(set(t for t in third if t))[:6])}）：署名≠授权，抖音对搬运/非原创会限流，发前确认授权或合理引用（解说为主、引用片段短）")
    top = [t for t in (O.get('subtitles', {}).get('top6pct_texts') or []) if re.search(r'来源|画面|样张|AI|示意|合成', t)]
    if top: MUST.append(f"署名/出处/AI 标识放在画面最顶 6%（如「{top[0][:24]}」），手机上会被抖音顶部「推荐/关注」栏挡住：下移到 8%–12% 高度（经验值 未核）")
    sm = subj_scores(S, {'passerby': 1}) if S else None
    if sm and not sm['f0_rec'] and (T.get('first_voice_s') or 0) > 1.0: V.append('第一帧路人认不出主体，且 1 秒后才开口')
    return V, list(dict.fromkeys(MUST))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--id', required=True); ap.add_argument('--rubric', default=os.path.join(ROOT, 'config/rubric.json'))
    ap.add_argument('--runs', default='r1,r2'); ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args(); R = json.load(open(a.rubric))
    O = json.load(open(os.path.join(ROOT, f'out/{a.id}/objective.json'))); S = load_subj(a.id, a.runs.split(','))
    m = subj_scores(S, R['persona_weights'])
    h, b, HO, BO = obj_scores(O, R, m)
    ff = O['facts']['facts_file']; ftxt = open(ff).read() if ff else ''
    fnums = set(re.findall(r'\d+(?:\.\d+)?', ftxt)); frows = [l for l in ftxt.splitlines() if l.startswith('|')]
    ent = {e['id']: e for e in json.load(open(os.path.join(ROOT, 'corpus/corpus.json')))['videos']}.get(a.id, {})
    V, MUST = vetoes(O, S, fnums, frows, ent.get('ai_kind', 'visual'))
    mx = R['mix']
    hook = mx['hook']['obj']*HO + mx['hook']['subj']*(m['S_hook'] if m else HO)
    body = mx['body']['obj']*BO + mx['body']['subj']*(m['S_body'] if m else BO)
    value = m['S_value'] if m else None
    total = mx['total']['hook']*hook + mx['total']['body']*body + mx['total']['value']*(value if value is not None else body)
    p = R['pass']
    verdict = '不可发（一票否决）' if V else ('可发' if total >= p['total'] and hook >= p['hook'] and not MUST else ('改完必改项后可发' if total >= p['total'] and hook >= p['hook'] else ('小改后可发' if total >= p['revise_band'] else '返修')))
    ban = R['house_prefs']['ban_fix_keywords']; fixes = []
    for r in S:
        for f in r.get('fixes', []) or []:
            if any(k in f.get('fix', '') for k in ban): continue
            fixes.append(f)
    out = dict(id=a.id, verdict=verdict, total=round(total, 1), hook=round(hook, 1), body=round(body, 1), value=None if value is None else round(value, 1),
               hook_obj=round(HO, 1), body_obj=round(BO, 1), hook_obj_items={k: None if v is None else round(v, 1) for k, v in h.items()},
               body_obj_items={k: None if v is None else round(v, 1) for k, v in b.items()},
               subj=None if not m else {k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()}, vetoes=V, must_fix=MUST, persona_fixes=fixes[:8])
    json.dump(out, open(os.path.join(ROOT, f'out/{a.id}/verdict.json'), 'w'), ensure_ascii=False, indent=1)
    # 返修单
    L = [f"# 返修单 · {a.id}", f"结论：**{verdict}**　总分 {out['total']}（钩子 {out['hook']} / 正文 {out['body']} / 收获 {out['value']}）　及格线：总分≥{p['total']} 且钩子≥{p['hook']}，无否决项", ""]
    if V: L += ['## 一票否决（不改不能发）'] + [f'- [ ] {x}' for x in V] + ['']
    if MUST: L += ['## 必改'] + [f'- [ ] {x}' for x in MUST] + ['']
    low = sorted([(v, k) for k, v in {**h, **b}.items() if v is not None and v < 60])
    if low: L += ['## 客观低分项（<60）'] + [f'- {k}: {v:.0f}' for v, k in low] + ['']
    if fixes: L += ['## 评审团建议（按收益排序，已滤掉违背账号偏好的建议）'] + [f"- [ ] {f.get('t')}：{f.get('fix')}（{f.get('why','')}）" for f in fixes[:6]] + ['']
    if m: L += ['## 评审团预测', f"- 过 2 秒 {m['stay2']:.0%}，过 5 秒 {m['stay5']:.0%}，看完 {m['finish']:.0%}，分享 {m['share']:.0%}，收藏 {m['save']:.0%}（加权人设比例，不是真实比率）"]
    open(os.path.join(ROOT, f'out/{a.id}/返修单.md'), 'w').write('\n'.join(L))
    if not a.quiet: print(json.dumps({k: out[k] for k in ('id','verdict','total','hook','body','value','hook_obj','body_obj')}, ensure_ascii=False))

if __name__ == '__main__': main()
