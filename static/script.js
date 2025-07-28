document.addEventListener('DOMContentLoaded', () => {
    const statusElements = {
        active: document.getElementById('active-downloads-count'),
        saved: document.getElementById('saved-videos-count'),
        success: document.getElementById('stats-success'),
        failed: document.getElementById('stats-failed'),
    };
    const videoListBody = document.getElementById('video-list');
    const viewModal = document.getElementById('view-modal');
    const cutModal = document.getElementById('cut-modal');
    const videoPlayer = document.getElementById('modal-video-player');
    const cutForm = document.getElementById('cut-form');
    let currentCutVideoId = null;

    const formatDuration = (seconds) => {
        if (!seconds || seconds < 0) return "N/A";
        return new Date(seconds * 1000).toISOString().substr(11, 8);
    };

    const showModal = (modal) => modal.style.display = 'block';
    const hideModal = (modal) => modal.style.display = 'none';

    const fetchData = async (url) => {
        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            return await response.json();
        } catch (error) { console.error(`Could not fetch ${url}:`, error); return null; }
    };

    const postAction = async (url, body = {}) => {
        try {
            const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || 'Unknown error');
            alert(result.message); return true;
        } catch (error) { console.error(`Action failed for ${url}:`, error); alert(`Lỗi: ${error.message}`); return false; }
    };
    
    const deleteAction = async (url) => {
        try {
            const response = await fetch(url, { method: 'DELETE' });
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || 'Unknown error');
            alert(result.message); return true;
        } catch (error) { console.error(`Action failed for ${url}:`, error); alert(`Lỗi: ${error.message}`); return false; }
    };

    const renderStatus = (statusData) => {
        if (!statusData) return;
        statusElements.active.textContent = statusData.active_downloads_count;
        statusElements.saved.textContent = statusData.saved_videos_count;
        statusElements.success.textContent = statusData.stats.success;
        statusElements.failed.textContent = statusData.stats.failed;
    };

    const renderVideos = (videos) => {
        if (!videos) { videoListBody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Không thể tải dữ liệu video.</td></tr>'; return; }
        if (videos.length === 0) { videoListBody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Chưa có video nào được lưu.</td></tr>'; return; }
        videoListBody.innerHTML = videos.map(video => `
            <tr data-id="${video.id}">
                <td>${video.id}</td><td>${video.name}</td><td>${formatDuration(video.duration)}</td><td>${video.timestamp}</td><td>${video.status}</td>
                <td class="actions">
                    <button class="btn btn-view" data-action="view">Xem</button><button class="btn btn-cut" data-action="cut">Cắt</button>
                    <button class="btn btn-upload" data-action="upload_telegram">Upload</button><button class="btn btn-delete" data-action="delete">Xóa</button>
                </td>
            </tr>`).join('');
    };

    const updateDashboard = async () => {
        const [statusData, videosData] = await Promise.all([ fetchData('/api/status'), fetchData('/api/videos') ]);
        renderStatus(statusData); renderVideos(videosData);
    };

    videoListBody.addEventListener('click', (e) => {
        if (e.target.tagName !== 'BUTTON') return;
        const action = e.target.dataset.action;
        const videoId = e.target.closest('tr').dataset.id;
        const videoName = e.target.closest('tr').children[1].textContent;
        switch (action) {
            case 'view':
                document.getElementById('view-modal-title').textContent = `Xem Video: ${videoName}`;
                videoPlayer.src = `/video/${videoId}`; showModal(viewModal); break;
            case 'cut':
                currentCutVideoId = videoId; document.getElementById('cut-modal-video-name').textContent = videoName;
                cutForm.reset(); showModal(cutModal); break;
            case 'upload_telegram':
                if (confirm(`Bạn có chắc muốn upload video "${videoName}" lên Telegram?`)) { postAction(`/api/action/${videoId}/upload_telegram`).then(updateDashboard); } break;
            case 'delete':
                if (confirm(`CẢNH BÁO: Hành động này sẽ XÓA VĨNH VIỄN file video "${videoName}". Bạn có chắc không?`)) { deleteAction(`/api/action/${videoId}/delete`).then(updateDashboard); } break;
        }
    });

    document.querySelectorAll('.close-button').forEach(btn => {
        btn.onclick = () => { hideModal(viewModal); hideModal(cutModal); videoPlayer.pause(); videoPlayer.src = ''; };
    });

    cutForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const startTime = document.getElementById('start-time').value;
        const endTime = document.getElementById('end-time').value;
        const success = await postAction(`/api/action/${currentCutVideoId}/cut`, { start: startTime, end: endTime });
        if (success) { hideModal(cutModal); updateDashboard(); }
    });

    updateDashboard(); setInterval(updateDashboard, 10000);
});