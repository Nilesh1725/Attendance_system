// Main JavaScript for AutoAttendance System

class AutoAttendance {
    constructor() {
        this.init();
    }

    init() {
        this.initTooltips();
        this.initEventListeners();
        this.checkBrowserCompatibility();
    }

    initTooltips() {
        // Initialize Bootstrap tooltips
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }

    initEventListeners() {
        // Global event listeners
        document.addEventListener('click', this.handleGlobalClick.bind(this));
    }

    handleGlobalClick(e) {
        // Handle global click events if needed
    }

    checkBrowserCompatibility() {
        const incompatibleFeatures = [];
        
        // Enhanced media devices check with fallbacks
        if (typeof navigator === 'undefined' || !navigator.mediaDevices) {
            incompatibleFeatures.push('Camera/Microphone Access - MediaDevices API not available');
        } else if (typeof navigator.mediaDevices.getUserMedia === 'undefined') {
            incompatibleFeatures.push('Camera/Microphone Access - getUserMedia not supported');
        }
        
        if (typeof MediaRecorder === 'undefined') {
            incompatibleFeatures.push('Audio Recording - MediaRecorder not supported');
        }
        
        // Check if we're on HTTPS (required for media devices)
        if (location.protocol !== 'https:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
            incompatibleFeatures.push('HTTPS Required - Camera/Microphone require secure connection');
        }
        
        if (incompatibleFeatures.length > 0) {
            this.showBrowserWarning(incompatibleFeatures);
        } else {
            console.log('✅ All required browser features are supported');
        }
    }

    showBrowserWarning(features) {
        const warningHtml = `
            <div class="alert alert-warning alert-dismissible fade show" role="alert">
                <h5><i class="fas fa-exclamation-triangle"></i> Browser Compatibility Warning</h5>
                <p class="mb-2">Your browser may not fully support the following features:</p>
                <ul class="mb-2">
                    ${features.map(feature => `<li>${feature}</li>`).join('')}
                </ul>
                <p class="mb-0"><strong>Solution:</strong> Use Chrome/Firefox/Edge with HTTPS, or enable camera/mic permissions.</p>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        // Insert at the beginning of main content
        const main = document.querySelector('main');
        if (main) {
            main.insertAdjacentHTML('afterbegin', warningHtml);
        }
    }

    // Utility method to show notifications
    static showNotification(message, type = 'info', duration = 5000) {
        const alertClass = {
            'success': 'alert-success',
            'error': 'alert-danger',
            'warning': 'alert-warning',
            'info': 'alert-info'
        }[type] || 'alert-info';

        const notificationHtml = `
            <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;

        // Create notifications container if it doesn't exist
        let container = document.getElementById('notifications-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'notifications-container';
            container.className = 'position-fixed top-0 end-0 p-3';
            container.style.zIndex = '1050';
            document.body.appendChild(container);
        }

        // Add notification
        container.insertAdjacentHTML('beforeend', notificationHtml);

        // Auto remove after duration
        if (duration > 0) {
            setTimeout(() => {
                const alerts = container.querySelectorAll('.alert');
                if (alerts.length > 0) {
                    const alert = alerts[alerts.length - 1];
                    if (alert.parentNode) {
                        alert.parentNode.removeChild(alert);
                    }
                }
            }, duration);
        }
    }

    // Utility method for API calls
    static async apiCall(url, options = {}) {
        try {
            const response = await fetch(url, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API call failed:', error);
            this.showNotification('Network error occurred. Please try again.', 'error');
            throw error;
        }
    }

    // Utility method to format date
    static formatDate(date, format = 'datetime') {
        const d = new Date(date);
        const options = {
            date: { year: 'numeric', month: 'short', day: 'numeric' },
            time: { hour: '2-digit', minute: '2-digit' },
            datetime: { 
                year: 'numeric', 
                month: 'short', 
                day: 'numeric',
                hour: '2-digit', 
                minute: '2-digit'
            }
        }[format] || options.datetime;

        return d.toLocaleDateString('en-US', options);
    }

    // Utility method to debounce function calls
    static debounce(func, wait, immediate) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                timeout = null;
                if (!immediate) func(...args);
            };
            const callNow = immediate && !timeout;
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
            if (callNow) func(...args);
        };
    }
}

