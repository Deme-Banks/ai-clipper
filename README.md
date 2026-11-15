# AI Clip Generator

Turn a YouTube or Twitch video into vertical TikTok and YouTube Shorts clips. The app downloads the video, ranks the moments most likely to hold a viewer, reframes each one to 9:16, and burns in a hook line plus captions.

## Features

- **YouTube and Twitch download**, with a local cache so the same URL is not fetched twice
- **Viral ranking**: each clip gets a score out of 100, a hook line, and a one-sentence reason. The ranker looks for hooks, emotional peaks, strong opinions, reveals, conflict, quotable lines, story payoffs, and practical tips
- **Long videos**: anything over 30 minutes is split into overlapping chunks so the later half is still considered. Overlapping candidates are collapsed by score
- **Vertical framing**
  - **Auto**: follow one face, stack a real two-shot, or keep the full frame on a blurred background
  - **Smart crop**: follow the largest face with a slow camera
  - **Split**: stack two people when both are in frame
  - **Blur**: keep the whole picture over a darkened background
  - A video that is already vertical is scaled, not cropped apart
- **Captions and hook text** burned into the clip. Captions come from the video's own subtitles. If there are none, a local Whisper transcript is used when one is installed
- **OpenAI or a local model** (Ollama, LM Studio, or any OpenAI-compatible server) for ranking. With no model, audio energy is used instead
- **Web UI** for progress, preview, download, a clip library, compilation, and a light/dark theme

## Requirements

- Python 3.10 or newer
- FFmpeg on your PATH, or the copy installed with `imageio-ffmpeg` (included in `requirements.txt`)
- An OpenAI API key **or** a local model, if you want ranked highlights instead of audio-based guesses

Face tracking needs OpenCV, which is in `requirements.txt`. Local transcription of videos that have no captions needs one of:

```bash
pip install faster-whisper
```

or the `openai-whisper` package already listed in `requirements.txt`.

## Install

```bash
git clone https://github.com/Deme-Banks/ai-clipper.git
cd ai-clipper
pip install -r requirements.txt
```

Copy `.env.example` to `.env`.

Use OpenAI:

```env
OPENAI_API_KEY=your_api_key_here
```

Or point at a local server. If `LLM_BASE_URL` is set, it is used instead of OpenAI. With no key and no URL, the app uses Ollama at `http://127.0.0.1:11434` when that port is open.

```env
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=llama3.2
LLM_API_KEY=ollama
```

Set the OpenAI model and the local model name in `config.json` under `ai_settings` (`model` and `local_model`).

## Web app

Windows: double-click `start.bat`.

Anywhere else:

```bash
python app.py
```

Open http://localhost:5000.

1. Paste a YouTube or Twitch URL, or upload a file.
2. Choose a framing mode. Auto is the default.
3. Leave captions on to burn in the hook and subtitles.
4. Pick TikTok, YouTube Shorts, or both.
5. Generate, then preview or download the clips. Each card shows the viral score and why that moment was picked.

## Command line

Both formats:

```bash
python clip_generator.py https://www.youtube.com/watch?v=VIDEO_ID
```

One format:

```bash
python clip_generator.py https://www.youtube.com/watch?v=VIDEO_ID tiktok
python clip_generator.py https://www.youtube.com/watch?v=VIDEO_ID youtube_shorts
```

The CLI uses the framing mode in `config.json` (`framing.mode`, default `auto`).

## Output

Clips land in `output/`:

- `video_title_clip1_tiktok.mp4`
- `video_title_clip1_youtube_shorts.mp4`

Downloads are stored in `downloads/`. Repeat URLs are served from `cache/` until they pass `cache.max_age_days`. Transcripts made locally are cached next to that as `<video>.cues.json`.

## Configuration

`config.json` controls length, framing, and how many clips to keep.

| Setting | Default | What it does |
|---|---|---|
| `clip_settings.min_duration` | 15 | Shortest clip, in seconds |
| `clip_settings.max_duration` | 60 | Longest clip. Longer picks are sped up to fit |
| `clip_settings.preferred_duration` | 30 | Length the ranker aims for |
| `clip_settings.buffer_seconds` | 2 | Extra time kept before and after the moment |
| `framing.mode` | `auto` | `auto`, `track`, `blur`, or `split` |
| `ai_settings.model` | `gpt-4o-mini` | OpenAI model |
| `ai_settings.local_model` | `llama3.2` | Model name on the local server |
| `ai_settings.max_clips_per_video` | 5 | How many clips to render |
| `captions.enabled` | true | Burn captions when cues exist |

Output size is 1080x1920 at 30 fps for both TikTok and YouTube Shorts.

## How a clip is made

1. Download the video, or reuse the cache.
2. Load YouTube captions. If the video has none, transcribe it with faster-whisper or Whisper and cache the cues.
3. Classify the video (podcast, tutorial, vlog, and so on) and rank moments. Videos longer than 30 minutes are ranked in 20-minute windows that overlap by one minute.
4. Drop a clip when more than half of it overlaps a higher-scoring clip.
5. Reframe to 9:16, burn the hook and captions, and write the mp4 plus a thumbnail.

## Troubleshooting

**FFmpeg was not found.** Install it and confirm `ffmpeg -version` works, or reinstall dependencies so `imageio-ffmpeg` is present. You can also set `FFMPEG_PATH` to the binary.

**No faces are followed.** Install OpenCV with `pip install opencv-python-headless`. Without it, Auto uses the blurred full-frame layout on widescreen video.

**Clips are chosen from audio peaks.** Ranking needs captions or a transcript, plus OpenAI or a local model. Install `faster-whisper` when the source has no subtitles.

**The model request fails.** Check `OPENAI_API_KEY`, billing, or that Ollama is running. The app falls back to audio peaks.

**A download fails.** Confirm the URL plays in a browser. Some videos block downloading.

## License

Free to use for personal and commercial projects.
