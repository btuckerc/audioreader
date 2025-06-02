#!/usr/bin/env python3
"""
Minimal local audiobook server with Whisper captioning and playlist player.

Folder layout
-------------
    app.py
    books/
        My Book/
            01.mp3
            02.mp3
            …

Install
-------
    pip install flask openai-whisper        # whisper CLI must be on PATH

Run
---
    python3 app.py   # then open http://localhost:8000
"""
from __future__ import annotations

import concurrent.futures
import datetime  # Added for timestamping speed results
import json
import os
import subprocess
import tempfile
import threading
import time
from functools import lru_cache
from pathlib import Path

from flask import (Flask, Response, jsonify, render_template, request,
                   send_from_directory, stream_with_context, url_for)

BASE   = Path(__file__).resolve().parent
BOOKS  = BASE / "books"
# SPEED_RATIOS_FILE is used to store speed ratios for model+settings combinations
SPEED_RATIOS_FILE = BASE / "speed_ratios.json"
MODEL  = "medium" # Default model for transcriptions and speed tests

_jobs: dict[tuple[str, str], subprocess.Popen] = {}
_lock = threading.Lock()

app = Flask(__name__, static_folder='static')

# ───────────────────────── helpers ────────────────────────────────
@lru_cache(maxsize=1)
def get_whisper_capabilities_cached():
    """Test Whisper capabilities by checking help output. Result is cached."""
    try:
        result = subprocess.run(['whisper', '--help'],
                               capture_output=True, text=True, timeout=10)
        help_text = result.stdout + result.stderr
        return {
            'word_timestamps_available': '--word_timestamps' in help_text,
            'highlight_words_available': '--highlight_words' in help_text,
            'installed': result.returncode == 0
        }
    except Exception as e:
        # Log the exception for server-side diagnosis
        app.logger.error(f"Error getting Whisper capabilities: {e}")
        return {
            'word_timestamps_available': False,
            'highlight_words_available': False,
            'installed': False
        }

def list_books() -> list[str]:
    return sorted(p.name for p in BOOKS.iterdir() if p.is_dir())

def list_mp3s(book: str) -> list[str]:
    return sorted(f.name for f in (BOOKS / book).glob("*.mp3"))

@lru_cache(None)
def caption_path(book: str, mp3: str) -> Path:
    return (BOOKS / book) / (Path(mp3).with_suffix(".vtt"))

def job_running(book: str, mp3: str) -> bool:
    with _lock:
        return (book, mp3) in _jobs

def has_word_timestamps(vtt_path: Path) -> bool:
    """Check if a VTT file contains word-level timestamps"""
    if not vtt_path.exists():
        return False

    try:
        content = vtt_path.read_text(encoding='utf-8')
        # Look for word-level timestamp markers in VTT format
        # Check for multiple word-level cues (indicating word-by-word timing)
        # or highlighted words with <u> tags or <c> tags
        lines = content.split('\n')
        word_level_indicators = 0

        for line in lines:
            # Count lines with word highlighting tags
            if '<u>' in line or '<c>' in line or '<c.highlight>' in line:
                word_level_indicators += 1
            # Count very short timestamp intervals (typical of word-level timing)
            elif '-->' in line:
                try:
                    parts = line.split('-->')
                    if len(parts) == 2:
                        start_str = parts[0].strip()
                        end_str = parts[1].strip()
                        # Parse timestamps (simplified)
                        start_time = float(start_str.split(':')[-1])
                        end_time = float(end_str.split(':')[-1])
                        # If the interval is very short (< 2 seconds), likely word-level
                        if 0 < (end_time - start_time) < 2.0:
                            word_level_indicators += 1
                except (ValueError, IndexError):
                    continue

        # Consider it word-level if we have multiple word-level indicators
        return word_level_indicators >= 3
    except Exception:
        return False

