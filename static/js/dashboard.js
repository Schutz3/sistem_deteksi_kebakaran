// ==============================================================================
// Tujuan       : Dashboard frontend logic - WebSocket, Chart.js, chat, settings
// Caller       : templates/index.html
// Dependensi   : Chart.js, html2canvas, jsPDF (CDN)
// Main Functions: connectWebSocket(), settings API, chat, PDF export
// Side Effects : WebSocket connection, fetch API calls
// ==============================================================================

// --- 1. Tab Navigation ---
function switchTab(tabId, btn) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    btn.classList.add('active');
    // Load settings saat tab Pengaturan dibuka
    if (tabId === 'tab4') { loadCameras(); loadThresholds(); }
}

// --- 2. Chart.js Init ---
const ctx = document.getElementById('liveChart').getContext('2d');
Chart.defaults.color = '#a1a1aa';
Chart.defaults.font.family = 'ui-sans-serif, system-ui, -apple-system, sans-serif';
const liveChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: [], datasets: [
            { label: 'MQ2 (Asap)', borderColor: '#f97316', backgroundColor: 'rgba(249,115,22,0.1)', borderWidth: 2, tension: 0.4, fill: true, pointRadius: 2, data: [], yAxisID: 'y' },
            { label: 'MQ7 (CO)', borderColor: '#a1a1aa', backgroundColor: 'rgba(161,161,170,0.1)', borderWidth: 2, tension: 0.4, fill: true, pointRadius: 2, data: [], yAxisID: 'y1' }
        ]
    },
    options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'top', labels: { boxWidth: 12, font: { size: 11 } } } },
        scales: {
            x: { grid: { color: 'rgba(82,82,91,0.2)' }, ticks: { maxTicksLimit: 8 } },
            y: { type: 'linear', position: 'left', min: 0, max: 10, title: { display: true, text: 'MQ2' } },
            y1: { type: 'linear', position: 'right', min: 0, max: 10, grid: { drawOnChartArea: false }, title: { display: true, text: 'MQ7' } }
        }
    }
});

// --- 3. DOM References ---
const ui = {
    wsStatus: document.getElementById('ws-status'),
    globalStatus: document.getElementById('global-status'),
    mMq2: document.getElementById('metric-mq2'),
    mMq7: document.getElementById('metric-mq7'),
    mProb: document.getElementById('metric-prob'),
    cameraTime: document.getElementById('camera-timestamp'),
    cameraFrame: document.getElementById('camera-frame'),
    cameraPlaceholder: document.getElementById('camera-placeholder'),
    cameraLabel: document.getElementById('camera-label'),
    cameraSelect: document.getElementById('camera-select'),
    logTable: document.getElementById('log-table-body'),
    noLog: document.getElementById('no-log-row'),
    aiYoloVal: document.getElementById('ai-yolo-val'),
    aiYoloBar: document.getElementById('ai-yolo-bar'),
    aiXgbVal: document.getElementById('ai-xgboost-val'),
    aiXgbBar: document.getElementById('ai-xgboost-bar'),
    aiFusionVal: document.getElementById('ai-fusion-val'),
    // Sensor detail cards
    sMq135: document.getElementById('sensor-mq135'),
    sMq2: document.getElementById('sensor-mq2'),
    sMq3: document.getElementById('sensor-mq3'),
    sMq4: document.getElementById('sensor-mq4'),
    sMq5: document.getElementById('sensor-mq5'),
    sMq7: document.getElementById('sensor-mq7-detail'),
};

let selectedCameraId = null;

// Clock
setInterval(() => {
    const now = new Date();
    ui.cameraTime.textContent = now.toLocaleTimeString('id-ID', { hour12: false }) + '.' + Math.floor(now.getMilliseconds() / 100);
}, 100);

function switchCamera(camId) {
    selectedCameraId = camId || null;
}

