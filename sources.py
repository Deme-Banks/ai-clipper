"""Resolve a YouTube or Twitch link to a direct stream, without saving the file."""

from pathlib import Path


class UnsupportedUrlError(Exception):
    """The URL is not a YouTube video or a Twitch VOD/clip."""


DEFAULT_LIVE_SECONDS = 180
MAX_LIVE_SECONDS = 600


def clamp_live_seconds(requested, default=DEFAULT_LIVE_SECONDS):
    """A live capture is always a finite window, never an open-ended recording."""
    if requested is None or requested == "":
        requested = default
    try:
        seconds = float(requested)
    except (TypeError, ValueError):
        seconds = float(default)
    if seconds <= 0:
        seconds = float(default)
    return min(MAX_LIVE_SECONDS, max(1.0, seconds))


def interpret_cli_window(token, default_seconds=DEFAULT_LIVE_SECONDS):
    """CLI window: 180 is seconds, 3 or 3m is minutes. Always clamped."""
    if token is None or str(token).strip() == "":
        return clamp_live_seconds(default_seconds)
    text = str(token).strip().lower()
    if text.endswith("m"):
        return clamp_live_seconds(float(text[:-1]) * 60, default_seconds)
    number = float(text)
    if number <= 10:
        return clamp_live_seconds(number * 60, default_seconds)
    return clamp_live_seconds(number, default_seconds)


def is_live_media(info):
    return bool(info.get("is_live") or info.get("live_status") == "is_live")


def live_capture_plan(info, requested_seconds=None):
    """None when the URL is not live. Otherwise a bounded window from the newest part.

    A known DVR duration seeks to the end minus the window. Without one, capture
    starts at the live edge. The duration is never left open.
    """
    if not is_live_media(info):
        return None
    seconds = clamp_live_seconds(requested_seconds)
    try:
        duration = float(info.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    seek = (duration - seconds) if duration > seconds else None
    return {"seconds": seconds, "seek": seek, "dvr": seek is not None}


def video_source(url):
    """Return YouTube, Twitch, or None."""
    host = (url or "").lower()
    if "twitch.tv" in host:
        return "Twitch"
    if any(name in host for name in ("youtube.com", "youtu.be", "youtube-nocookie.com")):
        return "YouTube"
    return None


def _ydl_options():
    options = {
        "format": "b/bv*+ba/b*",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    try:
        from framing import ffmpeg_exe
        ffmpeg = ffmpeg_exe()
        if ffmpeg:
            options["ffmpeg_location"] = str(Path(ffmpeg).parent)
    except Exception:
        pass
    return options


def _stream_urls(info):
    """One combined URL, or separate video and audio URLs."""
    requested = info.get("requested_formats") or []
    video = None
    audio = None
    for fmt in requested:
        if fmt.get("vcodec") not in (None, "none") and video is None:
            video = fmt
        elif fmt.get("acodec") not in (None, "none") and audio is None:
            audio = fmt
    if video and video.get("url"):
        audio_url = audio.get("url") if audio and audio.get("url") and audio is not video else None
        return video["url"], audio_url, video
    if info.get("url"):
        return info["url"], None, info
    return None, None, info


def resolve_media(url, live_seconds=None):
    """Metadata and a direct playable URL. Does not write the source video."""
    source = video_source(url)
    if source is None:
        raise UnsupportedUrlError(
            "Paste a YouTube link (watch, Shorts, or youtu.be) or a Twitch VOD or clip link."
        )
    import yt_dlp
    with yt_dlp.YoutubeDL(_ydl_options()) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") == "playlist":
        entries = [entry for entry in (info.get("entries") or []) if entry]
        if not entries:
            raise UnsupportedUrlError("That link did not contain a video.")
        info = entries[0]
    video_url, audio_url, chosen = _stream_urls(info)
    if not video_url:
        raise UnsupportedUrlError("Could not find a playable stream for that link.")
    has_audio = bool(audio_url) or chosen.get("acodec") not in (None, "none")
    plan = live_capture_plan(info, live_seconds)
    duration = plan["seconds"] if plan else float(info.get("duration") or 0)
    return {
        "source": source,
        "title": info.get("title") or info.get("id") or "video",
        "id": info.get("id") or "video",
        "duration": duration,
        "page_url": info.get("webpage_url") or url,
        "video_url": video_url,
        "audio_url": audio_url,
        "headers": dict(info.get("http_headers") or {}),
        "width": int(chosen.get("width") or info.get("width") or 0),
        "height": int(chosen.get("height") or info.get("height") or 0),
        "has_audio": has_audio,
        "is_live": plan is not None,
        "live_seconds": plan["seconds"] if plan else None,
        "live_seek": plan["seek"] if plan else None,
    }
