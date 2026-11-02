host_a talking sample v1 (2026-11-01)
- work/sprites.py: mouth erase + 6 vector mouths (8x supersampled, rounded corners, rot 7deg, center (483,611)); auto eye masks (connected comp + hull), half blink = original upper lash shifted down 42%, closed = drawn tapered lid curve; skin via inpaint w/ hair ring replaced by skin.
- work/render.py <LEAD> <out.mp4> [--score]: host_d v2 timeline reused; LEAD=0.02 chosen by sweeping lead and +-1/2 frame offsets (RMS-openness corr plateau 0..0.02s).
- exports/host_a_talking_v1.mp4, exports/host_a_mouth_blink_sheet.png; debug frames in work/dbg/.

v2 (2026-11-01 23:45)
- Sprites: Codex image_gen edits of 1254px face crop (/workspace/handoff/AI-01/imagegen/host_a_visemes, jobs.json/done.json), ECC-registered (shift <0.25px, eyes ~1.1px y) -> gpt/*.png; gsprites.py diff-masks + low-freq colour match + feather.
- Timing: fa.py (venv /workspace/venv_fa, torchaudio MMS_FA forced alignment, pinyin romanisation) -> chars_fa.json; initial/final split from letter spans. LEAD=0.025 (corr 0.617 vs 0.37 in v1).
- render_v2.py: MBP/F visemes, 1-2 frame in-betweens, jaw drop <=2px, saccades +-1.6px, brow raise on alternate stressed syllables, random blinks 2.5-5s w/ 25% doubles.

v3 (2026-11-01 23:55): GPT batch 2 (/workspace/handoff/AI-01/imagegen/host_a_visemes_v3) -> gpt/*3.png (E,O,U,I,MBP,e_closed,e_q34); U patch scaled 1.4x; blink 1-3-2-2-3-1-1; 2-frame linear cross-dissolve (0.4/0.75); body: bottom-anchored lean +-0.22deg (3.6s) + head sway 1.4px, shoulder breath, posture settle at 3.05s. render_v3.py 0.025. Optical-flow morph tried and rejected (tearing).
