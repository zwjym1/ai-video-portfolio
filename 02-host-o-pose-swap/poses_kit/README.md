# Host O posekit (closed poses_v2 + gsprites patches)

Same workflow as host_a/poses:
1. Closed-mouth pose PNGs from `../poses_v2/`
2. Face-locked mouth/blink edits on `base.png` → gsprites diff patches
3. `posekit.py` template-matches base face → each pose, warps patches
4. `pose_api.frame(pose, mouth, blink)` composites (no whole-image mouth redraw)

Mouths: `X`/`closed` (no paste), `open_s`/`S`, `open_l`/`L` (plus A/E/O aliases).

## blink_v2 (2026-11-02)
- `eyes_closed.png` / `eyes_half.png`: face-edit of O's face crop (eyes only), ECC-aligned (cc 0.996/0.991), pixel-locked outside eye mask;
  masks `eye_alpha_{closed,half}.png` (hull of whole eye incl. highlights + lower lash, dilated 15px, solid core) used directly by `gsprites.eye_patch`.
- `pose_api.frame` pastes mouth first, eyes last (mouth ROI overlaps lower eye rim → was leaving iris slivers on blink+open-mouth frames).
- Build/QC scripts: `../sprites/blink_v2/` (build.py, qc.py, qc_poses.py). Old eyes in `../sprites/eyes_old_bak/`.
