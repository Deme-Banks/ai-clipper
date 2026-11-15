"""
AI-Powered Clip Generator for Twitch/YouTube to TikTok/YouTube Shorts
Automatically finds engaging moments and creates viral-ready clips
"""

import os
import sys

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
import json
import re
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import yt_dlp
try:
    # Try MoviePy 2.x imports first
    from moviepy import VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips, vfx
    # MoviePy 2.x uses vfx.Resize and vfx.MultiplySpeed
    Resize = vfx.Resize
    MultiplySpeed = vfx.MultiplySpeed
    # Check actual version to be sure
    try:
        import moviepy
        version_str = getattr(moviepy, '__version__', '2.0.0')
        major_version = int(version_str.split('.')[0])
        MOVIEPY_VERSION = major_version if major_version >= 2 else 1
    except:
        MOVIEPY_VERSION = 2  # Assume 2.x if import succeeded
except ImportError:
    try:
        # Fallback to MoviePy 1.x imports
        from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
        try:
            from moviepy.video.fx.all import resize, speedx
            Resize = resize
            MultiplySpeed = speedx
        except ImportError:
            from moviepy.video.fx import resize, speedx
            Resize = resize
            MultiplySpeed = speedx
        MOVIEPY_VERSION = 1
    except ImportError:
        raise ImportError("MoviePy is not installed. Install with: pip install moviepy")
from PIL import Image
from dotenv import load_dotenv

# Try to import OpenAI (optional)
try:
    from openai import OpenAI
    from openai import RateLimitError, APIError, APIConnectionError, APITimeoutError
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    RateLimitError = Exception
    APIError = Exception
    APIConnectionError = Exception
    APITimeoutError = Exception

load_dotenv()