// Enhanced Media Utilities with Fallbacks and HTTPS support
class MediaUtils {
    static async checkMediaSupport() {
        const support = {
            camera: false,
            microphone: false,
            audioRecording: false,
            https: location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1',
            audioFormats: {
                wav: false,
                webm: false,
                mp4: false
            }
        };

        // Check if mediaDevices is available
        if (typeof navigator === 'undefined' || !navigator.mediaDevices) {
            console.error('navigator.mediaDevices is not available');
            return support;
        }

        try {
            // Check camera support
            if (navigator.mediaDevices.getUserMedia) {
                const cameraStream = await navigator.mediaDevices.getUserMedia({ video: true }).catch(() => null);
                if (cameraStream) {
                    support.camera = true;
                    cameraStream.getTracks().forEach(track => track.stop());
                }
            }

            // Check microphone support
            if (navigator.mediaDevices.getUserMedia) {
                const micStream = await navigator.mediaDevices.getUserMedia({ audio: true }).catch(() => null);
                if (micStream) {
                    support.microphone = true;
                    micStream.getTracks().forEach(track => track.stop());
                }
            }

            // Check audio recording support and formats
            support.audioRecording = typeof MediaRecorder !== 'undefined';
            
            if (support.audioRecording) {
                // Check supported audio formats
                const formats = [
                    'audio/wav',
                    'audio/webm',
                    'audio/webm; codecs=opus',
                    'audio/mp4',
                    'audio/mp4; codecs=mp4a.40.2'
                ];
                
                formats.forEach(format => {
                    try {
                        if (MediaRecorder.isTypeSupported(format)) {
                            if (format.includes('wav')) support.audioFormats.wav = true;
                            if (format.includes('webm')) support.audioFormats.webm = true;
                            if (format.includes('mp4')) support.audioFormats.mp4 = true;
                            console.log(`✅ Supported audio format: ${format}`);
                        }
                    } catch (e) {
                        console.log(`❌ Audio format not supported: ${format}`);
                    }
                });
            }

        } catch (error) {
            console.error('Error checking media support:', error);
        }

        return support;
    }

    static async getCameraStream() {
        if (typeof navigator === 'undefined' || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error('Camera API not supported in this browser. Please use Chrome, Firefox, or Edge with HTTPS.');
        }

        // Check if we're on a secure context
        if (!this.isSecureContext()) {
            throw new Error('Camera access requires HTTPS. Please access this site via HTTPS.');
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    facingMode: 'user'
                },
                audio: false
            });
            return stream;
        } catch (error) {
            let message = 'Camera access failed: ';
            switch (error.name) {
                case 'NotAllowedError':
                    message += 'Permission denied. Please allow camera access in your browser settings.';
                    break;
                case 'NotFoundError':
                    message += 'No camera found. Please connect a camera.';
                    break;
                case 'NotSupportedError':
                    message += 'Camera not supported.';
                    break;
                case 'NotReadableError':
                    message += 'Camera is already in use by another application.';
                    break;
                case 'SecurityError':
                    message += 'Camera access blocked for security reasons. Use HTTPS.';
                    break;
                default:
                    message += error.message;
            }
            throw new Error(message);
        }
    }

    static async getMicrophoneStream() {
        if (typeof navigator === 'undefined' || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error('Microphone API not supported in this browser. Please use Chrome, Firefox, or Edge with HTTPS.');
        }

        // Check if we're on a secure context
        if (!this.isSecureContext()) {
            throw new Error('Microphone access requires HTTPS. Please access this site via HTTPS.');
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 44100,
                    channelCount: 1,
                    autoGainControl: true
                },
                video: false
            });
            return stream;
        } catch (error) {
            let message = 'Microphone access failed: ';
            switch (error.name) {
                case 'NotAllowedError':
                    message += 'Permission denied. Please allow microphone access in your browser settings.';
                    break;
                case 'NotFoundError':
                    message += 'No microphone found. Please connect a microphone.';
                    break;
                case 'NotSupportedError':
                    message += 'Microphone not supported.';
                    break;
                case 'SecurityError':
                    message += 'Microphone access blocked for security reasons. Use HTTPS.';
                    break;
                default:
                    message += error.message;
            }
            throw new Error(message);
        }
    }

    static isSecureContext() {
        return location.protocol === 'https:' || 
               location.hostname === 'localhost' || 
               location.hostname === '127.0.0.1';
    }

    static stopStream(stream) {
        if (stream) {
            stream.getTracks().forEach(track => {
                track.stop();
            });
        }
    }

    static createMediaRecorder(stream, preferredFormat = 'wav') {
        if (typeof MediaRecorder === 'undefined') {
            throw new Error('Audio recording not supported in this browser.');
        }

        // Try different formats in order of preference
        const formatPreferences = [];
        
        if (preferredFormat === 'wav') {
            formatPreferences.push(
                'audio/wav',
                'audio/webm; codecs=1', // WebM with PCM (WAV-like)
                'audio/webm; codecs=opus',
                'audio/webm',
                '' // Default format
            );
        } else {
            formatPreferences.push(
                'audio/webm; codecs=opus',
                'audio/webm',
                'audio/wav',
                'audio/webm; codecs=1',
                '' // Default format
            );
        }

        for (const format of formatPreferences) {
            try {
                const options = format ? { mimeType: format } : {};
                const recorder = new MediaRecorder(stream, options);
                console.log(`✅ Using audio format: ${format || 'default'}`);
                return recorder;
            } catch (e) {
                console.log(`❌ Audio format not supported: ${format}`);
                continue;
            }
        }

        // Last resort: use default MediaRecorder
        console.warn('No specific format worked, using default MediaRecorder');
        return new MediaRecorder(stream);
    }

    static getSupportedAudioFormat() {
        // Check which audio formats are supported
        const formats = [
            'audio/wav',
            'audio/webm; codecs=opus',
            'audio/webm',
            'audio/mp4'
        ];

        for (const format of formats) {
            try {
                if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(format)) {
                    return format;
                }
            } catch (e) {
                continue;
            }
        }
        return ''; // Default format
    }

    static async playAudioBlob(blob) {
        return new Promise((resolve, reject) => {
            const audio = new Audio();
            audio.src = URL.createObjectURL(blob);
            audio.onended = () => {
                URL.revokeObjectURL(audio.src);
                resolve();
            };
            audio.onerror = reject;
            audio.play().catch(reject);
        });
    }
}

