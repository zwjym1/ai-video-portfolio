# 「你被设计了吗」系列模板（psych_series）

来源：EP-20261031-01（iPhone 存储分档里的诱饵效应）实际跑通的代码，2026-10-30 抽出。目标：一期 ≈40 分钟（不含等用户批稿）。

## 目录
| 路径 | 是什么 |
|---|---|
| `init_ep.sh` | 新建期目录骨架 + 拷模板 + 复用 node_modules |
| `remotion/src/episode.json` | 每期唯一要改的参数：时长、拍点网格（beat_grid.py 实测值）、封面文字 |
| `remotion/src/common/OneLineSubtitles.tsx` | 一句一卡字幕组件（= lib/remotion 版，未改）。单行、不换行、字号按句长自动缩，top=1560 |
| `remotion/src/common/beats.ts` | `B(k)=offset+k·period`、`BM(k)=B(k)−1帧`（画面提前 1 帧，首个可见变化落拍）、`makeEvents()` |
| `remotion/src/common/motion.ts` | 只允许的缓动：`lerp/fadeIn/fadeOut/win/xfade(≥0.5s)`；安全区常量 `SAFE` |
| `remotion/src/Film.tsx` | 成片骨架：第 0 帧即有画面+第一句字幕；场景只用交叉淡化/共享元素形变 |
| `remotion/src/film_events.json` | 事件表（id,k,desc,sfx,f,lvl）——画面和混音共用，音画同拍 |
| `remotion/src/Cover.tsx` | 封面 9:16（1080×1920，文字全在 y240–1680）+ 4:3（1440×1080，文字靠左 x70–750）；每期只换 `<Visual/>` 和 episode.json 文字 |
| `remotion/scripts/{render,stills,cover}.mjs` | 成片无声渲染 / 指定秒数截图 / 两版封面（gl=swangle，盒上无 GPU） |
| `audio/mix_film.py` + `mix_config.json` | 通用混音：VO −16 / BGM −24 / duck −5 / 总 −16 LUFS / alimiter 0.80；BGM 小节线拼接；音效放在 B(k) |
| 质检脚本（不复制，直接调用） | `tools/qc/script_lint.py`、`tools/qc/beat_grid.py`、`tools/qc/final_check.py`、`scripts/subs/oneline.py` |

模板自测（2026-10-30 18:5x UTC+8，实测）：用 EP01 的 vo_v3 + 同一 BGM 跑 `audio/mix_film.py` → −16.0 LUFS、LRA 2.6、TP −1.6 dBTP（ebur128 peak=true），BGM stem 网格 0.2711+k·0.51282（117.0 BPM，187/188 拍匹配）；Remotion 模板 `stills.mjs`/`cover.mjs` 渲染通过，第 0 帧有画面。

## 最短流程（‖ = 可以并行）
```
0. bash templates/psych_series/init_ep.sh projects/EP-…            1 分钟
1. 逐字稿 script/v1_draft.md（「N. 句子」一行一句）
   → python3 tools/qc/script_lint.py script/v1_draft.md             门禁：0 FAIL 才给用户批
   ‖ 同时：挑 BGM（sfx/bgm/）、找真实产品图放 remotion/public/real/、写 film_events.json 初稿
2. 用户批稿 → script/v1_approved.md
3. 配音（Fish，固定音色 906524668b6d4afe84736962e005cd09，整稿一条 take）→ vo/vo_v1.wav
   → ASR 词级时间戳（faster-whisper；EP01 实测 Fish 自带时间戳在 5 张卡上偏早 0.5–1.1s，所以用 ASR）
   参考实现：projects/EP-20261031-01/vo/{timing.py,asr_check.py}、subs/{asr_words.py,asr_cards_v3.py}
   ‖ 同时：python3 tools/qc/beat_grid.py <裁好入点的 BGM> --out final/beatcheck/beat_grid_src.json → 把 offset/period 填进 episode.json 和 mix_config.json
4. 字幕：python3 scripts/subs/oneline.py --cards subs/cards.json --words subs/asr_words.json \
         --out-json subs/subs_oneline.json --out-srt deliver/成片.srt --out-ts remotion/src/subs_oneline.ts
5. 画面：改 Film.tsx（事件全部引用 T.<id>）→ cd remotion && COMP=Film node scripts/stills.mjs out/st 0 3 8 …（只抽关键秒，别反复整片拼图）
   ‖ 同时：python3 audio/mix_film.py audio/mix_config.json → final/film_mix.wav
   ‖ 同时：cd remotion && node scripts/cover.mjs ../deliver
6. 整片：cd remotion && COMP=Film node scripts/render.mjs out/film_silent.mp4
   → ffmpeg -i remotion/out/film_silent.mp4 -i final/film_mix.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k -shortest deliver/成片_1080x1920.mp4
7. 脚本自检（一键，约 16 秒）：
   python3 tools/qc/beat_grid.py final/stem_bgm.wav --out final/beatcheck/beat_grid.json
   python3 tools/qc/final_check.py --video deliver/成片_1080x1920.mp4 --srt deliver/成片.srt \
       --grid final/beatcheck/beat_grid.json --script script/v1_approved.md --out review/qc_final
   → review/qc_final/qc_report.md 全 PASS 才进下一步；FAIL 直接按表里的时间点修，不要先给人看
8. 审片官（tools/review/）只看 qc 过了的片 ‖ 同时写 deliver/publish_copy.md
9. 交付：回报里的数字一律抄 qc_report.md；要声明数字时写 claims.json 跟 --claims 跑一遍，对不上就是 FAIL
```

## 规矩速查（全部被脚本量）
- 字幕：一句一卡、单行、≤16 字（去空格字符数）、句末不带 ，。、；：（？！可留）、不得两句拼一卡、第一张从 0.00s 起。
- 响度：−16 LUFS ±0.5、TP ≤ −1 dBTP。
- 丝滑：硬切 0、两帧亮度跳变 ≤17（EP01 成片 6.8；v2 试片 104 = 闪白）、闪白 0、整屏推近 0。
- 节拍：非字幕运动起点落拍（±2 帧）≥85%（EP01 成片 96.4%）。
- 时长 95–105s；1080×1920、30fps、带音轨。
- 立场：开头 25% 内要亮立场；禁「苹果承认/故意坑你/内部文件」这类事实红线，也禁「无法证明是故意的/也不能怪商家」这类替被讲对象辩护的话（script_lint 会 FAIL）。
