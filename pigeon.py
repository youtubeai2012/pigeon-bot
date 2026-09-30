"""Pigeon bot: @zachdfilms TikTok -> transcript -> whispering pigeon over muted original -> post.

MODE=new    (default, used by the 30-min schedule) -> only brand-new videos
MODE=random -> one random Zach video that has never been used before
"""
import asyncio, json, os, random, subprocess, sys
from pathlib import Path

HANDLE = "zachdfilms"
ACCOUNT = f"https://www.tiktok.com/@{HANDLE}"
ROOT = Path(__file__).parent
STATE = ROOT / "state" / "seen.json"   # videos the "new" checker already knows about
USED = ROOT / "state" / "used.json"    # videos that have been turned into pigeon videos
PIGEON_RAW = ROOT / "assets" / "pigeon.png"
PIGEON_CUT = ROOT / "assets" / "pigeon_cutout.png"
WORK = ROOT / "work"
VOICE = "en-US-GuyNeural"
MAX_PER_RUN = 1
RANDOM_POOL = 150


def run(cmd):
    print("+", " ".join(map(str, cmd)), flush=True)
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stderr[-3000:], flush=True)
        raise RuntimeError(f"Command failed: {cmd[0]}")
    return p.stdout


def load(path):
    return set(json.loads(path.read_text())) if path.exists() else set()


def save(path, items):
    path.write_text(json.dumps(sorted(items)))


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=nw=1:nk=1", path]).strip())


def make_cutout():
    if PIGEON_CUT.exists():
        return
    from rembg import remove
    from PIL import Image
    img = remove(Image.open(PIGEON_RAW))
    img = img.crop(img.getbbox())
    img.save(PIGEON_CUT)
    print("Pigeon background removed ->", PIGEON_CUT)


def ytdlp(use_cookies=True):
    args = ["yt-dlp", "--impersonate", "chrome"]
    sid = os.environ.get("TIKTOK_SESSIONID")
    if use_cookies and sid:
        jar = WORK / "cookies.txt"
        jar.write_text("# Netscape HTTP Cookie File\n"
                       f".tiktok.com\tTRUE\t/\tTRUE\t2147483647\tsessionid\t{sid}\n")
        args += ["--cookies", str(jar)]
    return args


def latest_videos_ytdlp(n):
    last = None
    for cookies in (True, False):
        try:
            data = json.loads(run(ytdlp(cookies) + ["--flat-playlist", "--playlist-end", str(n), "-J", ACCOUNT]))
            ids = []
            for e in data.get("entries", []):
                url = (e.get("url") or "").lower()
                if url and "/@" in url and f"/@{HANDLE}/" not in url:
                    print("Ignoring non-Zach entry:", url)
                    continue
                if e.get("id"):
                    ids.append(e["id"])
            if ids:
                return ids
        except Exception as e:
            last = e
    raise RuntimeError(f"yt-dlp found no videos ({last})")


def latest_videos_browser(n):
    import re
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
        sid = os.environ.get("TIKTOK_SESSIONID")
        if sid:
            ctx.add_cookies([{"name": "sessionid", "value": sid,
                              "domain": ".tiktok.com", "path": "/"}])
        page = ctx.new_page()
        page.goto(ACCOUNT, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_selector('a[href*="/video/"]', timeout=30000)
        except Exception:
            page.screenshot(path=str(WORK / "profile.png"))
            browser.close()
            raise RuntimeError("Browser could not see any videos (captcha/block?)")
        links = page.eval_on_selector_all('a[href*="/video/"]', "els => els.map(e => e.href)")
        browser.close()
    ids = []
    for link in links:
        m = re.search(rf"/@{HANDLE}/video/(\d+)", link)
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    return sorted(ids, key=int, reverse=True)[:n]


def latest_videos(n=5):
    for finder in (latest_videos_ytdlp, latest_videos_browser):
        try:
            ids = finder(n)
            if ids:
                print(f"Found {len(ids)} videos via {finder.__name__}")
                return ids
        except Exception as e:
            print(f"{finder.__name__} failed: {e}", flush=True)
    raise RuntimeError("Could not read @zachdfilms videos with any method")


def video_info(video_id):
    return json.loads(run(ytdlp() + ["-J", f"{ACCOUNT}/video/{video_id}"]))


def is_zach(info):
    owner = " ".join(str(info.get(k) or "") for k in ("uploader", "uploader_url")).lower()
    return HANDLE in owner


def download(video_id):
    out = WORK / f"{video_id}.mp4"
    run(ytdlp() + ["-f", "mp4/best", "-o", str(out), f"{ACCOUNT}/video/{video_id}"])
    return out


def transcribe(video):
    import whisper
    model = whisper.load_model("base")
    return model.transcribe(str(video), language="en", fp16=False)["text"].strip()


async def tts(text, out):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate="-5%", pitch="+15Hz", volume="-20%").save(str(out))


