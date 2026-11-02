#!/usr/bin/env python3
"""逐字稿立场/红线/配音友好度检查（2026-10-30 首期教训：v1 稿「我们无法证明苹果是故意这样定价的」被用户骂含糊、替被讲对象辩护）。
  python3 tools/qc/script_lint.py script/v1_draft.md [--json out.json]
读取「N. 句子」格式的编号句。FAIL 项必须改完才交「文案通过」；WARN 项人工过一眼。
规则：
  FAIL 事实红线：把推断说成事实/指控动机（「X 承认」「故意坑你」「内部文件」「就是在骗你」等）——结构可以骂，动机不能编。
  FAIL 含糊/辩护：替被讲对象开脱或和稀泥（「无法证明…故意」「也不能怪」「情有可原」「见仁见智」「商家也要赚钱」等）。
  WARN 配音易喊：感叹号、「居然」「震惊」「破防」类（§1.1-4）。
  WARN 分句超长：任一逗号分句 >16 字（oneline.py 会被迫硬拆）。
  WARN 立场缺失：前 25% 的句子里没有判定句（「这是套路/这不是巧合/就是/根本/别再/记住」等）。
"""
import re, sys, json, argparse
RED = [r'(苹果|官方|商家|平台|厂商|公司|[A-Za-z]+)\S{0,3}(亲口)?承认', r'故意(坑|骗|割|宰)', r'内部(文件|资料)(显示|曝光)', r'就是在骗你', r'实锤', r'百分之百|100%的人', r'所有人都(会|被)']
HEDGE = [r'无法证明.{0,12}故意', r'不(一定|能说)是故意', r'也不能怪', r'情有可原', r'无可厚非', r'见仁见智', r'各有各的道理', r'商家也要(赚钱|吃饭)', r'也(很)?(正常|合理)', r'公平(地|来)说', r'客观(地|来)说', r'也许只是', r'可能只是巧合', r'别(太)?(苛责|上纲上线)', r'说不定.{0,6}好意']
SHOUT = [r'！|!', r'居然', r'震惊', r'破防', r'太离谱了吧']
STANCE = r'套路|不是巧合|就是|根本|别再|记住|你被|摆给你|看穿|才是'
PUNCT = '，。？！；：、…,.?!;:'
def sents(p):
    out = []
    for i, line in enumerate(open(p, encoding='utf-8'), 1):
        m = re.match(r'^\s*(\d+)[.．、]\s*(.+?)\s*$', line)
        if m: out.append((int(m.group(1)), i, m.group(2)))
    return out
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('script'); ap.add_argument('--json'); a = ap.parse_args()
    S = sents(a.script); hits = []
    for n, ln, s in S:
        for kind, pats in (('FAIL·事实红线', RED), ('FAIL·含糊/辩护', HEDGE), ('WARN·配音易喊', SHOUT)):
            for p in pats:
                if re.search(p, s): hits.append((kind, n, ln, s, p)); break
        for c in re.split('[' + PUNCT + ']', s):
            if len(re.sub(r'\s', '', c)) > 16: hits.append(('WARN·分句超长', n, ln, s, c))
    head = S[:max(1, len(S) // 4)]
    if not any(re.search(STANCE, s) for _, _, s in head): hits.append(('WARN·立场缺失', 0, 0, '前 25% 没有判定句', STANCE))
    nf = sum(h[0].startswith('FAIL') for h in hits)
    print(f'# 逐字稿检查 {a.script}：{len(S)} 句；FAIL {nf}，WARN {len(hits) - nf}')
    for k, n, ln, s, p in hits: print(f'- {k}｜第 {n} 句（行 {ln}）｜{s}｜命中 {p}')
    if a.json: json.dump([dict(kind=k, n=n, line=ln, text=s, rule=p) for k, n, ln, s, p in hits], open(a.json, 'w'), ensure_ascii=False, indent=1)
    sys.exit(1 if nf else 0)
if __name__ == '__main__': main()
