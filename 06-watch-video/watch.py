#!/workspace/.venv-dy/bin/python
"""watch.py — 给 agent "看视频"：输入链接，输出 元数据 / 逐字稿 / 关键帧拼图 / 开头3秒拼图 / 评论(弹幕)。
用法:
  /workspace/tools/watch.py <URL或BV号> [--frames 16] [--model small|base] [--no-asr] [--out /workspace/watch]
  /workspace/tools/watch.py --local /path/video.mp4 [--id name]     # 已有视频文件（如用户电脑下载后拷进盒子）
  /workspace/tools/watch.py <YouTube链接> --hd                     # YouTube 取 1080p（默认 720p）
输出: /workspace/watch/<平台>_<id>/ 下 meta.json, video.mp4, transcript.txt/.srt/.json, contact_sheet.jpg,
      hook_3s.jpg, frames/, comments.json, danmaku.json, report.md
平台路线（均免登录、不读浏览器cookie、不做签名逆向）:
  B站   : api.bilibili.com 开放接口（匿名buvid + WBI签名，见 bilibili-API-collect 文档）取信息/360p mp4/热评/弹幕/CC字幕
  YouTube: oEmbed 元数据 → 在线解析站 loader.to(720p/--hd 1080p) → invidious.f5.si 公开API(360p) → snapany.com(无头浏览器)
           → yt-dlp → 仍失败回退 oEmbed + i.ytimg 自动缩略帧（无逐字稿）
  抖音  : iesdouyin.com 公开分享页（国内IP可用）→ 在线解析站 dlpanda.com(网页表单) → snapany.com(无头浏览器) → yt-dlp → 如实报告
  解析站逻辑见 parse_sites.py / parse_sites_pw.py（只用网站公开表单/接口，不登录、不破解签名、不用 cookie/key）
"""
import sys, os, re, json, time, zlib, argparse, subprocess, urllib.request, urllib.parse, http.cookiejar, datetime, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
TZ = datetime.timezone(datetime.timedelta(hours=8))
def now(): return datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M (UTC+8)")
def ts(sec): return datetime.datetime.fromtimestamp(sec, TZ).strftime("%Y-%m-%d %H:%M (UTC+8)") if sec else None
UA_PC = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
UA_IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
def log(*a): print("[watch]", *a, file=sys.stderr, flush=True)

def http_get(url, headers=None, binary=False, timeout=30):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA_PC})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read(); return (r.status, r.geturl(), b if binary else b.decode("utf-8", "replace"))

def download(urls, path, headers, expect=None):
    urls = [urls] if isinstance(urls, str) else urls; last = None
    for url in urls:
        for attempt in range(4):   # 断点续传重试（CDN 偶发中途断流）
            cmd = ["curl", "-sSL", "--fail", "-m", "900", "-C", "-", "-o", path, url]
            for k, v in headers.items(): cmd[1:1] = ["-H", f"{k}: {v}"]
            r = subprocess.run(cmd, capture_output=True, text=True); last = r.stderr.strip()
            size = os.path.getsize(path) if os.path.exists(path) else 0
            if r.returncode == 0 and (not expect or size >= expect): return
            log(f"下载未完成(rc={r.returncode}, {size} bytes)，重试", attempt + 1)
        if os.path.exists(path): os.remove(path)
    raise SystemExit("视频下载失败: " + (last or "")[:200])

def run(cmd, **kw): return subprocess.run(cmd, capture_output=True, text=True, **kw)

