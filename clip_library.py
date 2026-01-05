"""
Clip Library - Store and manage generated clips with metadata
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import os

class ClipLibrary:
    def __init__(self, db_path: str = "clip_library.db"):
        """Initialize the clip library database"""
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Create database tables if they don't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Clips table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                video_url TEXT NOT NULL,
                video_title TEXT,
                clip_filename TEXT NOT NULL,
                clip_path TEXT NOT NULL,
                thumbnail_path TEXT,
                format_type TEXT NOT NULL,
                clip_title TEXT,
                reason TEXT,
                engagement_score REAL,
                start_time REAL,
                end_time REAL,
                duration REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tags TEXT,
                views INTEGER DEFAULT 0,
                downloads INTEGER DEFAULT 0
            )
        ''')
        
        # Jobs table for tracking processing
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT UNIQUE NOT NULL,
                video_url TEXT NOT NULL,
                status TEXT NOT NULL,
                formats TEXT,
                output_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_clip(self, clip_data: Dict) -> int:
        """Save a clip to the library"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO clips (
                job_id, video_url, video_title, clip_filename, clip_path,
                thumbnail_path, format_type, clip_title, reason,
                engagement_score, start_time, end_time, duration, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            clip_data.get('job_id'),
            clip_data.get('video_url'),
            clip_data.get('video_title'),
            clip_data.get('filename'),
            clip_data.get('path'),
            clip_data.get('thumbnail'),
            clip_data.get('format'),
            clip_data.get('title'),
            clip_data.get('reason'),
            clip_data.get('engagement_score', 0),
            clip_data.get('start_time'),
            clip_data.get('end_time'),
            clip_data.get('duration'),
            json.dumps(clip_data.get('tags', []))
        ))
        
        clip_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return clip_id
    
    def save_job(self, job_data: Dict):
        """Save job information"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO jobs (
                job_id, video_url, status, formats, output_count, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            job_data.get('job_id'),
            job_data.get('video_url'),
            job_data.get('status'),
            json.dumps(job_data.get('formats', [])),
            job_data.get('output_count', 0),
            datetime.now().isoformat() if job_data.get('status') == 'completed' else None
        ))
        
        conn.commit()
        conn.close()
    
    def get_clips(self, limit: int = 50, offset: int = 0, 
                  format_type: Optional[str] = None,
                  search: Optional[str] = None,
                  min_score: Optional[float] = None,
                  max_score: Optional[float] = None,
                  date_from: Optional[str] = None,
                  date_to: Optional[str] = None,
                  sort_by: str = "created_at",
                  sort_order: str = "DESC") -> List[Dict]:
        """Get clips with optional filtering and sorting"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM clips WHERE 1=1"
        params = []
        
        if format_type:
            query += " AND format_type = ?"
            params.append(format_type)
        
        if search:
            query += " AND (clip_title LIKE ? OR reason LIKE ? OR video_title LIKE ?)"
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])
        
        if min_score is not None:
            query += " AND engagement_score >= ?"
            params.append(min_score)
        
        if max_score is not None:
            query += " AND engagement_score <= ?"
            params.append(max_score)
        
        if date_from:
            query += " AND DATE(created_at) >= ?"
            params.append(date_from)
        
        if date_to:
            query += " AND DATE(created_at) <= ?"
            params.append(date_to)
        
        # Validate sort_by to prevent SQL injection
        valid_sort_fields = ["created_at", "engagement_score", "views", "downloads", "duration", "clip_title"]
        if sort_by not in valid_sort_fields:
            sort_by = "created_at"
        
        # Validate sort_order
        if sort_order.upper() not in ["ASC", "DESC"]:
            sort_order = "DESC"
        
        query += f" ORDER BY {sort_by} {sort_order} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        clips = []
        for row in rows:
            clip = dict(row)
            clip['tags'] = json.loads(clip.get('tags', '[]'))
            clips.append(clip)
        
        conn.close()
        return clips
    
    def get_clip_by_id(self, clip_id: int) -> Optional[Dict]:
        """Get a specific clip by ID"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM clips WHERE id = ?", (clip_id,))
        row = cursor.fetchone()
        
        if row:
            clip = dict(row)
            clip['tags'] = json.loads(clip.get('tags', '[]'))
            conn.close()
            return clip
        
        conn.close()
        return None
    
    def increment_views(self, clip_id: int):
        """Increment view count for a clip"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE clips SET views = views + 1 WHERE id = ?", (clip_id,))
        conn.commit()
        conn.close()
    
    def increment_downloads(self, clip_id: int):
        """Increment download count for a clip"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE clips SET downloads = downloads + 1 WHERE id = ?", (clip_id,))
        conn.commit()
        conn.close()
    
    def delete_clip(self, clip_id: int) -> bool:
        """Delete a clip from the library"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get clip path first
        cursor.execute("SELECT clip_path FROM clips WHERE id = ?", (clip_id,))
        row = cursor.fetchone()
        
        if row:
            clip_path = row[0]
            # Delete file if it exists
            if os.path.exists(clip_path):
                try:
                    os.remove(clip_path)
                except:
                    pass
            
            # Delete from database
            cursor.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
            conn.commit()
            conn.close()
            return True
        
        conn.close()
        return False
    
    def get_statistics(self) -> Dict:
        """Get library statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {}
        
        # Total clips
        cursor.execute("SELECT COUNT(*) FROM clips")
        stats['total_clips'] = cursor.fetchone()[0]
        
        # Clips by format
        cursor.execute("SELECT format_type, COUNT(*) FROM clips GROUP BY format_type")
        stats['by_format'] = dict(cursor.fetchall())
        
        # Average engagement score
        cursor.execute("SELECT AVG(engagement_score) FROM clips WHERE engagement_score > 0")
        stats['avg_engagement'] = cursor.fetchone()[0] or 0
        
        # Total views and downloads
        cursor.execute("SELECT SUM(views), SUM(downloads) FROM clips")
        row = cursor.fetchone()
        stats['total_views'] = row[0] or 0
        stats['total_downloads'] = row[1] or 0
        
        conn.close()
        return stats

