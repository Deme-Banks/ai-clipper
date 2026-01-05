let currentJobId = null;
let statusInterval = null;

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

function initializeApp() {
    // Initialize video form
    const videoForm = document.getElementById('videoForm');
    if (videoForm) {
        videoForm.addEventListener('submit', async (e) => {
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
    }

function startStatusPolling(jobId) {
    if (statusInterval) {
        clearInterval(statusInterval);
    }
    
    // Reset progress tracking
    progressStartTime = null;
    lastProgress = 0;
    
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
                // Auto-refresh library if on library tab
                if (document.getElementById('libraryTab')?.classList.contains('active')) {
                    setTimeout(() => loadLibrary(), 1000);
                }
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

let progressStartTime = null;
let lastProgress = 0;

function updateProgress(progress, message) {
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const detailedProgress = document.getElementById('detailedProgress');
    const currentClipInfo = document.getElementById('currentClipInfo');
    const estimatedTime = document.getElementById('estimatedTime');
    
    if (progressFill) {
        progressFill.style.width = `${progress}%`;
    }
    if (progressText) {
        progressText.textContent = message;
    }
    
    // Track progress for time estimation
    if (progressStartTime === null && progress > 0) {
        progressStartTime = Date.now();
    }
    
    // Show detailed progress if available
    if (detailedProgress && progress > 0 && progress < 100) {
        detailedProgress.style.display = 'block';
        
        // Estimate time remaining
        if (progress > lastProgress && progressStartTime) {
            const elapsed = (Date.now() - progressStartTime) / 1000; // seconds
            const rate = progress / elapsed; // % per second
            const remaining = (100 - progress) / rate; // seconds remaining
            
            if (remaining > 0 && remaining < 3600) { // Less than 1 hour
                const minutes = Math.floor(remaining / 60);
                const seconds = Math.floor(remaining % 60);
                estimatedTime.textContent = `Estimated time remaining: ${minutes}m ${seconds}s`;
            }
        }
        lastProgress = progress;
    } else if (detailedProgress && progress >= 100) {
        detailedProgress.style.display = 'none';
        progressStartTime = null;
        lastProgress = 0;
    }
}

function showResults(outputFiles) {
    const resultsSection = document.getElementById('resultsSection');
    const clipsList = document.getElementById('clipsList');
    
    // Show loading skeletons while processing
    clipsList.innerHTML = Array(Math.min(outputFiles.length || 3, 6)).fill(0).map(() => `
        <div class="clip-card skeleton-card">
            <div class="skeleton skeleton-thumbnail" style="margin-bottom: 10px;"></div>
            <div class="skeleton skeleton-text"></div>
            <div class="skeleton skeleton-text short"></div>
        </div>
    `).join('');
    
    // Small delay for better UX
    setTimeout(() => {
        clipsList.innerHTML = '';
        
        if (outputFiles.length === 0) {
            clipsList.innerHTML = `
                <div style="text-align: center; padding: 40px; grid-column: 1 / -1;">
                    <div style="font-size: 48px; margin-bottom: 20px;">⚠️</div>
                    <h3 style="color: var(--text-primary); margin-bottom: 10px;">No clips were generated</h3>
                    <p style="color: var(--text-secondary);">Try a different video or adjust your settings.</p>
                </div>
            `;
            return;
        }
    
    // Show bulk actions
    const bulkActions = document.getElementById('bulkActions');
    if (bulkActions) {
        bulkActions.style.display = 'flex';
    }
    
    outputFiles.forEach((file, index) => {
        const clipCard = document.createElement('div');
        clipCard.className = 'clip-card';
        clipCard.dataset.filename = file.filename;
        clipCard.dataset.path = file.path;
        
        const formatEmoji = file.format === 'tiktok' ? '🎵' : '📺';
        const formatName = file.format === 'tiktok' ? 'TikTok' : 'YouTube Shorts';
        const thumbnailUrl = file.thumbnail ? `/api/thumbnail/${currentJobId}/${file.filename}` : '';
        
        // Format file size
        const fileSize = file.file_size_mb ? `${file.file_size_mb} MB` : 'Unknown';
        const duration = file.duration ? formatDuration(file.duration) : 'Unknown';
        
        clipCard.innerHTML = `
            <input type="checkbox" class="clip-checkbox" onchange="updateSelectedCount()" data-filename="${file.filename}">
            <div class="clip-thumbnail">
                ${thumbnailUrl ? `<img src="${thumbnailUrl}" alt="Clip thumbnail" onerror="this.style.display='none'">` : ''}
            </div>
            <div class="clip-card-info">
                <div class="clip-card-title">${formatEmoji} ${file.title || `Clip ${index + 1}`}</div>
                <div class="clip-card-subtitle">${formatName}</div>
                <div class="clip-metadata">
                    <div class="clip-metadata-item">
                        <span>⏱️</span>
                        <span>${duration}</span>
                    </div>
                    <div class="clip-metadata-item">
                        <span>💾</span>
                        <span>${fileSize}</span>
                    </div>
                    ${file.engagement_score ? `
                    <div class="clip-metadata-item">
                        <span>⭐</span>
                        <span>${file.engagement_score}/10</span>
                    </div>
                    ` : ''}
                </div>
                <div class="clip-card-actions">
                    <button onclick="previewClip('${currentJobId}', '${file.filename}', '${file.title || `Clip ${index + 1}`}')" class="btn-preview" style="flex: 1; padding: 8px; font-size: 12px;">
                        🎬 Preview
                    </button>
                    <a href="/api/download/${currentJobId}/${file.filename}" class="btn-download" download style="flex: 1; padding: 8px; font-size: 12px; text-align: center;">
                        💾 Download
                    </a>
                </div>
            </div>
        `;
        
        clipsList.appendChild(clipCard);
    });
    
        resultsSection.style.display = 'block';
        document.getElementById('progressSection').style.display = 'none';
        updateSelectedCount();
    }, 300); // Small delay for smooth transition
}

function formatDuration(seconds) {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Bulk Operations
function selectAllClips() {
    document.querySelectorAll('.clip-checkbox').forEach(cb => {
        cb.checked = true;
        cb.closest('.clip-card').classList.add('selected');
    });
    updateSelectedCount();
}

function deselectAllClips() {
    document.querySelectorAll('.clip-checkbox').forEach(cb => {
        cb.checked = false;
        cb.closest('.clip-card').classList.remove('selected');
    });
    updateSelectedCount();
}

function updateSelectedCount() {
    const checkboxes = document.querySelectorAll('.clip-checkbox:checked');
    const count = checkboxes.length;
    const countEl = document.getElementById('selectedCount');
    
    if (countEl) {
        countEl.textContent = `${count} selected`;
    }
    
    // Update card selected state
    document.querySelectorAll('.clip-card').forEach(card => {
        const checkbox = card.querySelector('.clip-checkbox');
        if (checkbox && checkbox.checked) {
            card.classList.add('selected');
        } else {
            card.classList.remove('selected');
        }
    });
}

async function bulkDownload() {
    const checkboxes = document.querySelectorAll('.clip-checkbox:checked');
    if (checkboxes.length === 0) {
        alert('Please select at least one clip to download');
        return;
    }
    
    // Download each selected clip
    checkboxes.forEach((cb, index) => {
        const filename = cb.dataset.filename;
        setTimeout(() => {
            const link = document.createElement('a');
            link.href = `/api/download/${currentJobId}/${filename}`;
            link.download = filename;
            link.click();
        }, index * 200); // Stagger downloads
    });
}

async function bulkDelete() {
    const checkboxes = document.querySelectorAll('.clip-checkbox:checked');
    if (checkboxes.length === 0) {
        alert('Please select at least one clip to delete');
        return;
    }
    
    // Enhanced confirmation
    const confirmed = confirm(
        `🗑️ Delete ${checkboxes.length} Clip(s)\n\n` +
        `Are you sure you want to delete ${checkboxes.length} selected clip(s)?\n\n` +
        'This action cannot be undone.'
    );
    
    if (!confirmed) return;
    
    // Delete each selected clip
    const filenames = Array.from(checkboxes).map(cb => cb.dataset.filename);
    let deleted = 0;
    let failed = 0;
    
    // Show loading state
    const bulkActions = document.getElementById('bulkActions');
    const originalHTML = bulkActions.innerHTML;
    bulkActions.innerHTML = '<span style="color: var(--text-secondary);">Deleting...</span>';
    
    // Note: This would need a delete endpoint for job clips
    // For now, show a message
    alert(`Bulk delete for ${checkboxes.length} clip(s) - would need delete endpoint implementation`);
    
    // Reset UI
    bulkActions.innerHTML = originalHTML;
    deselectAllClips();
}

function showError(message) {
    const errorSection = document.getElementById('errorSection');
    const errorMessage = document.getElementById('errorMessage');
    
    // Enhanced error messages with suggestions
    let errorHTML = `<strong>${message}</strong>`;
    
    if (message.includes('download') || message.includes('Download')) {
        errorHTML += '<p style="margin-top: 10px; font-size: 14px;">💡 Suggestions:</p>';
        errorHTML += '<ul style="margin-left: 20px; margin-top: 5px;">';
        errorHTML += '<li>Check your internet connection</li>';
        errorHTML += '<li>Verify the URL is correct and accessible</li>';
        errorHTML += '<li>Some videos may have download restrictions</li>';
        errorHTML += '</ul>';
    } else if (message.includes('OpenAI') || message.includes('API')) {
        errorHTML += '<p style="margin-top: 10px; font-size: 14px;">💡 The tool will use heuristic detection instead.</p>';
    } else if (message.includes('FFmpeg') || message.includes('codec')) {
        errorHTML += '<p style="margin-top: 10px; font-size: 14px;">💡 Make sure FFmpeg is installed and in your PATH.</p>';
    } else if (message.includes('No clips found')) {
        errorHTML += '<p style="margin-top: 10px; font-size: 14px;">💡 Try a different video or adjust clip settings in config.json</p>';
    }
    
    errorMessage.innerHTML = errorHTML;
    errorSection.style.display = 'block';
    document.getElementById('progressSection').style.display = 'none';
}

function resetForm() {
    const submitBtn = document.getElementById('submitBtn');
    submitBtn.disabled = false;
    document.getElementById('btnText').textContent = '⚡ Generate Clips';
    document.getElementById('btnLoader').style.display = 'none';
}

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    if (statusInterval) {
        clearInterval(statusInterval);
    }
});

// Tab Management - Make it globally accessible
window.showTab = function(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
        tab.style.display = 'none';
    });
    
    // Remove active class from all nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    
    // Show selected tab
    const tab = document.getElementById(tabName + 'Tab');
    if (tab) {
        tab.classList.add('active');
        tab.style.display = 'block';
    }
    
    // Add active class to nav item
    const navItems = document.querySelectorAll('.nav-item');
    if (tabName === 'create') navItems[0]?.classList.add('active');
    if (tabName === 'library') navItems[1]?.classList.add('active');
    if (tabName === 'edit') navItems[2]?.classList.add('active');
    
    // Load library if switching to library tab
    if (tabName === 'library') {
        loadLibrary();
    }
    
    // Load clips for editing if switching to edit tab
    if (tabName === 'edit') {
        loadLibraryClipsForEdit();
    }
}

// Library Functions
let librarySearchTimeout;

// Initialize library search after DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
        initializeLibrarySearch();
    });
} else {
    initializeLibrarySearch();
}