// --- 4. Status Helpers ---
function getStatusTheme(s) {
    if (s === 'Aman') return { bg: 'bg-emerald-500/20', border: 'border-emerald-500', text: 'text-emerald-400' };
    if (s === 'Waspada') return { bg: 'bg-yellow-500/20', border: 'border-yellow-500', text: 'text-yellow-400 shadow-[0_0_15px_rgba(234,179,8,0.3)]' };
    if (s === 'Bahaya') return { bg: 'bg-red-500/20', border: 'border-red-500', text: 'text-red-500 shadow-[0_0_20px_rgba(239,68,68,0.5)] animate-pulse' };
    return { bg: 'bg-zinc-800', border: 'border-zinc-600', text: 'text-zinc-400' };
}

function appendLog(time, status, message) {
    if (ui.noLog) { ui.noLog.remove(); ui.noLog = null; }
    const tr = document.createElement('tr');
    let badge = '', extra = '';
    if (status === 'Waspada') { badge = '<span class="px-2 py-0.5 text-[10px] rounded border font-bold bg-yellow-500/20 text-yellow-500 border-yellow-500/30">WASPADA</span>'; extra = 'border-l-2 border-l-yellow-500'; }
    else if (status === 'Bahaya') { badge = '<span class="px-2 py-0.5 text-[10px] rounded border font-bold bg-red-500/20 text-red-500 border-red-500/30">BAHAYA</span>'; extra = 'border-l-2 border-l-red-500'; }
    tr.className = `hover:bg-zinc-800/80 transition-colors ${extra}`;
    tr.innerHTML = `<td class="px-3 py-2 md:px-4 md:py-3 text-zinc-400 font-mono whitespace-nowrap">${time}</td><td class="px-3 py-2 md:px-4 md:py-3 whitespace-nowrap">${badge}</td><td class="px-3 py-2 md:px-4 md:py-3 text-zinc-300 min-w-[200px]">${message}</td>`;
    ui.logTable.prepend(tr);
    if (ui.logTable.children.length > 50) ui.logTable.lastElementChild.remove();
}

// --- 5. WebSocket + Heartbeat ---
let ws;
let heartbeatTimer;