@lru_cache(maxsize=128) # Cache results for recently checked files
def get_audio_duration(audio_path: Path) -> float:
    """Get audio duration in seconds using ffprobe"""
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', str(audio_path)
        ], capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        app.logger.warning(f"ffprobe failed for {audio_path}, or timed out.")
    except Exception as e:
        app.logger.error(f"Error getting duration for {audio_path}: {e}")

    # Fallback: very rough estimate based on file size if ffprobe fails
    try:
        file_size_mb = audio_path.stat().st_size / (1024 * 1024)
        # Common bitrates for audiobooks are 64kbps-128kbps.
        # 128 kbps = 16 KB/s. 1 MB = 1024 KB. So 1MB is approx 1024/16 = 64 seconds.
        # Let's use a rough factor, e.g., 1MB ≈ 60 seconds (adjust if needed)
        estimated_duration = file_size_mb * 60
        app.logger.info(f"Estimating duration for {audio_path} by size: {estimated_duration:.2f}s")
        return estimated_duration
    except Exception as e:
        app.logger.error(f"Could not estimate duration by file size for {audio_path}: {e}")
        return 0.0 # Should not happen if file exists

def create_test_audio_clip(source_audio: Path, duration_seconds: int = 15) -> Path | None:
    """Create a short test clip from the beginning of an audio file"""
    temp_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
    temp_path = Path(temp_file.name)
    temp_file.close() # Close it so ffmpeg can write to it

    try:
        # Use ffmpeg to extract first N seconds
        cmd = [
            'ffmpeg', '-i', str(source_audio), '-t', str(duration_seconds),
            '-acodec', 'copy', str(temp_path), '-y', '-hide_banner', '-loglevel', 'error'
        ]
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if process.returncode != 0:
            app.logger.error(f"ffmpeg error creating test clip: {process.stderr}")
            if temp_path.exists(): temp_path.unlink()
            return None

        if temp_path.exists() and temp_path.stat().st_size > 0:
            return temp_path
        else: # pragma: no cover
            app.logger.error(f"ffmpeg created an empty test clip from {source_audio}")
            if temp_path.exists(): temp_path.unlink()
            return None

    except subprocess.TimeoutExpired:
        app.logger.error(f"ffmpeg timed out creating test clip from {source_audio}")
        if temp_path.exists(): temp_path.unlink()
        return None
    except FileNotFoundError: # pragma: no cover
        app.logger.error("ffmpeg not found. Cannot create test audio clip.")
        if temp_path.exists(): temp_path.unlink()
        return None
    except Exception as e: # pragma: no cover
        app.logger.error(f"Unexpected error creating test clip: {e}")
        if temp_path.exists(): temp_path.unlink()
        return None

