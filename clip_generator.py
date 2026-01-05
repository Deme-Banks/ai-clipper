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
        
        # Initialize OpenAI if API key is available
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.openai_client = None
        self.openai_enabled = False
        if self.openai_key and OPENAI_AVAILABLE:
            try:
                self.openai_client = OpenAI(
                    api_key=self.openai_key,
                    timeout=60.0,  # 60 second timeout
                    max_retries=3
                )
                self.openai_enabled = True
                print("[OK] OpenAI API initialized successfully")
            except Exception as e:
                print(f"[WARNING] OpenAI initialization failed: {e}")
                self.openai_enabled = False
        elif not OPENAI_AVAILABLE:
            print("[INFO] OpenAI library not installed. Install with: pip install openai")
        elif not self.openai_key:
            print("[INFO] OpenAI API key not found. Add OPENAI_API_KEY to .env for AI-powered clip detection")
        
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
        """Extract transcript from video if available"""
        try:
            ydl_opts = {
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['en'],
                'skip_download': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Try to get subtitles
                subtitles = info.get('subtitles', {}) or info.get('automatic_captions', {})
                if 'en' in subtitles:
                    subtitle_url = subtitles['en'][0]['url']
                    import requests
                    response = requests.get(subtitle_url)
                    if response.status_code == 200:
                        # Parse WebVTT or SRT format (simplified)
                        text = response.text
                        # Remove timestamps and formatting
                        lines = text.split('\n')
                        transcript_lines = []
                        for line in lines:
                            if line and not line.startswith('<') and '-->' not in line and not line.strip().isdigit():
                                transcript_lines.append(line.strip())
                        return ' '.join(transcript_lines)
        except Exception as e:
            print(f"âš ï¸ Could not extract transcript: {e}")
        
        return None
    
    def find_engaging_clips_ai(self, video_path: str, transcript: Optional[str] = None) -> List[Dict]:
        """Use AI to find the most engaging moments in the video"""
        clip = VideoFileClip(video_path)
        duration = clip.duration
        clip.close()
        
        # If we have OpenAI API, use it for intelligent clip detection
        if self.openai_enabled and self.openai_client:
            if transcript:
                print("🤖 AI analyzing video transcript for engaging moments...")
                return self._ai_clip_detection(video_path, transcript, duration)
            else:
                print("⚠️  No transcript available. AI detection requires transcript. Using heuristics...")
                return self._heuristic_clip_detection(video_path, duration)
        else:
            # Fallback: Use heuristics to find potential clips
            if not self.openai_enabled:
                print("💡 Using heuristic detection (add OpenAI API key to .env for AI-powered clip detection)")
            return self._heuristic_clip_detection(video_path, duration)
    
    def _ai_clip_detection(self, video_path: str, transcript: str, duration: float) -> List[Dict]:
        """Use OpenAI to intelligently find engaging clips"""
        try:
            max_retries = 3
            retry_delay = 2
            
            # Truncate transcript if too long (keep it under token limits)
            max_transcript_length = 4000  # characters
            transcript_to_use = transcript
            if len(transcript_to_use) > max_transcript_length:
                transcript_to_use = transcript_to_use[:max_transcript_length] + "..."
                print(f"📝 Transcript truncated to {max_transcript_length} characters for API efficiency")
            
            for attempt in range(max_retries):
                try:
                    # Enhanced prompt for better clip detection
                    system_prompt = """You are an expert video editor and social media content strategist specializing in viral content. 
Your task is to identify the most engaging, shareable moments from video transcripts that would perform well on TikTok and YouTube Shorts.

Key principles:
- Prioritize moments with high emotional impact (laughter, surprise, tension, excitement)
- Look for clear narrative hooks that grab attention in the first 3 seconds
- Identify moments with strong visual potential (even from transcript context)
- Focus on self-contained clips that make sense without full context
- Prefer clips with memorable quotes, reactions, or dramatic moments
- Avoid clips that require extensive background knowledge

Return ONLY a valid JSON array. No markdown, no explanations, just JSON."""
                    
                    user_prompt = f"""Analyze this video transcript and identify the {self.config["ai_settings"]["max_clips_per_video"]} most engaging, viral-worthy moments.

Video Information:
- Duration: {duration:.1f} seconds
- Target clip length: {self.config["clip_settings"]["preferred_duration"]}-{self.config["clip_settings"]["max_duration"]} seconds
- Minimum clip length: {self.config["clip_settings"]["min_duration"]} seconds

Transcript:
{transcript_to_use}

Return a JSON array with this exact structure:
[
  {{
    "start_time": <number in seconds>,
    "end_time": <number in seconds>,
    "reason": "<brief explanation of why this moment is engaging>",
    "title": "<catchy, clickable title for the clip>",
    "engagement_score": <number 1-10 indicating viral potential>
  }}
]

Requirements:
- Each clip must be between {self.config["clip_settings"]["min_duration"]} and {self.config["clip_settings"]["max_duration"]} seconds
- start_time must be >= 0 and end_time must be <= {duration:.1f}
- Focus on moments with high engagement potential
- Ensure clips don't overlap significantly
- Return ONLY the JSON array, no other text"""

                    if attempt > 0:
                        print(f"🔄 Retrying OpenAI request (attempt {attempt + 1}/{max_retries})...")
                    else:
                        print("🔄 Sending request to OpenAI...")
                    
                    response = self.openai_client.chat.completions.create(
                        model=self.config["ai_settings"]["model"],
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=self.config["ai_settings"]["temperature"]
                    )
                    
                    # Extract and parse response
                    content = response.choices[0].message.content.strip()
                    
                    # Handle different response formats
                    if content.startswith("```"):
                        # Remove markdown code blocks
                        lines = content.split("\n")
                        content = "\n".join([line for line in lines if not line.strip().startswith("```")])
                    elif content.startswith("`"):
                        content = content.strip("`")
                        if content.startswith("json"):
                            content = content[4:].strip()
                    
                    # Try to parse as JSON
                    try:
                        clips_data = json.loads(content)
                    except json.JSONDecodeError:
                        # Try to extract JSON from text
                        json_match = re.search(r'\[.*\]', content, re.DOTALL)
                        if json_match:
                            clips_data = json.loads(json_match.group())
                        else:
                            raise ValueError("Could not extract JSON from response")
                    
                    # Handle if response is wrapped in an object
                    if isinstance(clips_data, dict):
                        # Look for common keys that might contain the array
                        for key in ['clips', 'results', 'data', 'output']:
                            if key in clips_data and isinstance(clips_data[key], list):
                                clips_data = clips_data[key]
                                break
                        # If still a dict, try to convert to list
                        if isinstance(clips_data, dict):
                            clips_data = [clips_data]
                    
                    if not isinstance(clips_data, list):
                        clips_data = [clips_data]
                    
                    # Validate and filter clips
                    valid_clips = []
                    for clip in clips_data:
                        if "start_time" in clip and "end_time" in clip:
                            try:
                                start = float(clip["start_time"])
                                end = float(clip["end_time"])
                                clip_duration = end - start
                                
                                # Validate clip timing
                                if (0 <= start < end <= duration and 
                                    self.config["clip_settings"]["min_duration"] <= clip_duration <= self.config["clip_settings"]["max_duration"]):
                                    
                                    # Add buffer if configured
                                    start = max(0, start - self.config["clip_settings"]["buffer_seconds"])
                                    end = min(duration, end + self.config["clip_settings"]["buffer_seconds"])
                                    
                                    valid_clips.append({
                                        "start_time": start,
                                        "end_time": end,
                                        "reason": clip.get("reason", "Engaging moment"),
                                        "title": clip.get("title", f"Clip {len(valid_clips) + 1}"),
                                        "engagement_score": clip.get("engagement_score", 7)
                                    })
                            except (ValueError, TypeError) as e:
                                print(f"⚠️  Skipping invalid clip data: {e}")
                                continue
                    
                    # Sort by engagement score if available
                    valid_clips.sort(key=lambda x: x.get("engagement_score", 0), reverse=True)
                    
                    # Limit to max clips
                    valid_clips = valid_clips[:self.config["ai_settings"]["max_clips_per_video"]]
                    
                    if valid_clips:
                        print(f"✅ AI found {len(valid_clips)} engaging clips!")
                        # Show estimated cost
                        self._estimate_cost(response)
                        return valid_clips
                    else:
                        print("⚠️  AI returned no valid clips, using heuristics...")
                        return self._heuristic_clip_detection(video_path, duration)
                        
                except RateLimitError as e:
                    wait_time = retry_delay * (2 ** attempt)
                    if attempt < max_retries - 1:
                        print(f"⏳ Rate limit hit. Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                    else:
                        print(f"❌ Rate limit exceeded after {max_retries} attempts. Using heuristics...")
                        return self._heuristic_clip_detection(video_path, duration)
                        
                except (APIConnectionError, APITimeoutError) as e:
                    wait_time = retry_delay * (2 ** attempt)
                    if attempt < max_retries - 1:
                        print(f"🔄 Connection error. Retrying in {wait_time} seconds...")
                        time.sleep(wait_time)
                    else:
                        print(f"❌ Connection failed after {max_retries} attempts. Using heuristics...")
                        return self._heuristic_clip_detection(video_path, duration)
                        
                except APIError as e:
                    error_msg = str(e)
                    if "insufficient_quota" in error_msg.lower() or "billing" in error_msg.lower():
                        print(f"❌ OpenAI API billing/quota issue: {e}")
                        print("💡 Check your OpenAI account billing and credits")
                    else:
                        print(f"❌ OpenAI API error: {e}")
                    return self._heuristic_clip_detection(video_path, duration)
                    
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"⚠️  Failed to parse AI response: {e}")
                    if attempt < max_retries - 1:
                        print(f"🔄 Retrying with different approach...")
                        time.sleep(retry_delay)
                    else:
                        print("❌ Could not parse AI response after retries. Using heuristics...")
                        return self._heuristic_clip_detection(video_path, duration)
            
            # If all retries failed
            return self._heuristic_clip_detection(video_path, duration)
            
        except Exception as e:
            print(f"âš ï¸ AI detection failed, using heuristics: {e}")
            return self._heuristic_clip_detection(video_path, duration)
    
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
                        "engagement_score": 5
                    })
        
        return clips
    
    def create_clip(self, video_path: str, start_time: float, end_time: float, 
                   output_path: str, format_type: str = "tiktok", clip_title: str = None) -> bool:
        """Create a formatted clip for TikTok or YouTube Shorts"""
        print(f"âœ‚ï¸ Creating {format_type} clip: {start_time}s - {end_time}s")
        
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
            format_config = self.config["output_formats"][format_type]
            target_width = format_config["width"]
            target_height = format_config["height"]
            
            # Resize to vertical format (9:16 aspect ratio)
            clip = self._resize_to_vertical(clip, target_width, target_height)
            
            # Speed up if needed to fit duration
            max_duration = format_config["duration_max"]
            if clip.duration > max_duration:
                speed_factor = clip.duration / max_duration
                if MOVIEPY_VERSION == 2:
                    clip = clip.fx(MultiplySpeed, speed_factor)
                else:
                    clip = MultiplySpeed(clip, speed_factor)
                print(f"âš¡ Sped up by {speed_factor:.2f}x to fit duration")
            
            # Add engaging elements (including captions if enabled)
            clip = self._add_engaging_elements(clip, format_type, clip_title, add_captions=True)
            
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
            
            print(f"âœ… Created: {output_path}")
            return True
            
        except Exception as e:
            print(f"âŒ Error creating clip: {e}")
            return False
    
    def _resize_to_vertical(self, clip: VideoFileClip, target_width: int, target_height: int) -> VideoFileClip:
        """Resize clip to vertical format, cropping intelligently"""
        # Try to import Crop function
        Crop = None
        try:
            if MOVIEPY_VERSION == 2:
                Crop = vfx.Crop
            else:
                try:
                    from moviepy.video.fx.all import crop as Crop
                except ImportError:
                    from moviepy.video.fx import crop as Crop
        except:
            # If crop is not available, just resize without crop
            if MOVIEPY_VERSION == 2:
                clip = clip.fx(Resize, (target_width, target_height))
            else:
                clip = Resize(clip, (target_width, target_height))
            return clip
        
        # Calculate aspect ratios
        clip_aspect = clip.w / clip.h
        target_aspect = target_width / target_height
        
        if Crop is not None:
            if clip_aspect > target_aspect:
                # Clip is wider, crop sides (center crop)
                new_width = int(clip.h * target_aspect)
                x_center = clip.w / 2
                if MOVIEPY_VERSION == 2:
                    clip = clip.fx(Crop, x_center=x_center, width=new_width)
                else:
                    clip = Crop(clip, x_center=x_center, width=new_width)
            else:
                # Clip is taller, crop top/bottom (center crop)
                new_height = int(clip.w / target_aspect)
                y_center = clip.h / 2
                if MOVIEPY_VERSION == 2:
                    clip = clip.fx(Crop, y_center=y_center, height=new_height)
                else:
                    clip = Crop(clip, y_center=y_center, height=new_height)
        
        # Resize to target dimensions
        if MOVIEPY_VERSION == 2:
            clip = clip.fx(Resize, (target_width, target_height))
        else:
            clip = Resize(clip, (target_width, target_height))
        return clip
    
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
                
                # Create text clip
                txt_clip = TextClip(
                    text,
                    fontsize=font_size,
                    color=font_color,
                    font='Arial-Bold',
                    method='caption',
                    size=(clip.w * 0.9, None),
                    stroke_color='black',
                    stroke_width=3
                ).set_duration(duration).set_start(start_time)
                
                # Position caption
                if position == "bottom":
                    txt_clip = txt_clip.set_position(('center', clip.h * 0.85))
                elif position == "top":
                    txt_clip = txt_clip.set_position(('center', 'top'))
                else:  # center
                    txt_clip = txt_clip.set_position('center')
                
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
    
    def _add_engaging_elements(self, clip: VideoFileClip, format_type: str, title: str = None, add_captions: bool = True) -> CompositeVideoClip:
        """Add engaging elements like captions, effects, etc."""
        clips_to_composite = [clip]
        
        # Add title text overlay if provided (for first 2 seconds)
        if title and len(title) > 0:
            try:
                title_clip = TextClip(
                    title[:50],  # Limit length
                    fontsize=40,
                    color='white',
                    font='Arial-Bold',
                    method='caption',
                    size=(clip.w * 0.9, None),
                    stroke_color='black',
                    stroke_width=2
                ).set_position(('center', 'top')).set_duration(min(2, clip.duration))
                
                clips_to_composite.append(title_clip)
            except Exception as e:
                print(f"⚠️  Could not add title overlay: {e}")
        
        # Add captions if enabled
        if add_captions and self.config.get("captions", {}).get("enabled", True):
            try:
                segments = self._transcribe_clip_audio(clip)
                if segments:
                    return self._add_captions_to_clip(CompositeVideoClip(clips_to_composite), segments)
            except Exception as e:
                print(f"⚠️  Caption generation skipped: {e}")
        
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
                
                if self.create_clip(video_path, start, end, str(output_path), format_type, clip_title):
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
