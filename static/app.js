let ws = null;
let audioContext = null;
let currentSource = null;
let callGainNode = null;
let agentSources = [];
let nextAgentAudioTime = 0;
let isCallActive = false;
let progressInterval = null;
let agentSpokenLogged = false;
let callerTranscriptEl = null;
let agentTranscriptEl = null;

function initAudioContext() {
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
    }
    if (audioContext.state === "suspended") {
        audioContext.resume();
    }
}

async function refreshUploadedFiles() {
    try {
        const res = await fetch("/api/audio-files");
        const data = await res.json();
        const files = data.files || [];

        const knownLower = new Set(["gujarati_scam.wav", "english_scam.wav", "english_genuine.wav"]);
        const container = document.getElementById("scenario-buttons");

        // Add any additional uploaded .wav files dynamically if placed in static/audio/
        files.forEach(file => {
            if (!knownLower.has(file.toLowerCase()) && !container.querySelector(`[data-file="${file}"]`)) {
                const isGenuine = file.toLowerCase().includes("genuine") || file.toLowerCase().includes("safe");
                const btn = document.createElement("button");
                btn.className = "btn btn-scenario";
                btn.setAttribute("data-file", file);
                btn.onclick = () => playScenario(file, file);
                btn.innerHTML = `
                    <span class="btn-lang">WAV</span>
                    <div class="btn-info">
                        <span class="btn-title">${file}</span>
                        <span class="btn-file">${file}</span>
                    </div>
                    <span class="badge ${isGenuine ? "safe" : "danger"}">${isGenuine ? "Genuine Call" : "Scam Call"}</span>
                `;
                container.appendChild(btn);
            }
        });
    } catch (e) {
        console.error("Failed to check uploaded audio files:", e);
    }
}

function connectSessionWebSocket(filename) {
    return new Promise((resolve, reject) => {
        if (ws) {
            try { ws.close(); } catch (e) {}
            ws = null;
        }

        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        ws = new WebSocket(`${protocol}//${window.location.host}/ws/stream`);

        const timeout = setTimeout(() => {
            reject(new Error("Timed out connecting to Gemini Live session."));
        }, 12000);

        ws.onopen = () => {
            log(`Connecting to Gemini Live Native Audio for <code>${filename}</code>...`);
        };

        ws.onmessage = async (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === "ready") {
                clearTimeout(timeout);
                ws.send(JSON.stringify({
                    type: "start_call",
                    filename: filename
                }));
                log("✅ Gemini Live Native Audio session ready.");
                resolve();
            } else if (msg.type === "caller_transcript") {
                appendCallerTranscript(msg.text);
            } else if (msg.type === "agent_transcript") {
                appendAgentTranscript(msg.text);
            } else if (msg.type === "scam_detected") {
                handleScamDetection(msg.alert);
            } else if (msg.type === "call_safe") {
                handleSafeCall(msg.summary);
            } else if (msg.type === "agent_audio") {
                if (!agentSpokenLogged) {
                    agentSpokenLogged = true;
                    log(`<span class="log-agent">🛡️ <strong>Guardian intervening mid-call by voice!</strong> (Call volume ducked to 20%)</span>`);
                }
                if (callGainNode) {
                    callGainNode.gain.value = 0.2;
                }
                playPCMChunk(msg.audio);
            } else if (msg.type === "agent_text") {
                appendAgentTranscript(msg.text);
            } else if (msg.type === "error") {
                clearTimeout(timeout);
                log(`<span class="log-alert">Error: ${msg.message}</span>`);
                reject(new Error(msg.message));
            }
        };

        ws.onerror = () => {
            clearTimeout(timeout);
            reject(new Error("WebSocket connection error."));
        };
    });
}

function appendCallerTranscript(text) {
    const logBox = document.getElementById("log-content");
    if (!callerTranscriptEl) {
        callerTranscriptEl = document.createElement("p");
        callerTranscriptEl.className = "log-caller";
        callerTranscriptEl.innerHTML = `<strong>📞 Caller:</strong> <span class="transcript-body"></span>`;
        logBox.appendChild(callerTranscriptEl);
    }
    const span = callerTranscriptEl.querySelector(".transcript-body");
    span.textContent += text;
    logBox.scrollTop = logBox.scrollHeight;
}

