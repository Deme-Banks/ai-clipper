# 📁 File Locations Guide

## Project Root
**Location:** `C:\Users\dxyou\ai-clipper\`

This is where all your project files are located.

## 📂 Directory Structure

### 1. **Generated Clips** (Output)
**Location:** `C:\Users\dxyou\ai-clipper\output\`

This is where all your generated clips are saved:
- Video clips: `video_title_clip1_tiktok.mp4`
- Video clips: `video_title_clip1_youtube_shorts.mp4`
- Thumbnails: `video_title_clip1_tiktok.jpg`
- Thumbnails: `video_title_clip1_youtube_shorts.jpg`

**Example:**
```
output/
  ├── My_Video_clip1_tiktok.mp4
  ├── My_Video_clip1_tiktok.jpg
  ├── My_Video_clip1_youtube_shorts.mp4
  ├── My_Video_clip1_youtube_shorts.jpg
  └── ...
```

### 2. **Downloaded Videos** (Temporary)
**Location:** `C:\Users\dxyou\ai-clipper\downloads\`

Original videos downloaded from YouTube/Twitch are stored here temporarily:
- Full video files before processing
- These can be deleted to save space (they're re-downloaded if needed)

### 3. **Configuration Files**
**Location:** `C:\Users\dxyou\ai-clipper\`

- `config.json` - AI and clip settings
- `.env` - Your OpenAI API key (keep this secret!)
- `requirements.txt` - Python dependencies

### 4. **Web Interface Files**
**Location:** `C:\Users\dxyou\ai-clipper\`

- `app.py` - Flask web server
- `templates/` - HTML templates
- `static/` - CSS and JavaScript files

## 🎯 Quick Access

### From Command Line:
```bash
# Go to project directory
cd C:\Users\dxyou\ai-clipper

# View generated clips
dir output

# View downloaded videos
dir downloads
```

### From File Explorer:
1. Open File Explorer
2. Navigate to: `C:\Users\dxyou\ai-clipper\`
3. Open the `output` folder to see your clips

### From Web Interface:
- Clips are automatically available for download
- Click the download button in the web UI
- Files are saved to your browser's default download location

## 💡 Tips

1. **Clean up downloads folder** periodically to save disk space
2. **Backup your output folder** if you want to keep generated clips
3. **The .env file** contains your API key - never share it or commit to Git
4. **Thumbnails** are saved alongside video files in the output folder

## 📊 File Sizes

- **Video clips:** Typically 5-50 MB each (depends on length)
- **Thumbnails:** ~50-200 KB each
- **Downloaded videos:** Can be 100 MB - 2 GB+ (full videos)

## 🔍 Finding Your Files

### Windows Search:
1. Press `Win + S`
2. Search for: `ai-clipper output`
3. Or navigate directly to: `C:\Users\dxyou\ai-clipper\output`

### PowerShell:
```powershell
# List all generated clips
Get-ChildItem "C:\Users\dxyou\ai-clipper\output" -Filter "*.mp4"

# List all thumbnails
Get-ChildItem "C:\Users\dxyou\ai-clipper\output" -Filter "*.jpg"
```

