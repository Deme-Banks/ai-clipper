"""
Flask Web Application for AI Clip Generator
Run with: python app.py
Access at: http://localhost:5000
"""

from flask import Flask, render_template, request, jsonify, send_file, session
from flask_cors import CORS
import os
import json
import threading
import time
from pathlib import Path
from clip_generator import ClipGenerator
from clip_library import ClipLibrary
import uuid

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management
CORS(app)

# Store processing jobs
jobs = {}

# Initialize clip generator and library
generator = ClipGenerator()
library = ClipLibrary()

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/api/process', methods=['POST'])
def process_video():
    """Start video processing (single or batch)"""
    try:
        data = request.json
        url = data.get('url', '').strip()
        urls = data.get('urls', [])  # Batch processing
        formats = data.get('formats', ['tiktok', 'youtube_shorts'])
        
        # Support both single URL and batch URLs
        if urls and isinstance(urls, list):
            # Batch processing
            return process_batch(urls, formats)
        elif url:
            # Single video processing
            if not (url.startswith('http://') or url.startswith('https://')):
                return jsonify({'error': 'Invalid URL format'}), 400
            
            # Create job ID
            job_id = str(uuid.uuid4())
            
            # Initialize job status
            jobs[job_id] = {
                'status': 'processing',
                'progress': 0,
                'message': 'Starting video download...',
                'url': url,
                'formats': formats,
                'output_files': [],
                'error': None,
                'created_at': time.time()
            }
            
            # Start processing in background thread
            thread = threading.Thread(target=process_video_background, args=(job_id, url, formats))
            thread.daemon = True
            thread.start()
            
            return jsonify({
                'job_id': job_id,
                'status': 'processing',
                'message': 'Processing started'
            })
        else:
            return jsonify({'error': 'URL or URLs array is required'}), 400
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def process_batch(urls, formats):
    """Process multiple videos in batch"""
    job_ids = []
    
    for url in urls:
        if not (url.startswith('http://') or url.startswith('https://')):
            continue
        
        job_id = str(uuid.uuid4())
        job_ids.append(job_id)
        
        jobs[job_id] = {
            'status': 'queued',
            'progress': 0,
            'message': 'Waiting in queue...',
            'url': url,
            'formats': formats,
            'output_files': [],
            'error': None,
            'created_at': time.time(),
            'batch_id': job_ids[0]  # First job ID as batch identifier
        }
        
        # Start processing
        thread = threading.Thread(target=process_video_background, args=(job_id, url, formats))
        thread.daemon = True
        thread.start()
    
    return jsonify({
        'batch_id': job_ids[0] if job_ids else None,
        'job_ids': job_ids,
        'count': len(job_ids),
        'message': f'Started processing {len(job_ids)} videos'
    })

