"""
Flask Web Application for AI Clip Generator
Run with: python app.py
Access at: http://localhost:5000
"""

from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import os
import json
import threading
import time
from pathlib import Path
from clip_generator import ClipGenerator
from clip_library import ClipLibrary
import uuid
from werkzeug.utils import secure_filename

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
        
        # Create clips with parallel processing
        video_name = Path(video_path).stem
        output_files = []
        total_clips = len(clips) * len(formats)
        current_clip = 0
        
        # Prepare all clip tasks
        clip_tasks = []
        for i, clip_info in enumerate(clips):
            start = clip_info["start_time"]
            end = clip_info["end_time"]
            
            for format_type in formats:
                output_filename = f"{video_name}_clip{i+1}_{format_type}.mp4"
                output_path = generator.output_dir / output_filename
                clip_title = clip_info.get('title', f'Clip {i+1}')
                
                clip_tasks.append({
                    'index': len(clip_tasks),
                    'video_path': video_path,
                    'start': start,
                    'end': end,
                    'output_path': str(output_path),
                    'format_type': format_type,
                    'clip_title': clip_title,
                    'output_filename': output_filename,
                    'clip_info': clip_info
                })
        
        # Process clips with limited parallelism (max 2-3 at a time to avoid overwhelming system)
        max_workers = min(3, len(clip_tasks))
        completed = 0
        lock = threading.Lock()
        
        def process_single_clip(task):
            nonlocal completed, current_clip
            try:
                with lock:
                    current_clip += 1
                    progress = 50 + int((current_clip / total_clips) * 40)
                    jobs[job_id]['progress'] = progress
                    jobs[job_id]['message'] = f'Creating clip {current_clip}/{total_clips}: {task["clip_title"]} ({task["format_type"]})...'
                
                if generator.create_clip(task['video_path'], task['start'], task['end'], 
                                       task['output_path'], task['format_type'], task['clip_title']):
                    thumbnail_path = generator.output_dir / f"{Path(task['output_path']).stem}.jpg"
                    
                    # Get file metadata
                    file_size = os.path.getsize(task['output_path']) if os.path.exists(task['output_path']) else 0
                    file_size_mb = file_size / (1024 * 1024)
                    
                    # Get clip duration
                    try:
                        try:
                            from moviepy import VideoFileClip
                        except ImportError:
                            from moviepy.editor import VideoFileClip
                        temp_clip = VideoFileClip(task['output_path'])
                        duration = temp_clip.duration
                        temp_clip.close()
                    except:
                        duration = task['end'] - task['start']
                    
                    file_info = {
                        'filename': task['output_filename'],
                        'path': task['output_path'],
                        'format': task['format_type'],
                        'title': task['clip_title'],
                        'reason': task['clip_info'].get('reason', 'Engaging moment'),
                        'thumbnail': str(thumbnail_path) if thumbnail_path.exists() else None,
                        'engagement_score': task['clip_info'].get('engagement_score', 7),
                        'file_size': file_size,
                        'file_size_mb': round(file_size_mb, 2),
                        'duration': round(duration, 2)
                    }
                    
                    with lock:
                        output_files.append(file_info)
                        completed += 1
                    
                    return True
                return False
            except Exception as e:
                print(f"Error processing clip {task['clip_title']}: {e}")
                return False
        
        # Process clips in parallel using threading
        threads = []
        task_index = 0
        
        while task_index < len(clip_tasks) or any(t.is_alive() for t in threads):
            # Start new threads up to max_workers
            while len(threads) < max_workers and task_index < len(clip_tasks):
                task = clip_tasks[task_index]
                thread = threading.Thread(target=process_single_clip, args=(task,))
                thread.daemon = True
                thread.start()
                threads.append(thread)
                task_index += 1
            
            # Remove completed threads
            threads = [t for t in threads if t.is_alive()]
            
            # Small delay to prevent CPU spinning
            time.sleep(0.1)
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
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
    """Download generated clip (or stream for preview)"""
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
                # Check if it's a preview request (Range header for video streaming)
                if request.headers.get('Range'):
                    return send_file(
                        str(file_path),
                        mimetype='video/mp4',
                        as_attachment=False,
                        conditional=True
                    )
                else:
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

# Clip Library API Endpoints
@app.route('/api/library/clips')
def get_library_clips():
    """Get clips from library with optional filters"""
    format_type = request.args.get('format')
    search = request.args.get('search')
    min_score = request.args.get('min_score', type=float)
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    clips = library.get_clips(
        limit=limit,
        offset=offset,
        format_type=format_type,
        search=search,
        min_score=min_score
    )
    
    return jsonify({
        'clips': clips,
        'count': len(clips),
        'limit': limit,
        'offset': offset
    })

@app.route('/api/library/clip/<int:clip_id>')
def get_library_clip(clip_id):
    """Get a specific clip from library"""
    clip = library.get_clip_by_id(clip_id)
    if clip:
        library.increment_views(clip_id)
        return jsonify(clip)
    return jsonify({'error': 'Clip not found'}), 404

@app.route('/api/library/statistics')
def get_library_stats():
    """Get library statistics"""
    stats = library.get_statistics()
    return jsonify(stats)

@app.route('/api/library/clip/<int:clip_id>/download')
def download_library_clip(clip_id):
    """Download a clip from library (or stream for preview)"""
    clip = library.get_clip_by_id(clip_id)
    if not clip:
        return jsonify({'error': 'Clip not found'}), 404
    
    file_path = Path(clip['clip_path'])
    if file_path.exists():
        # Check if it's a preview request (Range header for video streaming)
        if request.headers.get('Range'):
            return send_file(
                str(file_path),
                mimetype='video/mp4',
                as_attachment=False,
                conditional=True
            )
        else:
            library.increment_downloads(clip_id)
            return send_file(
                str(file_path),
                as_attachment=True,
                download_name=clip['clip_filename']
            )
    return jsonify({'error': 'File not found'}), 404

