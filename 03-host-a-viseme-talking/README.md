# host-a-viseme-talking：语音时间轴口型渲染（v4）

**做什么**：先用 faster-whisper 对配音做逐字时间对齐（`asr.py`），再把每个字映射到口型（viseme），配合眨眼、轻微呼吸位移，把静态立绘渲染成说话视频（`render_v4.py`）。`sprites.py / gsprites.py` 生成口型、眼睛分层素材。迭代记录见 `NOTES.md`（v1→v4）。

**运行**：`python asr.py` → `python render_v4.py`（需 numpy、Pillow、opencv、faster-whisper、ffmpeg；路径需按本地修改）

**效果**：[../videos/03_host_a_viseme_v4.mp4](../videos/03_host_a_viseme_v4.mp4)