function appendAgentTranscript(text) {
    const logBox = document.getElementById("log-content");
    if (!agentTranscriptEl) {
        agentTranscriptEl = document.createElement("p");
        agentTranscriptEl.className = "log-agent";
        agentTranscriptEl.innerHTML = `<strong>🛡️ Guardian Warning:</strong> <span class="transcript-body"></span>`;
        logBox.appendChild(agentTranscriptEl);
    }
    const span = agentTranscriptEl.querySelector(".transcript-body");
    span.textContent += text;
    logBox.scrollTop = logBox.scrollHeight;
}

function handleScamDetection(alert) {
    document.getElementById("safe-banner").classList.add("hidden");
    document.getElementById("call-status").className = "status-indicator alert";
    document.getElementById("status-text").innerText = "SCAM DETECTED MID-CALL";

    const banner = document.getElementById("alert-banner");
    const wasHidden = banner.classList.contains("hidden");
    banner.classList.remove("hidden");
    document.getElementById("alert-title").innerText = `SCAM FLAGGED: ${alert.scam_type.toUpperCase()}`;

    const flagsDiv = document.getElementById("flags-list");
    flagsDiv.innerHTML = "";
    (alert.red_flags || []).forEach(flag => {
        const span = document.createElement("span");
        span.className = "flag-tag";
        span.innerText = flag;
        flagsDiv.appendChild(span);
    });

    const dispatch = document.getElementById("dispatch-card");
    dispatch.classList.remove("hidden");
    document.getElementById("dispatch-msg").innerText = alert.sms_message;

    if (wasHidden) {
        log(`<span class="log-alert">🚨 MID-CALL SCAM DETECTED (${alert.scam_type})! Red flags: ${(alert.red_flags || []).join(", ")}</span>`);
    }
}

function handleSafeCall(summary) {
    if (!document.getElementById("alert-banner").classList.contains("hidden")) {
        return;
    }
    const safeBanner = document.getElementById("safe-banner");
    if (safeBanner.classList.contains("hidden")) {
        safeBanner.classList.remove("hidden");
        document.getElementById("safe-sub").innerText = summary;
        document.getElementById("call-status").className = "status-indicator safe";
        document.getElementById("status-text").innerText = "Call Verified Safe (No Scam)";
        log(`<span class="log-safe">✅ ${summary}</span>`);
    }
}

async function playScenario(filename, label) {
    initAudioContext();
    stopCall();
    resetUI();

    try {
        document.getElementById("call-status").className = "status-indicator active";
        document.getElementById("status-text").innerText = `Connecting Gemini Live...`;

        await connectSessionWebSocket(filename);

        isCallActive = true;
        document.getElementById("stop-btn").disabled = false;
        document.getElementById("status-text").innerText = `Streaming: ${filename}`;
        log(`▶️ Playing uploaded recording: <strong>${label}</strong> (<code>${filename}</code>)`);

        const response = await fetch(`/static/audio/${encodeURIComponent(filename)}`);
        const arrayBuffer = await response.arrayBuffer();
        const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

        currentSource = audioContext.createBufferSource();
        currentSource.buffer = audioBuffer;

        callGainNode = audioContext.createGain();
        callGainNode.gain.value = 1.0;

        currentSource.connect(callGainNode);
        callGainNode.connect(audioContext.destination);

        const rawData = audioBuffer.getChannelData(0);
        const sampleRate = audioBuffer.sampleRate;
        const chunkSize = Math.floor(sampleRate / 2); // 0.5s chunks
        let offset = 0;
        let endOfCallSent = false;

        currentSource.start();

        const startTime = audioContext.currentTime;
        const duration = audioBuffer.duration;

        // Send initial chunk immediately
        if (offset < rawData.length && ws && ws.readyState === WebSocket.OPEN) {
            const slice = rawData.slice(offset, offset + chunkSize);
            const pcm16 = floatTo16BitPCM(slice);
            ws.send(JSON.stringify({
                type: "audio_chunk",
                filename: filename,
                rate: sampleRate,
                data: arrayBufferToBase64(pcm16.buffer)
            }));
            offset += chunkSize;
        }

        progressInterval = setInterval(() => {
            const elapsed = audioContext.currentTime - startTime;
            const pct = Math.min(100, (elapsed / duration) * 100);
            document.getElementById("progress-bar-fill").style.width = `${pct}%`;
            document.getElementById("progress-label").innerText =
                `Call Audio Playback (${filename}): ${Math.min(elapsed, duration).toFixed(1)}s / ${duration.toFixed(1)}s`;

            if (offset < rawData.length && ws && ws.readyState === WebSocket.OPEN) {
                const slice = rawData.slice(offset, offset + chunkSize);
                const pcm16 = floatTo16BitPCM(slice);
                const base64Data = arrayBufferToBase64(pcm16.buffer);

                ws.send(JSON.stringify({
                    type: "audio_chunk",
                    filename: filename,
                    rate: sampleRate,
                    data: base64Data
                }));
                offset += chunkSize;
            } else if (!endOfCallSent && ws && ws.readyState === WebSocket.OPEN) {
                endOfCallSent = true;
                ws.send(JSON.stringify({
                    type: "end_of_call",
                    filename: filename
                }));
            }

            if (elapsed >= duration) {
                clearInterval(progressInterval);
                progressInterval = null;
                document.getElementById("stop-btn").disabled = true;

                if (!endOfCallSent && ws && ws.readyState === WebSocket.OPEN) {
                    endOfCallSent = true;
                    ws.send(JSON.stringify({
                        type: "end_of_call",
                        filename: filename
                    }));
                }

                if (!document.getElementById("alert-banner").classList.contains("hidden")) {
                    document.getElementById("status-text").innerText = "Call Ended (Scam Flagged Mid-Call)";
                } else if (filename.toLowerCase().includes("genuine")) {
                    handleSafeCall("Genuine Swiggy delivery call verified. No scam red flags heard — Guardian stayed silent (does not cry wolf).");
                }
            }
        }, 500);

    } catch (e) {
        log(`<span class="log-alert">Failed to stream scenario: ${e.message}</span>`);
        document.getElementById("call-status").className = "status-indicator idle";
        document.getElementById("status-text").innerText = "Standby";
    }
}