def process_video_background(job_id, url, formats):
    """Process video in background thread"""
    try:
        jobs[job_id]['progress'] = 10
        jobs[job_id]['message'] = 'Downloading video...'
        
        # Download video
        video_path = generator.download_video(url)
        if not video_path:
            jobs[job_id]['status'] = 'error'
            jobs[job_id]['error'] = 'Failed to download video'
            return
        
        jobs[job_id]['progress'] = 30
        jobs[job_id]['message'] = 'Extracting transcript...'
        
        # Get transcript
        transcript = generator.get_video_transcript(url)
        
        jobs[job_id]['progress'] = 40
        jobs[job_id]['message'] = 'Analyzing video with AI...'
        
        # Find clips
        clips = generator.find_engaging_clips_ai(video_path, transcript)
        
        if not clips:
            jobs[job_id]['status'] = 'error'
            jobs[job_id]['error'] = 'No engaging clips found'
            return
        
        jobs[job_id]['progress'] = 50
        jobs[job_id]['message'] = f'Found {len(clips)} engaging clips. Creating videos...'
        
        # Create clips
        video_name = Path(video_path).stem
        output_files = []
        
        for i, clip_info in enumerate(clips):
            start = clip_info["start_time"]
            end = clip_info["end_time"]
            
            for format_type in formats:
                output_filename = f"{video_name}_clip{i+1}_{format_type}.mp4"
                output_path = generator.output_dir / output_filename
                
                clip_title = clip_info.get('title', f'Clip {i+1}')
                if generator.create_clip(video_path, start, end, str(output_path), format_type, clip_title):
                    thumbnail_path = generator.output_dir / f"{Path(output_path).stem}.jpg"
                    output_files.append({
                        'filename': output_filename,
                        'path': str(output_path),
                        'format': format_type,
                        'title': clip_title,
                        'reason': clip_info.get('reason', 'Engaging moment'),
                        'thumbnail': str(thumbnail_path) if thumbnail_path.exists() else None,
                        'engagement_score': clip_info.get('engagement_score', 7)
                    })
            
            jobs[job_id]['progress'] = 50 + int((i + 1) / len(clips) * 40)
            jobs[job_id]['message'] = f'Processing clip {i+1}/{len(clips)}...'
        
        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['progress'] = 100
        jobs[job_id]['message'] = f'Successfully created {len(output_files)} clips!'
        jobs[job_id]['output_files'] = output_files
        
        # Save to library
        library.save_job({
            'job_id': job_id,
            'video_url': url,
            'status': 'completed',
            'formats': formats,
            'output_count': len(output_files)
        })
        
        # Save each clip to library
        video_title = Path(video_path).stem
        for file_info in output_files:
            clip_data = {
                'job_id': job_id,
                'video_url': url,
                'video_title': video_title,
                'filename': file_info['filename'],
                'path': file_info['path'],
                'thumbnail': file_info.get('thumbnail'),
                'format': file_info['format'],
                'title': file_info['title'],
                'reason': file_info.get('reason'),
                'engagement_score': file_info.get('engagement_score', 0),
                'start_time': None,  # Could extract from clip_info if needed
                'end_time': None,
                'duration': None,
                'tags': []
            }
            library.save_clip(clip_data)
        
    except Exception as e:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['error'] = str(e)
        jobs[job_id]['message'] = f'Error: {str(e)}'
        
        # Save failed job
        library.save_job({
            'job_id': job_id,
            'video_url': url,
            'status': 'error',
            'formats': formats,
            'output_count': 0
        })

@app.route('/api/status/<job_id>')
def get_status(job_id):
    """Get processing status"""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    return jsonify({
        'status': job['status'],
        'progress': job['progress'],
        'message': job['message'],
        'output_files': job.get('output_files', []),
        'error': job.get('error')
    })

@app.route('/api/download/<job_id>/<filename>')
def download_file(job_id, filename):
    """Download generated clip"""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    if job['status'] != 'completed':
        return jsonify({'error': 'Job not completed'}), 400
    
    # Find the file
    for file_info in job['output_files']:
        if file_info['filename'] == filename:
            file_path = Path(file_info['path'])
            if file_path.exists():
                return send_file(
                    str(file_path),
                    as_attachment=True,
                    download_name=filename
                )
    
    return jsonify({'error': 'File not found'}), 404

@app.route('/api/thumbnail/<job_id>/<filename>')
def get_thumbnail(job_id, filename):
    """Get thumbnail for a clip"""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    
    # Find the file and its thumbnail
    for file_info in job.get('output_files', []):
        if file_info['filename'] == filename and file_info.get('thumbnail'):
            thumb_path = Path(file_info['thumbnail'])
            if thumb_path.exists():
                return send_file(str(thumb_path), mimetype='image/jpeg')
    
    return jsonify({'error': 'Thumbnail not found'}), 404

@app.route('/api/jobs')
def list_jobs():
    """List all jobs"""
    return jsonify({
        'jobs': {job_id: {
            'status': job['status'],
            'progress': job['progress'],
            'message': job['message'],
            'url': job.get('url', ''),
            'created_at': job.get('created_at', time.time())
        } for job_id, job in jobs.items()}
    })

if __name__ == '__main__':
    print("=" * 60)
    print("🎬 AI Clip Generator - Web Interface")
    print("=" * 60)
    print("Starting server...")
    print("Access the application at: http://localhost:5000")
    print("Or on your local network at: http://0.0.0.0:5000")
    print("=" * 60)
    
    # Run on all interfaces (0.0.0.0) to allow network access
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)

