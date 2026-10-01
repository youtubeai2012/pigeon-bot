"""Publish a finished pigeon clip to the connected YouTube channel."""

import os
import re
from pathlib import Path


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
REQUIRED = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")


def configured():
    return all(os.environ.get(name, "").strip() for name in REQUIRED)


def metadata(video_id, caption, transcript):
    first_sentence = re.split(r"(?<=[.!?])\s+", transcript.strip(), maxsplit=1)[0]
    title = re.sub(r"\s+", " ", first_sentence).strip() or "Pigeon video"
    if len(title) > 100:
        title = title[:100].rsplit(" ", 1)[0].rstrip(" ,.;:-") or title[:100]
    source = f"https://www.tiktok.com/@zackdfilms92/video/{video_id}"
    description = (f"{caption.strip()}\n\n" if caption.strip() else "") + \
        f"Original video by @zackdfilms92: {source}\n\n#Shorts"
    return title, description[:5000]


def upload(video, video_id, caption, transcript):
    """Return upload ID and visibility; require all three OAuth secrets."""
    missing = [name for name in REQUIRED if not os.environ.get(name, "").strip()]
    if missing:
        raise RuntimeError("YouTube is not connected: missing " + ", ".join(missing))

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    credentials = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    credentials.refresh(Request())
    title, description = metadata(video_id, caption, transcript)
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    media = MediaFileUpload(str(Path(video)), mimetype="video/mp4", chunksize=8 * 1024 * 1024,
                            resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body={"snippet": {"title": title, "description": description, "categoryId": "22"},
              "status": {"privacyStatus": "public"}},
        media_body=media,
    )
    response = None
    while response is None:
        progress, response = request.next_chunk(num_retries=5)
        if progress is not None:
            print(f"YouTube upload: {progress.progress():.0%}", flush=True)
    upload_id = response.get("id")
    if not upload_id:
        raise RuntimeError(f"YouTube did not return a video ID: {response}")
    privacy = response.get("status", {}).get("privacyStatus", "unknown")
    url = f"https://www.youtube.com/watch?v={upload_id}"
    print(f"YouTube upload finished: {url} (visibility: {privacy})", flush=True)
    if privacy != "public":
        print("YouTube kept this upload private. New API projects need Google's compliance audit "
              "before API uploads can publish publicly.", flush=True)
    return {"state": "published" if privacy == "public" else "private",
            "id": upload_id, "url": url, "privacy": privacy}
