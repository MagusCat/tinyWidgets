#!/usr/bin/env python3
"""GitHub status for eww (defpoll). Always prints one valid JSON object.

Fetches via the authenticated `gh` CLI; owns its cache under $XDG_CACHE_HOME/tinyWidgets/<profile>/github and
falls back to the cache (marked offline) when gh is missing, logged out or offline.
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import time
import urllib.parse
import urllib.request

from pathlib import Path
from .paths import PROFILE_KEY
CACHE_DIR = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home()/'.cache')))/'tinyWidgets'/PROFILE_KEY/'github'
CACHE = str(CACHE_DIR/'status.json')
AVATAR = str(CACHE_DIR/'avatar.png')
AVATAR_RAW = str(CACHE_DIR/'avatar-raw.png')


def prepare_cache():
    """Create owned storage; preserve old cached data during migration."""
    CACHE_DIR.mkdir(parents=True,exist_ok=True)
    for old,new in [('eww-github.json',CACHE),('eww-github-avatar.png',AVATAR),('eww-github-avatar-raw.png',AVATAR_RAW)]:
        source=Path.home()/'.cache'/old
        if source.is_file() and not Path(new).exists():
            shutil.copy2(source,new)

AVATAR_MAX_AGE = 24 * 3600  # refresh the picture at most once a day
AVATAR_SIZE = 48
WEEKS = 18
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
QUERY = """
query {
  viewer {
    login
    pullRequests(states: OPEN) { totalCount }
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
  }
}
"""


def gh(*args):
    res = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=25)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip()[:200])
    return res.stdout


def empty():
    return {"login": "", "avatar": "", "total": 0, "streak": 0, "prs": 0, "notifs": 0,
            "weeks": [[{"l": -1}] * 7 for _ in range(WEEKS)],
            "offline": True, "updated": "", "status": "offline"}


def fetch():
    data = json.loads(gh("api", "graphql", "-f", f"query={QUERY}"))["data"]["viewer"]
    days = [d for w in data["contributionsCollection"]["contributionCalendar"]["weeks"]
            for d in w["contributionDays"]]
    days.sort(key=lambda d: d["date"])
    today = dt.date.today().isoformat()
    days = [d for d in days if d["date"] <= today]

    # Current streak: consecutive days with contributions, ending today (or yesterday).
    streak = 0
    seq = list(reversed(days))
    if seq and seq[0]["date"] == today and seq[0]["contributionCount"] == 0:
        seq = seq[1:]
    for d in seq:
        if d["contributionCount"] <= 0:
            break
        streak += 1

    # Last WEEKS calendar weeks (Sunday-first like GitHub), padded with l=-1.
    start = dt.date.today() - dt.timedelta(days=(dt.date.today().weekday() + 1) % 7 + 7 * (WEEKS - 1))
    by_date = {d["date"]: d for d in days}
    weeks, total = [], 0
    for w in range(WEEKS):
        col = []
        for k in range(7):
            day = (start + dt.timedelta(days=7 * w + k)).isoformat()
            d = by_date.get(day)
            if d is None:
                col.append({"l": -1})
            else:
                total += d["contributionCount"]
                col.append({"l": LEVELS.get(d["contributionLevel"], 0)})
        weeks.append(col)

    notifs = 0
    out = gh("api", "notifications", "--paginate", "--jq", "length")
    for line in out.split():
        notifs += int(line)

    return {"login": data["login"], "total": total, "streak": streak,
            "prs": data["pullRequests"]["totalCount"], "notifs": notifs, "weeks": weeks,
            "offline": False, "updated": dt.datetime.now().strftime("%H:%M"), "status": "online"}


def refresh_avatar():
    """Download the profile picture (once a day) and cut a circular 48x48 PNG.

    Any failure keeps the previous files, so the card still shows the old picture offline.
    """
    try:
        if time.time() - os.stat(AVATAR).st_mtime < AVATAR_MAX_AGE:
            return
    except OSError:
        pass
    prepare_cache()
    url = gh("api", "user", "--jq", ".avatar_url").strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname != "avatars.githubusercontent.com":
        raise RuntimeError("unexpected avatar url")
    query = urllib.parse.urlencode(urllib.parse.parse_qsl(parts.query) + [("s", str(AVATAR_SIZE * 4))])
    with urllib.request.urlopen(urllib.parse.urlunsplit(parts._replace(query=query)), timeout=15) as res:
        data = res.read(5 * 1024 * 1024)
    if not data:
        raise RuntimeError("empty avatar")
    tmp_raw, tmp = AVATAR_RAW + ".tmp", AVATAR + ".tmp.png"
    with open(tmp_raw, "wb") as fh:
        fh.write(data)
    big = AVATAR_SIZE * 4  # draw the mask at 4x, then downscale for a smooth edge
    r = big / 2
    subprocess.run(
        ["magick", tmp_raw + "[0]", "-resize", f"{big}x{big}^", "-gravity", "center",
         "-extent", f"{big}x{big}", "-alpha", "set",
         "(", "-size", f"{big}x{big}", "xc:none", "-fill", "white",
         "-draw", f"circle {r - 0.5},{r - 0.5} {r - 0.5},0", ")",
         "-compose", "DstIn", "-composite", "-resize", f"{AVATAR_SIZE}x{AVATAR_SIZE}",
         "PNG32:" + tmp],
        check=True, capture_output=True, timeout=20)
    os.replace(tmp_raw, AVATAR_RAW)
    os.replace(tmp, AVATAR)


def snapshot():
    try:
        prepare_cache()
        if not shutil.which("gh"):
            raise RuntimeError("gh not found")
        result = fetch()
        try:
            refresh_avatar()
        except Exception:  # noqa: BLE001 - keep the old picture
            pass
        try:
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            tmp = CACHE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(result, fh)
            os.replace(tmp, CACHE)
        except OSError:
            pass
    except Exception:  # noqa: BLE001 - any failure falls back to cache
        try:
            with open(CACHE, encoding="utf-8") as fh:
                result = json.load(fh)
            result["offline"] = True
            result["status"] = "offline · cached " + str(result.get("updated", ""))
        except (OSError, ValueError):
            result = empty()
    result["avatar"] = AVATAR if os.path.isfile(AVATAR) else ""
    return result


def main():
    print(json.dumps(snapshot(),ensure_ascii=False))

if __name__ == "__main__":
    main()
