"""Pigeon bot: @zackdfilms92 TikTok -> transcript -> talking pigeon over muted original -> post.

MODE=new    (default, used by the 30-min schedule) -> only brand-new videos
MODE=random -> one random Zack video that has never been used before
POST=0      -> make the video but don't post it (for testing)
"""
import asyncio, json, math, os, random, re, subprocess, sys, time
from pathlib import Path

HANDLE = "zackdfilms92"
ACCOUNT = f"https://www.tiktok.com/@{HANDLE}"
ROOT = Path(__file__).parent
STATE = ROOT / "state" / f"seen_{HANDLE}.json"      # videos the "new" checker already knows about
USED = ROOT / "state" / f"used_{HANDLE}.json"       # videos that have been turned into pigeon videos
TRIES = ROOT / "state" / f"attempts_{HANDLE}.json"  # failed attempts per video (gives up after 3)
PIGEON_RAW = ROOT / "assets" / "pigeon.png"
PIGEON_CUT = ROOT / "assets" / "pigeon_cutout.png"
FONT_DIR = ROOT / "assets" / "fonts"
FONT_FILE = FONT_DIR / "Anton-Regular.ttf"
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf"
WORK = ROOT / "work"

# Voice: deep US man. Change to en-GB-RyanNeural / en-US-EricNeural etc. if you like.
VOICE = "en-US-ChristopherNeural"
VOICE_RATE = "-6%"
VOICE_PITCH = "-14Hz"

W, H, FPS = 1080, 1920, 30
PIGEON_W = 400          # pigeon width on screen
PIGEON_X = 20           # distance from left edge
PIGEON_BOTTOM = 300     # distance from bottom edge
CAPTION_Y = 1130        # caption centre line (pixels from top)

# Beak / eye positions inside assets/pigeon_cutout.png (measured on the 554x524 cutout).
REF_W, REF_H = 554, 524
LOWER_BEAK = [(300, 236), (330, 232), (326, 262), (304, 296), (292, 326), (284, 326), (292, 290)]
UPPER_BEAK = [(232, 198), (300, 190), (330, 232), (300, 236), (292, 290), (284, 326), (262, 262), (248, 228)]
BEAK_HINGE = (322, 240)
EYE_BOX = (352, 102, 380, 158)

MAX_PER_RUN = 1
RANDOM_POOL = 150
MAX_ATTEMPTS = 3


# ----------------------------------------------------------------- helpers
def run(cmd, quiet=False):
    if not quiet:
        print("+", " ".join(map(str, cmd))[:400], flush=True)
    p = subprocess.run(list(map(str, cmd)), capture_output=True, text=True)
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
                      "-of", "default=nw=1:nk=1", path], quiet=True).strip())


def make_cutout():
    if PIGEON_CUT.exists():
        return
    from rembg import remove
    from PIL import Image
    img = remove(Image.open(PIGEON_RAW))
    img = img.crop(img.getbbox())
    img.save(PIGEON_CUT)
    print("Pigeon background removed ->", PIGEON_CUT)


def get_font():
    if FONT_FILE.exists():
        return
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import urllib.request
        urllib.request.urlretrieve(FONT_URL, FONT_FILE)
        print("Downloaded caption font")
    except Exception as e:
        print("Could not download caption font, using default:", e)


# ----------------------------------------------------------------- finding videos
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
                    print("Ignoring non-Zack entry:", url)
                    continue
                if e.get("id"):
                    ids.append(e["id"])
            if ids:
                return ids
        except Exception as e:
            last = e
    raise RuntimeError(f"yt-dlp found no videos ({last})")


def latest_videos_browser(n):
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
    raise RuntimeError(f"Could not read @{HANDLE} videos with any method")


def video_info(video_id):
    return json.loads(run(ytdlp() + ["-J", f"{ACCOUNT}/video/{video_id}"], quiet=True))


def is_zach(info):
    owner = " ".join(str(info.get(k) or "") for k in ("uploader", "uploader_url")).lower()
    return HANDLE in owner


