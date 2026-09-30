"""Pigeon bot: new @zachdfilms TikTok -> transcript -> whispering pigeon over muted original -> post."""
import asyncio, json, os, subprocess, sys
from pathlib import Path

ACCOUNT = "https://www.tiktok.com/@zachdfilms"
ROOT = Path(__file__).parent
STATE = ROOT / "state" / "seen.json"
PIGEON_RAW = ROOT / "assets" / "pigeon.png"
PIGEON_CUT = ROOT / "assets" / "pigeon_cutout.png"
WORK = ROOT / "work"
VOICE = "en-US-GuyNeural"          # free Microsoft Edge voice
MAX_PER_RUN = 1                     # post at most 1 video per run (looks less bot-like)


def run(cmd):
    print("+", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=nw=1:nk=1", path]).strip())


def make_cutout():
    """Remove the pigeon's background once, then reuse the cutout."""
    if PIGEON_CUT.exists():
        return
    from rembg import remove
    from PIL import Image
    img = remove(Image.open(PIGEON_RAW))
    img = img.crop(img.getbbox())
    img.save(PIGEON_CUT)
    print("Pigeon background removed ->", PIGEON_CUT)


def latest_videos(n=5):
    data = json.loads(run(["yt-dlp", "--flat-playlist", "--playlist-end", str(n), "-J", ACCOUNT]))
    return [e["id"] for e in data.get("entries", [])]


def download(video_id):
    url = f"{ACCOUNT}/video/{video_id}"
    out = WORK / f"{video_id}.mp4"
    info = json.loads(run(["yt-dlp", "-J", url]))
    run(["yt-dlp", "-f", "mp4/best", "-o", str(out), url])
    return out, info.get("description") or info.get("title") or ""


def transcribe(video):
    import whisper
    model = whisper.load_model("base")
    return model.transcribe(str(video))["text"].strip()


async def tts(text, out):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate="-5%", pitch="+15Hz", volume="-20%").save(str(out))


def render(video, voice_raw, out):
    # Make the TTS sound whispery: thin it out, add breathy noise, a touch of room.
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
        # bottom-left, raised above TikTok's caption area, gentle bob while 'whispering'
        "[bg][p]overlay=x=30:y=H-h-320+8*sin(2*PI*t*2.5)[v]"
    )
    run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", video, "-loop", "1", "-i", PIGEON_CUT,
         "-i", voice, "-filter_complex", fc, "-map", "[v]", "-map", "2:a",
         "-t", f"{length:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", out])  # original audio dropped = muted


def post(video, caption):
    from tiktok_uploader.upload import upload_video
    failed = upload_video(str(video), description=caption[:2200],
                          sessionid=os.environ["TIKTOK_SESSIONID"], headless=True)
    if failed:
        raise RuntimeError(f"TikTok upload failed: {failed}")


def main():
    WORK.mkdir(exist_ok=True)
    STATE.parent.mkdir(exist_ok=True)
    make_cutout()
    first_run = not STATE.exists()
    seen = set(json.loads(STATE.read_text())) if not first_run else set()
    ids = latest_videos()
    if first_run:  # don't dump his whole back catalogue on the first run
        STATE.write_text(json.dumps(sorted(ids)))
        print("First run: marked existing videos as seen. Waiting for new posts.")
        return
    new = [i for i in reversed(ids) if i not in seen][:MAX_PER_RUN]
    if not new:
        print("No new videos.")
    for vid in new:
        video, caption = download(vid)
        text = transcribe(video)
        print("Transcript:", text)
        raw = WORK / "voice.mp3"
        asyncio.run(tts(text or "...", raw))
        final = WORK / f"pigeon_{vid}.mp4"
        render(video, raw, final)
        post(final, caption)
        seen.add(vid)
        STATE.write_text(json.dumps(sorted(seen)))
        print("Posted", vid)


if __name__ == "__main__":
    sys.exit(main())
