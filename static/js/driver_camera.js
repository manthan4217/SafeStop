// SafeRide AI Driver Camera Verification & Market Standalone Features (Voice Assist & Offline Queue)

class DriverCameraScanner {
    constructor(videoElementId, canvasElementId, tripId) {
        this.video = document.getElementById(videoElementId);
        this.canvas = document.getElementById(canvasElementId);
        this.tripId = tripId;
        this.stream = null;
        this.isScanning = false;

        // Initialize Speech Synthesis for Driver Hands-Free Voice Guidance
        this.synth = window.speechSynthesis || null;
        
        // Check for pending offline queue items on init
        this.checkAndSyncOfflineQueue();
    }

    async startCamera() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: "environment", width: { ideal: 640 }, height: { ideal: 480 } },
                audio: false
            });
            this.video.srcObject = this.stream;
            await this.video.play();
            console.log("Driver camera stream started successfully.");
            return true;
        } catch (err) {
            console.error("Error accessing camera:", err);
            alert("Unable to access smartphone camera. Please check camera permissions.");
            return false;
        }
    }

    stopCamera() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            console.log("Camera stream stopped.");
        }
    }

    captureFrameBase64() {
        if (!this.video || this.video.paused || this.video.ended) return null;
        
        const context = this.canvas.getContext('2d');
        this.canvas.width = this.video.videoWidth || 640;
        this.canvas.height = this.video.videoHeight || 480;
        context.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
        
        return this.canvas.toDataURL('image/jpeg', 0.85);
    }

    async scanAndVerify() {
        const frameB64 = this.captureFrameBase64();
        if (!frameB64) {
            return { status: 'ERROR', message: 'Camera feed not active' };
        }

        const resultDisplay = document.getElementById('scan-result-card');
        if (resultDisplay) {
            resultDisplay.className = 'glass-card p-3 mb-3 text-center border-info';
            resultDisplay.innerHTML = `<div class="spinner-border spinner-border-sm text-info me-2"></div> Extracting AI facial embeddings & verifying bus...`;
        }

        try {
            const response = await fetch('/driver/api/verify-face', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    image: frameB64,
                    trip_id: this.tripId
                })
            });

            const data = await response.json();
            this.handleScanResult(data);
            return data;
        } catch (err) {
            console.warn("Network unavailable. Switched to Driver Offline Queue Mode:", err);
            
            // Queue scan for background offline sync
            this.queueOfflineScan(frameB64);
            
            if (resultDisplay) {
                resultDisplay.className = 'glass-card p-3 mb-3 text-center border-warning bg-warning bg-opacity-10';
                resultDisplay.innerHTML = `
                    <div class="h6 text-warning fw-bold mb-1">📶 OFFLINE QUEUE MODE</div>
                    <div class="small text-muted">Scan saved locally in device memory. Will auto-sync when cellular signal returns.</div>
                `;
            }
            this.speakVoiceAlert("Scan queued offline. Will sync when online.");
        }
    }

    handleScanResult(data) {
        const resultDisplay = document.getElementById('scan-result-card');
        if (!resultDisplay) return;

        if (data.status === 'VERIFIED') {
            resultDisplay.className = 'glass-card p-3 mb-3 text-center border-success bg-success bg-opacity-10';
            resultDisplay.innerHTML = `
                <div class="h4 text-success fw-bold mb-1">✅ STUDENT VERIFIED</div>
                <div class="h5 text-white">${data.student_name} (${data.roll_number})</div>
                <div class="text-muted small">Confidence: ${data.confidence}% • Attendance Recorded</div>
            `;
            this.playAudioAlert('success');
            this.speakVoiceAlert(`Verified: ${data.student_name}`);
            setTimeout(() => window.location.reload(), 1800);

        } else if (data.status === 'WRONG_BUS') {
            resultDisplay.className = 'glass-card p-3 mb-3 text-center border-danger bg-danger bg-opacity-25 animate__animated animate__shakeX';
            resultDisplay.innerHTML = `
                <div class="h3 text-danger fw-bold mb-1">🚨 WRONG BUS DETECTED!</div>
                <div class="h4 text-white">${data.student_name}</div>
                <div class="badge bg-danger p-2 fs-6 my-2">Assigned to ${data.assigned_bus} • Boarded ${data.current_bus}</div>
                <div class="text-white-50 small">Critical safety alert dispatched to parent and transport admin.</div>
            `;
            this.playAudioAlert('danger');
            this.speakVoiceAlert(`Warning! Wrong Bus Detected! ${data.student_name} belongs on ${data.assigned_bus}`);

        } else if (data.status === 'ALREADY_BOARDED') {
            resultDisplay.className = 'glass-card p-3 mb-3 text-center border-warning bg-warning bg-opacity-10';
            resultDisplay.innerHTML = `
                <div class="h5 text-warning fw-bold mb-1">ℹ️ ALREADY MARKED PRESENT</div>
                <div class="text-white">${data.student_name} is already verified on this trip.</div>
            `;
            this.speakVoiceAlert(`${data.student_name} is already marked present.`);

        } else {
            resultDisplay.className = 'glass-card p-3 mb-3 text-center border-warning';
            resultDisplay.innerHTML = `
                <div class="h6 text-warning mb-1">⚠️ Face Unrecognized / Align Face</div>
                <div class="text-muted small">${data.message || 'Please position student face inside circle.'}</div>
            `;
        }
    }

    speakVoiceAlert(text) {
        if (!this.synth) return;
        try {
            this.synth.cancel(); // Stop current speech
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.rate = 1.0;
            utterance.pitch = 1.0;
            utterance.volume = 1.0;
            this.synth.speak(utterance);
        } catch (e) {
            console.log("Web Speech API voice assist error:", e);
        }
    }

    playAudioAlert(type) {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);

            if (type === 'success') {
                osc.frequency.setValueAtTime(587.33, ctx.currentTime);
                osc.frequency.setValueAtTime(880, ctx.currentTime + 0.1);
                gain.gain.setValueAtTime(0.2, ctx.currentTime);
                osc.start();
                osc.stop(ctx.currentTime + 0.3);
            } else if (type === 'danger') {
                osc.type = 'sawtooth';
                osc.frequency.setValueAtTime(300, ctx.currentTime);
                osc.frequency.setValueAtTime(150, ctx.currentTime + 0.2);
                gain.gain.setValueAtTime(0.4, ctx.currentTime);
                osc.start();
                osc.stop(ctx.currentTime + 0.5);
            }
        } catch (e) {
            console.log("Web Audio API error:", e);
        }
    }

    // Offline Queue LocalStorage Sync Engine
    queueOfflineScan(frameB64) {
        const queueKey = 'saferide_offline_queue';
        const existing = JSON.parse(localStorage.getItem(queueKey) || '[]');
        existing.push({
            trip_id: this.tripId,
            image: frameB64,
            timestamp: new Date().toISOString()
        });
        localStorage.setItem(queueKey, JSON.stringify(existing));
    }

    async checkAndSyncOfflineQueue() {
        const queueKey = 'saferide_offline_queue';
        const items = JSON.parse(localStorage.getItem(queueKey) || '[]');
        if (items.length === 0) return;

        console.log(`Flushing ${items.length} queued offline scan items to server...`);
        try {
            const resp = await fetch('/driver/api/sync-offline-queue', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ queue: items })
            });

            if (resp.ok) {
                localStorage.removeItem(queueKey);
                console.log("Offline queue synced successfully!");
            }
        } catch (e) {
            console.log("Server still unreachable for offline sync.");
        }
    }
}