function resetHeartbeatWatchdog() {
    clearTimeout(heartbeatTimer);
    document.getElementById('disconnect-modal').classList.add('hidden');
    document.getElementById('disconnect-modal').classList.remove('flex');
    heartbeatTimer = setTimeout(() => {
        document.getElementById('disconnect-modal').classList.remove('hidden');
        document.getElementById('disconnect-modal').classList.add('flex');
        ui.globalStatus.className = 'px-6 py-2 w-full md:w-auto text-center rounded-full font-black text-sm md:text-base border bg-red-500/20 border-red-500 text-red-500 animate-pulse';
        ui.globalStatus.textContent = 'STATUS: PUTUS';
    }, 10000);
}

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/monitor`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        ui.wsStatus.textContent = 'TERHUBUNG';
        ui.wsStatus.className = 'bg-emerald-500/20 border border-emerald-500/50 text-emerald-400 text-[10px] font-bold px-2 py-0.5 rounded-full uppercase self-start mt-1 shadow-emerald-500/50';
        resetHeartbeatWatchdog();
    };

    ws.onmessage = (event) => {
        resetHeartbeatWatchdog();
        const data = JSON.parse(event.data);
        const cameras = data.cameras || [];

        // Update camera selector jika ada kamera baru
        updateCameraSelector(cameras);

        // Pilih kamera yang ditampilkan
        let cam = cameras.find(c => c.cam_id === selectedCameraId) || cameras[0];
        if (!cam) return;

        // Auto-select first camera
        if (!selectedCameraId && cam) {
            selectedCameraId = cam.cam_id;
            ui.cameraSelect.value = cam.cam_id;
        }

        // --- Update UI dari kamera terpilih ---
        const sensor = cam.sensor || {};
        const mq2 = sensor.mq2 || 0;
        const mq7 = sensor.mq7 || 0;

        ui.mMq2.textContent = mq2.toFixed ? mq2.toFixed(2) : mq2;
        ui.mMq7.textContent = mq7.toFixed ? mq7.toFixed(2) : mq7;
        ui.mProb.textContent = cam.prob_akhir;

        // Sensor detail cards
        ui.sMq135.textContent = (sensor.mq135 || 0).toFixed ? (sensor.mq135 || 0).toFixed(2) : '--';
        ui.sMq2.textContent = mq2.toFixed ? mq2.toFixed(2) : '--';
        ui.sMq3.textContent = (sensor.mq3 || 0).toFixed ? (sensor.mq3 || 0).toFixed(2) : '--';
        ui.sMq4.textContent = (sensor.mq4 || 0).toFixed ? (sensor.mq4 || 0).toFixed(2) : '--';
        ui.sMq5.textContent = (sensor.mq5 || 0).toFixed ? (sensor.mq5 || 0).toFixed(2) : '--';
        ui.sMq7.textContent = mq7.toFixed ? mq7.toFixed(2) : '--';

        // Global status
        const theme = getStatusTheme(cam.status);
        ui.globalStatus.className = `px-6 py-2 w-full md:w-auto text-center rounded-full font-black text-sm md:text-base border transition-all duration-500 ${theme.bg} ${theme.border} ${theme.text}`;
        ui.globalStatus.textContent = `STATUS: ${cam.status.toUpperCase()}`;

        // Camera label
        ui.cameraLabel.textContent = `REC • ${cam.cam_name || cam.cam_id}`;

        // Live frame
        if (cam.frame) {
            ui.cameraFrame.src = 'data:image/jpeg;base64,' + cam.frame;
            ui.cameraFrame.classList.remove('hidden');
            ui.cameraPlaceholder.classList.add('hidden');
        }

        // Chart
        liveChart.data.labels.push(data.timestamp);
        liveChart.data.datasets[0].data.push(mq2);
        liveChart.data.datasets[1].data.push(mq7);
        if (liveChart.data.labels.length > 20) {
            liveChart.data.labels.shift();
            liveChart.data.datasets[0].data.shift();
            liveChart.data.datasets[1].data.shift();
        }
        liveChart.update();

        // Log
        cameras.forEach(c => {
            if (c.log_message && c.status !== 'Aman') {
                appendLog(data.timestamp, c.status, c.log_message);
            }
        });

        // AI Tab
        ui.aiYoloVal.textContent = cam.prob_yolo + '%';
        ui.aiYoloBar.style.width = cam.prob_yolo + '%';
        ui.aiXgbVal.textContent = cam.prob_xgboost + '%';
        ui.aiXgbBar.style.width = cam.prob_xgboost + '%';
        ui.aiFusionVal.textContent = cam.prob_akhir + '%';
    };

    ws.onclose = () => {
        ui.wsStatus.textContent = 'TERPUTUS';
        ui.wsStatus.className = 'bg-red-500/20 border border-red-500/50 text-red-500 text-[10px] font-bold px-2 py-0.5 rounded-full uppercase self-start mt-1';
        // Reconnect setelah 3 detik
        setTimeout(connectWebSocket, 3000);
    };
}

function updateCameraSelector(cameras) {
    const select = ui.cameraSelect;
    const currentOptions = new Set();
    for (const opt of select.options) currentOptions.add(opt.value);

    cameras.forEach(cam => {
        if (!currentOptions.has(cam.cam_id)) {
            const opt = document.createElement('option');
            opt.value = cam.cam_id;
            opt.textContent = cam.cam_name || cam.cam_id;
            select.appendChild(opt);
        }
    });
}

connectWebSocket();

// --- 6. Settings: Camera CRUD ---
async function loadCameras() {
    try {
        const res = await fetch('/api/cameras');
        const data = await res.json();
        const list = document.getElementById('camera-list');
        const cameras = data.cameras || {};

        if (Object.keys(cameras).length === 0) {
            list.innerHTML = '<p class="text-xs text-zinc-500 italic">Belum ada kamera terdaftar.</p>';
            return;
        }

        list.innerHTML = '';
        for (const [id, cfg] of Object.entries(cameras)) {
            const div = document.createElement('div');
            div.className = 'flex items-center justify-between bg-zinc-900/80 border border-zinc-800 rounded-lg px-4 py-3';
            div.innerHTML = `
                <div class="flex-grow">
                    <span class="text-sm font-bold text-zinc-200">${cfg.name || id}</span>
                    <span class="text-xs text-zinc-500 ml-2">[${id}]</span>
                    <p class="text-xs text-zinc-500 font-mono mt-0.5">${cfg.rtsp_url}</p>
                </div>
                <button onclick="deleteCamera('${id}')" class="btn-danger ml-4">Hapus</button>
            `;
            list.appendChild(div);
        }
    } catch (e) { console.error('Error loading cameras:', e); }
}

async function addCamera() {
    const id = document.getElementById('new-cam-id').value.trim();
    const name = document.getElementById('new-cam-name').value.trim();
    const url = document.getElementById('new-cam-url').value.trim();
    if (!id || !name || !url) { alert('Semua field harus diisi!'); return; }

    try {
        await fetch('/api/cameras', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cam_id: id, name: name, rtsp_url: url })
        });
        document.getElementById('new-cam-id').value = '';
        document.getElementById('new-cam-name').value = '';
        document.getElementById('new-cam-url').value = '';
        loadCameras();
    } catch (e) { alert('Gagal menambah kamera: ' + e); }
}

async function deleteCamera(camId) {
    if (!confirm(`Hapus kamera ${camId}?`)) return;
    try {
        await fetch(`/api/cameras/${camId}`, { method: 'DELETE' });
        loadCameras();
    } catch (e) { alert('Gagal menghapus: ' + e); }
}

// --- 7. Settings: Threshold ---
async function loadThresholds() {
    try {
        const res = await fetch('/api/thresholds');
        const data = await res.json();
        const th = data.thresholds || {};
        document.getElementById('th-prob-aman').value = th.prob_aman ?? 30;
        document.getElementById('th-prob-waspada').value = th.prob_waspada ?? 70;
        document.getElementById('th-yolo-threshold').value = th.yolo_threshold ?? 50;
        document.getElementById('th-yolo-weight-high').value = th.yolo_weight_high ?? 0.7;
        document.getElementById('th-yolo-weight-low').value = th.yolo_weight_low ?? 0.3;
        document.getElementById('th-yolo-interval').value = th.yolo_interval ?? 3;
    } catch (e) { console.error('Error loading thresholds:', e); }
}

async function saveThresholds() {
    const payload = {
        prob_aman: parseFloat(document.getElementById('th-prob-aman').value),
        prob_waspada: parseFloat(document.getElementById('th-prob-waspada').value),
        yolo_threshold: parseFloat(document.getElementById('th-yolo-threshold').value),
        yolo_weight_high: parseFloat(document.getElementById('th-yolo-weight-high').value),
        yolo_weight_low: parseFloat(document.getElementById('th-yolo-weight-low').value),
        yolo_interval: parseFloat(document.getElementById('th-yolo-interval').value),
    };
    try {
        await fetch('/api/thresholds', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const st = document.getElementById('threshold-status');
        st.classList.remove('hidden');
        setTimeout(() => st.classList.add('hidden'), 2000);
    } catch (e) { alert('Gagal menyimpan: ' + e); }
}

// --- 8. PDF Export ---
async function downloadPDF() {
    const el = document.getElementById('exportable-area');
    const cs = document.getElementById('log-scroll-container');
    const oo = cs.style.overflow;
    const oh = cs.style.height;
    cs.style.overflow = 'visible';
    cs.style.height = 'auto';
    el.classList.add('printing');
    try {
        const canvas = await html2canvas(el, { scale: 2, backgroundColor: '#18181b' });
        const imgData = canvas.toDataURL('image/png');
        const pdf = new jspdf.jsPDF('landscape', 'mm', 'a4');
        const pw = pdf.internal.pageSize.getWidth();
        const m = 10;
        const aw = pw - m * 2;
        const ph = (canvas.height * aw) / canvas.width;
        const now = new Date();
        pdf.setTextColor(80, 80, 80);
        pdf.setFontSize(10);
        pdf.text(`Diekspor: ${now.toLocaleString('id-ID')}`, m, 8);
        pdf.addImage(imgData, 'PNG', m, 14, aw, ph);
        pdf.save(`Dashboard_Logs_${now.getTime()}.pdf`);
    } catch (err) { alert('Gagal generate PDF.'); console.error(err); }
    finally { cs.style.overflow = oo; cs.style.height = oh; el.classList.remove('printing'); }
}

// --- 9. Chatbot ---
const chatWindow = document.getElementById('chat-window');
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');

function toggleChat() {
    if (chatWindow.classList.contains('hidden')) {
        chatWindow.classList.remove('hidden');
        chatWindow.classList.add('flex');
        chatInput.focus();
    } else {
        chatWindow.classList.add('hidden');
        chatWindow.classList.remove('flex');
    }
}

function handleChatEnter(e) { if (e.key === 'Enter') sendChatMessage(); }

function appendMessage(text, sender) {
    const w = document.createElement('div');
    w.className = `flex flex-col ${sender === 'user' ? 'items-end' : 'items-start'} w-full`;
    const b = document.createElement('div');
    b.className = sender === 'user'
        ? 'bg-indigo-600 text-white text-sm rounded-2xl rounded-tr-none px-5 py-4 max-w-[90%] shadow-lg break-words text-left'
        : 'bg-zinc-800 text-zinc-200 text-sm rounded-2xl rounded-tl-none px-5 py-4 max-w-[95%] border border-zinc-700 shadow-lg whitespace-pre-wrap break-words leading-relaxed text-left';
    w.appendChild(b);
    chatMessages.appendChild(w);
    if (sender === 'bot') {
        let fmt = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        typeWriterEffect(b, fmt, 0);
    } else {
        b.textContent = text;
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

function typeWriterEffect(el, html, i) {
    if (i < html.length) {
        let c = html.charAt(i);
        if (c === '<') {
            let end = html.indexOf('>', i);
            if (end !== -1) { el.innerHTML += html.substring(i, end + 1); i = end + 1; }
            else { el.innerHTML += c; i++; }
        } else { el.innerHTML += c; i++; }
        chatMessages.scrollTop = chatMessages.scrollHeight;
        setTimeout(() => typeWriterEffect(el, html, i), 15);
    }
}

async function sendChatMessage() {
    const msg = chatInput.value.trim();
    if (!msg) return;
    appendMessage(msg, 'user');
    chatInput.value = '';

    const lid = 'loading-' + Date.now();
    const lw = document.createElement('div');
    lw.id = lid;
    lw.className = 'flex flex-col items-start w-full mt-1 mb-1';
    lw.innerHTML = '<div class="bg-zinc-800 text-zinc-400 text-xs px-3.5 py-2.5 rounded-xl rounded-tl-none flex gap-1.5 items-center max-w-[50%] border border-zinc-700"><div class="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce"></div><div class="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce" style="animation-delay:0.2s"></div><div class="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce" style="animation-delay:0.4s"></div></div>';
    chatMessages.appendChild(lw);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
        const res = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: msg }) });
        const data = await res.json();
        document.getElementById(lid).remove();
        appendMessage(data.reply, 'bot');
    } catch (e) {
        document.getElementById(lid).remove();
        appendMessage('Gagal terhubung ke AI. Periksa backend.', 'bot');
    }
}