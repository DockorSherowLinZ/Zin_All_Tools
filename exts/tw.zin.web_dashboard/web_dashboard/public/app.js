// Configure API URL dynamically based on current host
const currentHost = window.location.hostname;
const API_BASE = `http://${currentHost}:8013/api`;

// Setup WebRTC Stream URL
document.addEventListener("DOMContentLoaded", () => {
    const webrtcIframe = document.getElementById("webrtc-iframe");
    // WebRTC stream default port is 8011 in Omniverse
    webrtcIframe.src = `http://${currentHost}:8011/streaming/webrtc-client?server=${currentHost}`;
    
    // Start polling API
    setInterval(fetchStatus, 1000);
});

// UI Elements
const statusIndicator = document.getElementById('connection-status');
const simState = document.getElementById('sim-state');
const uphValue = document.getElementById('uph-value');
const speedDisplay = document.getElementById('speed-display');

let isTyping = false;
let firstRender = true;

// Fetch Status
async function fetchStatus() {
    try {
        const response = await fetch(`${API_BASE}/status`);
        if (!response.ok) throw new Error("Network response was not ok");
        
        const data = await response.json();
        
        // Update connection status
        statusIndicator.className = "status-indicator connected";
        statusIndicator.querySelector('.text').textContent = "Connected to Kit API";
        
        // Update Telemetry
        if (data.is_running) {
            simState.textContent = "RUNNING";
            simState.className = "value text-success";
        } else {
            simState.textContent = "STOPPED";
            simState.className = "value text-warning";
        }
        
        uphValue.textContent = data.uph || 0;
        speedDisplay.textContent = data.speed ? parseFloat(data.speed).toFixed(1) : 0.0;
        
        if (data.lines && data.lines.length > 0) {
            renderLines(data.lines);
        } else {
            document.getElementById('linesContainer').innerHTML = '<div style="color: #888; font-size: 14px; text-align: center; padding: 20px;">No lines active in simulation.</div>';
        }
        
    } catch (error) {
        console.error("Error fetching status:", error);
        statusIndicator.className = "status-indicator error";
        statusIndicator.querySelector('.text').textContent = "Disconnected";
    }
}

function renderLines(lines) {
    const container = document.getElementById('linesContainer');
    if (isTyping && !firstRender) return; // Prevent overwriting inputs while user is typing
    
    let html = '';
    lines.forEach(line => {
        let parts = line.path.replace(/\\/g, '/').split('/');
        let title = parts.length > 1 && parts[parts.length - 1] === "SmartConveyorConfig" 
            ? parts[parts.length - 2] 
            : parts.pop() || 'Unnamed Line';
        
        html += `
            <div class="line-card">
                <div class="line-card-header">${title}</div>
                <div class="line-card-controls">
                    <div class="line-card-input">
                        <label>Speed (m/s)</label>
                        <input type="number" id="speed-${line.type}-${line.index}" value="${line.speed}" step="0.5" onfocus="isTyping=true" onblur="isTyping=false">
                    </div>
                    <div class="line-card-input">
                        <label>Delay (s)</label>
                        <input type="number" id="delay-${line.type}-${line.index}" value="${line.initial_delay}" step="0.5" onfocus="isTyping=true" onblur="isTyping=false">
                    </div>
                    <div class="line-card-input">
                        <label>Interval (s)</label>
                        <input type="number" id="interval-${line.type}-${line.index}" value="${line.interval}" step="0.5" onfocus="isTyping=true" onblur="isTyping=false">
                    </div>
                    <button class="btn btn-secondary btn-line-apply" onclick="applyLineSettings('${line.type}', ${line.index})">Apply</button>
                </div>
            </div>
        `;
    });
    container.innerHTML = html;
    firstRender = false;
}

// Control API Wrapper
async function sendCommand(action) {
    const payload = { action };
    try {
        const response = await fetch(`${API_BASE}/control`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            throw new Error(`Command failed: ${response.status}`);
        }
        fetchStatus();
    } catch (error) {
        alert("Failed to send command to Omniverse API: " + error.message);
    }
}

async function applyLineSettings(lineType, lineIndex) {
    const speed = document.getElementById(`speed-${lineType}-${lineIndex}`).value;
    const interval = document.getElementById(`interval-${lineType}-${lineIndex}`).value;
    const delay = document.getElementById(`delay-${lineType}-${lineIndex}`).value;
    const payload = { 
        action: 'update_line', 
        line_type: lineType, 
        line_index: lineIndex, 
        speed: parseFloat(speed), 
        interval: parseFloat(interval),
        initial_delay: parseFloat(delay)
    };
    
    try {
        const response = await fetch(`${API_BASE}/control`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!response.ok) throw new Error(`Command failed: ${response.status}`);
        fetchStatus();
    } catch (e) {
        alert("Failed to apply line settings: " + e.message);
    }
}

async function loadConfigFolder() {
    const urlInput = document.getElementById('configUrlInput');
    if (!urlInput) return;
    
    const url = urlInput.value.trim();
    if (!url) return;
    
    const btn = event.target;
    const originalText = btn.innerText;
    btn.innerText = 'Loading...';
    btn.disabled = true;
    
    try {
        await fetch(`${API_BASE}/control`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'load_folder', url: url })
        });
        
        // Wait a bit for the backend to fetch and parse JSONs, then refresh UI
        setTimeout(() => {
            fetchStatus();
            btn.innerText = 'Success!';
            setTimeout(() => {
                btn.innerText = originalText;
                btn.disabled = false;
            }, 2000);
        }, 1500);
    } catch (error) {
        console.error('Error loading folder:', error);
        btn.innerText = 'Error';
        setTimeout(() => {
            btn.innerText = originalText;
            btn.disabled = false;
        }, 2000);
    }
}

// Button Events
document.getElementById('btn-start').addEventListener('click', () => {
    sendCommand("start");
});

document.getElementById('btn-stop').addEventListener('click', () => {
    sendCommand("stop");
});

async function applyBatchSettings() {
    const speed = document.getElementById('batch-speed').value;
    const delay = document.getElementById('batch-delay').value;
    const interval = document.getElementById('batch-interval').value;
    
    const payload = { action: 'update_all_lines' };
    if (speed !== '') payload.speed = parseFloat(speed);
    if (delay !== '') payload.initial_delay = parseFloat(delay);
    if (interval !== '') payload.interval = parseFloat(interval);
    
    if (Object.keys(payload).length === 1) return; // Nothing to update
    
    try {
        await fetch(`${API_BASE}/control`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        // Clear inputs after applying
        document.getElementById('batch-speed').value = '';
        document.getElementById('batch-delay').value = '';
        document.getElementById('batch-interval').value = '';
        
        setTimeout(fetchStatus, 500);
    } catch (error) {
        console.error('Error applying batch settings:', error);
    }
}