def pick_format(info):
    """Best format WITHOUT the TikTok watermark."""
    good = []
    for f in info.get("formats") or []:
        label = " ".join(str(f.get(k) or "") for k in ("format_id", "format_note", "format")).lower()
        if "watermark" in label or f.get("format_id") == "download":
            continue
        if f.get("vcodec") == "none":
            continue
        good.append(f)
    if not good:
        return None
    # prefer h264 (plays everywhere), then biggest resolution
    good.sort(key=lambda f: (("h264" in str(f.get("vcodec")) or "avc" in str(f.get("vcodec"))),
                             f.get("height") or 0, f.get("tbr") or 0))
    best = good[-1]
    print("Using format:", best.get("format_id"), best.get("format_note"), best.get("vcodec"),
          f"{best.get('width')}x{best.get('height')}")
    return best.get("format_id")


def download(video_id, info):
    out = WORK / f"{video_id}.mp4"
    fmt = pick_format(info)
    sel = fmt or "b[format_note!*=watermark]/bv*[format_note!*=watermark]+ba/b"
    run(ytdlp() + ["-f", sel, "--merge-output-format", "mp4", "-o", str(out), f"{ACCOUNT}/video/{video_id}"])
    return out


# ----------------------------------------------------------------- speech
def transcribe(video):
    import whisper
    model = whisper.load_model("base")
    return model.transcribe(str(video), language="en", fp16=False)["text"].strip()


async def tts(text, out):
    """Makes the voice and returns word timings [(start, end, word), ...]."""
    import edge_tts
    try:
        com = edge_tts.Communicate(text, VOICE, rate=VOICE_RATE, pitch=VOICE_PITCH, boundary="WordBoundary")
    except TypeError:
        com = edge_tts.Communicate(text, VOICE, rate=VOICE_RATE, pitch=VOICE_PITCH)
    words = []
    with open(out, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                s = chunk["offset"] / 1e7
                words.append([s, s + chunk["duration"] / 1e7, chunk["text"]])
    return words


def whisper_voice(raw, out):
    """Deep, breathy 'whisper' version of the voice (keeps the timing)."""
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-filter_complex",
         "[0:a]aresample=44100,highpass=f=70,lowpass=f=7500,"
         "equalizer=f=120:t=q:w=1:g=4,equalizer=f=3500:t=q:w=1.5:g=3,"
         "acompressor=threshold=-20dB:ratio=3:attack=5:release=80,"
         "aecho=0.8:0.5:35:0.18,volume=1.5[v];"
         "anoisesrc=color=pink:amplitude=0.008:r=44100[n];"
         "[v][n]amix=inputs=2:duration=first:normalize=0[a]",
         "-map", "[a]", "-ac", "2", out])