# ---------------- Bilibili ----------------
def do_bili(url, od, meta):
    import bili_view as b
    m = re.search(r"(BV[0-9A-Za-z]{10})", url)
    if not m and "b23.tv" in url:
        r = run(["curl", "-sI", "-m", "15", url]); m2 = re.search(r"(?im)^location:\s*(\S+)", r.stdout)
        if m2: m = re.search(r"(BV[0-9A-Za-z]{10})", m2.group(1))
    if not m: raise SystemExit("未识别到 BV 号")
    bvid = m.group(1); pm = re.search(r"[?&]p=(\d+)", url); p = int(pm.group(1)) if pm else 1
    via, d = b.view(bvid)
    if d.get("code") != 0: raise SystemExit(f"B站 view 接口失败: {d.get('code')} {d.get('message')}")
    v = d["data"]; page = (v.get("pages") or [{}])[p-1]; cid = page.get("cid") or v["cid"]
    dim = page.get("dimension") or v.get("dimension") or {}
    w, h = dim.get("width", 0), dim.get("height", 0)
    if dim.get("rotate"): w, h = h, w
    st = v.get("stat", {})
    meta.update(platform="bilibili", id=bvid, url=f"https://www.bilibili.com/video/{bvid}" + (f"?p={p}" if p > 1 else ""),
        title=v.get("title"), author=(v.get("owner") or {}).get("name"), author_mid=(v.get("owner") or {}).get("mid"),
        duration=page.get("duration") or v.get("duration"), width=w, height=h, orientation=("竖屏" if h > w else "横屏") if w and h else None,
        published=ts(v.get("pubdate")), desc=v.get("desc"), tname=v.get("tname"),
        stats={"播放": st.get("view"), "点赞": st.get("like"), "投币": st.get("coin"), "收藏": st.get("favorite"),
               "评论": st.get("reply"), "弹幕": st.get("danmaku"), "分享": st.get("share")}, fetched_at=now(), via=f"api.bilibili.com {via}")
    ck = {"Cookie": b.buvid()}; key = b.wbi_key()
    # CC/AI 字幕（匿名通常只返回UP主上传的CC字幕；AI字幕需登录）
    try:
        s, t = b.get("https://api.bilibili.com/x/player/wbi/v2?" + b.sign({"bvid": bvid, "cid": cid}, key), ck)
        subs = (((json.loads(t).get("data") or {}).get("subtitle") or {}).get("subtitles")) or []
        meta["platform_subtitles"] = [x.get("lan_doc") for x in subs]
        if subs:
            su = subs[0]["subtitle_url"]; su = "https:" + su if su.startswith("//") else su
            _, _, body = http_get(su); js = json.loads(body)
            open(f"{od}/platform_subtitle.json", "w").write(json.dumps(js, ensure_ascii=False, indent=1))
            open(f"{od}/platform_subtitle.txt", "w").write("\n".join(f"[{x['from']:.1f}] {x['content']}" for x in js.get("body", [])))
    except Exception as e: log("字幕接口失败", e)
    # 热评
    try:
        s, t = b.get(f"https://api.bilibili.com/x/v2/reply/main?type=1&oid={v['aid']}&mode=3&ps=20", ck)
        rp = (json.loads(t).get("data") or {}).get("replies") or []
        cm = [{"user": x["member"]["uname"], "like": x["like"], "text": x["content"]["message"], "replies": x.get("rcount")} for x in rp]
        json.dump(cm, open(f"{od}/comments.json", "w"), ensure_ascii=False, indent=1); meta["comments_saved"] = len(cm)
    except Exception as e: log("评论接口失败", e)
    # 弹幕（list.so 为 raw deflate 的 XML）
    try:
        _, _, raw = http_get(f"https://api.bilibili.com/x/v1/dm/list.so?oid={cid}", {"User-Agent": UA_PC, "Referer": "https://www.bilibili.com/"}, binary=True)
        try: xml = zlib.decompress(raw, -15).decode("utf-8", "replace")
        except Exception: xml = raw.decode("utf-8", "replace")
        dm = sorted([(float(a.split(",")[0]), txt) for a, txt in re.findall(r'<d p="([^"]+)">([^<]*)</d>', xml)])
        json.dump([{"t": round(t_, 1), "text": x} for t_, x in dm], open(f"{od}/danmaku.json", "w"), ensure_ascii=False, indent=0); meta["danmaku_saved"] = len(dm)
    except Exception as e: log("弹幕接口失败", e)
    # 视频：匿名 html5 mp4（通常 360p，含音轨）
    s, t = b.get("https://api.bilibili.com/x/player/wbi/playurl?" + b.sign({"bvid": bvid, "cid": cid, "qn": 64, "fnval": 1, "platform": "html5", "high_quality": 1}, key), ck)
    pd = json.loads(t).get("data") or {}; durl = pd.get("durl") or []
    if not durl: raise SystemExit(f"playurl 无可用流: {t[:200]}")
    meta["video_quality_qn"] = pd.get("quality")
    log(f"下载视频 qn={pd.get('quality')} {durl[0].get('size')} bytes")
    download([durl[0]["url"]] + (durl[0].get("backup_url") or []), f"{od}/video.mp4", {"User-Agent": UA_PC, "Referer": "https://www.bilibili.com/"}, durl[0].get("size"))
    return f"{od}/video.mp4"

