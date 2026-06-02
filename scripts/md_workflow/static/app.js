// MD Workflow Monitor - Dashboard Logic

const POLLING_INTERVALS = {
    SYSTEM: 10000,
    GPU: 5000,
    PROGRESS: 3000,
    LOGS: 5000,
    RESULTS: 10000
};

let config = null;
let activeLogFile = "";

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    fetchInitialData();
    setupEventListeners();
    startPolling();
});

async function fetchInitialData() {
    try {
        // Fetch Config
        const configRes = await fetch('/config');
        config = await configRes.json();
        
        // Fetch System Info (Root)
        const systemRes = await fetch('/');
        const systemData = await systemRes.json();
        updateSystemInfo(systemData);
        
        updateStatusBadge(true);
    } catch (err) {
        console.error("Failed to fetch initial data:", err);
        updateStatusBadge(false);
    }
}

function updateStatusBadge(isOnline) {
    const badge = document.getElementById('server-status');
    if (isOnline) {
        badge.textContent = "Online";
        badge.className = "status-badge status-online";
    } else {
        badge.textContent = "Offline";
        badge.className = "status-badge status-offline";
    }
}

function updateSystemInfo(data) {
    if (data.container_info) {
        document.getElementById('info-hostname').textContent = data.container_info.hostname || 'unknown';
        document.getElementById('info-gpu').textContent = data.container_info.gpu || 'unknown';
        document.getElementById('info-outdir').textContent = data.container_info.outdir || '/results';
        document.getElementById('info-workdir').textContent = data.container_info.workdir || '/work';
    }
}

function startPolling() {
    // GPU Polling
    setInterval(updateGPUStatus, POLLING_INTERVALS.GPU);
    updateGPUStatus();

    // Progress Polling
    setInterval(updateProgress, POLLING_INTERVALS.PROGRESS);
    updateProgress();

    // Logs Polling
    setInterval(updateLogs, POLLING_INTERVALS.LOGS);
    
    // Results Polling
    setInterval(updateResults, POLLING_INTERVALS.RESULTS);
    updateResults();
}

async function updateGPUStatus() {
    try {
        const res = await fetch('/gpu');
        const data = await res.json();
        document.getElementById('gpu-output').textContent = data.output || data.error || 'No GPU data available';
    } catch (err) {
        document.getElementById('gpu-output').textContent = "Error fetching GPU status";
    }
}

async function updateProgress() {
    try {
        const res = await fetch('/progress');
        const data = await res.json();
        const container = document.getElementById('simulation-list');
        
        const complexIds = Object.keys(data);
        if (complexIds.length === 0) {
            container.innerHTML = '<p class="placeholder">No active simulations detected.</p>';
            return;
        }

        let html = '';
        complexIds.forEach(id => {
            const info = data[id];
            if (info.error) return;

            // Calculate percentage if we have nsteps in config
            let percent = 0;
            const totalSteps = config && config.md ? config.md.nsteps : null;
            if (totalSteps) {
                percent = Math.min((info.step / totalSteps) * 100, 100).toFixed(1);
            }

            html += `
                <div class="simulation-item">
                    <div class="sim-header">
                        <strong>${id}</strong>
                        <span>${percent > 0 ? percent + '%' : 'Running...'}</span>
                    </div>
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill" style="width: ${percent}%"></div>
                    </div>
                    <div class="sim-stats">
                        <span>Step: ${info.step}</span>
                        <span>Time: ${info.time_ns.toFixed(3)} ns</span>
                        <span>Update: ${new Date(info.last_update).toLocaleTimeString()}</span>
                    </div>
                </div>
            `;
        });
        container.innerHTML = html;
    } catch (err) {
        console.error("Progress fetch error:", err);
    }
}

async function updateLogs() {
    if (!activeLogFile) return;

    try {
        const res = await fetch('/logs');
        const data = await res.json();
        
        if (data[activeLogFile]) {
            const output = document.getElementById('log-output');
            const lines = data[activeLogFile].join("");
            if (output.textContent !== lines) {
                output.textContent = lines;
                output.scrollTop = output.scrollHeight;
            }
        }
    } catch (err) {
        console.error("Log fetch error:", err);
    }
}

async function updateResults() {
    try {
        const res = await fetch('/results');
        const data = await res.json();
        
        // Update Log Selector if needed
        const selector = document.getElementById('log-selector');
        const logFiles = [];
        const resultFiles = [];
        
        if (data.files) {
            data.files.forEach(f => {
                const path = typeof f === 'string' ? f : f.filepath;
                if (path.endsWith('.log')) logFiles.push(path);
                resultFiles.push(path);
            });
        }

        // Update dropdown
        const currentOptions = Array.from(selector.options).map(o => o.value);
        logFiles.forEach(log => {
            if (!currentOptions.includes(log)) {
                const opt = document.createElement('option');
                opt.value = log;
                opt.textContent = log;
                selector.appendChild(opt);
            }
        });

        // Update File List
        const listContainer = document.getElementById('file-list');
        if (resultFiles.length === 0) {
            listContainer.innerHTML = '<p class="placeholder">No result files found.</p>';
        } else {
            listContainer.innerHTML = resultFiles.map(f => `
                <li>
                    <span>${f}</span>
                    <a href="/download/${f}" target="_blank">Download</a>
                </li>
            `).join("");
        }
    } catch (err) {
        console.error("Results fetch error:", err);
    }
}

function setupEventListeners() {
    // Log Selector
    document.getElementById('log-selector').addEventListener('change', (e) => {
        activeLogFile = e.target.value;
        if (activeLogFile) {
            document.getElementById('log-output').textContent = "Loading logs for " + activeLogFile + "...";
            updateLogs();
        } else {
            document.getElementById('log-output').textContent = "Select a log file to view its contents.";
        }
    });

    // Notify Button
    document.getElementById('btn-notify').addEventListener('click', async () => {
        const msgInput = document.getElementById('notify-message');
        const status = document.getElementById('notify-status');
        const msg = msgInput.value.trim();

        if (!msg) return;

        try {
            status.textContent = "Sending...";
            const res = await fetch(`/notify?message=${encodeURIComponent(msg)}`, { method: 'POST' });
            const data = await res.json();
            
            if (data.status === 'sent') {
                status.textContent = "✓ Notification sent successfully!";
                status.style.color = "var(--success-color)";
                msgInput.value = "";
            } else {
                status.textContent = "✗ Error: " + (data.message || data.error);
                status.style.color = "var(--error-color)";
            }
        } catch (err) {
            status.textContent = "✗ Network error";
            status.style.color = "var(--error-color)";
        }
        
        setTimeout(() => { status.textContent = ""; }, 5000);
    });
}
