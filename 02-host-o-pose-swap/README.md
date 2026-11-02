# host-o-pose-swap：角色姿态切换与面部编辑管线

**做什么**：给一个 2D 原创角色（Host O）准备多套姿态立绘（`poses_kit/`），配合语音驱动嘴型、眨眼，并在说话过程中按动作曲线平滑切换姿态，输出说话视频。

- `poses_kit/`：底图、眼/嘴分层素材与 `gsprites.py` 素材生成脚本
- `samples/render_posekit_swap.py`：姿态切换渲染；`drive_host_o_sample.py`：用 sprite-talk 驱动
- `samples/*_meta.json`：每次渲染参数；`*.jpg/png`：质检图（嘴型、眨眼、位移曲线）

**运行**（需 Python3、numpy、Pillow、ffmpeg，以及 ../01-sprite-talk 已 `pip install -e`）：
```bash
python samples/render_posekit_swap.py
```
> 注：脚本内部分路径为原工作环境的绝对路径，需要按本地目录修改。

**效果**：[../videos/02_pose_swap_posekit.mp4](../videos/02_pose_swap_posekit.mp4)、[动作预设版](../videos/02_pose_swap_dyn_preset.mp4)、[横版](../videos/02_talk_landscape.mp4)
