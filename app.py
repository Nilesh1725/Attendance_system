from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_mysqldb import MySQL
import face_recognition
import cv2
import numpy as np
import speech_recognition as sr
import os
import base64
from datetime import datetime, timedelta
import hashlib
import json
from config import config
import io
import wave
import audioop
from sklearn.metrics.pairwise import cosine_similarity
import librosa
import tempfile
import ssl
import subprocess
import shutil

app = Flask(__name__)
app.config.from_object(config['development'])

# Force HTTPS in production
@app.before_request
def force_https():
    if request.headers.get('X-Forwarded-Proto') == 'http':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)

mysql = MySQL(app)

class AudioProcessor:
    @staticmethod
    def convert_webm_to_wav(webm_data):
        """Convert WebM audio to WAV format using pydub or fallback methods"""
        try:
            from pydub import AudioSegment
            
            # Create temporary files
            with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as webm_file:
                webm_file.write(webm_data)
                webm_path = webm_file.name
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as wav_file:
                wav_path = wav_file.name
            
            # Convert using pydub
            audio = AudioSegment.from_file(webm_path, format="webm")
            
            # Check audio length
            duration = len(audio) / 1000.0  # Convert to seconds
            print(f"DEBUG - Audio duration: {duration:.2f} seconds")
            
            if duration < 1.0:
                raise Exception(f"Audio too short: {duration:.2f} seconds. Please record at least 2 seconds.")
            
            audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
            audio.export(wav_path, format="wav")
            
            # Read the converted WAV data
            with open(wav_path, 'rb') as f:
                wav_data = f.read()
            
            # Clean up temp files
            os.unlink(webm_path)
            os.unlink(wav_path)
            
            return wav_data
            
        except ImportError:
            # Fallback: Try using ffmpeg if available
            return AudioProcessor.convert_with_ffmpeg(webm_data)
        except Exception as e:
            print(f"Pydub conversion failed: {e}")
            # Final fallback
            return AudioProcessor.convert_with_ffmpeg(webm_data)
    
    @staticmethod
    def convert_with_ffmpeg(webm_data):
        """Convert using ffmpeg command line tool"""
        try:
            # Create temporary files
            with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as webm_file:
                webm_file.write(webm_data)
                webm_path = webm_file.name
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as wav_file:
                wav_path = wav_file.name
            
            # Use ffmpeg to convert and check duration
            cmd = [
                'ffmpeg', '-i', webm_path,
                '-acodec', 'pcm_s16le',
                '-ac', '1',
                '-ar', '16000',
                '-y', wav_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Check audio duration using ffprobe
                duration_cmd = [
                    'ffprobe', '-i', wav_path,
                    '-show_entries', 'format=duration',
                    '-v', 'quiet', '-of', 'csv=p=0'
                ]
                
                duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
                if duration_result.returncode == 0:
                    duration = float(duration_result.stdout.strip())
                    print(f"DEBUG - Audio duration: {duration:.2f} seconds")
                    
                    if duration < 1.0:
                        raise Exception(f"Audio too short: {duration:.2f} seconds. Please record at least 2 seconds.")
                
                with open(wav_path, 'rb') as f:
                    wav_data = f.read()
                
                os.unlink(webm_path)
                os.unlink(wav_path)
                return wav_data
            else:
                raise Exception(f"FFmpeg conversion failed: {result.stderr}")
                
        except Exception as e:
            print(f"FFmpeg conversion failed: {e}")
            # Last resort: create a simple WAV header
            return AudioProcessor.create_basic_wav(webm_data)
    
    @staticmethod
    def create_basic_wav(audio_data):
        """Create a basic WAV file from raw audio data (fallback)"""
        try:
            # This is a simplified approach - in production, use proper conversion
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as wav_file:
                # Create a simple WAV file with the audio data
                wav_file.write(audio_data)
                wav_path = wav_file.name
            
            with open(wav_path, 'rb') as f:
                wav_data = f.read()
            
            os.unlink(wav_path)
            return wav_data
        except Exception as e:
            print(f"Basic WAV creation failed: {e}")
            return None

    @staticmethod
    def check_audio_duration(audio_data):
        """Check if audio meets minimum duration requirement"""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                temp_file.write(audio_data)
                temp_path = temp_file.name
            
            # Try to get duration using wave module
            try:
                with wave.open(temp_path, 'rb') as wav_file:
                    frames = wav_file.getnframes()
                    rate = wav_file.getframerate()
                    duration = frames / float(rate)
                    print(f"DEBUG - Audio duration check: {duration:.2f} seconds")
                    
                    if duration < 2.0:
                        raise Exception(f"Audio too short: {duration:.2f} seconds. Please record at least 2 seconds.")
                    
                    return duration
            except:
                # If wave can't read it, try librosa
                y, sr = librosa.load(temp_path, sr=None)
                duration = len(y) / sr
                print(f"DEBUG - Audio duration check (librosa): {duration:.2f} seconds")
                
                if duration < 2.0:
                    raise Exception(f"Audio too short: {duration:.2f} seconds. Please record at least 2 seconds.")
                
                return duration
                
        except Exception as e:
            print(f"Audio duration check failed: {e}")
            raise e
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

class VoiceVerification:
    @staticmethod
    def extract_audio_features(audio_data):
        """Extract basic audio features for voice verification"""
        try:
            print("DEBUG - Starting audio feature extraction...")
            
            # First check audio duration
            duration = AudioProcessor.check_audio_duration(audio_data)
            print(f"DEBUG - Audio duration: {duration:.2f} seconds")
            
            # First try to process as WAV
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                    temp_file.write(audio_data)
                    temp_path = temp_file.name
                
                y, sr = librosa.load(temp_path, sr=None)
                os.unlink(temp_path)
                
            except Exception as e:
                print(f"DEBUG - Direct WAV loading failed, trying conversion: {e}")
                # If direct loading fails, try to convert
                converted_data = AudioProcessor.convert_webm_to_wav(audio_data)
                if converted_data:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                        temp_file.write(converted_data)
                        temp_path = temp_file.name
                    
                    y, sr = librosa.load(temp_path, sr=None)
                    os.unlink(temp_path)
                else:
                    raise Exception("Audio conversion failed")
            
            # Extract features
            print(f"DEBUG - Audio loaded: {len(y)} samples, {sr} Hz sample rate")
            
            # Extract more robust features for short audio
            mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20, n_fft=2048, hop_length=512)
            mfcc_mean = np.mean(mfcc, axis=1)
            
            # Also extract other features for better short audio handling
            spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
            spectral_centroid_mean = np.mean(spectral_centroid)
            
            # Combine features
            combined_features = np.concatenate([mfcc_mean, [spectral_centroid_mean]])
            
            print(f"DEBUG - Feature extraction complete: {len(combined_features)} features")
            
            return combined_features.tobytes()
        except Exception as e:
            print(f"DEBUG - Error extracting audio features: {e}")
            return None

    @staticmethod
    def compare_voice_features(feature1, feature2):
        """Compare two voice features using cosine similarity"""
        try:
            feat1 = np.frombuffer(feature1, dtype=np.float64)
            feat2 = np.frombuffer(feature2, dtype=np.float64)
            
            min_len = min(len(feat1), len(feat2))
            feat1 = feat1[:min_len].reshape(1, -1)
            feat2 = feat2[:min_len].reshape(1, -1)
            
            similarity = cosine_similarity(feat1, feat2)[0][0]
            print(f"DEBUG - Voice similarity score: {similarity:.3f}")
            
            return similarity
        except Exception as e:
            print(f"DEBUG - Error comparing voice features: {e}")
            return 0