def render(video, voice_raw, out):
    voice = WORK / "voice_whisper.wav"
    run(["ffmpeg", "-y", "-i", voice_raw, "-filter_complex",
         "[0:a]highpass=f=500,lowpass=f=6000,volume=1.6,aecho=0.8:0.6:40:0.25[v];"
         "anoisesrc=color=pink:amplitude=0.02[n];[v][n]amix=inputs=2:duration=first[a]",
         "-map", "[a]", voice])
    length = max(duration(video), duration(voice))
    fc = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[bg];"
        "[1:v]scale=380:-1[p];"
        "[bg][p]overlay=x=30:y=H-h-320+8*sin(2*PI*t*2.5)[v]"
    )
    run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", video, "-loop", "1", "-i", PIGEON_CUT,
         "-i", voice, "-filter_complex", fc, "-map", "[v]", "-map", "2:a",
         "-t", f"{length:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", out])


def post(video, caption):
    from tiktok_uploader.upload import upload_video
    sid = os.environ["TIKTOK_SESSIONID"]
    cookies = [{"name": name, "value": sid, "domain": ".tiktok.com", "path": "/",
                "secure": True, "httpOnly": True}
               for name in ("sessionid", "sessionid_ss", "sid_tt")]
    try:
        failed = upload_video(str(video), description=caption[:2200],
                              cookies_list=cookies, headless=True)
    except TypeError:
        failed = upload_video(str(video), description=caption[:2200],
                              sessionid=sid, headless=True)
    if failed:
        raise RuntimeError(f"TikTok upload failed: {failed}")


def process(vid):
    """Make + post a pigeon video. Returns False if the video isn't Zach's."""
    info = video_info(vid)
    if not is_zach(info):
        print(f"Skipping {vid}: uploader is '{info.get('uploader')}', not {HANDLE}")
        return False
    caption = info.get("description") or info.get("title") or ""
    video = download(vid)
    text = transcribe(video)
    print("Transcript:", text)
    raw = WORK / "voice.mp3"
    asyncio.run(tts(text or "...", raw))
    final = WORK / f"pigeon_{vid}.mp4"
    render(video, raw, final)
    post(final, caption)
    print("Posted", vid)
    return True


def new_mode():
    first_run = not STATE.exists()
    seen = load(STATE)
    used = load(USED)
    ids = latest_videos()
    if first_run:
        save(STATE, ids)
        print("First run: marked existing videos as seen. Waiting for new posts.")
        return
    candidates = [i for i in reversed(ids) if i not in seen and i not in used]
    if not candidates:
        print("No new videos.")
    done = 0
    for vid in candidates:
        if done >= MAX_PER_RUN:
            break
        ok = process(vid)
        seen.add(vid)
        save(STATE, seen)
        if ok:
            used.add(vid)
            save(USED, used)
            done += 1


def random_mode():
    used = load(USED)
    pool = [i for i in latest_videos(RANDOM_POOL) if i not in used]
    print(f"{len(pool)} Zach videos not used yet")
    if not pool:
        raise RuntimeError("Every video found has already been used")
    random.shuffle(pool)
    for vid in pool[:10]:
        print("Random pick:", vid)
        used.add(vid)
        save(USED, used)
        ok = process(vid)
        if ok:
            seen = load(STATE)
            seen.add(vid)
            save(STATE, seen)
            return
    raise RuntimeError("Couldn't find a usable Zach video in 10 tries")


def main():
    WORK.mkdir(exist_ok=True)
    STATE.parent.mkdir(exist_ok=True)
    make_cutout()
    mode = os.environ.get("MODE", "new").strip().lower()
    print("Mode:", mode)
    if mode == "random":
        random_mode()
    else:
        new_mode()


if __name__ == "__main__":
    sys.exit(main())