function initializeLibrarySearch() {
    const librarySearch = document.getElementById('librarySearch');
    const formatFilter = document.getElementById('formatFilter');
    
    if (librarySearch) {
        librarySearch.addEventListener('input', (e) => {
            clearTimeout(librarySearchTimeout);
            librarySearchTimeout = setTimeout(() => {
                loadLibrary();
            }, 500);
        });
    }
    
    if (formatFilter) {
        formatFilter.addEventListener('change', () => {
            loadLibrary();
        });
    }
}

async function loadLibrary() {
    const search = document.getElementById('librarySearch')?.value || '';
    const format = document.getElementById('formatFilter')?.value || '';
    const clipsDiv = document.getElementById('libraryClips');
    
    // Show loading skeletons
    if (clipsDiv) {
        clipsDiv.innerHTML = Array(6).fill(0).map(() => `
            <div class="clip-card skeleton-card">
                <div class="skeleton skeleton-thumbnail" style="margin-bottom: 10px;"></div>
                <div class="skeleton skeleton-text"></div>
                <div class="skeleton skeleton-text short"></div>
            </div>
        `).join('');
    }
    
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
        if (clipsDiv) {
            clipsDiv.innerHTML = `
                <div style="text-align: center; grid-column: 1 / -1; padding: 40px;">
                    <div style="font-size: 48px; margin-bottom: 20px;">⚠️</div>
                    <h3 style="color: var(--text-primary); margin-bottom: 10px;">Error loading library</h3>
                    <p style="color: var(--text-secondary); margin-bottom: 20px;">${error.message || 'Please try again'}</p>
                    <button onclick="loadLibrary()" class="btn btn-primary" style="width: auto; padding: 12px 24px;">
                        🔄 Retry
                    </button>
                </div>
            `;
        }
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
        clipsDiv.innerHTML = `
            <div style="text-align: center; grid-column: 1 / -1; padding: 40px;">
                <div style="font-size: 48px; margin-bottom: 20px;">📦</div>
                <h3 style="color: var(--text-primary); margin-bottom: 10px;">No clips found</h3>
                <p style="color: var(--text-secondary); margin-bottom: 20px;">Create some clips to see them here!</p>
                <button onclick="showTab('create')" class="btn btn-primary" style="width: auto; padding: 12px 24px;">
                    ✨ Create Your First Clip
                </button>
            </div>
        `;
        return;
    }
    
    clipsDiv.innerHTML = clips.map(clip => {
        const formatEmoji = clip.format_type === 'tiktok' ? '🎵' : '📺';
        const thumbnailUrl = clip.thumbnail_path ? `/api/thumbnail/${clip.job_id}/${clip.clip_filename}` : '';
        
        // Format metadata
        let fileSize = 'Unknown';
        let duration = 'Unknown';
        
        // Try to get file size
        if (clip.clip_path) {
            try {
                const size = new Blob([clip.clip_path]).size; // This won't work, need actual file
                // We'll fetch this from the API if needed
            } catch (e) {}
        }
        
        if (clip.duration) {
            duration = formatDuration(clip.duration);
        }
        
        // Format date
        let dateStr = '';
        if (clip.created_at) {
            try {
                const date = new Date(clip.created_at);
                dateStr = date.toLocaleDateString();
            } catch (e) {}
        }
        
        return `
            <div class="clip-card" onclick="previewLibraryClip(${clip.id}, '${clip.clip_title || 'Untitled'}')">
                <div class="clip-thumbnail">
                    ${thumbnailUrl ? `<img src="${thumbnailUrl}" alt="Clip thumbnail" onerror="this.style.display='none'">` : ''}
                </div>
                <div class="clip-card-info">
                    <div class="clip-card-title">${formatEmoji} ${clip.clip_title || 'Untitled'}</div>
                    <div class="clip-card-subtitle">${clip.video_title || 'Unknown'} • ${clip.format_type}</div>
                    <div class="clip-metadata">
                        ${duration !== 'Unknown' ? `
                        <div class="clip-metadata-item">
                            <span>⏱️</span>
                            <span>${duration}</span>
                        </div>
                        ` : ''}
                        ${clip.engagement_score ? `
                        <div class="clip-metadata-item">
                            <span>⭐</span>
                            <span>${clip.engagement_score}/10</span>
                        </div>
                        ` : ''}
                        ${clip.views !== undefined ? `
                        <div class="clip-metadata-item">
                            <span>👁️</span>
                            <span>${clip.views || 0}</span>
                        </div>
                        ` : ''}
                        ${dateStr ? `
                        <div class="clip-metadata-item">
                            <span>📅</span>
                            <span>${dateStr}</span>
                        </div>
                        ` : ''}
                    </div>
                    <div class="clip-card-actions">
                        <button onclick="event.stopPropagation(); previewLibraryClip(${clip.id}, '${clip.clip_title || 'Untitled'}')" class="btn-preview" style="flex: 1; padding: 8px; font-size: 12px;">
                            🎬 Preview
                        </button>
                        <a href="/api/library/clip/${clip.id}/download" onclick="event.stopPropagation();" class="btn-download" download style="flex: 1; padding: 8px; font-size: 12px; text-align: center;">
                            💾 Download
                        </a>
                        <button onclick="event.stopPropagation(); deleteClip(${clip.id})" class="btn-delete" style="flex: 1; padding: 8px; font-size: 12px;">
                            🗑️ Delete
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

async function deleteClip(clipId) {
    // Enhanced confirmation dialog
    const confirmed = confirm(
        '🗑️ Delete Clip\n\n' +
        'Are you sure you want to delete this clip?\n\n' +
        'This action cannot be undone.'
    );
    
    if (!confirmed) return;
    
    try {
        const response = await fetch(`/api/library/clip/${clipId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            // Show success feedback
            const clipCard = document.querySelector(`[onclick*="previewLibraryClip(${clipId}"]`)?.closest('.clip-card');
            if (clipCard) {
                clipCard.style.opacity = '0.5';
                clipCard.style.transition = 'opacity 0.3s';
                setTimeout(() => {
                    loadLibrary();
                }, 300);
            } else {
                loadLibrary();
            }
        } else {
            const data = await response.json().catch(() => ({}));
            alert('Failed to delete clip: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error deleting clip:', error);
        alert('Error deleting clip. Please try again.');
    }
}

// Preview Functions
function previewClip(jobId, filename, title) {
    const modal = document.getElementById('previewModal');
    const video = document.getElementById('previewVideo');
    const titleEl = document.getElementById('previewTitle');
    const downloadLink = document.getElementById('previewDownload');
    const metadataEl = document.getElementById('previewMetadata');
    
    titleEl.textContent = title;
    video.src = `/api/download/${jobId}/${filename}`;
    downloadLink.href = `/api/download/${jobId}/${filename}`;
    downloadLink.download = filename;
    
    // Try to get clip metadata
    // Find the clip in the results
    const clipCard = document.querySelector(`[data-filename="${filename}"]`);
    if (clipCard) {
        const metadata = {
            duration: clipCard.querySelector('.clip-metadata-item')?.textContent || 'Unknown',
            fileSize: Array.from(clipCard.querySelectorAll('.clip-metadata-item')).find(el => el.textContent.includes('MB'))?.textContent || 'Unknown'
        };
        
        if (metadataEl) {
            metadataEl.innerHTML = `
                <div class="preview-metadata-item">
                    <strong>Format:</strong> <span>${filename.includes('tiktok') ? 'TikTok' : 'YouTube Shorts'}</span>
                </div>
                <div class="preview-metadata-item">
                    <strong>Duration:</strong> <span>${metadata.duration}</span>
                </div>
                <div class="preview-metadata-item">
                    <strong>Size:</strong> <span>${metadata.fileSize}</span>
                </div>
            `;
        }
    } else if (metadataEl) {
        metadataEl.innerHTML = '';
    }
    
    modal.style.display = 'block';
    video.load();
}

function copyClipLink() {
    const downloadLink = document.getElementById('previewDownload');
    if (downloadLink && downloadLink.href) {
        const fullUrl = window.location.origin + downloadLink.href;
        navigator.clipboard.writeText(fullUrl).then(() => {
            const btn = document.getElementById('copyLinkBtn');
            const originalText = btn.textContent;
            btn.textContent = '✅ Copied!';
            setTimeout(() => {
                btn.textContent = originalText;
            }, 2000);
        }).catch(() => {
            alert('Could not copy link. Please copy manually: ' + fullUrl);
        });
    }
}

async function previewLibraryClip(clipId, title) {
    const modal = document.getElementById('previewModal');
    const video = document.getElementById('previewVideo');
    const titleEl = document.getElementById('previewTitle');
    const downloadLink = document.getElementById('previewDownload');
    const metadataEl = document.getElementById('previewMetadata');
    
    try {
        const response = await fetch(`/api/library/clip/${clipId}`);
        const clip = await response.json();
        
        titleEl.textContent = title;
        video.src = `/api/library/clip/${clipId}/download`;
        downloadLink.href = `/api/library/clip/${clipId}/download`;
        downloadLink.download = clip.clip_filename;
        
        // Display metadata
        if (metadataEl) {
            let metadataHTML = `
                <div class="preview-metadata-item">
                    <strong>Format:</strong> <span>${clip.format_type || 'Unknown'}</span>
                </div>
            `;
            
            if (clip.duration) {
                metadataHTML += `
                    <div class="preview-metadata-item">
                        <strong>Duration:</strong> <span>${formatDuration(clip.duration)}</span>
                    </div>
                `;
            }
            
            if (clip.engagement_score) {
                metadataHTML += `
                    <div class="preview-metadata-item">
                        <strong>Engagement:</strong> <span>${clip.engagement_score}/10</span>
                    </div>
                `;
            }
            
            if (clip.views !== undefined) {
                metadataHTML += `
                    <div class="preview-metadata-item">
                        <strong>Views:</strong> <span>${clip.views || 0}</span>
                    </div>
                `;
            }
            
            metadataEl.innerHTML = metadataHTML;
        }
        
        modal.style.display = 'block';
        video.load();
    } catch (error) {
        console.error('Error loading clip:', error);
        alert('Error loading clip preview');
    }
}

function closePreview() {
    const modal = document.getElementById('previewModal');
    const video = document.getElementById('previewVideo');
    
    modal.style.display = 'none';
    video.pause();
    video.src = '';
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('previewModal');
    if (event.target == modal) {
        closePreview();
    }
}

// Edit Tab Functions
let libraryClipsForEdit = [];

// Load library clips for editing dropdown
async function loadLibraryClipsForEdit() {
    try {
        const response = await fetch('/api/library/clips?limit=100');
        const data = await response.json();
        libraryClipsForEdit = data.clips || [];
        
        const select = document.getElementById('editClipSelect');
        select.innerHTML = '<option value="">-- Select a clip --</option>';
        
        libraryClipsForEdit.forEach(clip => {
            const option = document.createElement('option');
            option.value = clip.id;
            option.textContent = `${clip.clip_title || 'Untitled'} (${clip.format_type})`;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading clips for edit:', error);
    }
}

// Load clip info when selected
async function loadClipForEditing() {
    const clipId = document.getElementById('editClipSelect').value;
    if (!clipId) {
        document.getElementById('editClipInfo').style.display = 'none';
        return;
    }
    
    try {
        const clip = libraryClipsForEdit.find(c => c.id == clipId);
        if (!clip) {
            const response = await fetch(`/api/library/clip/${clipId}`);
            const clipData = await response.json();
            
            // Get detailed clip info
            const infoResponse = await fetch('/api/clip/info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ clip_id: clipId })
            });
            
            if (infoResponse.ok) {
                const info = await infoResponse.json();
                document.getElementById('clipDuration').textContent = info.duration.toFixed(2);
                document.getElementById('clipDimensions').textContent = `${info.width}x${info.height}`;
                
                // Set max values for trim inputs
                document.getElementById('trimEnd').max = info.duration;
                document.getElementById('trimEnd').placeholder = info.duration.toFixed(2);
                if (!document.getElementById('overlayDuration').value) {
                    document.getElementById('overlayDuration').placeholder = info.duration.toFixed(2);
                }
            }
            
            document.getElementById('editClipId').value = clipId;
            document.getElementById('editVideoPath').value = clipData.clip_path;
            document.getElementById('editClipInfo').style.display = 'block';
        } else {
            // Get detailed clip info
            const infoResponse = await fetch('/api/clip/info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ clip_id: clipId })
            });
            
            if (infoResponse.ok) {
                const info = await infoResponse.json();
                document.getElementById('clipDuration').textContent = info.duration.toFixed(2);
                document.getElementById('clipDimensions').textContent = `${info.width}x${info.height}`;
                
                // Set max values for trim inputs
                document.getElementById('trimEnd').max = info.duration;
                document.getElementById('trimEnd').placeholder = info.duration.toFixed(2);
                if (!document.getElementById('overlayDuration').value) {
                    document.getElementById('overlayDuration').placeholder = info.duration.toFixed(2);
                }
            }
            
            document.getElementById('editClipId').value = clipId;
            document.getElementById('editVideoPath').value = clip.clip_path;
            document.getElementById('editClipInfo').style.display = 'block';
        }
    } catch (error) {
        console.error('Error loading clip for editing:', error);
        alert('Error loading clip information');
    }
}

// Upload form handler
const uploadForm = document.getElementById('uploadForm');
if (uploadForm) {
    uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData();
    const fileInput = document.getElementById('videoFile');
    const format = document.getElementById('uploadFormat').value;
    
    if (!fileInput.files[0]) {
        alert('Please select a video file');
        return;
    }
    
    formData.append('file', fileInput.files[0]);
    formData.append('format', format);
    
    const submitBtn = e.target.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Uploading...';
    
    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
         if (response.ok) {
             // Show success message
             const successMsg = document.createElement('div');
             successMsg.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--accent-red); color: white; padding: 15px 20px; border-radius: 8px; z-index: 10000; box-shadow: 0 4px 12px rgba(0,0,0,0.3);';
             successMsg.innerHTML = '✅ Video uploaded and processed successfully!';
             document.body.appendChild(successMsg);
             
             setTimeout(() => {
                 successMsg.style.opacity = '0';
                 successMsg.style.transition = 'opacity 0.3s';
                 setTimeout(() => successMsg.remove(), 300);
             }, 3000);
             
             fileInput.value = '';
             // Reset drop zone
             const dropZoneText = document.querySelector('.drop-zone-text');
             if (dropZoneText) {
                 dropZoneText.textContent = 'Drag & drop video files here';
             }
             
             // Auto-refresh library if on library tab
             if (document.getElementById('libraryTab')?.classList.contains('active')) {
                 setTimeout(() => loadLibrary(), 1000);
             }
             
             loadLibraryClipsForEdit();
         } else {
             alert('Error: ' + (data.error || 'Upload failed'));
         }
    } catch (error) {
        console.error('Upload error:', error);
        alert('Error uploading video');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '📤 Upload & Process';
    }
    });
}

