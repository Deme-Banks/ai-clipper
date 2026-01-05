# 🎬 AI Clip Generator - Viral Content Creator

Automatically transform Twitch and YouTube videos into engaging TikTok Reels and YouTube Shorts! This AI-powered tool finds the most viral-worthy moments and formats them perfectly for maximum engagement.

## ✨ Features

- 🎥 **Auto-Download**: Supports Twitch and YouTube URLs
- 🤖 **AI-Powered Clip Detection**: Finds the most engaging moments automatically using OpenAI (optional)
- 📱 **Format Optimization**: Creates perfect vertical videos for TikTok (1080x1920)
- 🎯 **YouTube Shorts Ready**: Also formats for YouTube Shorts
- ⚡ **Smart Editing**: Auto-crops, speeds up, and optimizes clips
- 🚀 **Viral-Focused**: Designed to help your content blow up!

## 📋 Prerequisites

- **Python 3.8 or higher** - [Download Python](https://www.python.org/downloads/)
- **FFmpeg** - Required for video processing
- **OpenAI API Key** (Optional) - For enhanced AI clip detection

## 🛠️ Installation

### Step 1: Install FFmpeg

**Windows:**
```powershell
winget install --id=Gyan.FFmpeg
```

Or download from [FFmpeg Official Website](https://ffmpeg.org/download.html)

**Mac:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

### Step 2: Clone the Repository

```bash
git clone https://github.com/Deme-Banks/ai-clipper.git
cd ai-clipper
```

### Step 3: Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: (Optional) Configure OpenAI API Key

For enhanced AI-powered clip detection:

1. Get an API key from [OpenAI Platform](https://platform.openai.com/)
2. Create a `.env` file in the project root:
```env
OPENAI_API_KEY=your_api_key_here
```

> **Note:** The tool works without OpenAI, but AI detection provides significantly better clip selection by analyzing transcripts and identifying engaging moments.

## 🚀 Usage

### 🌐 Web Interface (Recommended)

The easiest way to use the AI Clip Generator is through the web interface:

1. **Start the web server:**
   ```bash
   python app.py
   ```
   
   Or on Windows:
   ```bash
   run_web.bat
   ```

2. **Open your browser:**
   - Local access: http://localhost:5000
   - Network access: http://YOUR_IP:5000 (accessible from other devices on your network)

3. **Use the interface:**
   - Paste a YouTube or Twitch URL
   - Select output formats (TikTok, YouTube Shorts, or both)
   - Click "Generate Clips"
   - Watch the progress and download your clips when ready!

### 💻 Command Line Usage

Create clips for both TikTok and YouTube Shorts:
```bash
python clip_generator.py https://www.youtube.com/watch?v=VIDEO_ID
```

Create only TikTok format:
```bash
python clip_generator.py https://www.youtube.com/watch?v=VIDEO_ID tiktok
```

Create only YouTube Shorts format:
```bash
python clip_generator.py https://www.youtube.com/watch?v=VIDEO_ID youtube_shorts
```

### Examples

**Twitch Stream:**
```bash
python clip_generator.py https://www.twitch.tv/videos/1234567890
```

**YouTube Video:**
```bash
python clip_generator.py https://www.youtube.com/watch?v=dQw4w9WgXcQ both
```

**YouTube Shorts Only:**
```bash
python clip_generator.py https://www.youtube.com/watch?v=dQw4w9WgXcQ youtube_shorts
```

## 📁 Output

All clips are saved in the `output/` directory with descriptive filenames:

- `video_title_clip1_tiktok.mp4`
- `video_title_clip1_youtube_shorts.mp4`
- `video_title_clip2_tiktok.mp4`
- etc.

The tool automatically:
- Downloads videos to the `downloads/` directory
- Analyzes content for engaging moments
- Creates multiple clips per video (up to 5 by default)
- Formats clips for optimal social media engagement

## ⚙️ Configuration

Edit `config.json` to customize settings:

### Output Formats
- **Dimensions**: Adjust width/height for TikTok and YouTube Shorts
- **Duration**: Set maximum clip duration (default: 60 seconds)
- **FPS**: Frame rate for output videos (default: 30)

### Clip Settings
- **min_duration**: Minimum clip length in seconds (default: 15)
- **max_duration**: Maximum clip length in seconds (default: 60)
- **preferred_duration**: Target clip length (default: 30)
- **buffer_seconds**: Extra seconds before/after clips (default: 2)

### AI Settings
- **model**: OpenAI model to use (default: "gpt-4")
- **temperature**: AI creativity level 0-1 (default: 0.7)
- **max_clips_per_video**: Maximum clips generated per video (default: 5)

### Example Configuration

```json
{
  "output_formats": {
    "tiktok": {
      "width": 1080,
      "height": 1920,
      "duration_max": 60,
      "fps": 30
    }
  },
  "clip_settings": {
    "min_duration": 15,
    "max_duration": 60,
    "preferred_duration": 30,
    "buffer_seconds": 2
  },
  "ai_settings": {
    "model": "gpt-4",
    "temperature": 0.7,
    "max_clips_per_video": 5
  }
}
```

## 🔍 How It Works

1. **Download**: Automatically downloads video from provided URL
2. **Analyze**: Extracts transcript (if available) and analyzes content
3. **Detect**: Uses AI or heuristics to find engaging moments
4. **Format**: Crops and resizes to vertical format (9:16 aspect ratio)
5. **Optimize**: Speeds up clips if needed, adds engaging elements
6. **Export**: Saves ready-to-upload clips in `output/` directory

## 🐛 Troubleshooting

### FFmpeg Not Found
- Ensure FFmpeg is installed and in your system PATH
- Verify installation: `ffmpeg -version`

### Import Errors
- Make sure all dependencies are installed: `pip install -r requirements.txt`
- Use a virtual environment to avoid conflicts

### Video Download Fails
- Check your internet connection
- Verify the URL is accessible
- Some videos may have download restrictions

### OpenAI API Errors
- Verify your API key is correct in `.env` file
- Check your OpenAI account has credits
- The tool will fall back to heuristic detection if AI fails

## 📝 Requirements

See `requirements.txt` for full list. Main dependencies:
- `yt-dlp` - Video downloading
- `moviepy` - Video editing
- `openai` - AI clip detection (optional)
- `pillow` - Image processing
- `python-dotenv` - Environment variables

## 🤝 Contributing

Contributions are welcome! Feel free to:
- Report bugs
- Suggest features
- Submit pull requests
- Improve documentation

## 📄 License

Free to use for personal and commercial projects!

## 🙏 Acknowledgments

Built for content creators who want to go viral! 🚀

---

**Made with ❤️ for the creator community**