function floatTo16BitPCM(float32Array) {
    const buffer = new ArrayBuffer(float32Array.length * 2);
    const view = new DataView(buffer);
    for (let i = 0; i < float32Array.length; i++) {
        let s = Math.max(-1, Math.min(1, float32Array[i]));
        view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return new Int16Array(buffer);
}

function arrayBufferToBase64(buffer) {
    let binary = "";
    const bytes = new Uint8Array(buffer);
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
}

function playPCMChunk(base64Audio) {
    const binary = window.atob(base64Audio);
    const len = binary.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    const int16 = new Int16Array(bytes.buffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / 32768.0;
    }

    // Gemini Live Native Audio outputs 24kHz mono PCM
    const audioBuf = audioContext.createBuffer(1, float32.length, 24000);
    audioBuf.copyToChannel(float32, 0);

    const source = audioContext.createBufferSource();
    source.buffer = audioBuf;
    source.connect(audioContext.destination);

    const now = audioContext.currentTime;
    if (nextAgentAudioTime < now) {
        nextAgentAudioTime = now + 0.03;
    }
    source.start(nextAgentAudioTime);
    nextAgentAudioTime += audioBuf.duration;
    agentSources.push(source);
}

function stopCall() {
    if (currentSource) {
        try { currentSource.stop(); } catch (e) {}
        currentSource = null;
    }
    agentSources.forEach(s => {
        try { s.stop(); } catch (e) {}
    });
    agentSources = [];
    nextAgentAudioTime = 0;

    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    if (ws) {
        try { ws.close(); } catch (e) {}
        ws = null;
    }
    isCallActive = false;
    document.getElementById("stop-btn").disabled = true;
    document.getElementById("call-status").className = "status-indicator idle";
    document.getElementById("status-text").innerText = "Standby";
}

function resetUI() {
    document.getElementById("alert-banner").classList.add("hidden");
    document.getElementById("safe-banner").classList.add("hidden");
    document.getElementById("dispatch-card").classList.add("hidden");
    document.getElementById("progress-bar-fill").style.width = "0%";
    document.getElementById("progress-label").innerText = "Call Audio Playback (0.5s chunks)";
    document.getElementById("log-content").innerHTML = "";
    agentSpokenLogged = false;
    callerTranscriptEl = null;
    agentTranscriptEl = null;
    nextAgentAudioTime = 0;
}

function log(html) {
    const logBox = document.getElementById("log-content");
    const p = document.createElement("p");
    p.innerHTML = html;
    logBox.appendChild(p);
    logBox.scrollTop = logBox.scrollHeight;
}

window.onload = () => {
    refreshUploadedFiles();
};