// Clip Templates
const clipTemplates = {
    gaming: {
        name: "🎮 Gaming Highlights",
        description: "Perfect for gaming clips with high energy",
        filters: { brightness: 1.1, contrast: 1.2, saturation: 1.1 },
        text_overlay: { position: "top", fontsize: 60, color: "#ffffff" }
    },
    vlog: {
        name: "📹 Vlog Style",
        description: "Clean and professional vlog aesthetic",
        filters: { brightness: 1.05, contrast: 1.1, saturation: 0.95 },
        text_overlay: { position: "bottom", fontsize: 48, color: "#ffffff" }
    },
    reaction: {
        name: "😱 Reaction Clips",
        description: "Vibrant colors for reaction content",
        filters: { brightness: 1.15, contrast: 1.3, saturation: 1.2 },
        text_overlay: { position: "center", fontsize: 72, color: "#ffff00" }
    },
    cinematic: {
        name: "🎬 Cinematic",
        description: "Moody, film-like aesthetic",
        filters: { brightness: 0.9, contrast: 1.4, saturation: 0.8 },
        text_overlay: { position: "bottom", fontsize: 40, color: "#ffffff" }
    },
    vibrant: {
        name: "🌈 Vibrant",
        description: "Super colorful and eye-catching",
        filters: { brightness: 1.2, contrast: 1.1, saturation: 1.5 },
        text_overlay: { position: "top", fontsize: 56, color: "#ffffff" }
    }
};

