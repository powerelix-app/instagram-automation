"""Разбор чужих IG-профилей и роликов для анализа/адаптации.

Usage:
  python ig_analyze.py reel <url> [--tag name]      # скачать один ролик
  python ig_analyze.py profile <username> [--n 10]  # скачать топ-N последних роликов профиля
  python ig_analyze.py prep <dir|mp4>               # транскрипт (Scribe) + кадры для всех mp4

Результат: analysis/<tag>/  ->  video.mp4, transcript.txt, frames/f0..f8.jpg
Дальше Claude читает кадры/транскрипты и делает разбор.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
BASE = Path(__file__).parent / "analysis"
YT = Path(__file__).parent / ".venv/bin/yt-dlp"
ELEVEN = os.getenv("ELEVENLABS_API_KEY", "")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


APIFY = os.getenv("APIFY_TOKEN") or os.getenv("APIFY_API_TOKEN", "")
APIFY_ACTOR = "apify~instagram-scraper"


def apify_items(input_json: dict) -> list:
    """Синхронный запуск Apify-актора, возвращает items датасета."""
    r = requests.post(
        f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items",
        params={"token": APIFY}, json=input_json, timeout=300)
    if not r.ok:
        print(f"  APIFY {r.status_code}: {r.text[:200]}")
        return []
    return r.json()


def dl_reel(url: str, tag: str) -> "Path | None":
    """Скачать один ролик: Apify (без логина) -> fallback yt-dlp с куками."""
    out = BASE / tag
    out.mkdir(parents=True, exist_ok=True)
    existing = list(out.glob("video.mp4"))
    if existing:
        return existing[0]
    # 1) Apify — надёжный путь без сессии
    if APIFY:
        items = apify_items({"directUrls": [url], "resultsType": "posts",
                             "resultsLimit": 1, "addParentData": False})
        for it in items:
            vurl = it.get("videoUrl") or (it.get("videoUrls") or [None])[0]
            if vurl:
                data = requests.get(vurl, timeout=300).content
                p = out / "video.mp4"
                p.write_bytes(data)
                meta = out / "meta.txt"
                meta.write_text(
                    f"url: {url}\nowner: {it.get('ownerUsername')}\n"
                    f"likes: {it.get('likesCount')}\ncomments: {it.get('commentsCount')}\n"
                    f"views: {it.get('videoPlayCount') or it.get('videoViewCount')}\n"
                    f"caption: {(it.get('caption') or '')[:500]}\n")
                return p
    # 2) fallback: yt-dlp с куками Chrome
    tpl = str(out / "video.%(ext)s")
    for cookies in (["--cookies-from-browser", "chrome"], []):
        r = run([str(YT), *cookies, "-f", "mp4/best", "--no-playlist",
                 "-o", tpl, url], timeout=180)
        vids = list(out.glob("video.*"))
        if vids:
            return vids[0]
        err = (r.stderr or "")[-300:]
    print(f"  FAIL {url}: {err}")
    return None


def dl_profile(username: str, n: int) -> list:
    """Скачать N последних роликов профиля через Apify (без логина)."""
    got = []
    items = apify_items({
        "directUrls": [f"https://www.instagram.com/{username}/"],
        "resultsType": "posts", "resultsLimit": n * 3,
        "onlyPostsNewerThan": "", "addParentData": False})
    reels = [it for it in items
             if it.get("videoUrl") or it.get("videoUrls")][:n]
    print(f"  найдено роликов: {len(reels)} (из {len(items)} постов)")
    for i, it in enumerate(reels):
        code = it.get("shortCode") or str(i)
        tag = f"{username}_{i:02d}_{code}"
        out = BASE / tag
        out.mkdir(parents=True, exist_ok=True)
        vurl = it.get("videoUrl") or (it.get("videoUrls") or [None])[0]
        try:
            (out / "video.mp4").write_bytes(requests.get(vurl, timeout=300).content)
            (out / "meta.txt").write_text(
                f"code: {code}\nlikes: {it.get('likesCount')}\n"
                f"comments: {it.get('commentsCount')}\n"
                f"views: {it.get('videoPlayCount') or it.get('videoViewCount')}\n"
                f"caption: {(it.get('caption') or '')[:500]}\n")
            got.append(out / "video.mp4")
            print(f"  OK {tag} (views={it.get('videoPlayCount')})")
        except Exception as e:
            print(f"  FAIL {tag}: {e}")
    return got


def prep(target: str):
    """Транскрипт (ElevenLabs Scribe) + 9 кадров для каждого mp4."""
    t = Path(target)
    vids = [t] if t.suffix == ".mp4" else sorted(t.rglob("video.mp4"))
    for v in vids:
        d = v.parent
        # аудио → Scribe
        mp3 = d / "_audio.mp3"
        run(["ffmpeg", "-y", "-i", str(v), "-vn", "-acodec", "libmp3lame",
             "-q:a", "5", str(mp3)])
        txt = d / "transcript.txt"
        if ELEVEN and mp3.exists() and not txt.exists():
            resp = requests.post("https://api.elevenlabs.io/v1/speech-to-text",
                                 headers={"xi-api-key": ELEVEN},
                                 files={"file": open(mp3, "rb")},
                                 data={"model_id": "scribe_v1"}, timeout=180)
            if resp.ok:
                txt.write_text(resp.json().get("text", ""))
        # кадры
        fr = d / "frames"
        fr.mkdir(exist_ok=True)
        dur = float(run(["ffprobe", "-v", "error", "-show_entries",
                         "format=duration", "-of", "default=nw=1:nk=1",
                         str(v)]).stdout or 10)
        for i in range(9):
            run(["ffmpeg", "-y", "-ss", str(round(dur * i / 9, 2)), "-i", str(v),
                 "-frames:v", "1", "-vf", "scale=360:-1", str(fr / f"f{i}.jpg")])
        print(f"  PREP {d.name}: {dur:.1f}s, transcript={'да' if txt.exists() else 'нет'}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "reel":
        tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "reel"
        p = dl_reel(sys.argv[2], tag)
        if p:
            prep(str(p))
    elif cmd == "profile":
        n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 10
        for p in dl_profile(sys.argv[2], n):
            prep(str(p))
    elif cmd == "prep":
        prep(sys.argv[2])
    else:
        print(__doc__)
