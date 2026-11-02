---
name: watch-video
description: >-
  需要「看」一条抖音/B站/YouTube 视频（给链接或本地文件，出元数据、逐字稿、关键帧拼图、开头 3 秒拼图、评论/弹幕），再交 Qoder Flash
  看画面拆解时使用；免登录。批量做抖音同题实地包用 douyin-field-collect。
---
# 看视频（watch.py + Qoder Flash）

## 准备
```bash
export PATH=/workspace/.venv-dy/bin:$HOME/.local/bin:$PATH
```
- `/workspace/.venv-dy`：faster-whisper、requests、Pillow 等（watch.py 首行就指向它）。
- `/workspace/.venv-watch`：playwright（解析站 snapany 用无头 Chrome，系统已有 google-chrome）。
- 系统：ffmpeg、curl、node；yt-dlp 在 `~/.local/bin`。

## 命令
```bash
/workspace/tools/watch.py <抖音/B站/YouTube 链接或BV号> [--frames 16] [--model small] [--no-asr] [--comments 200] [--out /workspace/watch]
/workspace/tools/watch.py --local /path/video.mp4 --id 名字      # 已有文件（用户电脑上的先拷进盒子）
/workspace/tools/watch.py <YouTube链接> --hd                      # 1080p
```
输出 `/workspace/watch/<平台>_<id>/`：meta.json、video.mp4、transcript.txt/.srt/.json、contact_sheet.jpg、hook_3s.jpg、frames/、comments.json、danmaku.json、report.md。

抖音下载顺序：iesdouyin 分享页（国内 IP 才有）→ dlpanda → snapany（无头浏览器）→ yt-dlp（抖音要 cookie，基本失败）。dlpanda 直链常 403，已补「403 后再试 snapany」。snapany 下载较慢；卡住或全失败时：先用 `douyin-field-collect` 的 `dy_collect.py video <ID> --media --keep-video` 下载，再 `watch.py --local`。

## 看画面（交给 Qoder，省自己额度）
```bash
cd /workspace/watch/douyin_<id>
qoder-flash -p --attachment hook_3s.jpg --attachment contact_sheet.jpg \
  "结合 transcript.txt，逐格说明：开头3秒钩子、镜头切换节奏、字幕样式、画面元素、可学的结构"
```
## 约定
- 调研可只看关键帧+逐字稿；**模仿/复刻某条视频时必须看整段**。
- 逐字稿给原文，不要总结；本地 ASR 结果要标「需复核」。
- 先给候选清单（博主、链接、时长、数据、理由），用户点头再下载实看长任务。
- 不登录、不用 cookie、不做签名逆向；被拦就如实写出。
- 视频用完不必保留的就删，节省空间。
