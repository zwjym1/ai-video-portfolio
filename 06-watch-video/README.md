# watch-video：让 AI “看”视频

**做什么**：输入抖音 / B站 / YouTube 链接或本地文件，免登录拿到元数据、逐字稿（faster-whisper）、关键帧拼图、开头 3 秒拼图、评论/弹幕，供多模态模型做画面拆解，用于对标视频分析。

**运行**：`python watch.py <链接或文件>`（需 ffmpeg、yt-dlp、faster-whisper、requests、Pillow；playwright 可选）。详细说明见 `SKILL.md`。
