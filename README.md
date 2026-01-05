# ðŸŽ¬ AI Clip Generator - Viral Content Creator

Automatically transform Twitch and YouTube videos into engaging TikTok Reels and YouTube Shorts! This AI-powered tool finds the most viral-worthy moments and formats them perfectly for maximum engagement.

## âœ¨ Features

- ðŸŽ¥ **Auto-Download**: Supports Twitch and YouTube URLs
- ðŸ¤– **AI-Powered Clip Detection**: Finds the most engaging moments automatically
- ðŸ“± **Format Optimization**: Creates perfect vertical videos for TikTok (1080x1920)
- ðŸŽ¯ **YouTube Shorts Ready**: Also formats for YouTube Shorts
- âš¡ **Smart Editing**: Auto-crops, speeds up, and optimizes clips
- ðŸš€ **Viral-Focused**: Designed to help your content blow up!

## ðŸ› ï¸ Setup

### Prerequisites

- Python 3.8 or higher
- FFmpeg installed on your system

### Install FFmpeg

**Windows:**
`powershell
winget install --id=Gyan.FFmpeg
`

**Mac:**
`ash
brew install ffmpeg
`

**Linux:**
`ash
sudo apt-get install ffmpeg
`

### Install Python Dependencies

`ash
cd ai-clip-generator
pip install -r requirements.txt
`

### Optional: OpenAI API Key (for better AI clip detection)

1. Get an API key from https://platform.openai.com/
2. Create a .env file in the project root:
`
OPENAI_API_KEY=your_api_key_here
`

*Note: The tool works without OpenAI, but AI detection provides better clip selection.*

## ðŸš€ Usage

### Basic Usage

`ash
# Create clips for both TikTok and YouTube Shorts
python clip_generator.py https://www.youtube.com/watch?v=VIDEO_ID

# Create only TikTok format
python clip_generator.py https://www.youtube.com/watch?v=VIDEO_ID tiktok

# Create only YouTube Shorts format
python clip_generator.py https://www.youtube.com/watch?v=VIDEO_ID youtube_shorts
`

## ðŸ“ Output

All clips are saved in the output/ directory with names like:
- ideo_title_clip1_tiktok.mp4
- ideo_title_clip1_youtube_shorts.mp4

## âš™ï¸ Configuration

Edit config.json to customize:
- Clip duration (min/max)
- Video quality
- Output dimensions
- AI model settings

## ðŸ“ License

Free to use for personal and commercial projects!

---

**Made for content creators who want to go viral! ðŸš€**
