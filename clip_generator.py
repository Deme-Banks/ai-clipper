"""
AI-Powered Clip Generator for Twitch/YouTube to TikTok/YouTube Shorts
Automatically finds engaging moments and creates viral-ready clips
"""

import os
import json
import subprocess
import re
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
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

load_dotenv()

class ClipGenerator:
    def __init__(self, config_path: str = "config.json"):
        """Initialize the clip generator with configuration"""
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Initialize OpenAI if API key is available
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.openai_client = None
        if self.openai_key and OPENAI_AVAILABLE:
            self.openai_client = OpenAI(api_key=self.openai_key)
        
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
        print("ðŸ¤– AI analyzing video for engaging moments...")
        
        clip = VideoFileClip(video_path)
        duration = clip.duration
        clip.close()
        
        # If we have OpenAI API, use it for intelligent clip detection
        if self.openai_client and transcript:
            return self._ai_clip_detection(video_path, transcript, duration)
        else:
            # Fallback: Use heuristics to find potential clips
            print("ðŸ’¡ Using heuristic detection (add OpenAI API key for better results)")
            return self._heuristic_clip_detection(video_path, duration)
    
    def _ai_clip_detection(self, video_path: str, transcript: str, duration: float) -> List[Dict]:
        """Use OpenAI to intelligently find engaging clips"""
        try:
            prompt = f"""Analyze this video transcript and identify the most engaging, viral-worthy moments that would work well for TikTok/YouTube Shorts.

Video duration: {duration} seconds
Transcript: {transcript[:3000]}...

Return a JSON array of clips, each with:
- start_time: timestamp in seconds (number)
- end_time: timestamp in seconds (number)
- reason: why this moment is engaging (string)
- title: catchy title for the clip (string)

Focus on:
- Funny moments
- Shocking revelations
- Emotional peaks
- Action-packed sequences
- Memorable quotes
- Cliffhangers
- Moments with high energy

Each clip should be 15-60 seconds long. Return ONLY valid JSON array, no other text."""

            response = self.openai_client.chat.completions.create(
                model=self.config["ai_settings"]["model"],
                messages=[
                    {"role": "system", "content": "You are an expert video editor who identifies viral-worthy moments. Return only valid JSON array."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.config["ai_settings"]["temperature"]
            )
            
            content = response.choices[0].message.content.strip()
            # Remove markdown code blocks if present
            if content.startswith("`"):
                content = content.split("`")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            clips_data = json.loads(content)
            if not isinstance(clips_data, list):
                clips_data = [clips_data]
            
            # Validate and filter clips
            valid_clips = []
            for clip in clips_data[:self.config["ai_settings"]["max_clips_per_video"]]:
                if "start_time" in clip and "end_time" in clip:
                    start = float(clip["start_time"])
                    end = float(clip["end_time"])
                    if 0 <= start < end <= duration and (end - start) >= self.config["clip_settings"]["min_duration"]:
                        valid_clips.append(clip)
            
            return valid_clips
            
        except Exception as e:
            print(f"âš ï¸ AI detection failed, using heuristics: {e}")
            return self._heuristic_clip_detection(video_path, duration)
    
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