def loudness(wav, fps=FPS):
    """Mouth-openness per video frame (0..1) from the voice."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(wav), "-f", "s16le",
                          "-ac", "1", "-ar", "16000", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    hop = 16000 // fps
    n = max(1, len(a) // hop)
    rms = np.array([np.sqrt(np.mean(a[i * hop:(i + 1) * hop] ** 2) + 1e-12) for i in range(n)])
    ref = np.percentile(rms, 95) or 1
    v = np.clip((rms / ref - 0.18) / 0.7, 0, 1)
    out, cur = [], 0.0
    for x in v:  # open fast, close a bit slower
        cur = cur + (x - cur) * (0.75 if x > cur else 0.45)
        out.append(float(cur))
    return out


# ----------------------------------------------------------------- captions
def ass_time(t):
    t = max(0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def make_captions(words, path):
    font = "Anton" if FONT_FILE.exists() else "DejaVu Sans"
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,9,4,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    clean = []
    for s, e, w in words:
        w = w.strip()
        if w:
            clean.append([s, e, w])
    # group into short chunks (max 3 words / 16 chars, break on pauses + punctuation)
    chunks, cur = [], []
    for i, wd in enumerate(clean):
        if cur:
            gap = wd[0] - cur[-1][1]
            text_len = len(" ".join(x[2] for x in cur + [wd]))
            if len(cur) >= 3 or text_len > 16 or gap > 0.35 or re.search(r"[.,!?;:]$", cur[-1][2]):
                chunks.append(cur)
                cur = []
        cur.append(wd)
    if cur:
        chunks.append(cur)

    lines = []
    for ci, ch in enumerate(chunks):
        chunk_end = ch[-1][1] + 0.15
        if ci + 1 < len(chunks):
            chunk_end = min(chunk_end + 0.25, chunks[ci + 1][0][0])
        for wi, wd in enumerate(ch):
            start = wd[0]
            end = ch[wi + 1][0] if wi + 1 < len(ch) else chunk_end
            parts = []
            for k, other in enumerate(ch):
                t = re.sub(r"[{}\\]", "", other[2]).upper()
                if k == wi:
                    parts.append("{\\c&H00F2FF&\\fscx112\\fscy112}" + t + "{\\c&HFFFFFF&\\fscx100\\fscy100}")
                else:
                    parts.append(t)
            pop = "{\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)}" if wi == 0 else ""
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Cap,,0,0,0,,"
                         f"{{\\pos({W // 2},{CAPTION_Y})}}{pop}" + " ".join(parts))
    Path(path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------------------------------------------- talking pigeon
class Pigeon:
    def __init__(self):
        from PIL import Image, ImageDraw, ImageFilter
        self.Image, self.ImageDraw, self.ImageFilter = Image, ImageDraw, ImageFilter
        src = Image.open(PIGEON_CUT).convert("RGBA")
        s = PIGEON_W / src.width
        sy = src.height * s / REF_H
        sx = PIGEON_W / REF_W
        self.base = src.resize((PIGEON_W, round(src.height * s)), Image.LANCZOS)
        pt = lambda p: (p[0] * sx, p[1] * sy)
        self.hinge = pt(BEAK_HINGE)
        self.pad = 70
        self.size = (self.base.width + self.pad * 2, self.base.height + self.pad * 2)

        # lower beak layer (the part that moves)
        mask = Image.new("L", self.base.size, 0)
        ImageDraw.Draw(mask).polygon([pt(p) for p in LOWER_BEAK], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(1.2))
        alpha = self.base.split()[3]
        from PIL import ImageChops
        self.lower = self.base.copy()
        self.lower.putalpha(ImageChops.multiply(alpha, mask))

        # upper beak layer (drawn on top so the mouth looks right)
        umask = Image.new("L", self.base.size, 0)
        ImageDraw.Draw(umask).polygon([pt(p) for p in UPPER_BEAK], fill=255)
        umask = umask.filter(ImageFilter.GaussianBlur(1.2))
        self.upper = self.base.copy()
        self.upper.putalpha(ImageChops.multiply(alpha, umask))

        # body with the lower beak painted as a dark mouth
        self.body = self.base.copy()
        mouth = Image.new("RGBA", self.base.size, (40, 12, 16, 255))
        self.body.paste(mouth, (0, 0), ImageChops.multiply(alpha, mask))
        self.lower_tip = pt(LOWER_BEAK[4])

        # eyelid colour = feathers around the eye
        x0, y0, x1, y1 = [v * (sx if i % 2 == 0 else sy) for i, v in enumerate(EYE_BOX)]
        self.eye = (x0 - 2, y0 - 2, x1 + 2, y1 + 2)
        ring = self.base.crop((int(x0 - 14), int(y0), int(x0 - 4), int(y1))).convert("RGB")
        px = list(ring.getdata())
        self.lid = tuple(sorted(c[i] for c in px)[len(px) // 2] for i in range(3)) + (255,)
        self.next_blink = random.uniform(1.5, 3.5)

    def frame(self, i, open_amt, speaking_level):
        Image, ImageDraw = self.Image, self.ImageDraw
        t = i / FPS
        img = self.body.copy()
        ang = 24 * open_amt
        lower = self.lower.rotate(ang, resample=Image.BICUBIC, center=self.hinge)
        if ang > 1:
            # dark inside of the mouth between the beak halves
            hx, hy = self.hinge
            tx, ty = self.lower_tip
            r = math.radians(ang)
            dx, dy = tx - hx, ty - hy
            rx = hx + dx * math.cos(r) + dy * math.sin(r)
            ry = hy - dx * math.sin(r) + dy * math.cos(r)
            ImageDraw.Draw(img).polygon([(hx, hy), (tx - 3, ty), (rx, ry)], fill=(40, 12, 16, 255))
        img.alpha_composite(lower)
        img.alpha_composite(self.upper)

        # blinking
        if t >= self.next_blink:
            if t < self.next_blink + 0.13:
                ImageDraw.Draw(img).ellipse(self.eye, fill=self.lid)
            else:
                self.next_blink = t + random.uniform(2.0, 4.5)

        # head movement: gentle sway + nod/bob while talking
        tilt = 3.0 * math.sin(2 * math.pi * 0.33 * t) + 5.0 * speaking_level * math.sin(2 * math.pi * 1.7 * t) - 4 * open_amt
        scale = 1.0 + 0.035 * open_amt
        canvas = Image.new("RGBA", self.size, (0, 0, 0, 0))
        if scale != 1.0:
            img = img.resize((round(img.width * scale), round(img.height * scale)), Image.BICUBIC)
        bob = -4 * open_amt + 1.5 * math.sin(2 * math.pi * 2.2 * t) * speaking_level
        ox = (self.size[0] - img.width) // 2
        oy = self.size[1] - self.pad // 2 - img.height + int(bob)
        canvas.alpha_composite(img, (ox, max(0, oy)))
        pivot = (self.size[0] / 2, self.size[1] - self.pad / 2)
        return canvas.rotate(tilt, resample=Image.BICUBIC, center=pivot)


def render(video, voice_raw, words, out):
    from caption_blur import blur_caption_video

    cleaned_video = WORK / f"caption_blurred_{video.stem}.mp4"
    print("Blurring Zack's burned-in caption letters", flush=True)
    blur_caption_video(video, cleaned_video)
    voice = WORK / "voice_whisper.wav"
    whisper_voice(voice_raw, voice)
    subs = WORK / "captions.ass"
    make_captions(words, subs)
    length = max(duration(video), duration(voice) + 0.4)
    frames = int(math.ceil(length * FPS))
    opens = loudness(voice)
    speak = []  # slower "is talking" envelope for head motion
    cur = 0.0
    for o in opens:
        cur += (o - cur) * 0.08
        speak.append(min(1.0, cur * 2.2))

    pig = Pigeon()
    pw, ph = pig.size
    px = PIGEON_X - pig.pad
    py = H - PIGEON_BOTTOM - ph
    subs_arg = str(subs).replace("\\", "/").replace(":", "\\:")
    fonts_arg = str(FONT_DIR).replace("\\", "/").replace(":", "\\:")
    fc = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}[bg];"
          f"[bg][1:v]overlay=x={px}:y={py}:format=auto[ov];"
          f"[ov]subtitles=filename='{subs_arg}':fontsdir='{fonts_arg}'[v]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-stream_loop", "-1", "-i", str(cleaned_video),
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{pw}x{ph}", "-r", str(FPS), "-i", "-",
           "-i", str(voice),
           "-filter_complex", fc, "-filter_complex_threads", "2", "-map", "[v]", "-map", "2:a",
           "-threads", "4", "-t", f"{length:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    print("+ ffmpeg render (talking pigeon)", flush=True)
    log = open(WORK / "ffmpeg_render.log", "w")
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log)
    try:
        for i in range(frames):
            o = opens[i] if i < len(opens) else 0.0
            s = speak[i] if i < len(speak) else 0.0
            p.stdin.write(pig.frame(i, o, s).tobytes())
        p.stdin.close()
    except BrokenPipeError:
        pass
    p.wait()
    log.close()
    if p.returncode != 0:
        print("ffmpeg exit code", p.returncode)
        print((WORK / "ffmpeg_render.log").read_text()[-3000:])
        raise RuntimeError("Render failed")
    print("Rendered", out)


# ----------------------------------------------------------------- posting
def shot(page, name):
    try:
        page.screenshot(path=str(WORK / f"post_{name}.png"), full_page=True)
    except Exception:
        pass


def dismiss_popups(page):
    for text in ("Got it", "Not now", "Allow all", "Decline optional cookies", "Accept all", "OK", "Skip"):
        try:
            b = page.get_by_role("button", name=text, exact=True)
            if b.count() and b.first.is_visible():
                b.first.click(timeout=2000)
                page.wait_for_timeout(500)
        except Exception:
            pass


def post_playwright(video, caption):
    from playwright.sync_api import sync_playwright
    sid = os.environ["TIKTOK_SESSIONID"].strip()
    cookies = [{"name": n, "value": sid, "domain": ".tiktok.com", "path": "/",
                "secure": True, "httpOnly": True, "sameSite": "None"}
               for n in ("sessionid", "sessionid_ss", "sid_tt")]
    caption = re.sub(r"\s+", " ", caption).strip()[:2000]
    headless = not os.environ.get("DISPLAY")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=headless,
                                        args=["--disable-blink-features=AutomationControlled"])
        except Exception:
            browser = p.chromium.launch(headless=headless,
                                        args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 1000}, locale="en-US",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        try:
            page.goto("https://www.tiktok.com/tiktokstudio/upload?from=webapp&lang=en",
                      wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(6000)
            shot(page, "1_opened")
            if "login" in page.url:
                raise RuntimeError("TikTok sent us to the LOGIN page -> your TIKTOK_SESSIONID secret is "
                                   "wrong or expired. Get a fresh sessionid cookie and update the secret.")
            dismiss_popups(page)
            file_input = page.locator("input[type=file]").first
            file_input.wait_for(state="attached", timeout=60000)
            file_input.set_input_files(str(video))
            print("Video file sent to TikTok, waiting for upload...", flush=True)

            editor = page.locator("div[contenteditable='true']").first
            editor.wait_for(state="visible", timeout=120000)
            page.wait_for_timeout(3000)
            dismiss_popups(page)
            shot(page, "2_uploading")
            editor.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            for word in caption.split(" "):
                page.keyboard.type(word, delay=15)
                if word.startswith(("#", "@")):
                    page.wait_for_timeout(1200)   # let the suggestion box appear...
                    page.keyboard.press("Escape")  # ...and close it without picking
                page.keyboard.type(" ")
            page.wait_for_timeout(1000)

            btn = page.locator("button[data-e2e='post_video_button']").first
            btn.wait_for(state="visible", timeout=60000)
            deadline = time.time() + 300
            while time.time() < deadline:   # wait until upload finished and Post is clickable
                dis = (btn.get_attribute("aria-disabled") or btn.get_attribute("data-disabled") or "").lower()
                if btn.is_enabled() and dis != "true":
                    break
                page.wait_for_timeout(2000)
            else:
                raise RuntimeError("Post button never became clickable (upload stuck?)")
            page.wait_for_timeout(2000)
            shot(page, "3_ready")
            btn.scroll_into_view_if_needed()
            btn.click()
            print("Clicked Post", flush=True)

            deadline = time.time() + 120
            while time.time() < deadline:
                page.wait_for_timeout(2000)
                try:
                    now = page.get_by_role("button", name=re.compile("Post now", re.I))
                    if now.count() and now.first.is_visible():
                        now.first.click()
                        print("Clicked 'Post now'", flush=True)
                        continue
                except Exception:
                    pass
                if "/tiktokstudio/content" in page.url or "/manage" in page.url:
                    break
                try:
                    if page.get_by_text(re.compile(r"(uploaded|published|Manage your posts)", re.I)).count():
                        break
                except Exception:
                    pass
            else:
                shot(page, "4_no_confirmation")
                raise RuntimeError("Clicked Post but never saw a confirmation")
            shot(page, "4_done")
        except Exception:
            shot(page, "error")
            raise
        finally:
            browser.close()


def post_uploader_lib(video, caption):
    from tiktok_uploader.upload import upload_video
    sid = os.environ["TIKTOK_SESSIONID"].strip()
    cookies = [{"name": n, "value": sid, "domain": ".tiktok.com", "path": "/",
                "secure": True, "httpOnly": True} for n in ("sessionid", "sessionid_ss", "sid_tt")]
    try:
        failed = upload_video(str(video), description=caption[:2000], cookies_list=cookies, headless=True)
    except TypeError:
        failed = upload_video(str(video), description=caption[:2000], sessionid=sid, headless=True)
    if failed:
        raise RuntimeError(f"tiktok-uploader failed: {failed}")


def posting_enabled():
    return os.environ.get("POST", "1").strip().lower() in ("1", "true", "yes")


def post(video, caption):
    if not posting_enabled():
        print("POST=0 -> not posting (video is in the pigeon-video artifact)")
        return
    if not os.environ.get("TIKTOK_SESSIONID"):
        raise RuntimeError("TIKTOK_SESSIONID secret is missing")
    errors = []
    for name, fn in (("browser uploader", post_playwright), ("tiktok-uploader", post_uploader_lib)):
        try:
            print(f"Posting with {name}...", flush=True)
            fn(video, caption)
            print(f"POSTED to TikTok with {name}")
            return
        except Exception as e:
            print(f"{name} failed: {e}", flush=True)
            errors.append(f"{name}: {e}")
            if "LOGIN page" in str(e):
                break
    raise RuntimeError("Could not post to TikTok -> " + " | ".join(errors))


# ----------------------------------------------------------------- main flow
def process(vid):
    """Make + post a pigeon video. Returns False if the video isn't Zack's."""
    info = video_info(vid)
    if not is_zach(info):
        print(f"Skipping {vid}: uploader is '{info.get('uploader')}', not {HANDLE}")
        return False
    caption = info.get("description") or info.get("title") or ""
    video = download(vid, info)
    text = transcribe(video)
    print("Transcript:", text)
    raw = WORK / "voice.mp3"
    words = asyncio.run(tts(text or "coo", raw))
    final = WORK / f"pigeon_{vid}.mp4"
    render(video, raw, words, final)
    post(final, caption)
    return True


def attempt(vid):
    tries = json.loads(TRIES.read_text()) if TRIES.exists() else {}
    tries[vid] = tries.get(vid, 0) + 1
    TRIES.write_text(json.dumps(tries))
    return tries[vid]


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
        n = attempt(vid)
        try:
            ok = process(vid)
        except Exception:
            if n >= MAX_ATTEMPTS:
                print(f"Giving up on {vid} after {n} tries")
                seen.add(vid)
                save(STATE, seen)
            raise
        seen.add(vid)
        save(STATE, seen)
        if ok:
            used.add(vid)
            save(USED, used)
            done += 1


def random_mode():
    used = load(USED)
    pool = [i for i in latest_videos(RANDOM_POOL) if i not in used]
    print(f"{len(pool)} Zack videos not used yet")
    if not pool:
        raise RuntimeError("Every video found has already been used")
    random.shuffle(pool)
    for vid in pool[:10]:
        print("Random pick:", vid)
        ok = process(vid)
        if ok:
            if posting_enabled():
                used.add(vid)
                save(USED, used)
                seen = load(STATE)
                seen.add(vid)
                save(STATE, seen)
            return
    raise RuntimeError("Couldn't find a usable Zack video in 10 tries")


def main():
    WORK.mkdir(exist_ok=True)
    STATE.parent.mkdir(exist_ok=True)
    make_cutout()
    get_font()
    mode = os.environ.get("MODE", "new").strip().lower()
    print("Mode:", mode)
    if mode == "random":
        random_mode()
    else:
        new_mode()


if __name__ == "__main__":
    sys.exit(main())