# ---------------- Douyin ----------------
def _do_douyin_dl(url, od, meta):
    vid = None
    m = re.search(r"(?:video/|modal_id=|note/)(\d{15,21})", url)
    if m: vid = m.group(1)
    elif "v.douyin.com" in url:
        r = run(["curl", "-sI", "-m", "15", "-A", UA_IOS, url]); m2 = re.search(r"(?im)^location:\s*(\S+)", r.stdout)
        if m2: m = re.search(r"/(\d{15,21})", m2.group(1)); vid = m and m.group(1)
    if not vid: raise SystemExit("未识别到抖音作品ID")
    meta.update(platform="douyin", id=vid, url=f"https://www.douyin.com/video/{vid}", fetched_at=now())
    _, _, h = http_get(f"https://www.iesdouyin.com/share/video/{vid}/", {"User-Agent": UA_IOS, "Referer": "https://www.douyin.com/"})
    mm = re.search(r"window\._ROUTER_DATA\s*=\s*(.*?)</script>", h, re.S)
    item = None
    if mm:
        ld = json.loads(mm.group(1)).get("loaderData", {})
        for k, val in ld.items():
            if isinstance(val, dict) and val.get("videoInfoRes", {}).get("item_list"): item = val["videoInfoRes"]["item_list"][0]
    if item and str(item.get("aweme_id", vid)) == vid:
        vv = item["video"]; st = item.get("statistics", {})
        w, h2 = vv.get("width"), vv.get("height")
        meta.update(title=item.get("desc"), author=(item.get("author") or {}).get("nickname"), duration=(vv.get("duration") or 0)/1000,
            width=w, height=h2, orientation=("竖屏" if (h2 or 0) > (w or 0) else "横屏") if w and h2 else None, published=ts(item.get("create_time")),
            stats={"点赞": st.get("digg_count"), "评论": st.get("comment_count"), "收藏": st.get("collect_count"), "分享": st.get("share_count"), "播放": st.get("play_count")},
            via="iesdouyin.com 公开分享页")
        play = vv["play_addr"]["url_list"][0].replace("playwm", "play")
        download(play, f"{od}/video.mp4", {"User-Agent": UA_IOS, "Referer": "https://www.douyin.com/"})
        return f"{od}/video.mp4"
    log("分享页未返回作品数据（海外IP常见），改走在线解析站（dlpanda → snapany）")
    import parse_sites
    r = parse_sites.douyin(url if url.startswith("http") else meta["url"])
    if r.get("url"):
        meta.update(title=meta.get("title") or r.get("title"), via=f"{r['site']} 在线解析（{r.get('quality')}，{r.get('seconds')}s）", parse_tried=r.get("tried"))
        log(f"{r['site']} 解析成功，下载中")
        try:
            download(r["url"], f"{od}/video.mp4", {"User-Agent": UA_PC}); return f"{od}/video.mp4"
        except SystemExit as e: log("解析站直链下载失败", e)
        if r.get("site") == "dlpanda.com":   # 2026-10-25：dlpanda 直链常 403，补试 snapany
            try:
                t0 = time.time(); r2 = parse_sites.via_browser("snapany", url if url.startswith("http") else meta["url"])
                log("snapany.com 解析成功，下载中"); download(r2["url"], f"{od}/video.mp4", {"User-Agent": UA_PC})
                meta.update(via=f"snapany.com 在线解析（{round(time.time()-t0,1)}s）"); return f"{od}/video.mp4"
            except (Exception, SystemExit) as e: log("snapany 也失败", e)
    meta["parse_tried"] = r.get("tried")
    log("解析站均失败，回退 yt-dlp", r.get("tried"))
    return do_ytdlp(meta["url"], od, meta, "douyin")