def test_whisper_speed(test_audio_path: Path, model_to_test: str, test_settings: dict) -> dict:
    """Test Whisper transcription speed on a small audio sample.
    test_settings might include 'word_timestamps', 'highlighting' if these affect speed test.
    However, Whisper CLI for a single run doesn't change much based on these VTT generation flags.
    The primary factor is the model.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        capabilities = get_whisper_capabilities_cached()

        cmd = [
            "whisper", str(test_audio_path),
            "--model", model_to_test, # Use the specified model
            "--output_format", "vtt", # Minimal output, though VTT not strictly needed for speed test itself
            "--output_dir", str(temp_dir_path),
            "--fp16", "False", # Consistent setting
        ]
        # Add word_timestamps and highlight_words if they are part of test_settings and available
        # These flags mostly affect VTT content, not raw speed significantly for a single run,
        # but including them if specified for completeness of the tested configuration.
        if test_settings.get("word_timestamps", True) and capabilities['word_timestamps_available']:
            cmd.extend(["--word_timestamps", "True"])
            if test_settings.get("highlighting", True) and capabilities['highlight_words_available']:
                 cmd.extend(["--highlight_words", "True"])

        start_time = time.time()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120) # 2 min timeout
            end_time = time.time()

            processing_time = end_time - start_time
            audio_duration = get_audio_duration(test_audio_path)

            speed_ratio = (audio_duration / processing_time) if audio_duration > 0 and processing_time > 0 else 0

            return {
                'success': result.returncode == 0,
                'processing_time': processing_time,
                'audio_duration': audio_duration,
                'speed_ratio': speed_ratio,
                'model_tested': model_to_test,
                'settings_tested': test_settings, # Record what settings were used for this ratio
                'error': result.stderr if result.returncode != 0 else None
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False, 'error': 'Transcription speed test timed out',
                'processing_time': 120, 'audio_duration': get_audio_duration(test_audio_path),
                'speed_ratio': 0, 'model_tested': model_to_test, 'settings_tested': test_settings
            }
        except Exception as e: # pragma: no cover
            app.logger.error(f"Exception during test_whisper_speed: {e}")
            return {
                'success': False, 'error': str(e),
                'processing_time': 0, 'audio_duration': get_audio_duration(test_audio_path),
                'speed_ratio': 0, 'model_tested': model_to_test, 'settings_tested': test_settings
            }

# ───────────────────────── whisper streamer ───────────────────────
def whisper_stream(book: str, mp3: str, enable_word_timestamps: bool = True, enable_highlighting: bool = True):
    folder = BOOKS / book
    mp3_path = folder / mp3

    # Ensure the MP3 file exists
    if not mp3_path.exists():
        yield f"Error: MP3 file not found: {mp3_path}\n"
        return

    # Build command with optional features
    cmd = [
        "whisper", str(mp3_path),
        "--model", MODEL,
        "--output_format", "vtt",
        "--output_dir", str(folder),
        "--fp16", "False",  # Suppress FP16 warning
    ]

    # Add word-level features if requested and available
    capabilities = get_whisper_capabilities_cached()
    if enable_word_timestamps and capabilities['word_timestamps_available']:
        cmd.extend(["--word_timestamps", "True"])
        if enable_highlighting and capabilities['highlight_words_available']:
            cmd.extend(["--highlight_words", "True"])

    yield f"Starting Whisper transcription for: {mp3}\n"
    yield f"Command: {' '.join(cmd)}\n"
    yield f"Word timestamps: {'enabled' if enable_word_timestamps and capabilities['word_timestamps_available'] else 'disabled'}\n"
    yield f"Word highlighting: {'enabled' if enable_highlighting and capabilities['highlight_words_available'] else 'disabled'}\n\n"

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
        with _lock:
            _jobs[(book, mp3)] = proc

        # Simplified line-by-line reading without complex progress parsing
        for line in iter(proc.stdout.readline, ''):
            line = line.rstrip()
            if not line:
                continue

            # Just yield all non-empty lines - much simpler and more reliable
            yield line + '\n'

        proc.wait()
        with _lock:
            _jobs.pop((book, mp3), None)

        # Verify the VTT file was created
        expected_vtt = caption_path(book, mp3)
        if expected_vtt.exists():
            has_words = has_word_timestamps(expected_vtt)
            yield f"\nSUCCESS: VTT file created at {expected_vtt}\n"
            yield f"Word-level timestamps: {'Yes' if has_words else 'No'}\n"
        else:
            yield f"\nWARNING: Expected VTT file not found at {expected_vtt}\n"

        if proc.returncode != 0:
            yield f"\nERROR: Whisper process failed with exit code {proc.returncode}\n"
        else:
            yield f"\n[DONE {mp3} - SUCCESS]\n"

    except Exception as e:
        yield f"\nEXCEPTION: {str(e)}\n"
        with _lock:
            _jobs.pop((book, mp3), None)

def whisper_stream_parallel(book: str, mp3_files: list[str], max_workers: int = 2):
    """Stream transcription of multiple files in parallel"""
    yield f"Starting parallel transcription of {len(mp3_files)} files with {max_workers} workers\n\n"

    def transcribe_single(mp3):
        """Transcribe a single file and collect output"""
        output_lines = []
        for line in whisper_stream(book, mp3):
            output_lines.append(f"[{mp3}] {line}")
        return mp3, output_lines

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all jobs
        future_to_mp3 = {executor.submit(transcribe_single, mp3): mp3 for mp3 in mp3_files}

        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_mp3):
            mp3 = future_to_mp3[future]
            try:
                mp3_name, output_lines = future.result()
                yield f"\n=== COMPLETED: {mp3_name} ===\n"
                for line in output_lines:
                    yield line
                yield f"=== END: {mp3_name} ===\n\n"
            except Exception as e:
                yield f"\n=== ERROR: {mp3} ===\n"
                yield f"Exception: {str(e)}\n"
                yield f"=== END ERROR: {mp3} ===\n\n"

# ───────────────────────── routes ─────────────────────────────────
@app.route("/")
def index():
    return render_template(
        "index.html",
        books=list_books(),
    )

@app.route("/book/<book>/")
def view_book(book):
    if not (BOOKS / book).is_dir():
        return "Book not found", 404

    mp3_files = list_mp3s(book)

    return render_template(
        "book.html",
        book=book,
        mp3s=mp3_files,
        current_model_name=MODEL
    )

@app.route("/api/whisper/capabilities")
def whisper_capabilities_route():
    """API endpoint to check Whisper capabilities (uses cached result)"""
    return jsonify(get_whisper_capabilities_cached())

@app.route("/api/speed-ratio", methods=["GET"])
def get_speed_ratio_route():
    try:
        # Query parameters define the configuration we're looking for
        # Default to global MODEL if not specified
        model_name = request.args.get('model', MODEL)
        word_timestamps = request.args.get('word_timestamps', 'true').lower() == 'true'
        # Client sends 'highlight_words', but speed_ratios.json and get_speed_test_key use 'highlighting'
        highlight_words_param = request.args.get('highlight_words', 'true').lower() == 'true'

        query_settings = {
            'word_timestamps': word_timestamps,
            'highlighting': highlight_words_param # Map to 'highlighting' for the key
        }

        key_to_find = get_speed_test_key(model_name, query_settings)
        all_ratios = load_saved_speed_ratios()

        if key_to_find in all_ratios:
            return jsonify(all_ratios[key_to_find]) # Returns {'speed_ratio': X, 'model_tested': Y, ...}
        else:
            return jsonify({"message": f"No speed ratio found for key: {key_to_find}"}), 404
    except Exception as e: # pragma: no cover
        app.logger.error(f"Error in /api/speed-ratio: {e}")
        return jsonify({"error": "Failed to retrieve speed ratio"}), 500

@app.route("/api/whisper/speed-test", methods=["POST"])
def whisper_speed_test():
    try:
        data = request.get_json()
        if not data: return jsonify({"error": "Missing JSON payload"}), 400

        book = data.get("book")
        # test_settings from client (e.g., from getTranscriptionOptions in JS)
        # These settings define the configuration being tested.
        test_settings = data.get("settings", {})
        # file_info for the current book, used to calculate on-the-fly estimates for immediate UI update
        book_file_info_for_estimates = data.get("file_info", {})

        if not book: return jsonify({"error": "Missing 'book' in request"}), 400

        mp3_files = list_mp3s(book)
        if not mp3_files: return jsonify({"error": "No audio files found in book"}), 400

        # Select a short, representative file for the test clip
        # Prefer a file around 1-5 minutes if possible, otherwise shortest.
        # For simplicity, still using the shortest, or first, if durations aren't easily available here.
        # The test_audio_clip creation handles fixed duration.
        # It's important that create_test_audio_clip gets a valid source_audio.
        source_audio_name = mp3_files[0] # Default, pick first
        if book_file_info_for_estimates: # if client sent file_info, try to pick a reasonably short one
            shortest_duration = float('inf')
            best_file = None
            for fname, info in book_file_info_for_estimates.items():
                if info.get('duration', float('inf')) < shortest_duration:
                    shortest_duration = info['duration']
                    best_file = fname
            if best_file: source_audio_name = best_file

        source_audio_path = BOOKS / book / source_audio_name
        if not source_audio_path.exists():
             return jsonify({"error": f"Selected source audio for test not found: {source_audio_path}"}), 400

        test_audio_clip_path = create_test_audio_clip(source_audio_path, duration_seconds=15)
        if not test_audio_clip_path:
            return jsonify({"error": "Failed to create test audio clip"}), 500

        try:
            # Test with the current global MODEL and client-provided settings for the test config
            speed_test_run_result = test_whisper_speed(test_audio_clip_path, MODEL, test_settings)

            if speed_test_run_result['success'] and speed_test_run_result['speed_ratio'] > 0:
                # Save this successful speed_ratio keyed by MODEL and test_settings
                save_key = get_speed_test_key(MODEL, test_settings)
                data_to_save = {
                    "speed_ratio": speed_test_run_result['speed_ratio'],
                    "model_tested": MODEL, # Explicitly state which model this ratio is for
                    "settings_key_info": test_settings, # What settings produced this key
                    "test_audio_duration": speed_test_run_result['audio_duration'],
                    "test_processing_time": speed_test_run_result['processing_time'],
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
                }
                save_speed_ratio_data(save_key, data_to_save)

                # For the immediate response, calculate estimates for the *current book's files*
                # using the newly determined speed_ratio.
                current_book_estimates = {}
                for mp3_file_name, info in book_file_info_for_estimates.items():
                    duration = info.get('duration', 0)
                    if duration > 0:
                        estimated_time = duration / speed_test_run_result['speed_ratio']
                        current_book_estimates[mp3_file_name] = {
                            'duration': duration,
                            'estimated_time': estimated_time
                        }

                # Return success, new ratio, and on-the-fly estimates for current book
                return jsonify({
                    "success": True,
                    "speed_ratio": speed_test_run_result['speed_ratio'],
                    "model_tested": MODEL,
                    "settings_tested_key_info": test_settings, # For user display confirmation
                    "estimates": current_book_estimates # For immediate UI update for *this* book
                })
            else:
                # Test failed or speed_ratio is 0
                return jsonify({
                    "success": False,
                    "error": speed_test_run_result.get('error', "Speed test failed or resulted in zero speed ratio."),
                    "speed_ratio": 0,
                    "model_tested": MODEL,
                    "settings_tested_key_info": test_settings
                }), 200 # Return 200 OK but with success:false and an error message
        finally:
            if test_audio_clip_path and test_audio_clip_path.exists():
                test_audio_clip_path.unlink() # Cleanup test clip
    except Exception as e: # pragma: no cover
        app.logger.error(f"Error in /api/whisper/speed-test: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/gen_one", methods=["POST"])
def stream_single_caption_route():
    data = request.get_json(True)
    book, mp3 = data["book"], data["mp3"]
    enable_word_timestamps = data.get("word_timestamps", True)
    enable_highlighting = data.get("highlighting", True)

    if caption_path(book, mp3).exists():
        return "exists", 200
    return Response(stream_with_context(whisper_stream(book, mp3, enable_word_timestamps, enable_highlighting)),
                    mimetype="text/plain")

@app.route("/gen_all", methods=["POST"])
def stream_book_captions_route():
    data = request.get_json(True)
    book = data["book"]
    parallel = data.get("parallel", False)
    max_workers = data.get("max_workers", 2)
    enable_word_timestamps = data.get("word_timestamps", True)
    enable_highlighting = data.get("highlighting", True)

    # Get files that need transcription
    files_to_process = [mp3 for mp3 in list_mp3s(book) if not caption_path(book, mp3).exists()]

    if not files_to_process:
        return Response("All files already have transcripts\n", mimetype="text/plain")

    if parallel and len(files_to_process) > 1:
        return Response(stream_with_context(whisper_stream_parallel(book, files_to_process, max_workers)),
                        mimetype="text/plain")
    else:
        def batch():
            for mp3 in files_to_process:
                yield f"\n=== {mp3} ===\n"
                yield from whisper_stream(book, mp3, enable_word_timestamps, enable_highlighting)
        return Response(stream_with_context(batch()), mimetype="text/plain")

# ───────────────────────── playlist player ───────────────────────
@app.route("/player/<book>/")
def player(book):
    tracks = [m for m in list_mp3s(book) if caption_path(book, m).exists()]
    if not tracks:
        return "No captioned tracks yet", 404
    start = request.args.get("file") or tracks[0]
    return render_template(
        "player.html",
        book=book,
    )

@app.route("/api/player/<book>/data")
def player_data(book):
    tracks = [m for m in list_mp3s(book) if caption_path(book, m).exists()]
    if not tracks:
        return {"error": "No captioned tracks yet"}, 404
    start = request.args.get("file") or tracks[0]
    return {
        "book": book,
        "tracks": tracks,
        "start": start
    }

# ───────────────────────── static helper ──────────────────────────
@app.route("/file/<book>/<path:filename>")
def serve_file(book, filename):
    return send_from_directory(BOOKS / book, filename)

# ───────────────────────── speed test persistence ────────────────────────────────
def get_speed_test_key(model_name: str, settings: dict) -> str:
    """Generate a unique key for speed test results based on model and settings."""
    # Settings from UI/client (e.g., word_timestamps, highlighting)
    # For now, assume these are the primary settings from client that might affect tested config.
    # If whisper CLI changes speed based on more VTT flags, add them here.
    word_ts = settings.get('word_timestamps', True)
    highlight = settings.get('highlighting', True)
    # Future: could add other settings like 'beam_size', 'temperature' if they become configurable for test
    return f"{model_name}:{word_ts}:{highlight}"

def load_saved_speed_ratios() -> dict:
    if SPEED_RATIOS_FILE.exists():
        try:
            return json.loads(SPEED_RATIOS_FILE.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, IOError) as e:
            app.logger.error(f"Error loading speed ratios file {SPEED_RATIOS_FILE}: {e}")
    return {}

def save_speed_ratio_data(key: str, data: dict):
    all_ratios = load_saved_speed_ratios()
    all_ratios[key] = data # data includes speed_ratio, model_tested, settings_tested, timestamp etc.
    try:
        SPEED_RATIOS_FILE.write_text(json.dumps(all_ratios, indent=2), encoding='utf-8')
    except IOError as e: # pragma: no cover
        app.logger.error(f"Error saving speed ratios file {SPEED_RATIOS_FILE}: {e}")

@app.route("/api/book/<book_name>/file-info")
def book_file_info(book_name):
    try:
        book_path = BOOKS / book_name
        if not book_path.is_dir():
            return jsonify({"error": "Book not found"}), 404

        file_info_map = {}
        for mp3_file in list_mp3s(book_name):
            mp3_path = book_path / mp3_file
            vtt_file_path = caption_path(book_name, mp3_file)
            vtt_exists = vtt_file_path.exists()
            file_info_map[mp3_file] = {
                "duration": get_audio_duration(mp3_path),
                "size": mp3_path.stat().st_size,
                "vtt_exists": vtt_exists,
                "has_word_timestamps": has_word_timestamps(vtt_file_path) if vtt_exists else False,
                "job_running": job_running(book_name, mp3_file)
            }
        return jsonify(file_info_map)
    except Exception as e: # pragma: no cover
        app.logger.error(f"Error in /api/book/{book_name}/file-info: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# ───────────────────────── entry ────────────────────────────────
if __name__ == "__main__":
    BOOKS.mkdir(exist_ok=True) # Ensure the books directory exists
    # Configure logging
    if not app.debug: # pragma: no cover
        import logging
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler('audiobooks_app.log', maxBytes=1024 * 1024 * 10, backupCount=5) # 10MB per file
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('Audiobooks App startup')

    print(f"Audiobooks server running. Access at http://localhost:8000 (Model: {MODEL})")
    app.run(host="0.0.0.0", port=8000, debug=True)
