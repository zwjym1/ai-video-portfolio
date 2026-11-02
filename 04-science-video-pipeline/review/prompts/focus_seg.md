你是抖音科普短视频（「热门科技和奇观背后的原理」）的剪辑审片评审团。附件是成片 {a}–{b} 秒这一段：
- shots.jpg：本段每个镜头的首/中/末帧（左上角 #镜号 和秒数）
- dense.jpg：本段每 {step} 秒一帧（左上角是秒数）

下面是脚本已经量好的客观数据（闪帧/运动/实拍-2D/口播字幕时间）。**闪帧、字幕有无以脚本数据为准**：脚本说是「快速运动」「叠化」的地方不要再说成快闪；字幕时间表里有的句子就是有字幕。只根据图和数据判断，不要编造图里没有的东西，不要客套。

{ctx}

任务（只评 {a}–{b} 秒）：
1. 逐镜判断：画面与口播是否对得上（举出画面里的具体东西）；与上一镜的关联；是否为切而切的碎切；实拍↔2D 是否来回跳；构图/主体位置跳不跳；字幕或署名是否被挡；切点是否卡句首/鼓点。
2. 5 个观众（passerby 路人、tech_fan 科技爱好者、expert 懂行的人、student_elder 学生/长辈、social_sharer 爱转发的人）在本段哪一秒最想划走（不会就 null），≤30 字理由。
3. 本段返修单（精确到 0.1 秒；优先用片里已有素材）。
4. 本段 BGM 与画面情绪是否搭（只凭数据里的 BGM 描述 + 画面节奏判断，标「需人耳确认」）。

只输出一个 JSON，不要别的文字：
{"segment":[{a},{b}],"shots":[{"no":1,"t":"a-b","match":1-5,"issues":[{"type":"flash|fragment|style_jump|vo_mismatch|composition|subtitle|rhythm|other","t":秒,"note":"≤30字"}],"verdict":"保留|修改|删"}],
 "personas":[{"id":"passerby","swipe_at_s":秒或null,"why":"…"}],
 "segment_score":0-100,"fixes":[{"t":"a-b","action":"…","why":"…","priority":1-3}],"bgm":{"fit":0-100,"note":"…"}}