function applyTemplate() {
    const templateSelect = document.getElementById('clipTemplate');
    const templateName = templateSelect.value;
    const descriptionEl = document.getElementById('templateDescription');
    
    if (!templateName || !clipTemplates[templateName]) {
        descriptionEl.textContent = '';
        return;
    }
    
    const template = clipTemplates[templateName];
    descriptionEl.textContent = template.description;
    
    // Apply filter values
    if (template.filters) {
        if (template.filters.brightness) {
            document.getElementById('filterBrightness').value = template.filters.brightness;
            document.getElementById('brightnessValue').textContent = template.filters.brightness.toFixed(1) + 'x';
        }
        if (template.filters.contrast) {
            document.getElementById('filterContrast').value = template.filters.contrast;
            document.getElementById('contrastValue').textContent = template.filters.contrast.toFixed(1) + 'x';
        }
        if (template.filters.saturation) {
            document.getElementById('filterSaturation').value = template.filters.saturation;
            document.getElementById('saturationValue').textContent = template.filters.saturation.toFixed(1) + 'x';
        }
    }
    
    // Apply text overlay settings
    if (template.text_overlay) {
        if (template.text_overlay.position) {
            document.getElementById('overlayPosition').value = template.text_overlay.position;
        }
        if (template.text_overlay.fontsize) {
            document.getElementById('overlayFontSize').value = template.text_overlay.fontsize;
        }
        if (template.text_overlay.color) {
            document.getElementById('overlayColor').value = template.text_overlay.color;
        }
    }
}

