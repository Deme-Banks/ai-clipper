@echo off
REM AI Clip Generator - Quick Run Script for Windows
REM Usage: run_clip_generator.bat <url> [tiktok|youtube_shorts|both]

if "%1"=="" (
    echo Usage: run_clip_generator.bat ^<url^> [tiktok^|youtube_shorts^|both]
    echo Example: run_clip_generator.bat https://www.youtube.com/watch?v=VIDEO_ID
    exit /b 1
)

python clip_generator.py %1 %2
pause