class ClipGenerator:
    def __init__(self, config_path: str = "config.json"):
        """Initialize the clip generator with configuration"""
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Cloud OpenAI, or a local OpenAI-compatible server (Ollama, LM Studio, vLLM)
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.openai_client = None
        self.openai_enabled = False
        self.ai_provider = None
        self.ai_model = self.config.get("ai_settings", {}).get("model", "gpt-4o-mini")
        self.caption_cues = []
        llm_base = os.getenv("LLM_BASE_URL", "").strip()
        local_model = os.getenv("LLM_MODEL") or self.config.get("ai_settings", {}).get("local_model", "llama3.2")

        if not OPENAI_AVAILABLE:
            print("[INFO] OpenAI library not installed. Install with: pip install openai")
        elif self.openai_key and not llm_base:
            try:
                self.openai_client = OpenAI(
                    api_key=self.openai_key,
                    timeout=60.0,
                    max_retries=3
                )
                self.openai_enabled = True
                self.ai_provider = "openai"
                print("[OK] OpenAI API initialized successfully")
            except Exception as e:
                print(f"[WARNING] OpenAI initialization failed: {e}")
                self.openai_enabled = False
        elif llm_base or self._local_llm_reachable():
            try:
                base_url = llm_base or "http://127.0.0.1:11434/v1"
                self.openai_client = OpenAI(
                    base_url=base_url,
                    api_key=os.getenv("LLM_API_KEY", "ollama"),
                    timeout=120.0,
                    max_retries=1
                )
                self.openai_enabled = True
                self.ai_provider = "local"
                self.ai_model = local_model
                print(f"[OK] Local LLM ready at {base_url} ({local_model})")
            except Exception as e:
                print(f"[WARNING] Local LLM setup failed: {e}")
        else:
            print("[INFO] No AI provider. Add OPENAI_API_KEY, or run Ollama, for clip detection")
        
        # Create output directories
        self.output_dir = Path("output")
        self.downloads_dir = Path("downloads")
        self.cache_dir = Path("cache")
        self.output_dir.mkdir(exist_ok=True)
        self.downloads_dir.mkdir(exist_ok=True)
        self.cache_dir.mkdir(exist_ok=True)
        
        # Cache configuration
        self.cache_enabled = self.config.get("cache", {}).get("enabled", True)
        self.cache_max_size_gb = self.config.get("cache", {}).get("max_size_gb", 10)
        self.cache_max_age_days = self.config.get("cache", {}).get("max_age_days", 30)

    def _local_llm_reachable(self) -> bool:
        """True when something is listening on Ollama's default port."""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.4)
        try:
            sock.connect(("127.0.0.1", 11434))
            return True
        except OSError:
            return False
        finally:
            sock.close()
    
    def _get_cache_key(self, url: str) -> str:
        """Generate cache key from URL"""
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()
    
    def _get_cached_video(self, url: str) -> Optional[str]:
        """Check if video is cached and return path if valid"""
        if not self.cache_enabled:
            return None
        
        cache_key = self._get_cache_key(url)
        cache_file = self.cache_dir / f"{cache_key}.mp4"
        cache_meta = self.cache_dir / f"{cache_key}.json"
        
        if cache_file.exists() and cache_meta.exists():
            try:
                # Check cache metadata
                with open(cache_meta, 'r') as f:
                    meta = json.load(f)
                
                # Check if cache is expired
                from datetime import datetime, timedelta
                cache_date = datetime.fromisoformat(meta.get('cached_at', ''))
                age = datetime.now() - cache_date
                
                if age.days > self.cache_max_age_days:
                    print(f"🗑️  Cache expired for {url}, removing...")
                    cache_file.unlink()
                    cache_meta.unlink()
                    return None
                
                # Verify file exists and is valid
                if cache_file.stat().st_size > 0:
                    print(f"💾 Using cached video: {meta.get('title', 'Unknown')}")
                    return str(cache_file)
                else:
                    # Corrupted cache, remove it
                    cache_file.unlink()
                    cache_meta.unlink()
            except Exception as e:
                print(f"⚠️  Error reading cache metadata: {e}")
                return None
        
        return None
    
    def _save_to_cache(self, url: str, video_path: str, video_info: Dict):
        """Save downloaded video to cache"""
        if not self.cache_enabled:
            return
        
        try:
            cache_key = self._get_cache_key(url)
            cache_file = self.cache_dir / f"{cache_key}.mp4"
            cache_meta = self.cache_dir / f"{cache_key}.json"
            
            # Copy file to cache (or move if from downloads)
            import shutil
            if video_path != str(cache_file):
                shutil.copy2(video_path, cache_file)
            
            # Save metadata
            from datetime import datetime
            metadata = {
                'url': url,
                'title': video_info.get('title', 'Unknown'),
                'cached_at': datetime.now().isoformat(),
                'duration': video_info.get('duration', 0),
                'size': cache_file.stat().st_size
            }
            
            with open(cache_meta, 'w') as f:
                json.dump(metadata, f)
            
            # Clean up old cache if needed
            self._cleanup_cache()
            
        except Exception as e:
            print(f"⚠️  Error saving to cache: {e}")
    
    def _cleanup_cache(self):
        """Clean up old cache files if cache size exceeds limit"""
        try:
            cache_files = list(self.cache_dir.glob("*.mp4"))
            if not cache_files:
                return
            
            # Calculate total cache size
            total_size = sum(f.stat().st_size for f in cache_files)
            max_size_bytes = self.cache_max_size_gb * 1024 * 1024 * 1024
            
            if total_size > max_size_bytes:
                print(f"🧹 Cache size ({total_size / (1024**3):.2f} GB) exceeds limit ({self.cache_max_size_gb} GB), cleaning up...")
                
                # Sort by modification time (oldest first)
                cache_files.sort(key=lambda f: f.stat().st_mtime)
                
                # Remove oldest files until under limit
                for cache_file in cache_files:
                    if total_size <= max_size_bytes * 0.9:  # Clean to 90% of limit
                        break
                    
                    cache_key = cache_file.stem
                    meta_file = self.cache_dir / f"{cache_key}.json"
                    
                    file_size = cache_file.stat().st_size
                    cache_file.unlink()
                    if meta_file.exists():
                        meta_file.unlink()
                    
                    total_size -= file_size
                    print(f"🗑️  Removed old cache: {cache_key}")
        
        except Exception as e:
            print(f"⚠️  Error cleaning cache: {e}")
    
    def download_video(self, url: str) -> Optional[str]:
        """Download video from Twitch or YouTube URL (with caching)"""
        # Check cache first
        cached_path = self._get_cached_video(url)
        if cached_path:
            return cached_path
        
        print(f"📥 Downloading video from: {url}")
        
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': str(self.downloads_dir / '%(title)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                # Ensure .mp4 extension
                if not filename.endswith('.mp4'):
                    new_filename = filename.rsplit('.', 1)[0] + '.mp4'
                    if os.path.exists(filename):
                        os.rename(filename, new_filename)
                    filename = new_filename
                
                # Save to cache
                video_info = {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0)
                }
                self._save_to_cache(url, filename, video_info)
                
                print(f"✅ Downloaded: {filename}")
                return filename
        except Exception as e:
            print(f"âŒ Error downloading video: {e}")
            return None
    
    def get_video_transcript(self, url: str) -> Optional[str]:
        """Extract a timestamped transcript and keep cues for burned-in captions."""
        self.caption_cues = []
        try:
            ydl_opts = {
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['en'],
                'skip_download': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                tracks = (info.get('subtitles') or {}).get('en') or (info.get('automatic_captions') or {}).get('en') or []
                if not tracks:
                    return None
                track = next((t for t in tracks if t.get('ext') == 'json3'), tracks[0])
                import requests
                response = requests.get(track['url'], timeout=30)
                if response.status_code != 200:
                    return None
                self.caption_cues = self._parse_timed_captions(response.text)
                if not self.caption_cues:
                    return None
                print(f"[OK] Loaded {len(self.caption_cues)} caption cues")
                return self._transcript_for_ai(self.caption_cues)
        except Exception as e:
            print(f"[WARNING] Could not extract transcript: {e}")
            self.caption_cues = []
        return None

    def _parse_timed_captions(self, raw: str) -> List[Dict]:
        """Parse YouTube json3, WebVTT, or SRT into timed cues."""
        raw = (raw or "").strip()
        cues = []
        if raw.startswith('{') or raw.startswith('['):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict):
                for event in data.get('events', []):
                    text = ''.join(seg.get('utf8', '') for seg in (event.get('segs') or []))
                    text = re.sub(r'\s+', ' ', text.replace('\n', ' ')).strip()
                    if not text:
                        continue
                    start = event.get('tStartMs', 0) / 1000.0
                    end = start + event.get('dDurationMs', 0) / 1000.0
                    cues.append({'start': start, 'end': end, 'text': text})
            return self._dedupe_cues(cues)

        time_re = re.compile(
            r'(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})'
        )

        def to_seconds(hours, minutes, seconds, millis):
            millis = (millis or '0').ljust(3, '0')[:3]
            return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0

        lines = raw.splitlines()
        index = 0
        while index < len(lines):
            match = time_re.search(lines[index])
            if not match:
                index += 1
                continue
            start = to_seconds(match.group(1), match.group(2), match.group(3), match.group(4))
            end = to_seconds(match.group(5), match.group(6), match.group(7), match.group(8))
            index += 1
            text_lines = []
            while index < len(lines) and lines[index].strip():
                text_lines.append(lines[index].strip())
                index += 1
            text = re.sub(r'<[^>]+>', '', ' '.join(text_lines))
            text = re.sub(r'\s+', ' ', text).strip()
            if text:
                cues.append({'start': start, 'end': end, 'text': text})
        return self._dedupe_cues(cues)

    def _dedupe_cues(self, cues: List[Dict]) -> List[Dict]:
        cleaned = []
        for cue in cues:
            if cleaned and cleaned[-1]['text'] == cue['text'] and abs(cleaned[-1]['start'] - cue['start']) < 0.4:
                cleaned[-1]['end'] = max(cleaned[-1]['end'], cue['end'])
                continue
            cleaned.append(cue)
        return cleaned

    def _transcript_for_ai(self, cues: List[Dict], limit: int = 7000) -> str:
        """Timestamped lines, sampled across the whole video when the transcript is long."""
        lines = [f"[{cue['start']:.1f}-{cue['end']:.1f}] {cue['text']}" for cue in cues]
        text = "\n".join(lines)
        if len(text) <= limit:
            return text
        step = max(1, len(lines) // 90)
        return "\n".join(lines[::step])[:limit]

    def _cues_for_range(self, cues: List[Dict], start: float, end: float) -> List[Dict]:
        ranged = []
        for cue in cues or []:
            if cue['end'] <= start or cue['start'] >= end:
                continue
            cue_start = max(cue['start'], start) - start
            cue_end = min(cue['end'], end) - start
            text = re.sub(r'<[^>]+>', '', cue['text']).strip()
            if text and cue_end - cue_start >= 0.2:
                ranged.append({'start': cue_start, 'end': cue_end, 'text': text})
        return ranged
    
    def find_engaging_clips_ai(self, video_path: str, transcript: Optional[str] = None) -> List[Dict]:
        """Use AI to find the most engaging moments in the video"""
        clip = VideoFileClip(video_path)
        duration = clip.duration
        clip.close()
        
        if not self.caption_cues:
            local_transcript = self.transcribe_video(video_path)
            if local_transcript:
                transcript = local_transcript

        # If we have OpenAI API, use it for intelligent clip detection
        if self.openai_enabled and self.openai_client:
            if transcript or self.caption_cues:
                print("🤖 AI ranking transcript for viral moments...")
                return self._ai_clip_detection(video_path, transcript, duration)
            else:
                print("⚠️  No transcript available. AI detection requires transcript. Using heuristics...")
                return self._heuristic_clip_detection(video_path, duration)
        else:
            # Fallback: Use heuristics to find potential clips
            if not self.openai_enabled:
                print("💡 Using heuristic detection (add OpenAI API key to .env for AI-powered clip detection)")
            return self._heuristic_clip_detection(video_path, duration)
    
    def _llm_complete(self, system: str, user: str) -> str:
        """One chat completion. Works for OpenAI and a local OpenAI-compatible server."""
        response = self.openai_client.chat.completions.create(
            model=self.ai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.config["ai_settings"]["temperature"],
        )
        self._estimate_cost(response)
        return response.choices[0].message.content or ""

    def transcribe_video(self, video_path: str) -> Optional[str]:
        """Transcribe a file when the platform did not provide captions. Cached beside the video cache."""
        cache_path = self.cache_dir / f"{Path(video_path).stem}.cues.json"
        source = Path(video_path)
        if cache_path.exists() and source.exists() and cache_path.stat().st_mtime >= source.stat().st_mtime:
            try:
                self.caption_cues = json.loads(cache_path.read_text(encoding="utf-8"))
                if self.caption_cues:
                    print(f"[OK] Reused {len(self.caption_cues)} cached transcript cues")
                    return self._transcript_for_ai(self.caption_cues)
            except (OSError, json.JSONDecodeError):
                pass

        cues = self._whisper_cues(video_path)
        if not cues:
            return None
        self.caption_cues = cues
        try:
            cache_path.write_text(json.dumps(cues), encoding="utf-8")
        except OSError as error:
            print(f"[WARNING] Could not cache transcript: {error}")
        print(f"[OK] Transcribed {len(cues)} cues")
        return self._transcript_for_ai(cues)

    def _whisper_cues(self, video_path: str) -> List[Dict]:
        try:
            from faster_whisper import WhisperModel
            print("[OK] Transcribing with faster-whisper...")
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, _info = model.transcribe(video_path, vad_filter=True)
            return [
                {"start": segment.start, "end": segment.end, "text": segment.text.strip()}
                for segment in segments
                if segment.text and segment.text.strip()
            ]
        except ImportError:
            pass
        except Exception as error:
            print(f"[WARNING] faster-whisper failed: {error}")
            return []

        try:
            import whisper
            print("[OK] Transcribing with Whisper...")
            model = whisper.load_model("base")
            result = model.transcribe(video_path)
            return [
                {"start": segment["start"], "end": segment["end"], "text": segment["text"].strip()}
                for segment in result.get("segments", [])
                if segment.get("text", "").strip()
            ]
        except ImportError:
            print("[INFO] No captions on this video. Install faster-whisper to transcribe it locally.")
            return []
        except Exception as error:
            print(f"[WARNING] Whisper transcription failed: {error}")
            return []

    def _ai_clip_detection(self, video_path: str, transcript: str, duration: float) -> List[Dict]:
        """Rank viral moments, then drop overlaps."""
        from highlights import rank_highlights

        cues = list(self.caption_cues)
        if not cues and transcript:
            cues = self._cues_from_transcript_lines(transcript)
        if not cues:
            print("⚠️  No timed transcript, using heuristics...")
            return self._heuristic_clip_detection(video_path, duration)

        settings = self.config["clip_settings"]
        try:
            ranked = rank_highlights(
                cues,
                duration,
                self._llm_complete,
                num_clips=self.config["ai_settings"]["max_clips_per_video"],
                min_duration=settings["min_duration"],
                max_duration=settings["max_duration"],
                preferred=settings["preferred_duration"],
            )
        except (RateLimitError, APIConnectionError, APITimeoutError, APIError, ValueError, json.JSONDecodeError) as error:
            print(f"⚠️  Highlight ranking failed, using heuristics: {error}")
            return self._heuristic_clip_detection(video_path, duration)
        except Exception as error:
            print(f"⚠️  Highlight ranking failed, using heuristics: {error}")
            return self._heuristic_clip_detection(video_path, duration)

        if not ranked:
            print("⚠️  AI returned no valid clips, using heuristics...")
            return self._heuristic_clip_detection(video_path, duration)

        buffer_seconds = settings["buffer_seconds"]
        clips = []
        for item in ranked:
            start = max(0, item["start_time"] - buffer_seconds)
            end = min(duration, item["end_time"] + buffer_seconds)
            score = item["score"]
            clips.append({
                "start_time": start,
                "end_time": end,
                "reason": item["virality_reason"] or "Engaging moment",
                "title": item["title"],
                "hook": (item["hook_sentence"] or item["title"])[:80],
                "engagement_score": max(1, min(10, round(score / 10))),
                "viral_score": score,
            })
            print(f"#{len(clips)} score={score}  {start:.1f}s -> {end:.1f}s  {item['title']}")
        print(f"✅ Ranked {len(clips)} clips")
        return clips

    def _cues_from_transcript_lines(self, transcript: str) -> List[Dict]:
        cues = []
        pattern = re.compile(r"\[(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\]\s*(.*)")
        for line in (transcript or "").splitlines():
            match = pattern.match(line.strip())
            if not match or not match.group(3).strip():
                continue
            cues.append({
                "start": float(match.group(1)),
                "end": float(match.group(2)),
                "text": match.group(3).strip(),
            })
        return cues

    def _estimate_cost(self, response) -> None:
        """Estimate and display API cost"""
        try:
            usage = response.usage
            if usage:
                # Cost estimates (as of 2024, adjust as needed)
                model = self.config["ai_settings"]["model"].lower()
                
                # GPT-4o-mini (best value - newest model)
                if "gpt-4o-mini" in model or "gpt-4-mini" in model:
                    input_cost = (usage.prompt_tokens / 1000) * 0.00015
                    output_cost = (usage.completion_tokens / 1000) * 0.0006
                # GPT-4o (premium quality)
                elif "gpt-4o" in model and "mini" not in model:
                    input_cost = (usage.prompt_tokens / 1000) * 0.005
                    output_cost = (usage.completion_tokens / 1000) * 0.015
                # GPT-4 Turbo
                elif "gpt-4-turbo" in model or ("gpt-4" in model and "turbo" in model):
                    input_cost = (usage.prompt_tokens / 1000) * 0.01
                    output_cost = (usage.completion_tokens / 1000) * 0.03
                # GPT-4 (standard)
                elif "gpt-4" in model:
                    input_cost = (usage.prompt_tokens / 1000) * 0.03
                    output_cost = (usage.completion_tokens / 1000) * 0.06
                # GPT-3.5-turbo
                elif "gpt-3.5" in model:
                    input_cost = (usage.prompt_tokens / 1000) * 0.0005
                    output_cost = (usage.completion_tokens / 1000) * 0.0015
                else:
                    input_cost = output_cost = 0
                
                total_cost = input_cost + output_cost
                if total_cost > 0:
                    print(f"💰 Estimated API cost: ${total_cost:.6f} ({usage.prompt_tokens} input + {usage.completion_tokens} output tokens)")
        except Exception:
            pass  # Silently fail cost estimation
    
    def _analyze_audio_engagement(self, video_path: str, duration: float) -> List[Tuple[float, float]]:
        """Analyze audio to find engaging moments (volume spikes, energy peaks)"""
        try:
            import librosa
            import numpy as np
            
            print("🎵 Analyzing audio for engagement peaks...")
            
            # Load audio
            y, sr = librosa.load(video_path, duration=duration)
            
            # Calculate RMS energy (volume)
            rms = librosa.feature.rms(y=y)[0]
            times = librosa.frames_to_time(np.arange(len(rms)), sr=sr)
            
            # Find volume spikes (potential exciting moments)
            rms_mean = np.mean(rms)
            rms_std = np.std(rms)
            threshold = rms_mean + (rms_std * 1.5)  # Moments above 1.5 std dev
            
            # Find peaks
            peaks = []
            for i, energy in enumerate(rms):
                if energy > threshold and times[i] < duration:
                    peaks.append((times[i], energy))
            
            # Sort by energy and return top moments
            peaks.sort(key=lambda x: x[1], reverse=True)
            return [time for time, _ in peaks[:10]]  # Top 10 moments
            
        except ImportError:
            print("⚠️  librosa not installed. Install with: pip install librosa")
            return []
        except Exception as e:
            print(f"⚠️  Audio analysis failed: {e}")
            return []
    
    def _heuristic_clip_detection(self, video_path: str, duration: float) -> List[Dict]:
        """Fallback: Use heuristics to find potential clips, enhanced with audio analysis"""
        clips = []
        min_duration = self.config["clip_settings"]["min_duration"]
        max_duration = self.config["clip_settings"]["max_duration"]
        preferred_duration = self.config["clip_settings"]["preferred_duration"]
        
        # Try audio analysis first
        audio_peaks = self._analyze_audio_engagement(video_path, duration)
        
        if audio_peaks:
            # Use audio peaks as clip starting points
            for i, peak_time in enumerate(audio_peaks[:self.config["ai_settings"]["max_clips_per_video"]]):
                start_time = max(0, peak_time - (preferred_duration / 2))
                end_time = min(start_time + preferred_duration, duration)
                
                if end_time - start_time >= min_duration:
                    clips.append({
                        "start_time": max(0, start_time - self.config["clip_settings"]["buffer_seconds"]),
                        "end_time": min(end_time + self.config["clip_settings"]["buffer_seconds"], duration),
                        "reason": f"High audio energy moment at {int(peak_time)}s",
                        "title": f"Clip {i+1}",
                        "hook": "Wait for this",
                        "engagement_score": 7
                    })
        
        # Fallback to time-based if no audio peaks found
        if not clips:
            num_clips = min(5, int(duration / (preferred_duration * 2)))
            
            for i in range(num_clips):
                start_time = (duration / (num_clips + 1)) * (i + 1)
                end_time = min(start_time + preferred_duration, duration)
                
                if end_time - start_time >= min_duration:
                    clips.append({
                        "start_time": max(0, start_time - self.config["clip_settings"]["buffer_seconds"]),
                        "end_time": min(end_time + self.config["clip_settings"]["buffer_seconds"], duration),
                        "reason": f"Engaging moment at {int(start_time)}s",
                        "title": f"Clip {i+1}",
                        "hook": "Don't skip this",
                        "engagement_score": 5
                    })
        
        return clips
    
    def create_clip(self, video_path: str, start_time: float, end_time: float, 
                   output_path: str, format_type: str = "tiktok", clip_title: str = None,
                   framing: str = "track", hook: str = None, caption_cues: Optional[List[Dict]] = None,
                   burn_captions: bool = True) -> bool:
        """Create a formatted clip for TikTok or YouTube Shorts"""
        print(f"Creating {format_type} clip ({framing}): {start_time}s - {end_time}s")

        format_config = self.config["output_formats"][format_type]
        try:
            from framing import render_vertical_clip, write_thumbnail
            rendered = render_vertical_clip(
                video_path,
                output_path,
                start_time,
                end_time,
                format_config["width"],
                format_config["height"],
                fps=format_config["fps"],
                mode=framing or "auto",
                hook=(hook or clip_title) if burn_captions else None,
                cues=self._cues_for_range(caption_cues, start_time, end_time) if burn_captions else [],
                burn_captions=burn_captions,
                max_duration=format_config["duration_max"],
            )
            if rendered:
                thumbnail_path = Path(output_path).with_suffix(".jpg")
                try:
                    write_thumbnail(output_path, thumbnail_path)
                except Exception as thumb_error:
                    print(f"[WARNING] Thumbnail skipped: {thumb_error}")
                print(f"Created: {output_path}")
                return True
            print("[INFO] ffmpeg was not found, using the simple crop")
        except Exception as render_error:
            print(f"[WARNING] Vertical reframe failed, using the simple crop: {render_error}")
        
        full_clip = None
        clip = None
        try:
            # Load video
            full_clip = VideoFileClip(video_path)
            # Try to extract subclip - handle both MoviePy 1.x and 2.x
            # Try slicing first (MoviePy 2.x), then fallback to subclip (MoviePy 1.x)
            clip = None
            try:
                # MoviePy 2.x uses slicing syntax
                clip = full_clip[start_time:end_time]
            except (TypeError, AttributeError, NotImplementedError, IndexError):
                # Fallback to subclip method (MoviePy 1.x)
                try:
                    if hasattr(full_clip, 'subclip'):
                        clip = full_clip.subclip(start_time, end_time)
                    else:
                        raise AttributeError("Neither slicing nor subclip available")
                except Exception as e:
                    raise AttributeError(f"Could not extract subclip: {e}")
            
            if clip is None:
                raise ValueError("Failed to extract subclip from video")
            
            # Get format settings
            target_width = format_config["width"]
            target_height = format_config["height"]
            
            # Reframe to 9:16: face crop, blurred background, or stacked speakers
            fallback_mode = "track" if framing == "auto" else framing
            clip = self._resize_to_vertical(clip, target_width, target_height, framing=fallback_mode)
            
            # Speed up if needed to fit duration
            max_duration = format_config["duration_max"]
            if clip.duration > max_duration:
                speed_factor = clip.duration / max_duration
                if MOVIEPY_VERSION == 2:
                    clip = clip.fx(MultiplySpeed, speed_factor)
                else:
                    clip = MultiplySpeed(clip, speed_factor)
                print(f"Sped up by {speed_factor:.2f}x to fit duration")
            
            segments = self._cues_for_range(caption_cues, start_time, end_time) if burn_captions else []
            clip = self._add_engaging_elements(
                clip, format_type, hook or clip_title, add_captions=burn_captions, segments=segments
            )
            
            # Write output
            clip.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                fps=format_config["fps"],
                preset='medium',
                bitrate='8000k'
            )
            
            # Generate thumbnail (before closing clip)
            self._generate_thumbnail(clip, output_path)
            
            print(f"Created: {output_path}")
            return True
            
        except Exception as e:
            print(f"Error creating clip: {e}")
            return False
        finally:
            for item in (clip, full_clip):
                if item is not None:
                    try:
                        item.close()
                    except Exception:
                        pass
    
    def _resize_to_vertical(self, clip: VideoFileClip, target_width: int, target_height: int, framing: str = "track") -> VideoFileClip:
        """Resize clip to vertical format. framing is track, blur, or split."""
        mode = (framing or "track").lower()
        if mode == "blur":
            return self._frame_blur(clip, target_width, target_height)
        if mode == "split" and clip.w > clip.h * 1.2:
            return self._frame_split(clip, target_width, target_height)
        x_ratio = self._face_x_ratio(clip) if mode == "track" else 0.5
        return self._frame_crop(clip, target_width, target_height, x_ratio)

    def _apply_resize(self, clip, size):
        if MOVIEPY_VERSION == 2:
            return clip.fx(Resize, size)
        return Resize(clip, size)

    def _with_duration(self, clip, duration):
        if hasattr(clip, "with_duration"):
            return clip.with_duration(duration)
        return clip.set_duration(duration)

    def _with_position(self, clip, position):
        if hasattr(clip, "with_position"):
            return clip.with_position(position)
        return clip.set_position(position)

    def _with_audio(self, visual, source):
        if getattr(source, "audio", None) is None:
            return visual
        if hasattr(visual, "with_audio"):
            return visual.with_audio(source.audio)
        return visual.set_audio(source.audio)

    def _image_clip(self, array, duration):
        try:
            from moviepy import ImageClip
        except ImportError:
            from moviepy.editor import ImageClip
        return self._with_duration(ImageClip(array), duration)

    def _face_x_ratio(self, clip: VideoFileClip) -> float:
        """Average horizontal face position, or 0.5 when detection is unavailable."""
        try:
            import cv2
        except ImportError:
            return 0.5
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        detector = cv2.CascadeClassifier(cascade_path)
        if detector.empty():
            return 0.5
        centers = []
        for fraction in (0.15, 0.4, 0.65, 0.85):
            moment = min(clip.duration * fraction, max(0, clip.duration - 0.05))
            frame = clip.get_frame(moment)
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            faces = detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(36, 36))
            if len(faces):
                x, _y, w, _h = max(faces, key=lambda rect: rect[2] * rect[3])
                centers.append((x + w / 2) / frame.shape[1])
        if not centers:
            return 0.5
        return sum(centers) / len(centers)

    def _frame_crop(self, clip: VideoFileClip, target_width: int, target_height: int, x_ratio: float) -> VideoFileClip:
        """Center or face-weighted crop into 9:16, then scale."""
        Crop = None
        try:
            if MOVIEPY_VERSION == 2:
                Crop = vfx.Crop
            else:
                try:
                    from moviepy.video.fx.all import crop as Crop
                except ImportError:
                    from moviepy.video.fx import crop as Crop
        except Exception:
            Crop = None
        if Crop is None:
            return self._apply_resize(clip, (target_width, target_height))

        clip_aspect = clip.w / clip.h
        target_aspect = target_width / target_height
        if clip_aspect > target_aspect:
            new_width = int(clip.h * target_aspect)
            half = new_width / 2
            x_center = max(half, min(clip.w - half, clip.w * x_ratio))
            if MOVIEPY_VERSION == 2:
                clip = clip.fx(Crop, x_center=x_center, width=new_width)
            else:
                clip = Crop(clip, x_center=x_center, width=new_width)
        else:
            new_height = int(clip.w / target_aspect)
            y_center = clip.h / 2
            if MOVIEPY_VERSION == 2:
                clip = clip.fx(Crop, y_center=y_center, height=new_height)
            else:
                clip = Crop(clip, y_center=y_center, height=new_height)
        return self._apply_resize(clip, (target_width, target_height))

    def _frame_blur(self, clip: VideoFileClip, target_width: int, target_height: int) -> VideoFileClip:
        """Fit the full frame over a blurred cover, so nothing important is cropped away."""
        import numpy as np
        from PIL import Image, ImageEnhance, ImageFilter

        moment = min(clip.duration * 0.35, max(0, clip.duration - 0.05))
        frame = clip.get_frame(moment)
        background = Image.fromarray(frame).resize((target_width, target_height), Image.LANCZOS)
        background = background.filter(ImageFilter.GaussianBlur(radius=28))
        background = ImageEnhance.Brightness(background).enhance(0.55)
        bg_clip = self._image_clip(np.array(background), clip.duration)

        scale = min(target_width / clip.w, target_height / clip.h)
        fitted = self._apply_resize(clip, (max(2, int(clip.w * scale)), max(2, int(clip.h * scale))))
        fitted = self._with_position(fitted, ("center", "center"))
        composite = CompositeVideoClip([bg_clip, fitted], size=(target_width, target_height))
        return self._with_audio(self._with_duration(composite, clip.duration), clip)

    def _frame_split(self, clip: VideoFileClip, target_width: int, target_height: int) -> VideoFileClip:
        """Stack the left and right of a wide shot, the way a two-person interview is reframed."""
        half_height = target_height // 2
        top = self._apply_resize(self._frame_crop(clip, target_width, half_height, 0.27), (target_width, half_height))
        bottom = self._apply_resize(self._frame_crop(clip, target_width, half_height, 0.73), (target_width, half_height))
        top = self._with_position(top, (0, 0))
        bottom = self._with_position(bottom, (0, half_height))
        composite = CompositeVideoClip([top, bottom], size=(target_width, target_height))
        return self._with_audio(self._with_duration(composite, clip.duration), clip)

    def _transcribe_clip_audio(self, clip: VideoFileClip) -> List[Dict]:
        """Transcribe audio from clip using Whisper"""
        try:
            import whisper
            
            # Check if captions are enabled
            if not self.config.get("captions", {}).get("enabled", True):
                return []
            
            print("🎤 Transcribing audio for captions...")
            
            # Extract audio to temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_audio:
                clip.audio.write_audiofile(tmp_audio.name, logger=None, verbose=False)
                audio_path = tmp_audio.name
            
            try:
                # Load Whisper model (use base model for speed)
                model = whisper.load_model("base")
                
                # Transcribe
                result = model.transcribe(audio_path, language="en", task="transcribe")
                
                # Extract segments with timestamps
                segments = []
                for segment in result.get("segments", []):
                    segments.append({
                        "text": segment["text"].strip(),
                        "start": segment["start"],
                        "end": segment["end"]
                    })
                
                # Clean up temp file
                os.unlink(audio_path)
                
                return segments
                
            except Exception as e:
                # Clean up temp file on error
                if os.path.exists(audio_path):
                    os.unlink(audio_path)
                raise e
                
        except ImportError:
            print("⚠️  Whisper not installed. Install with: pip install openai-whisper")
            return []
        except Exception as e:
            print(f"⚠️  Transcription failed: {e}")
            return []
    
    def _add_captions_to_clip(self, clip: VideoFileClip, segments: List[Dict]) -> CompositeVideoClip:
        """Add styled captions to video clip"""
        if not segments:
            return clip
        
        clips_to_composite = [clip]
        caption_config = self.config.get("captions", {})
        
        try:
            for segment in segments:
                text = segment["text"]
                start_time = segment["start"]
                end_time = min(segment["end"], clip.duration)
                duration = end_time - start_time
                
                if duration <= 0:
                    continue
                
                # Style captions based on config
                font_size = caption_config.get("font_size", 48)
                font_color = caption_config.get("font_color", "white")
                bg_color = caption_config.get("background_color", "black")
                bg_opacity = caption_config.get("background_opacity", 0.7)
                position = caption_config.get("position", "bottom")
                
                txt_clip = self._make_text_clip(text, font_size, int(clip.w * 0.9), font_color)
                txt_clip = self._with_duration(txt_clip, duration)
                txt_clip = self._with_start(txt_clip, start_time)

                if position == "bottom":
                    txt_clip = self._with_position(txt_clip, ('center', clip.h * 0.78))
                elif position == "top":
                    txt_clip = self._with_position(txt_clip, ('center', 140))
                else:
                    txt_clip = self._with_position(txt_clip, 'center')
                
                # Add background if enabled
                if bg_opacity > 0:
                    from moviepy.video.fx.all import margin
                    # Simple background using margin (full implementation would use ImageClip)
                    pass
                
                clips_to_composite.append(txt_clip)
            
            return CompositeVideoClip(clips_to_composite)
            
        except Exception as e:
            print(f"⚠️  Could not add captions: {e}")
            return clip
    
    def _with_start(self, clip, start):
        if hasattr(clip, "with_start"):
            return clip.with_start(start)
        return clip.set_start(start)

    def _make_text_clip(self, text: str, font_size: int, width: int, color: str = "white"):
        """Text overlay that works on MoviePy 1.x and 2.x."""
        common = dict(
            color=color,
            method="caption",
            size=(width, None),
            stroke_color="black",
            stroke_width=3,
        )
        try:
            return TextClip(text=text, font_size=font_size, **common)
        except TypeError:
            return TextClip(text, fontsize=font_size, font="Arial-Bold", **common)

    def _add_engaging_elements(self, clip: VideoFileClip, format_type: str, title: str = None, add_captions: bool = True, segments: Optional[List[Dict]] = None) -> CompositeVideoClip:
        """Add a hook line and burned-in captions."""
        clips_to_composite = [clip]
        
        if title and len(title) > 0:
            try:
                title_clip = self._make_text_clip(title[:60], 54, int(clip.w * 0.88))
                title_clip = self._with_position(title_clip, ("center", 70))
                title_clip = self._with_duration(title_clip, min(4, clip.duration))
                clips_to_composite.append(title_clip)
            except Exception as e:
                print(f"[WARNING] Could not add hook overlay: {e}")
        
        if add_captions and self.config.get("captions", {}).get("enabled", True):
            try:
                if not segments and self.config.get("captions", {}).get("whisper_fallback", False):
                    segments = self._transcribe_clip_audio(clip)
                if segments:
                    return self._add_captions_to_clip(CompositeVideoClip(clips_to_composite), segments)
            except Exception as e:
                print(f"[WARNING] Caption generation skipped: {e}")
        
        return CompositeVideoClip(clips_to_composite)
    
    def process_url(self, url: str, formats: List[str] = ["tiktok", "youtube_shorts"]) -> List[str]:
        """Main processing function: Download, analyze, and create clips"""
        self.last_url = url
        
        # Download video
        video_path = self.download_video(url)
        if not video_path:
            return []
        
        # Try to get transcript for better AI detection
        transcript = self.get_video_transcript(url)
        
        # Find engaging clips
        clips = self.find_engaging_clips_ai(video_path, transcript)
        if not clips:
            print("âš ï¸ No clips found")
            return []
        
        # Create clips in requested formats
        output_files = []
        video_name = Path(video_path).stem
        
        for i, clip_info in enumerate(clips):
            start = clip_info["start_time"]
            end = clip_info["end_time"]
            clip_title = clip_info.get("title", f"Clip {i+1}")
            
            for format_type in formats:
                output_filename = f"{video_name}_clip{i+1}_{format_type}.mp4"
                output_path = self.output_dir / output_filename
                
                if self.create_clip(
                    video_path, start, end, str(output_path), format_type, clip_title,
                    framing=self.config.get("framing", {}).get("mode", "track"),
                    hook=clip_info.get("hook") or clip_title,
                    caption_cues=self.caption_cues,
                ):
                    output_files.append(str(output_path))
        
        print(f"\nðŸŽ‰ Successfully created {len(output_files)} clips!")
        return output_files
    
    def edit_clip(self, video_path: str, output_path: str, 
                  trim_start: Optional[float] = None,
                  trim_end: Optional[float] = None,
                  speed: Optional[float] = None,
                  text_overlay: Optional[Dict] = None,
                  format_type: str = "tiktok",
                  filters: Optional[Dict] = None) -> bool:
        """
        Edit an existing clip with various options
        
        Args:
            video_path: Path to input video file
            output_path: Path to save edited video
            trim_start: Start time for trimming (seconds)
            trim_end: End time for trimming (seconds)
            speed: Speed multiplier (1.0 = normal, 2.0 = 2x speed, 0.5 = half speed)
            text_overlay: Dict with text overlay settings:
                - text: Text to display
                - position: 'top', 'bottom', 'center'
                - fontsize: Font size
                - color: Text color
                - start_time: When to show (seconds)
                - duration: How long to show (seconds)
            format_type: Output format (tiktok/youtube_shorts)
        """
        print(f"✂️ Editing clip: {video_path}")
        
        full_clip = None
        clip = None
        try:
            # Load video
            full_clip = VideoFileClip(video_path)
            
            # Extract subclip if trimming is requested
            start_time = trim_start if trim_start is not None else 0
            end_time = trim_end if trim_end is not None else full_clip.duration
            
            # Try to extract subclip
            try:
                if MOVIEPY_VERSION == 2:
                    clip = full_clip[start_time:end_time]
                else:
                    if hasattr(full_clip, 'subclip'):
                        clip = full_clip.subclip(start_time, end_time)
                    else:
                        clip = full_clip[start_time:end_time]
            except (TypeError, AttributeError, NotImplementedError, IndexError):
                if hasattr(full_clip, 'subclip'):
                    clip = full_clip.subclip(start_time, end_time)
                else:
                    raise AttributeError("Could not extract subclip")
            
            if clip is None:
                raise ValueError("Failed to extract subclip from video")
            
            # Apply speed change if requested
            if speed is not None and speed != 1.0:
                if MOVIEPY_VERSION == 2:
                    clip = clip.fx(MultiplySpeed, speed)
                else:
                    clip = MultiplySpeed(clip, speed)
                print(f"⚡ Speed adjusted to {speed}x")
            
            # Get format settings
            format_config = self.config["output_formats"].get(format_type, self.config["output_formats"]["tiktok"])
            target_width = format_config["width"]
            target_height = format_config["height"]
            
            # Resize to target format
            clip = self._resize_to_vertical(clip, target_width, target_height)
            
            # Apply video filters if requested
            if filters:
                clip = self._apply_filters(clip, filters)
            
            # Add text overlay if requested
            if text_overlay:
                clip = self._add_text_overlay(clip, text_overlay)
            
            # Write output
            clip.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                fps=format_config["fps"],
                preset='medium',
                bitrate='8000k'
            )
            
            print(f"✅ Edited clip saved: {output_path}")
            return True
            
        except Exception as e:
            print(f"❌ Error editing clip: {e}")
            return False
        finally:
            # Clean up clips
            if 'clip' in locals() and clip is not None:
                try:
                    clip.close()
                except:
                    pass
            if 'full_clip' in locals() and full_clip is not None:
                try:
                    full_clip.close()
                except:
                    pass
    
    def _generate_thumbnail(self, clip: VideoFileClip, output_path: str) -> Optional[str]:
        """Generate a thumbnail for the clip"""
        try:
            # Get thumbnail path (same name as video but .jpg)
            thumbnail_path = Path(output_path).with_suffix('.jpg')
            
            # Extract frame at midpoint of clip
            frame_time = clip.duration / 2
            frame = clip.get_frame(frame_time)
            
            # Convert numpy array to PIL Image
            img = Image.fromarray(frame)
            
            # Resize thumbnail (keep aspect ratio, max 400px width)
            max_width = 400
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
            
            # Save thumbnail
            img.save(thumbnail_path, 'JPEG', quality=85)
            
            return str(thumbnail_path)
        except Exception as e:
            print(f"⚠️  Could not generate thumbnail: {e}")
            return None
    
    def _apply_filters(self, clip: VideoFileClip, filters: Dict) -> VideoFileClip:
        """Apply video filters (brightness, contrast, saturation)"""
        try:
            # Import colorx for filters
            try:
                if MOVIEPY_VERSION == 2:
                    from moviepy.video.fx import colorx
                    Brightness = colorx.colorx
                    Contrast = colorx.colorx
                    Saturation = colorx.colorx
                else:
                    from moviepy.video.fx.all import colorx
                    Brightness = colorx
                    Contrast = colorx
                    Saturation = colorx
            except ImportError:
                # Fallback: use manual color adjustment
                print("⚠️  Color filters not available, using basic adjustments")
                return clip
            
            # Apply brightness
            if 'brightness' in filters and filters['brightness'] != 1.0:
                brightness = filters['brightness']
                try:
                    if MOVIEPY_VERSION == 2:
                        clip = clip.fx(lambda c: c.fx(lambda gf: gf * brightness))
                    else:
                        # Manual brightness adjustment
                        clip = clip.fx(lambda gf: gf * brightness)
                except:
                    print(f"⚠️  Could not apply brightness filter")
            
            # Apply contrast
            if 'contrast' in filters and filters['contrast'] != 1.0:
                contrast = filters['contrast']
                try:
                    # Contrast adjustment: (pixel - 128) * contrast + 128
                    if MOVIEPY_VERSION == 2:
                        clip = clip.fx(lambda c: c.fx(lambda gf: (gf - 128) * contrast + 128))
                    else:
                        clip = clip.fx(lambda gf: (gf - 128) * contrast + 128)
                except:
                    print(f"⚠️  Could not apply contrast filter")
            
            # Apply saturation (simplified - would need proper color space conversion)
            if 'saturation' in filters and filters['saturation'] != 1.0:
                saturation = filters['saturation']
                print(f"📊 Saturation adjustment: {saturation}x (simplified)")
                # Note: Full saturation requires HSV conversion which is complex
            
            return clip
            
        except Exception as e:
            print(f"⚠️  Error applying filters: {e}")
            return clip
    
    def compile_clips(self, clip_paths: List[str], output_path: str, 
                     transition: str = "fade", transition_duration: float = 0.5,
                     format_type: str = "tiktok") -> bool:
        """
        Compile multiple clips into one video with transitions
        
        Args:
            clip_paths: List of paths to video clips to merge
            output_path: Path to save compiled video
            transition: Type of transition ('fade', 'cut', 'crossfade', 'none')
            transition_duration: Duration of transition in seconds
            format_type: Output format (tiktok/youtube_shorts)
        """
        print(f"🎬 Compiling {len(clip_paths)} clips with {transition} transition...")
        
        if not clip_paths:
            print("❌ No clips provided for compilation")
            return False
        
        clips = []
        try:
            # Load all clips
            for i, clip_path in enumerate(clip_paths):
                if not os.path.exists(clip_path):
                    print(f"⚠️  Clip not found: {clip_path}, skipping...")
                    continue
                
                clip = VideoFileClip(clip_path)
                
                # Get format settings and resize if needed
                format_config = self.config["output_formats"].get(format_type, self.config["output_formats"]["tiktok"])
                target_width = format_config["width"]
                target_height = format_config["height"]
                
                # Resize to match format
                if clip.w != target_width or clip.h != target_height:
                    clip = self._resize_to_vertical(clip, target_width, target_height)
                
                clips.append(clip)
                print(f"✅ Loaded clip {i+1}/{len(clip_paths)}: {Path(clip_path).name}")
            
            if not clips:
                print("❌ No valid clips to compile")
                return False
            
            # Apply transitions
            if transition == "fade" and len(clips) > 1:
                # Add fade in/out to clips
                for i, clip in enumerate(clips):
                    if i == 0:
                        # Fade in first clip
                        clips[i] = clip.fadein(transition_duration)
                    elif i == len(clips) - 1:
                        # Fade out last clip
                        clips[i] = clip.fadeout(transition_duration)
                    else:
                        # Fade in and out for middle clips
                        clips[i] = clip.fadein(transition_duration).fadeout(transition_duration)
            
            elif transition == "crossfade" and len(clips) > 1:
                # Crossfade between clips (overlap)
                for i in range(len(clips) - 1):
                    clips[i] = clips[i].fadeout(transition_duration)
                    clips[i+1] = clips[i+1].fadein(transition_duration)
            
            # Concatenate clips
            final_clip = concatenate_videoclips(clips, method="compose")
            
            # Get format settings
            format_config = self.config["output_formats"].get(format_type, self.config["output_formats"]["tiktok"])
            
            # Write output
            final_clip.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                fps=format_config["fps"],
                preset='medium',
                bitrate='8000k'
            )
            
            # Generate thumbnail
            self._generate_thumbnail(final_clip, output_path)
            
            # Clean up
            final_clip.close()
            for clip in clips:
                clip.close()
            
            print(f"✅ Compiled video saved: {output_path}")
            return True
            
        except Exception as e:
            print(f"❌ Error compiling clips: {e}")
            # Clean up on error
            for clip in clips:
                try:
                    clip.close()
                except:
                    pass
            return False
    
    def _add_text_overlay(self, clip: VideoFileClip, overlay_config: Dict) -> CompositeVideoClip:
        """Add text overlay to clip"""
        try:
            text = overlay_config.get('text', '')
            position = overlay_config.get('position', 'bottom')
            fontsize = overlay_config.get('fontsize', 48)
            color = overlay_config.get('color', 'white')
            start_time = overlay_config.get('start_time', 0)
            duration = overlay_config.get('duration', clip.duration)
            
            if not text:
                return clip
            
            # Create text clip
            txt_clip = TextClip(
                text,
                fontsize=fontsize,
                color=color,
                font='Arial-Bold',
                method='caption',
                size=(clip.w * 0.9, None),
                stroke_color='black',
                stroke_width=3
            ).set_duration(min(duration, clip.duration)).set_start(start_time)
            
            # Position text
            if position == "bottom":
                txt_clip = txt_clip.set_position(('center', clip.h * 0.85))
            elif position == "top":
                txt_clip = txt_clip.set_position(('center', 'top'))
            else:  # center
                txt_clip = txt_clip.set_position('center')
            
            return CompositeVideoClip([clip, txt_clip])
            
        except Exception as e:
            print(f"⚠️  Could not add text overlay: {e}")
            return clip
    
    def process_uploaded_video(self, video_path: str, output_path: str, 
                               format_type: str = "tiktok") -> bool:
        """
        Process an uploaded video file (convert to target format)
        
        Args:
            video_path: Path to uploaded video file
            output_path: Path to save processed video
            format_type: Target format (tiktok/youtube_shorts)
        """
        print(f"📤 Processing uploaded video: {video_path}")
        
        clip = None
        try:
            # Load video
            clip = VideoFileClip(video_path)
            
            # Get format settings
            format_config = self.config["output_formats"].get(format_type, self.config["output_formats"]["tiktok"])
            target_width = format_config["width"]
            target_height = format_config["height"]
            
            # Resize to target format
            clip = self._resize_to_vertical(clip, target_width, target_height)
            
            # Check duration and speed up if needed
            max_duration = format_config["duration_max"]
            if clip.duration > max_duration:
                speed_factor = clip.duration / max_duration
                if MOVIEPY_VERSION == 2:
                    clip = clip.fx(MultiplySpeed, speed_factor)
                else:
                    clip = MultiplySpeed(clip, speed_factor)
                print(f"⚡ Sped up by {speed_factor:.2f}x to fit duration")
            
            # Write output
            clip.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                fps=format_config["fps"],
                preset='medium',
                bitrate='8000k'
            )
            
            print(f"✅ Processed video saved: {output_path}")
            return True
            
        except Exception as e:
            print(f"❌ Error processing video: {e}")
            return False
        finally:
            if clip is not None:
                try:
                    clip.close()
                except:
                    pass


def main():
    """Main entry point"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python clip_generator.py <url> [tiktok|youtube_shorts|both]")
        print("Example: python clip_generator.py https://www.youtube.com/watch?v=... both")
        return
    
    url = sys.argv[1]
    formats = ["tiktok", "youtube_shorts"]
    
    if len(sys.argv) > 2:
        format_arg = sys.argv[2].lower()
        if format_arg == "tiktok":
            formats = ["tiktok"]
        elif format_arg == "youtube_shorts":
            formats = ["youtube_shorts"]
        elif format_arg != "both":
            print("Invalid format. Use: tiktok, youtube_shorts, or both")
            return
    
    generator = ClipGenerator()
    output_files = generator.process_url(url, formats)
    
    if output_files:
        print("\nðŸ“ Output files:")
        for f in output_files:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