// Filter slider value updates
const brightnessSlider = document.getElementById('filterBrightness');
const contrastSlider = document.getElementById('filterContrast');
const saturationSlider = document.getElementById('filterSaturation');

if (brightnessSlider) {
    brightnessSlider.addEventListener('input', (e) => {
        document.getElementById('brightnessValue').textContent = parseFloat(e.target.value).toFixed(1) + 'x';
    });
}
if (contrastSlider) {
    contrastSlider.addEventListener('input', (e) => {
        document.getElementById('contrastValue').textContent = parseFloat(e.target.value).toFixed(1) + 'x';
    });
}
if (saturationSlider) {
    saturationSlider.addEventListener('input', (e) => {
        document.getElementById('saturationValue').textContent = parseFloat(e.target.value).toFixed(1) + 'x';
    });
}

// Edit form handler
const editForm = document.getElementById('editForm');
if (editForm) {
    editForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const clipId = document.getElementById('editClipId').value;
    const videoPath = document.getElementById('editVideoPath').value;
    
    if (!clipId && !videoPath) {
        alert('Please select a clip to edit or provide a video path');
        return;
    }
    
    // Build edit parameters
    const editData = {
        clip_id: clipId || null,
        video_path: videoPath || null,
        format: document.getElementById('editFormat').value,
        trim_start: document.getElementById('trimStart').value ? parseFloat(document.getElementById('trimStart').value) : null,
        trim_end: document.getElementById('trimEnd').value ? parseFloat(document.getElementById('trimEnd').value) : null,
        speed: document.getElementById('speed').value ? parseFloat(document.getElementById('speed').value) : null,
        filters: {}
    };
    
    // Add filters if provided
    const brightness = document.getElementById('filterBrightness')?.value;
    const contrast = document.getElementById('filterContrast')?.value;
    const saturation = document.getElementById('filterSaturation')?.value;
    
    if (brightness && brightness !== '1.0') {
        editData.filters.brightness = parseFloat(brightness);
    }
    if (contrast && contrast !== '1.0') {
        editData.filters.contrast = parseFloat(contrast);
    }
    if (saturation && saturation !== '1.0') {
        editData.filters.saturation = parseFloat(saturation);
    }
    
    if (Object.keys(editData.filters).length === 0) {
        delete editData.filters;
    }
    
    // Add text overlay if provided
    const overlayText = document.getElementById('overlayText').value;
    if (overlayText) {
        editData.text_overlay = {
            text: overlayText,
            position: document.getElementById('overlayPosition').value,
            fontsize: parseInt(document.getElementById('overlayFontSize').value),
            color: document.getElementById('overlayColor').value,
            start_time: parseFloat(document.getElementById('overlayStartTime').value) || 0,
            duration: document.getElementById('overlayDuration').value ? parseFloat(document.getElementById('overlayDuration').value) : null
        };
    }
    
    const submitBtn = e.target.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Processing...';
    
    try {
        const response = await fetch('/api/edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(editData)
        });
        
        const data = await response.json();
        
         if (response.ok) {
             // Show success notification
             const successMsg = document.createElement('div');
             successMsg.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--accent-red); color: white; padding: 15px 20px; border-radius: 8px; z-index: 10000; box-shadow: 0 4px 12px rgba(0,0,0,0.3);';
             successMsg.innerHTML = '🎊 Clip edited successfully!';
             document.body.appendChild(successMsg);
             
             setTimeout(() => {
                 successMsg.style.opacity = '0';
                 successMsg.style.transition = 'opacity 0.3s';
                 setTimeout(() => successMsg.remove(), 300);
             }, 3000);
             
             // Show results
             const resultsDiv = document.getElementById('editResults');
             const resultsContent = document.getElementById('editResultsContent');
             
             resultsContent.innerHTML = `
                 <p>🎊 Clip edited successfully!</p>
                 <p><strong>Filename:</strong> ${data.filename}</p>
                 <div style="margin-top: 15px;">
                     <a href="/api/library/clip/${data.clip_id}/download" class="btn-download" download>💾 Download Edited Clip</a>
                 </div>
             `;
             
             resultsDiv.style.display = 'block';
             resultsDiv.scrollIntoView({ behavior: 'smooth' });
             
             // Reset form
             e.target.reset();
             document.getElementById('editClipInfo').style.display = 'none';
             
             // Auto-refresh library if on library tab
             if (document.getElementById('libraryTab')?.classList.contains('active')) {
                 setTimeout(() => loadLibrary(), 1000);
             }
             
             loadLibraryClipsForEdit();
         } else {
             alert('Error: ' + (data.error || 'Edit failed'));
         }
    } catch (error) {
        console.error('Edit error:', error);
        alert('Error editing clip');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '💾 Apply Edits';
    }
    });
}