def do_douyin(url, od, meta):
    """下载 + 免登录元数据/评论（dy_data.py：so.douyin.com 公开接口）"""
    video = None; err = None
    try: video = _do_douyin_dl(url, od, meta)
    except SystemExit as e: err = e
    vid = meta.get("id")
    if vid:
        try:
            import dy_data
            info = dy_data.video(vid)
            meta.update(title=info["desc"] or meta.get("title"), author=info["author"], published=info["published"] + " (UTC+8)",
                        duration=meta.get("duration") or info["duration_s"],
                        stats={"点赞": info["likes"], "评论": info["comments"], "收藏": info["collects"], "分享": info["shares"], "播放": info["plays"] or "抖音不公开"},
                        hashtags=info["hashtags"], bgm=info["bgm"], author_sec_uid=info["author_sec_uid"], related_search=info["related_search"])
            cm = dy_data.comments(vid, n=COMMENTS_N)
            cm = sorted(cm, key=lambda c: -(c["like"] or 0))
            json.dump(cm, open(f"{od}/comments.json", "w"), ensure_ascii=False, indent=1); meta["comments_saved"] = len(cm)
            log(f"抖音元数据+评论已取（{len(cm)} 条评论）")
        except BaseException as e: log("抖音元数据/评论获取失败", e)
    if err and not video: raise err
    return video

