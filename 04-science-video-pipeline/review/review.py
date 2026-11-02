#!/workspace/.venv-review/bin/python
"""一条片子一键审：ASR → 客观层 → 拼图 → qoder-flash 盲审(1~2 轮) → 合并 → 返修单。
用法:
  review.py --id EP-xxx --video 成片.mp4 [--srt 字幕.srt | --asr asr.json] [--facts facts.md] [--cover 封面.png]
            [--publish 发布文案.md] [--beats beat_map.json] [--ai] [--nobgm 1] [--frames-dir PC抽好的帧目录] [--runs 2] [--skip-subjective]
重计算放 PC：先在 PC 上跑 pc/pc_frames.ps1 抽帧（Downloads 下新建目录），CopyToBox 拿回 zip，解压后用 --frames-dir 传进来；
PC 不在线就不传 --frames-dir，sheets.py 自动回退到盒上 ffmpeg。qoder-flash 永远在盒上跑。
v2 新增（全部可选、失败不致命，旧命令行不变）：
  默认多跑 剪辑质量 lib/cutquality.py + BGM 契合 lib/bgmfit.py（--no-edit 关掉）；--proxy-dir 给 PC 上 pc/pc_proxy.ps1 产出的 <id> 目录（proxy.mp4/audio.flac）
  --design-cuts ShotsV2.tsx（或 {"cuts":[..]} json）→ 能查「设计外切点」并用 REAL 集校验风格分类；--focus → 跑分段精审 lib/focus_run.py（+自动假阳性校验）
  --bgm-note "现版 BGM 描述" 给精审参考。
v2.1（2026-10-29）：默认多跑 0–2s 开头提示 lib/gate02.py（只看前 2 秒的路人划走测试，qoder-flash-qwen）；单独打分、在返修单单列，不影响结论。"""
import argparse, os, subprocess, sys, time, json
ROOT = os.path.dirname(os.path.abspath(__file__)); PY = '/workspace/.venv-review/bin/python'; DY = '/workspace/.venv-dy/bin/python'
def run(cmd, **kw):
    t = time.time(); print('»', ' '.join(cmd)[:200], flush=True); subprocess.run(cmd, check=True, cwd=ROOT, **kw); return round(time.time()-t, 1)
ap = argparse.ArgumentParser()
for k in ('id', 'video', 'srt', 'asr', 'facts', 'cover', 'publish', 'beats', 'nobgm', 'frames_dir', 'title'): ap.add_argument('--'+k.replace('_', '-'), dest=k)
ap.add_argument('--proxy-dir'); ap.add_argument('--design-cuts'); ap.add_argument('--bgm-note', default=''); ap.add_argument('--focus', action='store_true'); ap.add_argument('--no-edit', action='store_true')
ap.add_argument('--ai', action='store_true'); ap.add_argument('--runs', type=int, default=2); ap.add_argument('--skip-subjective', action='store_true')
a = ap.parse_args(); out = os.path.join(ROOT, 'out', a.id); os.makedirs(out, exist_ok=True); T = {}
asr = a.asr or os.path.join(out, 'asr.json')
if not a.asr: T['asr'] = run([DY, 'lib/asr.py', a.video, asr] + (['--srt', a.srt] if a.srt else []))
cmd = [PY, 'lib/objective.py', '--video', a.video, '--asr', asr, '--out', os.path.join(out, 'objective.json')]
for k in ('cover', 'facts', 'publish', 'beats', 'nobgm'):
    if getattr(a, k): cmd += ['--'+k, getattr(a, k)]
if a.ai: cmd.append('--ai')
T['objective'] = run(cmd)
T['sheets'] = run([PY, 'lib/sheets.py', a.video, os.path.join(out, 'sheets')] + (['--frames-dir', a.frames_dir] if a.frames_dir else []))
runs = []
if not a.skip_subjective:
    for i in range(1, a.runs+1):
        r = f'r{i}'; runs.append(r)
        T['subjective_'+r] = run([PY, 'lib/subjective.py', '--sheets', os.path.join(out, 'sheets'), '--asr', asr, '--out', os.path.join(out, f'subjective_{r}.json')] + (['--title', a.title] if a.title else []))
def soft(name, cmd):
    try: T[name] = run(cmd)
    except Exception as e: print(f'!! {name} 失败（不影响其余步骤，merge 会跳过该维度）:', e, flush=True); T[name] = None
if not a.no_edit:
    px = os.path.join(a.proxy_dir, 'proxy.mp4') if a.proxy_dir else None; pa = os.path.join(a.proxy_dir, 'audio.flac') if a.proxy_dir else None
    cq = [PY, 'lib/cutquality.py', '--video', a.video, '--out', os.path.join(out, 'cutquality.json'), '--asr', asr, '--objective', os.path.join(out, 'objective.json')]
    if px and os.path.exists(px): cq += ['--proxy', px]
    soft('cutquality', cq)
    if a.design_cuts:
        soft('cutquality_design', cq[:5] + [os.path.join(out, 'cutquality_design.json')] + cq[6:] + ['--design-cuts', a.design_cuts, '--style-truth', a.design_cuts])
    bf = [DY, 'lib/bgmfit.py', '--video', a.video, '--out', os.path.join(out, 'bgmfit.json'), '--asr', asr, '--objective', os.path.join(out, 'objective.json')]
    if pa and os.path.exists(pa): bf += ['--audio', pa]
    soft('bgmfit', bf)
    if a.focus:
        fr = [PY, 'lib/focus_run.py', '--id', a.id, '--video', a.video, '--asr', asr, '--bgm-note', a.bgm_note]
        if a.design_cuts: fr += ['--design-cuts', a.design_cuts, '--cutq', os.path.join(out, 'cutquality_design.json')]
        soft('focus_run', fr)
if not a.skip_subjective:
    soft('gate02', [PY, 'lib/gate02.py', '--video', a.video, '--asr', asr, '--out', os.path.join(out, 'gate02.json')])   # 0–2s 单独路人划走测试（提示项，不拦放行）
T['merge'] = run([PY, 'lib/merge.py', '--id', a.id, '--runs', ','.join(runs) or 'none'])
json.dump(T, open(os.path.join(out, 'timing.json'), 'w')); print(open(os.path.join(out, '返修单.md')).read()); print('耗时(s):', T)
