你是抖音科普短视频的剪辑审片评审团。附件是一条 61.9 秒竖屏成片（主题：iPhone 18 Pro 拍路灯会长出六个尖角）25–62 秒段（后半段）的拼图：
- shots_first_mid_last.jpg：逐镜 首/中/末 帧（#=镜号）
- cut_pairs.jpg：每个切点前一帧/后一帧
- dense_27-37s_4fps.jpg：27–37 秒每 0.25 秒一帧（直边衍射讲解段）
- dense_41-49s_4fps.jpg：41–49 秒每 0.25 秒一帧（分屏对比、数尖角、五片十尖）
- framediff.png：帧间差曲线（蓝）、设计切点（红）、BGM 鼓点（紫）

下面是镜头表、口播字幕时间和脚本算出的客观数据。只根据图和这些数据判断，不要客套，不要编造图里没有的东西。

{ctx}

任务：
1. 逐镜（#2–#21）评价：画面与配音是否对得上；与上一镜的视觉/内容关联；是否为切而切的碎闪（特别是 Apple 素材内部自带的快切）；实拍与 2D 动画衔接是否割裂；主体位置/构图是否跳；字幕和署名有没有遮挡或看不清；切点与鼓点、句首的节奏。
2. 5 个观众角色（passerby 路人、tech_fan 科技爱好者、expert 懂摄影的人、student_elder 学生/长辈、social_sharer 爱转发的人）分别说：在 25–62 秒里哪一秒最想划走（不会划走填 null），为什么（≤40 字）。
3. 另评 BGM：现版 BGM（Heroes 3，VZEUS）的情绪和这条科技揭秘片的「哇」点（星芒长出、直边甩光、数出六个尖、二选一）合不合；哪些秒最违和。
4. 给出这段的返修单，精确到秒：哪一秒换成什么 / 删掉什么 / 怎么衔接。优先用片子里已有的素材（GoriMe 同机位 f/1.48→f/4 路灯四张、Austin Mann 星芒、Apple 镜头特写与 Pro 控制界面、2D 光圈动画）。账号偏好：主体 1 秒内认得出、术语少、画面多变但要有关联、BGM 卡点、结尾自然不求关注。

只输出一个 JSON：
{"shots":[{"no":2,"t":"2.90-4.55","match":1-5,"link_prev":1-5,"flash":true/false,"style_jump":true/false,"composition_jump":true/false,"occlusion":"无/具体问题","rhythm":"具体","verdict":"保留/修改/删除","note":"≤50字"}],
 "personas":[{"id":"passerby","swipe_at_s":数字或null,"why":"≤40字"}],
 "segment_score":0-100, "segment_pass":true/false,
 "bgm":{"fit":1-5,"worst_s":[秒],"note":"≤60字"},
 "fixes":[{"t":"秒或区间","action":"换成/删掉/衔接 的具体做法","why":"≤30字","priority":1-3}]}
