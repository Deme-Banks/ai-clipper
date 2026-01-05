let currentJobId = null;
let statusInterval = null;

document.getElementById('videoForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const url = document.getElementById('videoUrl').value.trim();
    const formatCheckboxes = document.querySelectorAll('input[name="formats"]:checked');
    const formats = Array.from(formatCheckboxes).map(cb => cb.value);
    
    if (formats.length === 0) {
        alert('Please select at least one output format');
        return;
    }
    
    // Hide previous results/errors
    document.getElementById('resultsSection').style.display = 'none';
    document.getElementById('errorSection').style.display = 'none';
    
    // Show progress
    document.getElementById('progressSection').style.display = 'block';
    updateProgress(0, 'Starting...');
    
    // Disable form
    const submitBtn = document.getElementById('submitBtn');
    submitBtn.disabled = true;
    document.getElementById('btnText').textContent = 'Processing...';
    document.getElementById('btnLoader').style.display = 'inline-block';
    
    try {
        const response = await fetch('/api/process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                url: url,
                formats: formats
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to start processing');
        }
        
        currentJobId = data.job_id;
        startStatusPolling(currentJobId);
        
    } catch (error) {
        showError(error.message);
        resetForm();
    }
});

function startStatusPolling(jobId) {
    if (statusInterval) {
        clearInterval(statusInterval);
    }
    
    statusInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/status/${jobId}`);
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Failed to get status');
            }
            
            updateProgress(data.progress, data.message);
            
            if (data.status === 'completed') {
                clearInterval(statusInterval);
                statusInterval = null;
                showResults(data.output_files);
                resetForm();
            } else if (data.status === 'error') {
                clearInterval(statusInterval);
                statusInterval = null;
                showError(data.error || 'An error occurred during processing');
                resetForm();
            }
            
        } catch (error) {
            clearInterval(statusInterval);
            statusInterval = null;
            showError(error.message);
            resetForm();
        }
    }, 2000); // Poll every 2 seconds
}

function updateProgress(progress, message) {
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    
    progressFill.style.width = `${progress}%`;
    progressFill.textContent = `${progress}%`;
    progressText.textContent = message;
}

function showResults(outputFiles) {
    const resultsSection = document.getElementById('resultsSection');
    const clipsList = document.getElementById('clipsList');
    
    clipsList.innerHTML = '';
    
    if (outputFiles.length === 0) {
        clipsList.innerHTML = '<p>No clips were generated.</p>';
        return;
    }
    
    outputFiles.forEach((file, index) => {
        const clipItem = document.createElement('div');
        clipItem.className = 'clip-item';
        
        const formatEmoji = file.format === 'tiktok' ? '📱' : '🎯';
        const formatName = file.format === 'tiktok' ? 'TikTok' : 'YouTube Shorts';
        const engagementScore = file.engagement_score || 0;
        const scoreStars = '⭐'.repeat(Math.min(5, Math.floor(engagementScore / 2)));
        
        // Thumbnail image
        const thumbnailUrl = file.thumbnail ? `/api/thumbnail/${currentJobId}/${file.filename}` : '';
        
        clipItem.innerHTML = `
            ${thumbnailUrl ? `
            <div class="clip-thumbnail">
                <img src="${thumbnailUrl}" alt="Clip thumbnail" onerror="this.style.display='none'">
            </div>
            ` : ''}
            <div class="clip-info">
                <div class="clip-title">${formatEmoji} ${file.title || `Clip ${index + 1}`}</div>
                <div class="clip-details">Format: ${formatName} • ${file.filename}</div>
                ${file.reason ? `<div class="clip-reason">${file.reason}</div>` : ''}
                ${engagementScore > 0 ? `<div class="clip-score">Viral Score: ${scoreStars} (${engagementScore}/10)</div>` : ''}
            </div>
            <div class="clip-actions">
                <a href="/api/download/${currentJobId}/${file.filename}" class="btn-download" download>
                    ⬇️ Download
                </a>
            </div>
        `;
        
        clipsList.appendChild(clipItem);
    });
    
    resultsSection.style.display = 'block';
    document.getElementById('progressSection').style.display = 'none';
}

function showError(message) {
    const errorSection = document.getElementById('errorSection');
    const errorMessage = document.getElementById('errorMessage');
    
    errorMessage.textContent = message;
    errorSection.style.display = 'block';
    document.getElementById('progressSection').style.display = 'none';
}

function resetForm() {
    const submitBtn = document.getElementById('submitBtn');
    submitBtn.disabled = false;
    document.getElementById('btnText').textContent = '🚀 Generate Clips';
    document.getElementById('btnLoader').style.display = 'none';
}

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    if (statusInterval) {
        clearInterval(statusInterval);
    }
});

// Tab Management
function showTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
        tab.style.display = 'none';
    });
    
    // Remove active class from all buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab
    const tab = document.getElementById(tabName + 'Tab');
    if (tab) {
        tab.classList.add('active');
        tab.style.display = 'block';
    }
    
    // Add active class to button
    event.target.classList.add('active');
    
    // Load library if switching to library tab
    if (tabName === 'library') {
        loadLibrary();
    }
}

// Library Functions
let librarySearchTimeout;

document.getElementById('librarySearch')?.addEventListener('input', (e) => {
    clearTimeout(librarySearchTimeout);
    librarySearchTimeout = setTimeout(() => {
        loadLibrary();
    }, 500);
});

document.getElementById('formatFilter')?.addEventListener('change', () => {
    loadLibrary();
});

async function loadLibrary() {
    const search = document.getElementById('librarySearch')?.value || '';
    const format = document.getElementById('formatFilter')?.value || '';
    
    try {
        // Load statistics
        const statsResponse = await fetch('/api/library/statistics');
        const stats = await statsResponse.json();
        displayLibraryStats(stats);
        
        // Load clips
        const params = new URLSearchParams();
        if (search) params.append('search', search);
        if (format) params.append('format', format);
        params.append('limit', '50');
        
        const clipsResponse = await fetch(`/api/library/clips?${params}`);
        const data = await clipsResponse.json();
        displayLibraryClips(data.clips);
        
    } catch (error) {
        console.error('Error loading library:', error);
    }
}

function displayLibraryStats(stats) {
    const statsDiv = document.getElementById('libraryStats');
    if (!statsDiv) return;
    
    statsDiv.innerHTML = `
        <div class="stat-card">
            <div class="stat-value">${stats.total_clips || 0}</div>
            <div class="stat-label">Total Clips</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${stats.total_views || 0}</div>
            <div class="stat-label">Total Views</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${stats.total_downloads || 0}</div>
            <div class="stat-label">Total Downloads</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${(stats.avg_engagement || 0).toFixed(1)}</div>
            <div class="stat-label">Avg Engagement</div>
        </div>
    `;
}

function displayLibraryClips(clips) {
    const clipsDiv = document.getElementById('libraryClips');
    if (!clipsDiv) return;
    
    if (clips.length === 0) {
        clipsDiv.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">No clips found. Create some clips to see them here!</p>';
        return;
    }
    
    clipsDiv.innerHTML = clips.map(clip => {
        const formatEmoji = clip.format_type === 'tiktok' ? '📱' : '🎯';
        const scoreStars = '⭐'.repeat(Math.min(5, Math.floor((clip.engagement_score || 0) / 2)));
        const thumbnailUrl = clip.thumbnail_path ? `/api/thumbnail/${clip.job_id}/${clip.clip_filename}` : '';
        
        return `
            <div class="clip-item">
                ${thumbnailUrl ? `
                <div class="clip-thumbnail">
                    <img src="${thumbnailUrl}" alt="Clip thumbnail" onerror="this.style.display='none'">
                </div>
                ` : ''}
                <div class="clip-info">
                    <div class="clip-title">${formatEmoji} ${clip.clip_title || 'Untitled'}</div>
                    <div class="clip-details">${clip.video_title || 'Unknown'} • ${clip.format_type}</div>
                    ${clip.reason ? `<div class="clip-reason">${clip.reason}</div>` : ''}
                    ${clip.engagement_score > 0 ? `<div class="clip-score">Score: ${scoreStars} (${clip.engagement_score}/10)</div>` : ''}
                    <div class="clip-meta">Views: ${clip.views || 0} • Downloads: ${clip.downloads || 0}</div>
                </div>
                <div class="clip-actions">
                    <a href="/api/library/clip/${clip.id}/download" class="btn-download" download>
                        ⬇️ Download
                    </a>
                    <button onclick="deleteClip(${clip.id})" class="btn-delete">🗑️ Delete</button>
                </div>
            </div>
        `;
    }).join('');
}

async function deleteClip(clipId) {
    if (!confirm('Are you sure you want to delete this clip?')) return;
    
    try {
        const response = await fetch(`/api/library/clip/${clipId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadLibrary();
        } else {
            alert('Failed to delete clip');
        }
    } catch (error) {
        console.error('Error deleting clip:', error);
        alert('Error deleting clip');
    }
}

