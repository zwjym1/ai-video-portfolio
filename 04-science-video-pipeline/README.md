# science-video-pipeline：科普短视频生产流水线

**做什么**：把一期抖音科普短视频从文案到成片的“制作—质检—审片”环节工具化。

- `qc/final_check.py`：成片终检（分辨率、时长、响度、黑帧/静音等）；`script_lint.py`：口播文案检查；`beat_grid.py`：BGM 节拍网格
- `review/`：发布前审片系统原型（客观指标 + 多模态模型主观评审，详见 `review/README.md`）
- `templates/psych_series/`：心理学系列模板（Remotion 画面 + 音频混音 + `init_ep.sh` 初始化一期）

**成果**：第 1 期《iPhone 存储分档里的诱饵（诱饵效应）》已用本流水线完成并发布（成片不收录在本仓库）。

**运行**：`python qc/final_check.py <成片.mp4>`；审片见 `review/README.md`。
