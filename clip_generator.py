"""
AI-Powered Clip Generator for Twitch/YouTube to TikTok/YouTube Shorts
Automatically finds engaging moments and creates viral-ready clips
"""

import os
import json
import subprocess
import re
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import yt_dlp
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
try:
    from moviepy.video.fx.all import resize, speedx
except ImportError:
    from moviepy.video.fx import resize, speedx
from PIL import Image, ImageDraw, ImageFont
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
                print("✅ OpenAI API initialized successfully")
            except Exception as e:
                print(f"⚠️  Warning: OpenAI initialization failed: {e}")
                self.openai_enabled = False
        elif not OPENAI_AVAILABLE:
            print("ℹ️  OpenAI library not installed. Install with: pip install openai")
        elif not self.openai_key:
            print("ℹ️  OpenAI API key not found. Add OPENAI_API_KEY to .env for AI-powered clip detection")
        
        # Create output directories
        self.output_dir = Path("output")
        self.downloads_dir = Path("downloads")
        self.output_dir.mkdir(exist_ok=True)
        self.downloads_dir.mkdir(exist_ok=True)
    
    def download_video(self, url: str) -> Optional[str]:
        """Download video from Twitch or YouTube URL"""
        print(f"ðŸ“¥ Downloading video from: {url}")
        
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
                print(f"âœ… Downloaded: {filename}")
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
                # Rough cost estimates (as of 2024, adjust as needed)
                model = self.config["ai_settings"]["model"]
                if "gpt-4" in model.lower():
                    # GPT-4 pricing: ~$0.03 per 1K input tokens, ~$0.06 per 1K output tokens
                    input_cost = (usage.prompt_tokens / 1000) * 0.03
                    output_cost = (usage.completion_tokens / 1000) * 0.06
                elif "gpt-3.5" in model.lower():
                    # GPT-3.5-turbo pricing: ~$0.0015 per 1K input tokens, ~$0.002 per 1K output tokens
                    input_cost = (usage.prompt_tokens / 1000) * 0.0015
                    output_cost = (usage.completion_tokens / 1000) * 0.002
                else:
                    input_cost = output_cost = 0
                
                total_cost = input_cost + output_cost
                if total_cost > 0:
                    print(f"💰 Estimated API cost: ${total_cost:.4f} ({usage.prompt_tokens} input + {usage.completion_tokens} output tokens)")
        except Exception:
            pass  # Silently fail cost estimation
    
    def _heuristic_clip_detection(self, video_path: str, duration: float) -> List[Dict]:
        """Fallback: Use heuristics to find potential clips"""
        clips = []
        min_duration = self.config["clip_settings"]["min_duration"]
        max_duration = self.config["clip_settings"]["max_duration"]
        preferred_duration = self.config["clip_settings"]["preferred_duration"]
        
        # Strategy: Create clips at different points in the video
        num_clips = min(5, int(duration / (preferred_duration * 2)))
        
        for i in range(num_clips):
            start_time = (duration / (num_clips + 1)) * (i + 1)
            end_time = min(start_time + preferred_duration, duration)
            
            if end_time - start_time >= min_duration:
                clips.append({
                    "start_time": max(0, start_time - self.config["clip_settings"]["buffer_seconds"]),
                    "end_time": min(end_time + self.config["clip_settings"]["buffer_seconds"], duration),
                    "reason": f"Engaging moment at {int(start_time)}s",
                    "title": f"Clip {i+1}"
                })
        
        return clips
    
    def create_clip(self, video_path: str, start_time: float, end_time: float, 
                   output_path: str, format_type: str = "tiktok") -> bool:
        """Create a formatted clip for TikTok or YouTube Shorts"""
        print(f"âœ‚ï¸ Creating {format_type} clip: {start_time}s - {end_time}s")
        
        try:
            # Load video
            clip = VideoFileClip(video_path).subclip(start_time, end_time)
            
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
                clip = speedx(clip, speed_factor)
                print(f"âš¡ Sped up by {speed_factor:.2f}x to fit duration")
            
            # Add engaging elements
            clip = self._add_engaging_elements(clip, format_type)
            
            # Write output
            clip.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                fps=format_config["fps"],
                preset='medium',
                bitrate='8000k'
            )
            
            clip.close()
            print(f"âœ… Created: {output_path}")
            return True
            
        except Exception as e:
            print(f"âŒ Error creating clip: {e}")
            return False
    
    def _resize_to_vertical(self, clip: VideoFileClip, target_width: int, target_height: int) -> VideoFileClip:
        """Resize clip to vertical format, cropping intelligently"""
        try:
            from moviepy.video.fx.all import crop
        except ImportError:
            from moviepy.video.fx import crop
        
        # Calculate aspect ratios
        clip_aspect = clip.w / clip.h
        target_aspect = target_width / target_height
        
        if clip_aspect > target_aspect:
            # Clip is wider, crop sides (center crop)
            new_width = int(clip.h * target_aspect)
            x_center = clip.w / 2
            clip = crop(clip, x_center=x_center, width=new_width)
        else:
            # Clip is taller, crop top/bottom (center crop)
            new_height = int(clip.w / target_aspect)
            y_center = clip.h / 2
            clip = crop(clip, y_center=y_center, height=new_height)
        
        # Resize to target dimensions
        clip = resize(clip, (target_width, target_height))
        return clip
    
    def _add_engaging_elements(self, clip: VideoFileClip, format_type: str) -> CompositeVideoClip:
        """Add engaging elements like captions, effects, etc."""
        clips_to_composite = [clip]
        
        # Add subtle zoom effect for engagement
        def zoom_in(t):
            return 1 + 0.05 * (t / clip.duration)
        
        # Add captions if we have them (simplified version)
        # In a full implementation, you'd use speech-to-text here
        
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
            
            for format_type in formats:
                output_filename = f"{video_name}_clip{i+1}_{format_type}.mp4"
                output_path = self.output_dir / output_filename
                
                if self.create_clip(video_path, start, end, str(output_path), format_type):
                    output_files.append(str(output_path))
        
        print(f"\nðŸŽ‰ Successfully created {len(output_files)} clips!")
        return output_files


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