def get_db_connection():
    return mysql.connection

def init_database():
    """Initialize database tables"""
    try:
        cur = get_db_connection().cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                face_encoding BLOB NOT NULL,
                voice_features BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_name (name)
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                verification_method VARCHAR(50),
                confidence_score FLOAT,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                INDEX idx_timestamp (timestamp),
                INDEX idx_student_id (student_id)
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS attendance_reports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                report_date DATE,
                report_text TEXT,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_report_date (report_date)
            )
        """)
        
        get_db_connection().commit()
        cur.close()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Error initializing database: {e}")

@app.route('/')
def index():
    """Home page with system overview"""
    try:
        cur = get_db_connection().cursor()
        
        cur.execute("SELECT COUNT(*) as total FROM students")
        total_students = cur.fetchone()['total']
        
        cur.execute("""
            SELECT COUNT(DISTINCT student_id) as today_count 
            FROM attendance 
            WHERE DATE(timestamp) = CURDATE()
        """)
        today_attendance = cur.fetchone()['today_count']
        
        cur.execute("""
            SELECT s.name, a.timestamp 
            FROM attendance a 
            JOIN students s ON a.student_id = s.id 
            ORDER BY a.timestamp DESC 
            LIMIT 5
        """)
        recent_attendance = cur.fetchall()
        
        cur.close()
        
        return render_template('index.html', 
                             total_students=total_students,
                             today_attendance=today_attendance,
                             recent_attendance=recent_attendance)
    except Exception as e:
        flash(f"Error loading dashboard: {str(e)}", "error")
        return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register_student():
    """Register new student with face and voice"""
    if request.method == 'POST':
        try:
            name = request.form['name'].strip()
            if not name:
                return jsonify({'success': False, 'message': 'Name is required.'})
            
            face_image_data = request.form.get('face_image_data')
            if not face_image_data:
                return jsonify({'success': False, 'message': 'Face image is required.'})
            
            face_image_data = face_image_data.split(',')[1]
            face_image_bytes = base64.b64decode(face_image_data)
            
            nparr = np.frombuffer(face_image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                return jsonify({'success': False, 'message': 'Invalid image data.'})
            
            rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            face_encodings = face_recognition.face_encodings(rgb_img)
            
            if not face_encodings:
                return jsonify({'success': False, 'message': 'No face detected. Please ensure your face is clearly visible.'})
            
            face_encoding = face_encodings[0]
            print(f"DEBUG - Face encoding extracted: {len(face_encoding)} dimensions")
            
            voice_data = request.files.get('voice_data')
            if not voice_data:
                return jsonify({'success': False, 'message': 'Voice recording is required.'})
            
            # Read the audio data
            audio_bytes = voice_data.read()
            print(f"DEBUG - Audio data received: {len(audio_bytes)} bytes")
            
            # Process audio with speech recognition
            recognizer = sr.Recognizer()
            spoken_name = ""
            
            try:
                # Try direct processing first
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                        temp_file.write(audio_bytes)
                        temp_path = temp_file.name
                    
                    with sr.AudioFile(temp_path) as source:
                        # Adjust for ambient noise and use longer audio
                        recognizer.adjust_for_ambient_noise(source, duration=0.5)
                        audio_data = recognizer.record(source)
                        spoken_name = recognizer.recognize_google(audio_data).lower().strip()
                    
                    os.unlink(temp_path)
                    
                except Exception as e:
                    print(f"DEBUG - Direct audio processing failed, trying conversion: {e}")
                    # Convert WebM to WAV
                    converted_audio = AudioProcessor.convert_webm_to_wav(audio_bytes)
                    if converted_audio:
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                            temp_file.write(converted_audio)
                            temp_path = temp_file.name
                        
                        with sr.AudioFile(temp_path) as source:
                            recognizer.adjust_for_ambient_noise(source, duration=0.5)
                            audio_data = recognizer.record(source)
                            spoken_name = recognizer.recognize_google(audio_data).lower().strip()
                        
                        os.unlink(temp_path)
                    else:
                        raise Exception("Audio conversion failed")
                
                print(f"DEBUG - Spoken name: '{spoken_name}', Expected name: '{name.lower()}'")
                
                if spoken_name != name.lower():
                    return jsonify({
                        'success': False, 
                        'message': f'Spoken name "{spoken_name}" does not match typed name "{name}". Please try again.'
                    })
                    
            except sr.UnknownValueError:
                return jsonify({'success': False, 'message': 'Could not understand audio. Please speak clearly and for at least 2 seconds.'})
            except sr.RequestError as e:
                return jsonify({'success': False, 'message': f'Speech recognition service error: {str(e)}'})
            except Exception as e:
                return jsonify({'success': False, 'message': f'Audio processing error: {str(e)}'})
            
            # Extract voice features
            voice_features = VoiceVerification.extract_audio_features(audio_bytes)
            if not voice_features:
                return jsonify({'success': False, 'message': 'Could not process voice features. Please record audio for at least 2 seconds.'})
            
            cur = get_db_connection().cursor()
            
            cur.execute("SELECT id FROM students WHERE name = %s", (name,))
            if cur.fetchone():
                cur.close()
                return jsonify({'success': False, 'message': 'Student with this name already exists.'})
            
            cur.execute(
                "INSERT INTO students (name, face_encoding, voice_features) VALUES (%s, %s, %s)",
                (name, face_encoding.tobytes(), voice_features)
            )
            get_db_connection().commit()
            cur.close()
            
            return jsonify({'success': True, 'message': f'Student {name} registered successfully!'})
            
        except Exception as e:
            print(f"DEBUG - Registration error: {str(e)}")
            return jsonify({'success': False, 'message': f'Registration error: {str(e)}'})
    
    return render_template('register.html')

@app.route('/mark_attendance', methods=['GET', 'POST'])
def mark_attendance():
    """Mark attendance with dual verification"""
    if request.method == 'POST':
        try:
            face_image_data = request.form.get('face_image_data')
            if not face_image_data:
                return jsonify({'success': False, 'message': 'Face image is required.'})
            
            face_image_data = face_image_data.split(',')[1]
            face_image_bytes = base64.b64decode(face_image_data)
            
            nparr = np.frombuffer(face_image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                return jsonify({'success': False, 'message': 'Invalid image data.'})
            
            rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            face_encodings = face_recognition.face_encodings(rgb_img)
            
            if not face_encodings:
                return jsonify({'success': False, 'message': 'No face detected. Please ensure your face is clearly visible.'})
            
            captured_encoding = face_encodings[0]
            print(f"DEBUG - Captured face encoding: {len(captured_encoding)} dimensions")
            
            voice_data = request.files.get('voice_data')
            if not voice_data:
                return jsonify({'success': False, 'message': 'Voice recording is required.'})
            
            # Read audio data
            audio_bytes = voice_data.read()
            print(f"DEBUG - Attendance audio data: {len(audio_bytes)} bytes")
            
            recognizer = sr.Recognizer()
            spoken_name = ""
            
            try:
                # Try direct processing first
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                        temp_file.write(audio_bytes)
                        temp_path = temp_file.name
                    
                    with sr.AudioFile(temp_path) as source:
                        recognizer.adjust_for_ambient_noise(source, duration=0.5)
                        audio_data = recognizer.record(source)
                        spoken_name = recognizer.recognize_google(audio_data).lower().strip()
                    
                    os.unlink(temp_path)
                    
                except Exception as e:
                    print(f"DEBUG - Direct audio processing failed, trying conversion: {e}")
                    # Convert WebM to WAV
                    converted_audio = AudioProcessor.convert_webm_to_wav(audio_bytes)
                    if converted_audio:
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                            temp_file.write(converted_audio)
                            temp_path = temp_file.name
                        
                        with sr.AudioFile(temp_path) as source:
                            recognizer.adjust_for_ambient_noise(source, duration=0.5)
                            audio_data = recognizer.record(source)
                            spoken_name = recognizer.recognize_google(audio_data).lower().strip()
                        
                        os.unlink(temp_path)
                    else:
                        raise Exception("Audio conversion failed")
                        
                print(f"DEBUG - Spoken name for attendance: '{spoken_name}'")
                        
            except sr.UnknownValueError:
                return jsonify({'success': False, 'message': 'Could not understand audio. Please speak clearly and for at least 2 seconds.'})
            except sr.RequestError as e:
                return jsonify({'success': False, 'message': f'Speech recognition service error: {str(e)}'})
            except Exception as e:
                return jsonify({'success': False, 'message': f'Audio processing error: {str(e)}'})
            
            cur = get_db_connection().cursor()
            cur.execute("SELECT id, name, face_encoding, voice_features FROM students")
            students = cur.fetchall()
            
            best_match = None
            best_confidence = 0
            best_voice_similarity = 0
            best_face_confidence = 0
            
            print(f"DEBUG - Comparing with {len(students)} registered students")
            print(f"DEBUG - Spoken name to match: '{spoken_name}'")
            
            for student in students:
                student_id = student['id']
                db_name = student['name']
                db_encoding_blob = student['face_encoding']
                db_voice_features = student['voice_features']
                
                db_encoding = np.frombuffer(db_encoding_blob, dtype=np.float64)
                
                # Compare faces with tolerance
                face_distance = face_recognition.face_distance([db_encoding], captured_encoding)[0]
                face_confidence = 1 - face_distance
                
                print(f"DEBUG - Comparing with student: {db_name}")
                print(f"DEBUG - Face confidence: {face_confidence:.3f}")
                
                # Voice comparison - prioritize name matching first
                voice_similarity = 0
                name_matches = spoken_name == db_name.lower()
                print(f"DEBUG - Name matches: {name_matches}")
                
                if name_matches:
                    if db_voice_features:
                        current_voice_features = VoiceVerification.extract_audio_features(audio_bytes)
                        if current_voice_features:
                            voice_similarity = VoiceVerification.compare_voice_features(db_voice_features, current_voice_features)
                            print(f"DEBUG - Voice similarity: {voice_similarity:.3f}")
                    else:
                        # If no voice features but names match, give some credit
                        voice_similarity = 0.6
                        print(f"DEBUG - No voice features, using default similarity: {voice_similarity:.3f}")
                else:
                    print(f"DEBUG - Name doesn't match, skipping voice comparison")
                
                # Combined confidence score (more weight to face, less strict)
                combined_confidence = (face_confidence * 0.7) + (voice_similarity * 0.3)
                
                print(f"DEBUG - Combined confidence: {combined_confidence:.3f}")
                
                # MUCH LOWER THRESHOLD and require reasonable face match
                if (combined_confidence > best_confidence and 
                    combined_confidence > 0.3 and  # Lowered from 0.6 to 0.3
                    face_confidence > 0.4):        # Require at least some face match
                    
                    best_confidence = combined_confidence
                    best_match = student_id
                    best_voice_similarity = voice_similarity
                    best_face_confidence = face_confidence
                    
                    print(f"DEBUG - NEW BEST MATCH: Student {db_name}")
                    print(f"DEBUG - Best confidence: {best_confidence:.3f}")
            
            if best_match:
                # Record attendance
                cur.execute(
                    "INSERT INTO attendance (student_id, verification_method, confidence_score) VALUES (%s, %s, %s)",
                    (best_match, 'dual_verification', best_confidence)
                )
                get_db_connection().commit()
                cur.close()
                
                print(f"DEBUG - ATTENDANCE SUCCESS: Student ID {best_match}, Confidence: {best_confidence:.3f}")
                
                return jsonify({
                    'success': True, 
                    'message': f'Attendance marked successfully! Confidence: {best_confidence:.2%}',
                    'confidence': best_confidence
                })
            else:
                cur.close()
                print(f"DEBUG - ATTENDANCE FAILED: No match found. Best confidence was: {best_confidence:.3f}")
                return jsonify({
                    'success': False, 
                    'message': f'Verification failed. Best match confidence: {best_confidence:.2%} (needed >30%). Please ensure good lighting and speak clearly for 2+ seconds.'
                })
                
        except Exception as e:
            print(f"DEBUG - Attendance marking error: {str(e)}")
            return jsonify({'success': False, 'message': f'Attendance marking error: {str(e)}'})
    
    return render_template('attendance.html')

@app.route('/reports')
def reports():
    """Generate and display attendance reports"""
    try:
        report_text = generate_nlp_report()
        
        cur = get_db_connection().cursor()
        cur.execute(
            "INSERT INTO attendance_reports (report_date, report_text) VALUES (%s, %s)",
            (datetime.now().date(), report_text)
        )
        get_db_connection().commit()
        cur.close()
        
        return render_template('reports.html', report_text=report_text)
    except Exception as e:
        flash(f"Error generating reports: {str(e)}", "error")
        return render_template('reports.html', report_text="Error generating report.")

def generate_nlp_report():
    """Generate natural language summary of attendance data"""
    try:
        cur = get_db_connection().cursor()
        
        cur.execute("SELECT COUNT(*) as total FROM students")
        total_students = cur.fetchone()['total']
        
        cur.execute("""
            SELECT COUNT(DISTINCT student_id) as present_count 
            FROM attendance 
            WHERE DATE(timestamp) = CURDATE()
        """)
        present_today = cur.fetchone()['present_count']
        
        cur.execute("""
            SELECT DATE(timestamp) as date, COUNT(DISTINCT student_id) as daily_count
            FROM attendance 
            WHERE timestamp >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY DATE(timestamp)
            ORDER BY date
        """)
        weekly_data = cur.fetchall()
        
        cur.execute("""
            SELECT s.name, COUNT(a.id) as attendance_count
            FROM students s 
            LEFT JOIN attendance a ON s.id = a.student_id 
            AND a.timestamp >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            GROUP BY s.id, s.name
            ORDER BY attendance_count DESC
        """)
        student_attendance = cur.fetchall()
        
        cur.close()
        
        report_parts = []
        report_parts.append("📊 ATTENDANCE ANALYSIS REPORT")
        report_parts.append("=" * 50)
        report_parts.append(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        report_parts.append("")
        
        report_parts.append("📈 SUMMARY")
        report_parts.append(f"• Total Registered Students: {total_students}")
        report_parts.append(f"• Present Today: {present_today}/{total_students} ({present_today/total_students*100:.1f}%)")
        report_parts.append("")
        
        if weekly_data:
            report_parts.append("📅 WEEKLY TREND")
            for day in weekly_data:
                report_parts.append(f"• {day['date']}: {day['daily_count']} students")
            report_parts.append("")
        
        report_parts.append("👥 STUDENT PERFORMANCE (Last 30 days)")
        for student in student_attendance:
            name = student['name']
            count = student['attendance_count']
            percentage = (count / 30) * 100 if 30 > 0 else 0
            status = "Excellent" if percentage >= 90 else "Good" if percentage >= 70 else "Needs Improvement"
            report_parts.append(f"• {name}: {count} days ({percentage:.1f}%) - {status}")
        
        report_parts.append("")
        report_parts.append("💡 RECOMMENDATIONS")
        if present_today / total_students < 0.8:
            report_parts.append("• Attendance today is below 80%. Consider sending reminders.")
        
        low_attendance = [s for s in student_attendance if s['attendance_count'] < 15]
        if low_attendance:
            report_parts.append("• Students with low attendance (<50%):")
            for student in low_attendance[:3]:
                report_parts.append(f"  - {student['name']} ({student['attendance_count']} days)")
        
        return "\n".join(report_parts)
        
    except Exception as e:
        return f"Error generating report: {str(e)}"

@app.route('/api/students')
def api_students():
    """API endpoint to get all students"""
    try:
        cur = get_db_connection().cursor()
        cur.execute("SELECT id, name, created_at FROM students ORDER BY name")
        students = cur.fetchall()
        cur.close()
        return jsonify([dict(student) for student in students])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        init_database()

    try:
        print("🔒 Trying to start HTTPS server...")
        app.run(
            debug=True,
            host='0.0.0.0',
            port=5000,
            ssl_context=('cert.pem', 'key.pem')
        )
    except Exception as e:
        print(f"⚠️ SSL error: {e}")
        print("🔧 Running in HTTP mode instead.")
        app.run(debug=True, host='0.0.0.0', port=5000)