@app.route('/api/library/clip/<int:clip_id>', methods=['DELETE'])
def delete_library_clip(clip_id):
    """Delete a clip from library"""
    if library.delete_clip(clip_id):
        return jsonify({'message': 'Clip deleted successfully'})
    return jsonify({'error': 'Clip not found'}), 404

# Clip Editing API Endpoints
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/upload', methods=['POST'])
def upload_video():
    """Upload a video file for editing"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    format_type = request.form.get('format', 'tiktok')
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Allowed: mp4, avi, mov, mkv, webm, flv'}), 400
    
    try:
        # Save uploaded file
        filename = secure_filename(file.filename)
        upload_dir = Path("uploads")
        upload_dir.mkdir(exist_ok=True)
        
        upload_path = upload_dir / filename
        file.save(str(upload_path))
        
        # Process the video
        output_filename = f"edited_{Path(filename).stem}.mp4"
        output_path = generator.output_dir / output_filename
        
        if generator.process_uploaded_video(str(upload_path), str(output_path), format_type):
            # Save to library
            clip_data = {
                'job_id': str(uuid.uuid4()),
                'video_url': f'uploaded:{filename}',
                'video_title': Path(filename).stem,
                'filename': output_filename,
                'path': str(output_path),
                'thumbnail': None,
                'format': format_type,
                'title': f'Edited: {Path(filename).stem}',
                'reason': 'Uploaded and processed video',
                'engagement_score': 0,
                'start_time': None,
                'end_time': None,
                'duration': None,
                'tags': []
            }
            clip_id = library.save_clip(clip_data)
            
            return jsonify({
                'message': 'Video uploaded and processed successfully',
                'clip_id': clip_id,
                'filename': output_filename,
                'path': str(output_path)
            })
        else:
            return jsonify({'error': 'Failed to process video'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/edit', methods=['POST'])
def edit_clip():
    """Edit an existing clip"""
    try:
        data = request.json
        video_path = data.get('video_path')
        clip_id = data.get('clip_id')  # Optional: if editing from library
        
        if not video_path:
            # Try to get from clip_id
            if clip_id:
                clip = library.get_clip_by_id(clip_id)
                if clip:
                    video_path = clip['clip_path']
                else:
                    return jsonify({'error': 'Clip not found'}), 404
            else:
                return jsonify({'error': 'video_path or clip_id required'}), 400
        
        if not os.path.exists(video_path):
            return jsonify({'error': 'Video file not found'}), 404
        
        # Get edit parameters
        trim_start = data.get('trim_start')
        trim_end = data.get('trim_end')
        speed = data.get('speed')
        text_overlay = data.get('text_overlay')
        filters = data.get('filters')
        format_type = data.get('format', 'tiktok')
        
        # Generate output filename
        input_path = Path(video_path)
        output_filename = f"edited_{input_path.stem}.mp4"
        output_path = generator.output_dir / output_filename
        
        # Edit the clip
        if generator.edit_clip(
            video_path,
            str(output_path),
            trim_start=trim_start,
            trim_end=trim_end,
            speed=speed,
            text_overlay=text_overlay,
            format_type=format_type,
            filters=filters
        ):
            # Save edited clip to library
            clip_data = {
                'job_id': str(uuid.uuid4()),
                'video_url': data.get('video_url', f'edited:{input_path.name}'),
                'video_title': input_path.stem,
                'filename': output_filename,
                'path': str(output_path),
                'thumbnail': None,
                'format': format_type,
                'title': data.get('title', f'Edited: {input_path.stem}'),
                'reason': data.get('reason', 'Edited clip'),
                'engagement_score': 0,
                'start_time': trim_start,
                'end_time': trim_end,
                'duration': (trim_end - trim_start) if (trim_start and trim_end) else None,
                'tags': []
            }
            edited_clip_id = library.save_clip(clip_data)
            
            return jsonify({
                'message': 'Clip edited successfully',
                'clip_id': edited_clip_id,
                'filename': output_filename,
                'path': str(output_path)
            })
        else:
            return jsonify({'error': 'Failed to edit clip'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/clip/info', methods=['POST'])
def get_clip_info():
    """Get information about a video clip (duration, dimensions, etc.)"""
    try:
        data = request.json
        video_path = data.get('video_path')
        clip_id = data.get('clip_id')
        
        if not video_path:
            if clip_id:
                clip = library.get_clip_by_id(clip_id)
                if clip:
                    video_path = clip['clip_path']
                else:
                    return jsonify({'error': 'Clip not found'}), 404
            else:
                return jsonify({'error': 'video_path or clip_id required'}), 400
        
        if not os.path.exists(video_path):
            return jsonify({'error': 'Video file not found'}), 404
        
        # Load video to get info
        # Import VideoFileClip from clip_generator (it's already imported there)
        from moviepy import VideoFileClip
        try:
            clip = VideoFileClip(video_path)
        except ImportError:
            from moviepy.editor import VideoFileClip
            clip = VideoFileClip(video_path)
        
        info = {
            'duration': clip.duration,
            'fps': clip.fps,
            'width': clip.w,
            'height': clip.h,
            'size': os.path.getsize(video_path),
            'has_audio': clip.audio is not None
        }
        
        clip.close()
        
        return jsonify(info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