// Add click event listeners to nav items for better reliability
const navItems = document.querySelectorAll('.nav-item');
navItems.forEach((item, index) => {
    item.addEventListener('click', function(e) {
        e.preventDefault();
        const tabNames = ['create', 'library', 'edit'];
        if (tabNames[index]) {
            showTab(tabNames[index]);
        }
    });
});

// Add click event listener to NEW CLIP button
const newClipBtn = document.getElementById('newClipBtn');
if (newClipBtn) {
    newClipBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        showTab('create');
    });
}

// Initialize drag and drop
initializeDragAndDrop();

// Initialize keyboard shortcuts
initializeKeyboardShortcuts();
}

// Drag and Drop Functionality
function initializeDragAndDrop() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('videoFile');
    
    if (!dropZone || !fileInput) return;
    
    // Click to browse
    dropZone.addEventListener('click', () => {
        fileInput.click();
    });
    
    // Drag events
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });
    
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        
        const files = e.dataTransfer.files;
        if (files.length > 0 && files[0].type.startsWith('video/')) {
            fileInput.files = files;
            // Update drop zone text
            const dropZoneText = dropZone.querySelector('.drop-zone-text');
            if (dropZoneText) {
                dropZoneText.textContent = `Selected: ${files[0].name}`;
            }
        } else {
            alert('Please drop a valid video file');
        }
    });
    
    // Update drop zone when file is selected via input
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            const dropZoneText = dropZone.querySelector('.drop-zone-text');
            if (dropZoneText) {
                dropZoneText.textContent = `Selected: ${e.target.files[0].name}`;
            }
        }
    });
}

// Keyboard Shortcuts
function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Only trigger if not typing in an input
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }
        
        // Ctrl/Cmd + N - New clip (Create tab)
        if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
            e.preventDefault();
            showTab('create');
        }
        
        // Ctrl/Cmd + L - Library
        if ((e.ctrlKey || e.metaKey) && e.key === 'l') {
            e.preventDefault();
            showTab('library');
        }
        
        // Ctrl/Cmd + E - Edit
        if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
            e.preventDefault();
            showTab('edit');
        }
        
        // Ctrl/Cmd + / - Show help (future feature)
        if ((e.ctrlKey || e.metaKey) && e.key === '/') {
            e.preventDefault();
            // Could show a help modal
            console.log('Keyboard shortcuts:\nCtrl+N: Create Clips\nCtrl+L: Library\nCtrl+E: Edit');
        }
    });
}
