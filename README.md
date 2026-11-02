# AI 视频创作工具集（作品集）

本仓库整理了我在 AI 辅助科普短视频制作方向上**已跑通、有成功示例**的工具和流水线。每个子目录是一个独立项目，均附中文说明和演示视频。

| # | 项目 | 做什么 | 演示 |
|---|---|---|---|
| 01 | [sprite-talk](01-sprite-talk/) | 2D 立绘说话：按音量开合嘴型、自动眨眼、动作预设、姿态切换（Python 包，带测试） | [videos/01_sprite_talk_host_o.mp4](videos/01_sprite_talk_host_o.mp4)；独立仓库：[zwjym1/sprite-talk](https://github.com/zwjym1/sprite-talk) |
| 02 | [host-o-pose-swap](02-host-o-pose-swap/) | 角色多姿态立绘切换 + 眨眼/口型面部编辑的渲染管线（posekit） | [videos/02_pose_swap_posekit.mp4](videos/02_pose_swap_posekit.mp4) |
| 03 | [host-a-viseme-talking](03-host-a-viseme-talking/) | 基于语音识别时间轴的口型（viseme）说话渲染 v4 | [videos/03_host_a_viseme_v4.mp4](videos/03_host_a_viseme_v4.mp4) |
| 04 | [science-video-pipeline](04-science-video-pipeline/) | 科普短视频生产流水线：质检脚本、审片系统、心理学系列模板；已产出并发布成片 | — |
| 05 | [douyin-field-collect](05-douyin-field-collect/) | 免登录抖音同题视频数据采集（详情/字幕/评论/BGM 卡点分析） | — |
| 06 | [watch-video](06-watch-video/) | “看视频”工具：链接 → 元数据、逐字稿、关键帧拼图、评论 | — |

## 技术栈
Python（NumPy / OpenCV / Pillow / ffmpeg）、faster-whisper 语音识别、Remotion（React 视频模板）、多模态大模型辅助质检。

## 试过但未采用的方案
LivePortrait、LatentSync、THA3（Talking Head Anime 3）等神经网络驱动方案在本项目画风上效果不稳定，最终采用了更可控的 2D 立绘 + 规则驱动方案（项目 01–03）。

## 说明
- 角色立绘均为 AI 生成的原创角色。
- 演示视频已压缩（H.264, CRF 26）。
- 许可证：MIT。
