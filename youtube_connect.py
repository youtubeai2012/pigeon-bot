"""Authorize your YouTube channel once and save OAuth secrets to this GitHub repo.

Run on your computer after downloading a Desktop OAuth client JSON from Google Cloud:
    python youtube_connect.py path/to/client_secret.json
"""

import argparse
import base64
import json
import os
import subprocess
import urllib.request

from google_auth_oauthlib.flow import InstalledAppFlow
from nacl.public import PublicKey, SealedBox

from youtube_upload import SCOPES


REPO = "youtubeai2012/pigeon-bot"
API = f"https://api.github.com/repos/{REPO}/actions/secrets"


def github_token():
    token = os.environ.get("GH_TOKEN", "").strip()
    if token:
        return token
    result = subprocess.run(["git", "credential", "fill"],
                            input="protocol=https\nhost=github.com\n\n",
                            capture_output=True, text=True, check=True)
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if not values.get("password"):
        raise RuntimeError("No GitHub login found. Set GH_TOKEN with access to repository Actions secrets.")
    return values["password"]


def save_secrets(values, token):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "User-Agent": "pigeon-youtube-connect", "X-GitHub-Api-Version": "2022-11-28"}
    with urllib.request.urlopen(urllib.request.Request(API + "/public-key", headers=headers),
                                timeout=30) as response:
        key = json.load(response)
    box = SealedBox(PublicKey(base64.b64decode(key["key"])))
    for name, value in values.items():
        encrypted = base64.b64encode(box.encrypt(value.encode())).decode()
        body = json.dumps({"encrypted_value": encrypted, "key_id": key["key_id"]}).encode()
        request = urllib.request.Request(API + "/" + name, data=body, method="PUT",
                                         headers={**headers, "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status not in (201, 204):
                raise RuntimeError(f"Could not save {name}: HTTP {response.status}")
        print(f"Saved {name} to GitHub Actions")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client_json", help="Desktop OAuth client JSON downloaded from Google Cloud")
    args = parser.parse_args()
    with open(args.client_json, encoding="utf-8") as file:
        config = json.load(file)
    client = config.get("installed")
    if not client:
        raise RuntimeError("Create a Desktop app OAuth client in Google Cloud and download its JSON file.")
    flow = InstalledAppFlow.from_client_config(config, scopes=SCOPES)
    flow.run_local_server(port=0, open_browser=False, access_type="offline", prompt="consent",
                          authorization_prompt_message="Open this URL in the browser signed into your YouTube channel: {url}")
    refresh_token = flow.credentials.refresh_token
    if not refresh_token:
        raise RuntimeError("Google did not return a refresh token. Remove the old grant and try again.")
    save_secrets({"YOUTUBE_CLIENT_ID": client["client_id"],
                  "YOUTUBE_CLIENT_SECRET": client["client_secret"],
                  "YOUTUBE_REFRESH_TOKEN": refresh_token}, github_token())
    print("YouTube connected. Future pigeon videos will also be sent to YouTube.")


if __name__ == "__main__":
    main()
