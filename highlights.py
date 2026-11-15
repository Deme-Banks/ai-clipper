"""Rank transcript moments the way a shorts editor would.

Long videos are split into overlapping chunks so the later half is not dropped.
Each candidate gets a 0-100 viral score, a hook line, and a one-line reason.
A clip that overlaps a higher-scoring one by more than half is discarded.
"""

import json
import re


CHUNK_SECONDS = 1200
LONG_VIDEO_SECONDS = 1800
CHUNK_OVERLAP_SECONDS = 60

VIRALITY_SIGNALS = """
Rank moments by how likely they are to stop a scroll, in this order:
1. A hook in the first seconds: a secret, a mistake, a contradiction, or a dare.
2. An emotional peak: surprise, laughter, anger, or an unscripted reaction.
3. A sharp opinion someone would agree or argue with.
4. A reveal: a number, confession, or fact that changes the story.
5. Conflict: disagreement or a problem confronted directly.
6. A line that stands alone as a quote.
7. The payoff of a story, not the setup.
8. A tip the viewer can use immediately.
Ignore filler, greetings, and moments that need the rest of the video to make sense.
"""


def transcript_chunks(cues, duration, chunk_seconds=CHUNK_SECONDS, overlap=CHUNK_OVERLAP_SECONDS, threshold=LONG_VIDEO_SECONDS):
    """One chunk for a normal video. Overlapping windows once it passes 30 minutes."""
    if duration < threshold:
        return [list(cues)]
    chunks = []
    start = 0.0
    while start < duration:
        end = min(start + chunk_seconds, duration)
        window_end = min(duration, end + overlap)
        selected = [
            cue for cue in cues
            if cue["end"] > start and cue["start"] < window_end
        ]
        if selected:
            chunks.append(selected)
        if end >= duration:
            break
        start += chunk_seconds - overlap
    return chunks or [list(cues)]


def format_cues(cues, limit=12000):
    lines = [f"[{cue['start']:.1f}-{cue['end']:.1f}] {cue['text'].strip()}" for cue in cues if cue.get("text")]
    text = "\n".join(lines)
    if len(text) <= limit:
        return text
    step = max(1, len(lines) // 140)
    return "\n".join(lines[::step])[:limit]


def parse_json_object(raw):
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            array_start = text.find("[")
            array_end = text.rfind("]")
            if array_start == -1 or array_end == -1:
                raise
            parsed = json.loads(text[array_start:array_end + 1])
        else:
            parsed = json.loads(text[start:end + 1])
    if isinstance(parsed, list):
        return {"highlights": parsed}
    if isinstance(parsed, dict) and "highlights" not in parsed:
        for key in ("clips", "results", "data"):
            if isinstance(parsed.get(key), list):
                return {"highlights": parsed[key]}
    return parsed


def sanitize_highlights(items, duration, min_duration, max_duration):
    cleaned = []
    if not isinstance(items, list):
        return cleaned
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start_time"))
            end = float(item.get("end_time"))
            raw_score = item.get("score", item.get("engagement_score", 0))
            score = int(float(raw_score))
        except (TypeError, ValueError):
            continue
        score = max(0, min(100, score))
        if start < 0 or end <= start or end > duration + 1:
            continue
        end = min(end, duration)
        length = end - start
        if length < min_duration or length > max_duration:
            continue
        cleaned.append({
            "_raw_score": score,
            "title": str(item.get("title") or "Highlight").strip()[:120],
            "start_time": start,
            "end_time": end,
            "score": score,
            "hook_sentence": str(item.get("hook_sentence") or item.get("hook") or "").strip()[:140],
            "virality_reason": str(item.get("virality_reason") or item.get("reason") or "").strip()[:240],
        })
    if cleaned and max(item["_raw_score"] for item in cleaned) <= 10:
        for item in cleaned:
            item["score"] = item["_raw_score"] * 10
    for item in cleaned:
        item.pop("_raw_score", None)
    return cleaned


def dedupe_highlights(highlights, overlap_ratio=0.5):
    """Keep the higher score when two clips cover the same stretch."""
    ordered = sorted(highlights, key=lambda item: item.get("score", 0), reverse=True)
    kept = []
    for candidate in ordered:
        length = candidate["end_time"] - candidate["start_time"]
        if length <= 0:
            continue
        overlaps = False
        for chosen in kept:
            shared = min(candidate["end_time"], chosen["end_time"]) - max(candidate["start_time"], chosen["start_time"])
            if shared > overlap_ratio * length:
                overlaps = True
                break
        if not overlaps:
            kept.append(candidate)
    return kept


def content_type_prompt(sample):
    return (
        "Classify this transcript sample. content_type is one of: "
        "podcast, interview, tutorial, lecture, commentary, debate, vlog, other. "
        "density is low, medium, or high. Reply with JSON only: "
        '{"content_type":"...","density":"..."}\n\n'
        f"Transcript sample:\n{sample}"
    )


def highlight_prompt(transcript_text, content_type, density, num_clips, min_duration, max_duration, preferred):
    system = f"""You pick moments from a transcript that can stand alone as a short video.
{VIRALITY_SIGNALS}
This video is a {content_type} with {density} density.
Each clip must be {min_duration:.0f}-{max_duration:.0f} seconds. Prefer about {preferred:.0f} seconds.
Use the absolute timestamps in the transcript. Do not restart the clock at zero.
Return at least {num_clips} highlights when the transcript has that many real moments.
Reply with JSON only:
{{"highlights":[{{"title":"","start_time":0,"end_time":0,"score":0,"hook_sentence":"","virality_reason":""}}]}}
score is viral potential from 0 to 100. hook_sentence is the line that opens the clip, six words or fewer. virality_reason is one sentence."""
    return system, f"Transcript:\n{transcript_text}"


def rank_highlights(cues, duration, complete, num_clips=5, min_duration=15, max_duration=60, preferred=30):
    """complete(system, user) returns the model text."""
    sample = " ".join(cue["text"] for cue in cues[:25])[:3000]
    content = {"content_type": "other", "density": "medium"}
    try:
        parsed = parse_json_object(complete(*_split_content_prompt(sample)))
        if parsed.get("content_type"):
            content["content_type"] = str(parsed["content_type"])
        if parsed.get("density"):
            content["density"] = str(parsed["density"])
    except Exception:
        pass
    print(f"[highlights] {content['content_type']}, {content['density']} density, {duration:.0f}s")

    found = []
    chunks = transcript_chunks(cues, duration)
    if len(chunks) > 1:
        print(f"[highlights] long video, {len(chunks)} overlapping chunks")
    ask_for = max(num_clips, 3)
    for index, chunk in enumerate(chunks, start=1):
        if len(chunks) > 1:
            print(f"[highlights] chunk {index}/{len(chunks)}")
        system, user = highlight_prompt(
            format_cues(chunk),
            content["content_type"],
            content["density"],
            ask_for,
            min_duration,
            max_duration,
            preferred,
        )
        extra = ""
        for attempt in range(2):
            try:
                raw = complete(system, user + extra)
                parsed = parse_json_object(raw)
                batch = sanitize_highlights(parsed.get("highlights"), duration, min_duration, max_duration)
                if batch:
                    found.extend(batch)
                    break
                extra = "\nReply with JSON only. No markdown."
            except Exception as error:
                print(f"[highlights] attempt {attempt + 1} failed: {error}")
                extra = "\nReply with JSON only. No markdown."

    ranked = dedupe_highlights(found)
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:num_clips]


def _split_content_prompt(sample):
    prompt = content_type_prompt(sample)
    return "Reply with JSON only.", prompt
