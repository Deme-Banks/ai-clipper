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