// Audio Recording Manager for consistent format handling
class AudioRecorder {
    constructor() {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.stream = null;
        this.recordingFormat = 'wav';
        this.recordingStartTime = null;
        this.minRecordingTime = 2000; // 2 seconds minimum
        this.maxRecordingTime = 10000; // 10 seconds maximum
    }

    async startRecording(preferredFormat = 'wav') {
        try {
            this.stream = await MediaUtils.getMicrophoneStream();
            this.mediaRecorder = MediaUtils.createMediaRecorder(this.stream, preferredFormat);
            this.audioChunks = [];
            this.recordingFormat = this.getFormatFromMimeType(this.mediaRecorder.mimeType);
            this.recordingStartTime = Date.now();

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.start();
            console.log(`🎤 Recording started with format: ${this.mediaRecorder.mimeType}`);
            
            // Auto-stop after maximum time to prevent overly long recordings
            setTimeout(() => {
                if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
                    console.log('🛑 Auto-stopping recording after maximum time');
                    this.stopRecording();
                }
            }, this.maxRecordingTime);
            
            return true;
        } catch (error) {
            console.error('Error starting recording:', error);
            throw error;
        }
    }

    stopRecording() {
        return new Promise((resolve) => {
            if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
                const recordingDuration = Date.now() - this.recordingStartTime;
                
                this.mediaRecorder.onstop = () => {
                    const blob = new Blob(this.audioChunks, { 
                        type: this.mediaRecorder.mimeType || 'audio/wav' 
                    });
                    
                    console.log(`🎤 Recording stopped after ${recordingDuration}ms`);
                    
                    // Check if recording meets minimum duration
                    if (recordingDuration < this.minRecordingTime) {
                        console.warn(`⚠️ Recording too short: ${recordingDuration}ms (minimum: ${this.minRecordingTime}ms)`);
                        resolve({
                            blob: blob,
                            format: this.recordingFormat,
                            mimeType: this.mediaRecorder.mimeType,
                            size: blob.size,
                            duration: recordingDuration,
                            valid: false,
                            error: `Recording too short: ${(recordingDuration/1000).toFixed(1)}s. Please record for at least ${(this.minRecordingTime/1000).toFixed(1)} seconds.`
                        });
                    } else {
                        resolve({
                            blob: blob,
                            format: this.recordingFormat,
                            mimeType: this.mediaRecorder.mimeType,
                            size: blob.size,
                            duration: recordingDuration,
                            valid: true
                        });
                    }
                    
                    // Stop the stream
                    if (this.stream) {
                        MediaUtils.stopStream(this.stream);
                    }
                };
                
                this.mediaRecorder.stop();
            } else {
                resolve(null);
            }
        });
    }

    getFormatFromMimeType(mimeType) {
        if (!mimeType) return 'wav';
        
        if (mimeType.includes('wav')) return 'wav';
        if (mimeType.includes('webm')) return 'webm';
        if (mimeType.includes('mp4')) return 'mp4';
        
        return 'wav'; // Default to wav
    }

    getFileExtension() {
        switch (this.recordingFormat) {
            case 'wav': return 'wav';
            case 'webm': return 'webm';
            case 'mp4': return 'mp4';
            default: return 'wav';
        }
    }

    cancelRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
            this.mediaRecorder.stop();
        }
        if (this.stream) {
            MediaUtils.stopStream(this.stream);
        }
        this.audioChunks = [];
    }

    getRecordingTime() {
        if (this.recordingStartTime) {
            return Date.now() - this.recordingStartTime;
        }
        return 0;
    }
}

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    window.autoAttendance = new AutoAttendance();
    
    // Check media support on load
    MediaUtils.checkMediaSupport().then(support => {
        console.log('Media support check:', support);
        
        // Update browser support message
        const supportElement = document.getElementById('browserSupport');
        const supportMessage = document.getElementById('supportMessage');
        
        if (supportElement && supportMessage) {
            if (!support.https && !support.camera) {
                supportMessage.textContent = '⚠️ Camera/Microphone access requires HTTPS. Please use HTTPS for full functionality.';
                supportElement.className = 'alert alert-warning';
            } else if (support.camera && support.microphone) {
                supportMessage.textContent = '✅ Your browser supports all required features!';
                supportElement.className = 'alert alert-success';
            } else {
                supportMessage.textContent = '⚠️ Some features may not work properly. Please use Chrome/Firefox/Edge with HTTPS.';
                supportElement.className = 'alert alert-warning';
            }
            supportElement.style.display = 'block';
        }
    });
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AutoAttendance, MediaUtils, AudioRecorder };
}