# ---------------- YouTube：先走在线解析站 ----------------
HD = False
COMMENTS_N = 200
def do_youtube(url, od, meta):
    vid = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([\w-]{11})", url)
    if not vid: return do_ytdlp(url, od, meta, "youtube")
    vid = vid.group(1); wurl = f"https://www.youtube.com/watch?v={vid}"
    meta.update(platform="youtube", id=vid, url=wurl, fetched_at=now())
    try:
        _, _, t = http_get("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(wurl)); o = json.loads(t)
        meta.update(title=o.get("title"), author=o.get("author_name"))
    except Exception as e: log("oEmbed 失败", e)
    import parse_sites
    log("走在线解析站（loader.to → invidious → snapany）" + ("，--hd" if HD else ""))
    r = parse_sites.youtube(wurl, hd=HD)
    if r.get("url") or r.get("video_only_url"):
        ex = r.get("extra") or {}
        if ex: meta.update(author=meta.get("author") or ex.get("author"), duration=ex.get("duration"), published=ts(ex.get("published")),
                           stats={"播放": ex.get("views"), "点赞": ex.get("likes")})
        meta.update(title=meta.get("title") or r.get("title"), via=f"{r['site']} 在线解析（{r.get('quality')}，{r.get('seconds')}s）", parse_tried=r.get("tried"))
        try:
            if HD and r.get("video_only_url") and r.get("audio_url"):
                download(r["video_only_url"], f"{od}/v.mp4", {"User-Agent": UA_PC}); download(r["audio_url"], f"{od}/a.m4a", {"User-Agent": UA_PC})
                run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{od}/v.mp4", "-i", f"{od}/a.m4a", "-c", "copy", f"{od}/video.mp4"])
                os.remove(f"{od}/v.mp4"); os.remove(f"{od}/a.m4a")
            else:
                download(r["url"], f"{od}/video.mp4", {"User-Agent": UA_PC})
            return f"{od}/video.mp4"
        except SystemExit as e: log("解析站直链下载失败", e)
        if r.get("site") == "dlpanda.com":   # 2026-10-25：dlpanda 直链常 403，补试 snapany
            try:
                t0 = time.time(); r2 = parse_sites.via_browser("snapany", url if url.startswith("http") else meta["url"])
                log("snapany.com 解析成功，下载中"); download(r2["url"], f"{od}/video.mp4", {"User-Agent": UA_PC})
                meta.update(via=f"snapany.com 在线解析（{round(time.time()-t0,1)}s）"); return f"{od}/video.mp4"
            except (Exception, SystemExit) as e: log("snapany 也失败", e)
    meta["parse_tried"] = r.get("tried")
    log("解析站均失败，回退 yt-dlp", r.get("tried"))
    return do_ytdlp(wurl, od, meta, "youtube")

# ---------------- YouTube / 通用 ----------------
def do_ytdlp(url, od, meta, platform):
    base = ["yt-dlp", "--no-playlist", "--js-runtimes", "node", "--remote-components", "ejs:github"]
    r = run(base + ["-J", url], timeout=180)
    if r.returncode == 0:
        j = json.loads(r.stdout); w, h = j.get("width"), j.get("height")
        meta.update(platform=platform, id=j.get("id"), url=j.get("webpage_url") or url, title=j.get("title"), author=j.get("uploader") or j.get("channel"),
            duration=j.get("duration"), width=w, height=h, orientation=("竖屏" if (h or 0) > (w or 0) else "横屏") if w and h else None,
            published=j.get("upload_date"), desc=(j.get("description") or "")[:2000],
            stats={"播放": j.get("view_count"), "点赞": j.get("like_count"), "评论": j.get("comment_count")}, fetched_at=now(), via="yt-dlp",
            platform_subtitles=list((j.get("subtitles") or {}).keys()) + [f"auto:{k}" for k in list((j.get("automatic_captions") or {}).keys())[:5]])
        run(base + ["--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "zh.*,en,en-orig", "--sub-format", "vtt", "-o", f"{od}/platform_subtitle.%(ext)s", url], timeout=180)
        r2 = run(base + ["-f", "b[height<=480]/bv*[height<=480]+ba/b", "--merge-output-format", "mp4", "-o", f"{od}/video.%(ext)s", url], timeout=900)
        if r2.returncode == 0:
            for f in os.listdir(od):
                if f.startswith("video."): return f"{od}/{f}"
        meta["error"] = "yt-dlp 下载失败: " + r2.stderr.strip().splitlines()[-1][:300] if r2.stderr.strip() else "yt-dlp 下载失败"
        return None
    err = (r.stderr.strip().splitlines() or ["?"])[-1][:300]; meta.update(platform=platform, url=url, fetched_at=now(), error="yt-dlp: " + err)
    if platform == "youtube":   # 回退：oEmbed + 自动缩略帧
        vid = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([\w-]{11})", url); vid = vid and vid.group(1)
        meta["id"] = vid
        try:
            _, _, t = http_get("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url)); o = json.loads(t)
            meta.update(title=o.get("title"), author=o.get("author_name"), via="YouTube oEmbed（yt-dlp 被要求登录，已回退）")
        except Exception as e: log("oEmbed 失败", e)
        os.makedirs(f"{od}/frames", exist_ok=True); got = []
        for n in ["hqdefault", "hq1", "hq2", "hq3"]:
            try:
                _, _, b_ = http_get(f"https://i.ytimg.com/vi/{vid}/{n}.jpg", binary=True); open(f"{od}/frames/{n}.jpg", "wb").write(b_); got.append(f"{od}/frames/{n}.jpg")
            except Exception: pass
        if got: tile(got, [n for n in ["封面", "约25%", "约50%", "约75%"]][:len(got)], f"{od}/contact_sheet.jpg", cols=2)
        meta["note"] = "仅拿到 oEmbed 元数据 + YouTube 自动生成的 3 张缩略帧（非精确时间点）；无视频文件和逐字稿。"
    return None

# ---------------- 处理：抽帧 / 拼图 / ASR ----------------
def probe(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", path])
    j = json.loads(r.stdout); dur = float(j["format"]["duration"])
    vs = [s for s in j["streams"] if s["codec_type"] == "video"]; has_a = any(s["codec_type"] == "audio" for s in j["streams"])
    return dur, (vs[0]["width"], vs[0]["height"]) if vs else (0, 0), has_a

def fmt(t): return f"{int(t//60):02d}:{t%60:05.2f}"

def grab(path, t, out, width=360):
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "3", out])
    return os.path.exists(out)

def tile(imgs, labels, out, cols=4):
    from PIL import Image, ImageDraw, ImageFont
    ims = [Image.open(i).convert("RGB") for i in imgs]; w = max(i.width for i in ims); h = max(i.height for i in ims)
    rows = (len(ims) + cols - 1) // cols; sheet = Image.new("RGB", (cols * w, rows * h), "black"); d = ImageDraw.Draw(sheet)
    try: f = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", max(14, w // 14))
    except Exception:
        try: f = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc", max(14, w // 14))
        except Exception: f = ImageFont.load_default()
    for k, (im, lb) in enumerate(zip(ims, labels)):
        x, y = (k % cols) * w, (k // cols) * h; sheet.paste(im, (x, y))
        bb = d.textbbox((x + 4, y + 4), lb, font=f); d.rectangle(bb, fill="black"); d.text((x + 4, y + 4), lb, fill="yellow", font=f)
    sheet.save(out, quality=85)

def scene_times(path, thr=0.3):
    r = run(["ffmpeg", "-hide_banner", "-i", path, "-vf", f"select='gt(scene,{thr})',showinfo", "-an", "-f", "null", "-"], timeout=600)
    return [float(x) for x in re.findall(r"pts_time:([\d.]+)", r.stderr)]

def asr(path, od, model):
    from faster_whisper import WhisperModel
    wav = f"{od}/audio16k.wav"; run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000", wav])
    m = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=4)
    segs, info = m.transcribe(wav, language=None, vad_filter=True, beam_size=1, initial_prompt="以下是普通话的句子，使用简体中文和标点。")
    segs = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segs]
    json.dump({"language": info.language, "model": model, "segments": segs}, open(f"{od}/transcript.json", "w"), ensure_ascii=False, indent=1)
    open(f"{od}/transcript.txt", "w").write("\n".join(f"[{fmt(s['start'])}] {s['text']}" for s in segs))
    def srt_t(t): return f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d},{int(t*1000%1000):03d}"
    open(f"{od}/transcript.srt", "w").write("\n".join(f"{i+1}\n{srt_t(s['start'])} --> {srt_t(s['end'])}\n{s['text']}\n" for i, s in enumerate(segs)))
    os.remove(wav); return info.language, len(segs)

def process(video, od, meta, nframes, model, do_asr):
    dur, (w, h), has_a = probe(video)
    meta.setdefault("duration", round(dur, 2)); meta["file_duration"] = round(dur, 2); meta["file_resolution"] = f"{w}x{h}"
    if not meta.get("orientation") and w and h: meta["orientation"] = "竖屏" if h > w else "横屏"
    os.makedirs(f"{od}/frames", exist_ok=True)
    width = 300 if h > w else 400
    # 1) 均匀关键帧拼图
    tl = [(i + 0.5) * dur / nframes for i in range(nframes)]; imgs = []
    for i, t in enumerate(tl):
        p = f"{od}/frames/u{i:02d}_{t:07.2f}.jpg"
        if grab(video, t, p, width): imgs.append((p, fmt(t)))
    tile([a for a, _ in imgs], [b for _, b in imgs], f"{od}/contact_sheet.jpg", cols=4 if h <= w else 6)
    # 2) 开头3秒（每0.5秒一帧）
    hk = []
    for i, t in enumerate([0.05, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]):
        if t < dur:
            p = f"{od}/frames/h{i}_{t:.2f}.jpg"
            if grab(video, t, p, width): hk.append((p, fmt(t)))
    tile([a for a, _ in hk], [b for _, b in hk], f"{od}/hook_3s.jpg", cols=4 if h <= w else 7)
    # 3) 镜头切换统计（剪辑节奏）
    cuts = scene_times(video); meta["shot_cuts"] = len(cuts)
    meta["avg_shot_sec"] = round(dur / (len(cuts) + 1), 2); meta["cut_times"] = [round(c, 2) for c in cuts[:200]]
    if cuts:
        sel = cuts[:: max(1, len(cuts) // 24)][:24]; ims = []
        for i, t in enumerate(sel):
            p = f"{od}/frames/s{i:02d}_{t:07.2f}.jpg"
            if grab(video, t + 0.1, p, width): ims.append((p, fmt(t)))
        if ims: tile([a for a, _ in ims], [b for _, b in ims], f"{od}/shots_sheet.jpg", cols=4 if h <= w else 6)
    # 4) 逐字稿
    if do_asr and has_a:
        t0 = time.time(); lang, n = asr(video, od, model); meta["asr"] = {"model": f"faster-whisper {model}", "language": lang, "segments": n, "seconds": round(time.time() - t0, 1)}
    elif not has_a: meta["asr"] = "无音轨"

def report(od, meta):
    L = [f"# {meta.get('title')}", "", f"- 平台: {meta.get('platform')}  ID: {meta.get('id')}", f"- 链接: {meta.get('url')}",
         f"- 作者: {meta.get('author')}", f"- 发布: {meta.get('published')}", f"- 时长: {meta.get('duration')} 秒  {meta.get('orientation') or ''} {meta.get('file_resolution') or ''}",
         f"- 数据(抓取于 {meta.get('fetched_at')}): {json.dumps(meta.get('stats'), ensure_ascii=False)}", f"- 来源: {meta.get('via')}"]
    if meta.get("hashtags"): L.append(f"- 话题: {' '.join('#'+h for h in meta['hashtags'])}")
    if meta.get("bgm"): L.append(f"- BGM: {meta['bgm'].get('title')} / {meta['bgm'].get('author')}")
    if meta.get("related_search"): L.append(f"- 视频页相关搜索: {'、'.join(meta['related_search'])}")
    if meta.get("shot_cuts") is not None: L.append(f"- 镜头切换: {meta['shot_cuts']} 次，平均 {meta['avg_shot_sec']} 秒/镜头")
    if meta.get("error"): L.append(f"- 问题: {meta['error']}")
    if meta.get("note"): L.append(f"- 说明: {meta['note']}")
    L += ["", "## 文件"] + [f"- {f}" for f in sorted(os.listdir(od)) if f != "frames"]
    for fn, title in [("transcript.txt", "逐字稿"), ("platform_subtitle.txt", "平台字幕")]:
        if os.path.exists(f"{od}/{fn}"): L += ["", f"## {title}", "", open(f"{od}/{fn}").read()[:6000]]
    if os.path.exists(f"{od}/comments.json"):
        L += ["", "## 热评 Top 10"] + [f"- ({c['like']}赞{(' · ' + c['ip']) if c.get('ip') else ''}) {c['text'][:120]}" for c in json.load(open(f"{od}/comments.json"))[:10]]
    open(f"{od}/report.md", "w").write("\n".join(str(x) for x in L))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("url", nargs="?"); ap.add_argument("--frames", type=int, default=16)
    ap.add_argument("--model", default="small"); ap.add_argument("--no-asr", action="store_true"); ap.add_argument("--out", default="/workspace/watch")
    ap.add_argument("--local"); ap.add_argument("--id"); ap.add_argument("--comments", type=int, default=200, help="抖音评论条数（0=不取）")
    ap.add_argument("--hd", action="store_true", help="YouTube 取高清：loader.to 1080p，或 snapany 无声高清+音轨合并"); a = ap.parse_args()
    meta = {}
    if a.local:
        vid = a.id or re.sub(r"\W+", "_", os.path.splitext(os.path.basename(a.local))[0]); od = f"{a.out}/local_{vid}"; os.makedirs(od, exist_ok=True)
        meta.update(platform="local", id=vid, title=os.path.basename(a.local), fetched_at=now()); video = a.local
    else:
        u = a.url.strip(); um = re.search(r"https?://\S+", u); u = um.group(0) if um else u
        if re.fullmatch(r"BV[0-9A-Za-z]{10}", u) or "bilibili.com" in u or "b23.tv" in u: plat = "bilibili"
        elif "douyin.com" in u or "iesdouyin" in u: plat = "douyin"
        elif "youtube.com" in u or "youtu.be" in u: plat = "youtube"
        else: plat = "web"
        tmp = f"{a.out}/_tmp_{int(time.time())}"; os.makedirs(tmp, exist_ok=True)
        try:
            global HD, COMMENTS_N; HD = a.hd; COMMENTS_N = a.comments
            video = {"bilibili": do_bili, "douyin": do_douyin, "youtube": do_youtube}.get(plat, lambda x, o, m: do_ytdlp(x, o, m, plat))(u, tmp, meta)
        except SystemExit as e: meta.setdefault("platform", plat); meta.setdefault("url", u); meta["error"] = str(e); video = None
        od = f"{a.out}/{meta.get('platform', plat)}_{meta.get('id') or int(time.time())}"
        if os.path.exists(od): shutil.rmtree(od)
        os.rename(tmp, od); video = video and video.replace(tmp, od)
    if video: process(video, od, meta, a.frames, a.model, not a.no_asr)
    json.dump(meta, open(f"{od}/meta.json", "w"), ensure_ascii=False, indent=1); report(od, meta)
    print(json.dumps({"out": od, "ok": bool(video), "title": meta.get("title"), "error": meta.get("error")}, ensure_ascii=False))
    sys.exit(0 if video else 2)
if __name__ == "__main__": main()
