"""Vertical reframing inspired by OpenShorts layouts.

Track follows one face with a slow camera. Split stacks two people when they
are both in frame. Blur keeps the whole picture over a darkened background.
Captions and the hook are burned in with an ASS subtitle file, so the render
does not need ImageMagick.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def even(value):
    value = int(round(value))
    if value < 2:
        return 2
    return value - (value % 2)


def source_already_fits(src_w, src_h, target_aspect, tol=0.01):
    """True when the source is already as tall as the 9:16 output."""
    if src_h <= 0:
        return False
    return (src_w / float(src_h)) <= target_aspect * (1 + tol)


def smooth_track(centers, deadzone=0.025, alpha=0.18):
    """Heavy-tripod follow. Small jitters hold still; real moves ease in."""
    current = None
    smoothed = []
    for sample in centers:
        target = sample if sample is not None else current
        if target is None:
            smoothed.append(0.5)
            continue
        if current is None:
            current = target
        elif abs(target - current) >= deadzone:
            current = current + alpha * (target - current)
        smoothed.append(current)
    return smoothed


def expand_track(centers, sample_fps, command_fps=12):
    """Interpolate analysis samples so the crop eases instead of stepping."""
    if len(centers) <= 1:
        return list(centers)
    duration = (len(centers) - 1) / float(sample_fps)
    count = max(1, int(round(duration * command_fps)))
    expanded = []
    for index in range(count):
        position = (index / command_fps) * sample_fps
        left = min(int(position), len(centers) - 1)
        right = min(left + 1, len(centers) - 1)
        mix = position - left
        expanded.append(centers[left] * (1 - mix) + centers[right] * mix)
    return expanded


def crop_x(center_ratio, frame_w, crop_w):
    origin = int(round(center_ratio * frame_w - crop_w / 2))
    return max(0, min(frame_w - crop_w, origin))


def track_crop_size(src_w, src_h, out_w, out_h):
    aspect = out_w / float(out_h)
    crop_w = even(src_h * aspect)
    crop_h = even(src_h)
    if crop_w > src_w:
        crop_w = even(src_w)
        crop_h = even(crop_w / aspect)
    return crop_w, crop_h


def split_anchors(frames, min_fraction=0.5, min_gap=0.18):
    """Average left/right face when both are in at least half the samples.

    Shot/reverse-shot has one face per frame, so it stays a single crop.
    """
    pairs = []
    for faces in frames:
        if len(faces) < 2:
            continue
        ordered = sorted(faces[:2], key=lambda face: face["cx"])
        if ordered[1]["cx"] - ordered[0]["cx"] < min_gap:
            continue
        pairs.append(ordered)
    if not frames or len(pairs) < min_fraction * len(frames):
        return None
    left = sum(pair[0]["cx"] for pair in pairs) / len(pairs)
    right = sum(pair[1]["cx"] for pair in pairs) / len(pairs)
    top_y = sum(pair[0]["cy"] for pair in pairs) / len(pairs)
    return {"left": left, "right": right, "top_y": top_y}


def split_crop_size(src_w, src_h, out_w, out_h, left, right, tightness=0.8):
    """Zoom just enough that each half keeps the other speaker out."""
    panel_h = out_h // 2
    panel_aspect = out_w / float(panel_h)
    crop_h = even(src_h)
    crop_w = even(crop_h * panel_aspect * tightness)
    gap = max(0.2, (right - left) * 0.92)
    crop_w = min(crop_w, even(src_w * gap))
    crop_w = max(even(src_w * 0.28), min(crop_w, even(src_w)))
    crop_h = even(min(src_h, crop_w / panel_aspect))
    crop_w = even(min(src_w, crop_h * panel_aspect))
    return crop_w, crop_h


def blur_foreground_height(src_w, src_h, out_w, out_h, ratio=0.42):
    """Foreground is tall enough to read, and never a shrunk portrait."""
    full_width = even(round(out_w * src_h / float(src_w)))
    target = even(round(out_h * ratio))
    return min(out_h, max(target, full_width))


def choose_layout(src_w, src_h, out_w, out_h, frames, requested):
    requested = (requested or "auto").lower()
    if source_already_fits(src_w, src_h, out_w / float(out_h)):
        return "fit"
    if requested == "split":
        return "split" if split_anchors(frames) else "track"
    if requested == "blur":
        return "blur"
    if requested == "track":
        return "track"
    if split_anchors(frames):
        return "split"
    if any(frames):
        return "track"
    return "blur"


def largest_face_centers(frames):
    centers = []
    heights = []
    for faces in frames:
        if not faces:
            centers.append(None)
            heights.append(None)
            continue
        face = max(faces, key=lambda item: item["w"] * item["h"])
        centers.append(face["cx"])
        heights.append(face["cy"])
    return centers, heights


def hook_and_caption_pos(mode, out_w, out_h, face_y):
    """Keep the hook off the face. Split captions sit on the seam."""
    y = 0.5 if face_y is None else face_y
    if mode == "split":
        hook_y = 72 if y > 0.22 else int(out_h * 0.46)
        return (out_w // 2, hook_y, 8), (out_w // 2, out_h // 2, 5)
    caption = (out_w // 2, int(out_h * 0.90), 2)
    if y < 0.32:
        return (out_w // 2, int(out_h * 0.76), 2), caption
    return (out_w // 2, int(out_h * 0.07), 8), caption


def group_cues(cues, max_chars=42, max_gap=0.35, max_duration=2.4):
    groups = []
    current = None
    for cue in cues or []:
        text = re.sub(r"\s+", " ", (cue.get("text") or "")).strip()
        if not text:
            continue
        start = float(cue["start"])
        end = float(cue["end"])
        if current is None:
            current = {"start": start, "end": end, "text": text}
            continue
        merged = f"{current['text']} {text}"
        if (
            start - current["end"] <= max_gap
            and len(merged) <= max_chars
            and end - current["start"] <= max_duration
        ):
            current["text"] = merged
            current["end"] = end
        else:
            groups.append(current)
            current = {"start": start, "end": end, "text": text}
    if current:
        groups.append(current)
    return groups


def ass_escape(text):
    cleaned = text.replace("\\", "").replace("{", "(").replace("}", ")")
    return cleaned.replace("\n", r"\N")


def wrap_ass(text, width=26):
    words = ass_escape(text).split()
    lines = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if current and len(trial) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return r"\N".join(lines)


def ass_time(seconds):
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remain = seconds % 60
    return f"{hours}:{minutes:02d}:{remain:05.2f}"


def build_ass(out_w, out_h, hook, cues, mode, face_y, duration):
    hook_pos, caption_pos = hook_and_caption_pos(mode, out_w, out_h, face_y)
    events = []
    if hook:
        hook_end = min(3.6, duration)
        events.append(
            "Dialogue: 0,{start},{end},Hook,,0,0,0,,{{\\an{align}\\pos({x},{y})}}{text}".format(
                start=ass_time(0),
                end=ass_time(hook_end),
                align=hook_pos[2],
                x=hook_pos[0],
                y=hook_pos[1],
                text=wrap_ass(hook[:80], 22),
            )
        )
    for cue in group_cues(cues):
        end = min(cue["end"], duration)
        if end - cue["start"] < 0.15:
            continue
        events.append(
            "Dialogue: 0,{start},{end},Cap,,0,0,0,,{{\\an{align}\\pos({x},{y})}}{text}".format(
                start=ass_time(cue["start"]),
                end=ass_time(end),
                align=caption_pos[2],
                x=caption_pos[0],
                y=caption_pos[1],
                text=wrap_ass(cue["text"]),
            )
        )
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {out_w}
PlayResY: {out_h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,Arial,62,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,0,8,40,40,40,1
Style: Cap,Arial,52,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,2,50,50,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header + "\n".join(events) + ("\n" if events else "")


def dedupe_sendcmd(xs, fps, crop_w, frame_w):
    lines = []
    previous = None
    for index, center in enumerate(xs):
        origin = crop_x(center, frame_w, crop_w)
        if origin == previous:
            continue
        lines.append(f"{index / fps:.4f} crop@c x {origin};")
        previous = origin
    return lines


def ffmpeg_exe():
    configured = os.environ.get("FFMPEG_PATH", "").strip()
    if configured and Path(configured).exists():
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def escape_filter_path(path):
    text = Path(path).as_posix()
    if len(text) > 1 and text[1] == ":":
        text = text[0] + r"\:" + text[2:]
    return text.replace("'", r"\'")


def probe_video(ffmpeg, path):
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    details = (result.stderr or "") + (result.stdout or "")
    match = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", details)
    if not match:
        raise RuntimeError("Could not read video size")
    has_audio = "Audio:" in details
    return int(match.group(1)), int(match.group(2)), has_audio


def _run(cmd):
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "")[-1800:]
        raise RuntimeError(tail.strip() or "ffmpeg failed")
    return result


def sample_faces(ffmpeg, src, start, duration, fps=4):
    try:
        import cv2
    except ImportError:
        return []
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    if detector.empty():
        return []
    frames = []
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        _run([
            ffmpeg, "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
            "-i", str(src), "-vf", f"fps={fps},scale=640:-2",
            "-q:v", "6", str(folder / "%04d.jpg"),
        ])
        for image_path in sorted(folder.glob("*.jpg")):
            image = cv2.imread(str(image_path))
            if image is None:
                frames.append([])
                continue
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            height, width = gray.shape[:2]
            rects = detector.detectMultiScale(
                gray, scaleFactor=1.15, minNeighbors=5, minSize=(28, 28)
            )
            faces = []
            for x, y, w, h in rects:
                faces.append({
                    "cx": (x + w / 2) / width,
                    "cy": (y + h / 2) / height,
                    "w": w / width,
                    "h": h / height,
                })
            faces.sort(key=lambda face: face["w"] * face["h"], reverse=True)
            frames.append(faces[:3])
    return frames


def render_vertical_clip(
    src, dest, start, end, out_w, out_h, fps=30, mode="auto",
    hook=None, cues=None, burn_captions=True, max_duration=60,
):
    """Cut, reframe, and burn captions in one ffmpeg pass. Returns False if ffmpeg is missing."""
    ffmpeg = ffmpeg_exe()
    if not ffmpeg:
        return False
    duration = max(0.4, float(end) - float(start))
    speed = duration / max_duration if duration > max_duration else 1.0
    src_w, src_h, has_audio = probe_video(ffmpeg, src)
    face_frames = sample_faces(ffmpeg, src, start, duration) if mode in ("auto", "track", "split") else []
    layout = choose_layout(src_w, src_h, out_w, out_h, face_frames, mode)
    centers, face_ys = largest_face_centers(face_frames)
    known_y = [value for value in face_ys if value is not None]
    face_y = sorted(known_y)[len(known_y) // 2] if known_y else None
    if layout == "split":
        anchors = split_anchors(face_frames)
        face_y = anchors["top_y"] if anchors else face_y
    output_duration = duration / speed
    if abs(speed - 1.0) >= 0.01 and cues:
        cues = [
            {**cue, "start": cue["start"] / speed, "end": cue["end"] / speed}
            for cue in cues
        ]

    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        ass_path = folder / "captions.ass"
        if burn_captions or hook:
            ass_path.write_text(
                build_ass(
                    out_w, out_h, hook, cues if burn_captions else [],
                    "track" if layout == "fit" else layout, face_y, output_duration,
                ),
                encoding="utf-8",
            )
            subtitle_filter = f"subtitles='{escape_filter_path(ass_path)}'"
        else:
            subtitle_filter = None

        video_filter = _video_filter(
            layout, src_w, src_h, out_w, out_h, fps, speed,
            centers, face_frames, folder, subtitle_filter, has_audio,
        )
        cmd = [
            ffmpeg, "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
            "-i", str(src), "-filter_complex", video_filter,
            "-map", "[v]",
        ]
        if has_audio:
            audio_map = "[a]" if abs(speed - 1.0) >= 0.01 else "0:a"
            cmd += ["-map", audio_map, "-c:a", "aac", "-b:a", "160k"]
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-r", str(fps), "-movflags", "+faststart", str(dest),
        ]
        _run(cmd)
    print(f"[OK] Reframes as {layout}")
    return True


def _atempo(speed):
    parts = []
    remaining = speed
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining:.4f}")
    return ",".join(parts)


def _video_filter(layout, src_w, src_h, out_w, out_h, fps, speed, centers, face_frames, folder, subtitle_filter, has_audio):
    finish = []
    if abs(speed - 1.0) >= 0.01:
        finish.append(f"setpts=PTS/{speed:.4f}")
    if subtitle_filter:
        finish.append(subtitle_filter)
    tail = ("," + ",".join(finish)) if finish else ""
    audio = ""
    if has_audio and abs(speed - 1.0) >= 0.01:
        audio = f";[0:a]{_atempo(speed)}[a]"

    if layout == "fit":
        body = (
            f"[0:v]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
            f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,fps={fps}{tail}[v]"
        )
        return body + audio

    if layout == "blur":
        fg_h = blur_foreground_height(src_w, src_h, out_w, out_h)
        body = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h},boxblur=24:2,eq=brightness=-0.12[bgb];"
            f"[fg]scale=-2:{fg_h}:flags=lanczos[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,fps={fps}{tail}[v]"
        )
        return body + audio

    if layout == "split":
        anchors = split_anchors(face_frames) or {"left": 0.27, "right": 0.73}
        crop_w, crop_h = split_crop_size(src_w, src_h, out_w, out_h, anchors["left"], anchors["right"])
        left = crop_x(anchors["left"], src_w, crop_w)
        right = crop_x(anchors["right"], src_w, crop_w)
        top_y = max(0, even((src_h - crop_h) / 2))
        panel_h = even(out_h / 2)
        body = (
            f"[0:v]split=2[top][bot];"
            f"[top]crop={crop_w}:{crop_h}:{left}:{top_y},scale={out_w}:{panel_h}:flags=lanczos[t];"
            f"[bot]crop={crop_w}:{crop_h}:{right}:{top_y},scale={out_w}:{panel_h}:flags=lanczos[b];"
            f"[t][b]vstack,fps={fps}{tail}[v]"
        )
        return body + audio

    crop_w, crop_h = track_crop_size(src_w, src_h, out_w, out_h)
    smoothed = smooth_track(centers or [0.5])
    expanded = expand_track(smoothed, sample_fps=4, command_fps=12)
    origins = [crop_x(center, src_w, crop_w) for center in expanded]
    top_y = max(0, even((src_h - crop_h) / 2))
    if len(set(origins)) <= 1:
        crop = f"crop={crop_w}:{crop_h}:{origins[0]}:{top_y}"
    else:
        command_path = folder / "crop.cmd"
        lines = []
        previous = None
        for index, origin in enumerate(origins):
            if origin == previous:
                continue
            lines.append(f"{index / 12:.4f} crop@c x {origin};")
            previous = origin
        command_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        crop = f"sendcmd=filename='{escape_filter_path(command_path)}',crop@c={crop_w}:{crop_h}:{origins[0]}:{top_y}"
    return f"[0:v]{crop},scale={out_w}:{out_h}:flags=lanczos,fps={fps}{tail}[v]" + audio


def write_thumbnail(video_path, image_path):
    ffmpeg = ffmpeg_exe()
    if not ffmpeg:
        return False
    _run([
        ffmpeg, "-y", "-ss", "0.4", "-i", str(video_path),
        "-frames:v", "1", "-vf", "scale=400:-2", str(image_path),
    ])
    return True
