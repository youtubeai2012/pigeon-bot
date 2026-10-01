"""Merge the runner's progress with the latest main branch after a post."""

import json
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).parent
STATE = ROOT / "state"
ASSETS = (ROOT / "assets/pigeon_cutout.png", ROOT / "assets/fonts/Anton-Regular.ttf")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True)


def merge_progress(current, posted):
    for name, value in posted.items():
        if name not in current:
            current[name] = value
        elif isinstance(value, list):
            current[name] = sorted(set(current[name]) | set(value))
        elif isinstance(value, dict):
            for key, count in value.items():
                current[name][key] = max(current[name].get(key, 0), count)
    return current


def main():
    posted = {p.name: json.loads(p.read_text()) for p in STATE.glob("*.json")}
    generated = {p.relative_to(ROOT): p.read_bytes() for p in ASSETS if p.exists()}
    git("config", "user.name", "pigeon-bot")
    git("config", "user.email", "pigeon-bot@users.noreply.github.com")
    for attempt in range(5):
        git("fetch", "origin", "main")
        git("reset", "--hard", "origin/main")
        current = {p.name: json.loads(p.read_text()) for p in STATE.glob("*.json")}
        for name, value in merge_progress(current, posted).items():
            path = STATE / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(value, sort_keys=True))
        for relative, contents in generated.items():
            path = ROOT / relative
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)
        git("add", "state", "assets")
        if git("status", "--porcelain").stdout.strip():
            git("commit", "-m", "pigeon bot: update state")
            result = subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=ROOT,
                                    capture_output=True, text=True)
            if result.returncode == 0:
                print("Progress saved")
                return
            if "fetch first" not in result.stderr and "non-fast-forward" not in result.stderr:
                raise RuntimeError(result.stderr)
            time.sleep(attempt + 1)
        else:
            print("Progress already saved")
            return
    raise RuntimeError("Could not save progress after five push attempts")


if __name__ == "__main__":
    main()
