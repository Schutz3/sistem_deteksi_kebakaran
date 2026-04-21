// --- 1. Tab Navigation System ---
        function switchTab(tabId, btn) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            btn.classList.add('active');
        }

        // --- 2. Chart.js Initialization ---
        const ctx = document.getElementById('liveChart').getContext('2d');
        Chart.defaults.color = '#a1a1aa';
        Chart.defaults.font.family = 'ui-sans-serif, system-ui, -apple-system, sans-serif';
        const liveChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [], datasets: [
                    {
                        label: 'Suhu Lingkungan (°C)', borderColor: '#f97316', backgroundColor: 'rgba(249, 115, 22, 0.1)',
                        borderWidth: 2, tension: 0.4, fill: true, pointRadius: 2, data: [], yAxisID: 'y'
                    },
                    {
                        label: 'Kepadatan Asap (%)', borderColor: '#a1a1aa', backgroundColor: 'rgba(161, 161, 170, 0.1)',
                        borderWidth: 2, tension: 0.4, fill: true, pointRadius: 2, data: [], yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
                interaction: { mode: 'index', intersect: false },
                plugins: { legend: { position: 'top', labels: { boxWidth: 12, font: {size: 11} } } },
                scales: {
                    x: { grid: { color: 'rgba(82, 82, 91, 0.2)' }, ticks: { maxTicksLimit: 8 } },
                    y: { type: 'linear', position: 'left', min: 20, max: 70 },
                    y1: { type: 'linear', position: 'right', min: 0, max: 100, grid: { drawOnChartArea: false } }
                }
            }
        });

        // --- 3. DOM Logic & Utils ---
        const uiParams = {
            wsStatus: document.getElementById('ws-status'),
            globalStatus: document.getElementById('global-status'),
            mSuhu: document.getElementById('metric-suhu'),
            mAsap: document.getElementById('metric-asap'),
            mProb: document.getElementById('metric-prob'),
            cameraTime: document.getElementById('camera-timestamp'),
            logTable: document.getElementById('log-table-body'),
            noLog: document.getElementById('no-log-row'),
            aiYoloVal: document.getElementById('ai-yolo-val'),
            aiYoloBar: document.getElementById('ai-yolo-bar'),
            aiXformVal: document.getElementById('ai-xgboost-val'),
            aiXformBar: document.getElementById('ai-xgboost-bar'),
            aiFusionVal: document.getElementById('ai-fusion-val')
        };

        // Realtime clock for Camera Feed
        setInterval(() => {
            const now = new Date();
            uiParams.cameraTime.textContent = now.toLocaleTimeString('id-ID', { hour12: false }) + '.' + Math.floor(now.getMilliseconds()/100);
        }, 100);

        function getStatusTheme(statusText) {
            if (statusText === 'Aman') return { bg: 'bg-emerald-500/20', border: 'border-emerald-500', text: 'text-emerald-400' };
            if (statusText === 'Waspada') return { bg: 'bg-yellow-500/20', border: 'border-yellow-500', text: 'text-yellow-400 shadow-[0_0_15px_rgba(234,179,8,0.3)]' };
            if (statusText === 'Bahaya') return { bg: 'bg-red-500/20', border: 'border-red-500', text: 'text-red-500 shadow-[0_0_20px_rgba(239,68,68,0.5)] animate-pulse' };
            return { bg: 'bg-zinc-800', border: 'border-zinc-600', text: 'text-zinc-400' };
        }

        function appendLog(time, status, message) {
            if (uiParams.noLog) { uiParams.noLog.remove(); uiParams.noLog = null; }
            const tr = document.createElement('tr');
            
            let statusBadge = "";
            let trExtra = "";
            if (status === 'Waspada') {
                statusBadge = '<span class="px-2 py-0.5 text-[10px] md:text-xs rounded border font-bold bg-yellow-500/20 text-yellow-500 border-yellow-500/30">WASPADA</span>';
                trExtra = "border-l-2 border-l-yellow-500";
            } else if (status === 'Bahaya') {
                statusBadge = '<span class="px-2 py-0.5 text-[10px] md:text-xs rounded border font-bold bg-red-500/20 text-red-500 border-red-500/30">BAHAYA</span>';
                trExtra = "border-l-2 border-l-red-500";
            }

            tr.className = `hover:bg-zinc-800/80 transition-colors ${trExtra}`;
            tr.innerHTML = `
                <td class="px-3 py-2 md:px-4 md:py-3 text-zinc-400 font-mono whitespace-nowrap">${time}</td>
                <td class="px-3 py-2 md:px-4 md:py-3 whitespace-nowrap">${statusBadge}</td>
                <td class="px-3 py-2 md:px-4 md:py-3 text-zinc-300 min-w-[200px]">${message}</td>
            `;
            uiParams.logTable.prepend(tr);
            if (uiParams.logTable.children.length > 50) uiParams.logTable.lastElementChild.remove();
        }

        // --- 4. WebSocket & Heartbeat Watchdog ---
        let ws;
        let heartbeatTimer;
        
        function resetHeartbeatWatchdog() {
            clearTimeout(heartbeatTimer);
            document.getElementById('disconnect-modal').classList.add('hidden');
            document.getElementById('disconnect-modal').classList.remove('flex');
            
            // Watchdog Timeout (10 Detik)
            heartbeatTimer = setTimeout(() => {
                document.getElementById('disconnect-modal').classList.remove('hidden');
                document.getElementById('disconnect-modal').classList.add('flex');
                uiParams.globalStatus.className = `px-6 py-2 w-full md:w-auto text-center rounded-full font-black text-sm md:text-base border bg-red-500/20 border-red-500 text-red-500 shadow-[0_0_20px_rgba(239,68,68,0.5)] animate-pulse`;
                uiParams.globalStatus.textContent = `STATUS SISTEM: PUTUS`;
            }, 10000);
        }

        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/sensor`; 
            ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                uiParams.wsStatus.textContent = 'TERHUBUNG';
                uiParams.wsStatus.className = 'bg-emerald-500/20 border border-emerald-500/50 text-emerald-400 text-[10px] font-bold px-2 py-0.5 rounded-full uppercase self-start mt-1 shadow-[0_0_10px_rgba(16,185,129,0.3)] shadow-emerald-500/50';
                resetHeartbeatWatchdog();
            };

            ws.onmessage = (event) => {
                resetHeartbeatWatchdog(); // Reset timer saat ping diterima
                const data = JSON.parse(event.data);
                
                // Update UI Metrik
                uiParams.mSuhu.textContent = data.suhu;
                uiParams.mAsap.textContent = data.asap;
                uiParams.mProb.textContent = data.prob_akhir;

                const theme = getStatusTheme(data.status);
                uiParams.globalStatus.className = `px-6 py-2 w-full md:w-auto text-center rounded-full font-black text-sm md:text-base border transition-all duration-500 ${theme.bg} ${theme.border} ${theme.text}`;
                uiParams.globalStatus.textContent = `STATUS SISTEM: ${data.status.toUpperCase()}`;

                // Update Chart
                liveChart.data.labels.push(data.timestamp);
                liveChart.data.datasets[0].data.push(data.suhu);
                liveChart.data.datasets[1].data.push(data.asap);
                if (liveChart.data.labels.length > 20) {
                    liveChart.data.labels.shift();
                    liveChart.data.datasets[0].data.shift();
                    liveChart.data.datasets[1].data.shift();
                }
                liveChart.update();

                // Log Records
                if (data.log_message && data.status !== 'Aman') {
                    appendLog(data.timestamp, data.status, data.log_message);
                }

                // Update Tab 3 (AI)
                uiParams.aiYoloVal.textContent = data.prob_yolo + '%';
                uiParams.aiYoloBar.style.width = data.prob_yolo + '%';
                uiParams.aiXformVal.textContent = data.prob_xgboost + '%';
                uiParams.aiXformBar.style.width = data.prob_xgboost + '%';
                uiParams.aiFusionVal.textContent = data.prob_akhir + '%';
            };

            ws.onclose = () => {
                uiParams.wsStatus.textContent = 'TERPUTUS';
                uiParams.wsStatus.className = 'bg-red-500/20 border border-red-500/50 text-red-500 text-[10px] font-bold px-2 py-0.5 rounded-full uppercase self-start mt-1 shadow-[0_0_10px_rgba(239,68,68,0.3)] shadow-red-500/50';
                // Jika koneksi websocket secara asinkron ditutup, Watchdog otomatis akan mentrigger alert setelah 10 detik.
            };
        }

        connectWebSocket();

        // --- 5. Fungsi Ekspor PDF ---
        async function downloadPDF() {
            const el = document.getElementById('exportable-area');
            const containerScroll = document.getElementById('log-scroll-container');
            const originalOverflow = containerScroll.style.overflow;
            const originalHeight = containerScroll.style.height;
            
            // Expand div to show all logs for capturing
            containerScroll.style.overflow = 'visible';
            containerScroll.style.height = 'auto';
            el.classList.add('printing'); 
            
            try {
                // Render Canvas
                const canvas = await html2canvas(el, { 
                    scale: 2, 
                    backgroundColor: '#18181b', // Menggunakan warna zinc-900 sebagai dasar hitam
                    windowWidth: document.documentElement.offsetWidth,
                    windowHeight: document.documentElement.offsetHeight
                });
                const imgData = canvas.toDataURL('image/png');
                
                // Initialize jsPDF
                const pdf = new jspdf.jsPDF('landscape', 'mm', 'a4'); 
                const pdfWidth = pdf.internal.pageSize.getWidth();
                // Memberikan margin
                const margin = 10;
                const availableWidth = pdfWidth - (margin * 2);
                const pdfHeight = (canvas.height * availableWidth) / canvas.width;
                
                // Add header info
                const now = new Date();
                pdf.setTextColor(80, 80, 80);
                pdf.setFontSize(10);
                pdf.text(`Diekspor pada: ${now.toLocaleString('id-ID')}`, margin, 8);
                pdf.text(`Sistem Penilaian Risiko Kebakaran - Tim PBL (Ervin, Akmal, Jascon, Farhan)`, margin, 12);
                
                // Add Image
                pdf.addImage(imgData, 'PNG', margin, 16, availableWidth, pdfHeight);
                
                // Save Payload
                const filename = `PBL_Dashboard_Logs_${now.getTime()}.pdf`;
                pdf.save(filename);
            } catch (err) {
                alert("Gagal menggenerate PDF. Pastikan library ter-load dengan benar.");
                console.error(err);
            } finally {
                // Restore classes & styles
                containerScroll.style.overflow = originalOverflow;
                containerScroll.style.height = originalHeight;
                el.classList.remove('printing');
            }
        }
        // --- 6. Logika Integrasi Chatbot RAG ---
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

        function handleChatEnter(event) {
            if (event.key === 'Enter') {
                sendChatMessage();
            }
        }

        // Fungsi utama untuk menambahkan balon chat ke layar
        function appendMessage(text, sender) {
            const wrapper = document.createElement('div');
            wrapper.className = `flex flex-col ${sender === 'user' ? 'items-end' : 'items-start'} w-full`;
            
            const bubble = document.createElement('div');
            bubble.className = sender === 'user' 
                ? 'bg-indigo-600 text-white text-sm md:text-base rounded-2xl rounded-tr-none px-5 py-4 max-w-[90%] shadow-lg break-words text-left'
                : 'bg-zinc-800 text-zinc-200 text-sm md:text-base rounded-2xl rounded-tl-none px-5 py-4 max-w-[95%] border border-zinc-700 shadow-lg whitespace-pre-wrap break-words leading-relaxed overflow-x-hidden text-left';
            
            wrapper.appendChild(bubble);
            chatMessages.appendChild(wrapper);

            if (sender === 'bot') {
                // Mengubah format bold (**) menjadi tag <strong> HTML
                let formattedText = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                // Panggil efek mengetik khusus untuk bot
                typeWriterEffect(bubble, formattedText, 0);
            } else {
                // Jika user, langsung tampilkan tanpa animasi
                bubble.textContent = text;
                chatMessages.scrollTop = chatMessages.scrollHeight; // Auto-scroll
            }
        }

        // Fungsi animasi mengetik yang aman dari kerusakan tag HTML
        function typeWriterEffect(element, htmlString, index) {
            if (index < htmlString.length) {
                let char = htmlString.charAt(index);
                
                // Jika mendeteksi awalan tag HTML (<), langsung cetak seluruh tag agar format tidak rusak
                if (char === '<') {
                    let tagEnd = htmlString.indexOf('>', index);
                    if (tagEnd !== -1) {
                        element.innerHTML += htmlString.substring(index, tagEnd + 1);
                        index = tagEnd + 1;
                    } else {
                        element.innerHTML += char;
                        index++;
                    }
                } else {
                    element.innerHTML += char;
                    index++;
                }
                
                // Layar otomatis scroll ke bawah mengikuti ketikan
                chatMessages.scrollTop = chatMessages.scrollHeight;
                
                // Kecepatan mengetik (atur angka 15 di bawah ini. Semakin kecil = semakin cepat)
                setTimeout(() => typeWriterEffect(element, htmlString, index), 15); 
            }
        }

        async function sendChatMessage() {
            const message = chatInput.value.trim();
            if (!message) return;

            // 1. Render pesan user ke layar
            appendMessage(message, 'user');
            chatInput.value = '';

            // 2. Render animasi loading titik-titik
            const loadingId = 'loading-' + Date.now();
            const loadingWrapper = document.createElement('div');
            loadingWrapper.id = loadingId;
            loadingWrapper.className = `flex flex-col items-start w-full mt-1 mb-1`;
            loadingWrapper.innerHTML = `<div class="bg-zinc-800 text-zinc-400 text-xs px-3.5 py-2.5 rounded-xl rounded-tl-none flex gap-1.5 items-center max-w-[50%] border border-zinc-700"><div class="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce"></div><div class="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce" style="animation-delay: 0.2s"></div><div class="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce" style="animation-delay: 0.4s"></div></div>`;
            chatMessages.appendChild(loadingWrapper);
            chatMessages.scrollTop = chatMessages.scrollHeight;

            try {
                // 3. Panggil API ke FastAPI backend (main.py)
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message })
                });
                
                const data = await response.json();
                
                // 4. Hapus loading, tampilkan jawaban dari Gemini
                document.getElementById(loadingId).remove();
                appendMessage(data.reply, 'bot');

            } catch (error) {
                document.getElementById(loadingId).remove();
                appendMessage('⚠️ Gagal terhubung ke sistem AI. Periksa koneksi backend.', 'bot');
            }
        }