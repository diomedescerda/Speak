"""Loopback web service for the Speak coach."""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Lock
from uuid import UUID, uuid4

from flask import Flask, abort, jsonify, request, send_file
from waitress import serve
from werkzeug.exceptions import HTTPException

import ai
import audio
import db
import speak


MAX_UPLOAD_SIZE = 16 * 1024 * 1024
MAX_RECORDING_SECONDS = 180
WEB_DIR = Path(__file__).resolve().parent / "web"
app = Flask(__name__, static_folder=WEB_DIR, static_url_path="/assets")
app.config.update(MAX_CONTENT_LENGTH=MAX_UPLOAD_SIZE, MAX_FORM_PARTS=8, MAX_FORM_MEMORY_SIZE=128 * 1024)
app.config["TRUSTED_HOSTS"] = [
    "localhost", "127.0.0.1", *filter(None, [os.environ.get("SPEAK_TAILSCALE_HOST")])
]
allowed_login = os.environ.get("SPEAK_ALLOWED_LOGIN", "").strip().casefold()
coach_lock = Lock()


@app.before_request
def protect_private_routes():
    if request.endpoint == "health":
        return
    if allowed_login and request.headers.get("Tailscale-User-Login", "").casefold() != allowed_login:
        abort(403, description="Open Speak through Tailscale with the account that owns this practice history.")
    if request.path.startswith("/api/") and request.headers.get("Sec-Fetch-Site") == "cross-site":
        abort(403, description="Open Speak directly to use the coach.")
    if request.method == "POST" and request.headers.get("X-Speak-Request") != "1":
        abort(403, description="Submit responses from the Speak app.")


@app.after_request
def set_browser_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; media-src 'self' blob:; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    )
    response.headers["Permissions-Policy"] = "microphone=(self), camera=()"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "private, no-store"
    return response


@app.errorhandler(HTTPException)
def request_error(error):
    message = "The response file is too large." if error.code == 413 else error.description
    return jsonify(error=message), error.code


@app.get("/")
def index():
    return send_file(WEB_DIR / "index.html", max_age=0)


@app.get("/manifest.webmanifest")
def manifest():
    return send_file(WEB_DIR / "manifest.webmanifest", mimetype="application/manifest+json")


@app.get("/health")
def health():
    return jsonify(status="ok")


def language():
    lang = request.args.get("lang", "en")
    if lang not in ("en", "ja"):
        abort(400, description="Choose English or Japanese.")
    return lang


def positive_id(value, label):
    try:
        identifier = int(value)
    except (TypeError, ValueError):
        identifier = 0
    if not 0 < identifier < 2**63:
        abort(400, description=f"A valid {label} is required.")
    return identifier


def find_mission(lang, identifier):
    find = db.get_ja_mission_by_id if lang == "ja" else db.get_mission_by_id
    mission = find(identifier)
    if mission is None:
        abort(404, description="This mission could not be found.")
    return mission


@app.get("/api/mission")
def daily_mission():
    lang = language()
    get_today = db.get_today_ja_mission if lang == "ja" else db.get_today_mission
    mission = get_today()
    if mission is None:
        prepare = speak._prepare_ja_mission if lang == "ja" else speak._prepare_mission
        with coach_lock:
            mission = prepare(quiet=True)
    return jsonify(mission=mission)


def recording_path(value):
    if not value:
        return None
    path = Path(value).resolve()
    if path.is_relative_to(db.RECORDINGS_DIR.resolve()) and path.is_file():
        return path
    return None


def attempt_rows(lang, identifier=None):
    if lang == "ja":
        attempt_table, mission_table, title = "ja_attempts", "ja_missions", "topic_title"
    else:
        attempt_table, mission_table, title = "attempts", "missions", "source_title"
    query = f"""
        SELECT a.*, m.date, m.{title} AS title
        FROM {attempt_table} a JOIN {mission_table} m ON m.id = a.mission_id
    """
    fields = ()
    if identifier is not None:
        query += " WHERE a.id = ?"
        fields = (identifier,)
    with closing(db.get_conn()) as conn:
        return conn.execute(query + " ORDER BY a.id DESC", fields).fetchall()


def find_attempt(lang, identifier):
    rows = attempt_rows(lang, identifier)
    if not rows:
        abort(404, description="This practice attempt could not be found.")
    return rows[0]


def present_attempt(lang, row):
    metrics = {"duration_sec": row["duration_sec"]}
    if lang == "ja":
        metrics.update(cpm=row["cpm"], char_count=row["char_count"], grammar_used=bool(row["grammar_used"]))
        metrics["vocab_used"] = json.loads(row["vocab_used_json"])
    else:
        metrics.update(wpm=row["wpm"], unique_word_ratio=row["unique_word_ratio"])
        for key in ("targets_used", "forbidden_used", "repeated_words"):
            metrics[key] = json.loads(row[f"{key}_json"])
    result = {key: row[key] for key in ("id", "mission_id", "round_num", "transcript", "date", "title")}
    return dict(result, review=json.loads(row["review_json"]), metrics=metrics,
                has_audio=recording_path(row["audio_path"]) is not None)


@app.get("/api/history")
def history():
    lang = language()
    return jsonify(attempts=[present_attempt(lang, row) for row in attempt_rows(lang)])


def convert_recording(upload, directory):
    original = directory / "upload"
    wav_path = directory / "recording.wav"
    upload.save(original)
    try:
        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-loglevel", "error", "-protocol_whitelist", "file,pipe",
                "-format_whitelist", "mov,matroska,webm,ogg,wav,aac,mp3", "-i", str(original),
                "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                "-t", str(MAX_RECORDING_SECONDS + 1), str(wav_path),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        abort(422, description="The recording could not be read. Try recording again or enter text.")
    except FileNotFoundError:
        abort(503, description="Audio conversion is unavailable. Install ffmpeg or enter text.")
    duration = audio._get_wav_duration(wav_path)
    if duration < 1.2 or duration > MAX_RECORDING_SECONDS:
        abort(422, description="Record at least two seconds and no more than three minutes.")
    return wav_path, duration


def existing_submission(lang, request_id):
    if not request_id:
        return None
    with closing(db.get_conn()) as conn:
        row = conn.execute(
            "SELECT attempt_id FROM web_submissions WHERE language = ? AND request_id = ?",
            (lang, request_id),
        ).fetchone()
    return find_attempt(lang, row["attempt_id"]) if row else None


def save_review(lang, mission, text, duration, wav_path, previous, request_id):
    round_num = 2 if previous is not None else 1
    prior_text = previous["transcript"] if previous is not None else None
    if lang == "ja":
        metrics = audio.analyze_ja_transcript(text, duration, mission)
        review = ai.review_ja_attempt(mission, metrics, text, round_num=round_num, prev_transcript=prior_text)
        save, write_report, reports = db.save_ja_attempt, speak.save_ja_markdown_report, db.JA_REVIEWS_DIR
    else:
        metrics = audio.analyze_transcript(text, duration, mission)
        review = ai.review_attempt(mission, metrics, text, round_num=round_num, prev_transcript=prior_text)
        save, write_report, reports = db.save_attempt, speak.save_markdown_report, db.REVIEWS_DIR

    saved_path = None
    if wav_path is not None:
        saved_path = db.RECORDINGS_DIR / f"web_{lang}_{uuid4().hex}.wav"
        wav_path.replace(saved_path)
    try:
        attempt_id = save(
            mission["id"], round_num, str(saved_path) if saved_path else None, metrics,
            text, review, request_id=request_id,
        )
    except Exception:
        if saved_path:
            saved_path.unlink(missing_ok=True)
        raise

    first_attempt_id = previous["id"] if previous is not None else attempt_id
    report = reports / f"{mission['date']}_web_{first_attempt_id}.md"
    try:
        write_report(mission, metrics, text, review, round_num, report_path=report)
    except OSError:
        app.logger.exception("Could not export Speak attempt %d as Markdown", attempt_id)
    return find_attempt(lang, attempt_id)


@app.post("/api/review")
def review_response():
    lang = language()
    mission_id = positive_id(request.form.get("mission_id"), "mission")
    text = request.form.get("text", "").strip()
    upload = request.files.get("audio")
    if bool(text) == (upload is not None) or len(text) > 10_000:
        abort(400, description="Enter a response of up to 10,000 characters or submit one recording.")
    request_id = request.form.get("request_id")
    if request_id:
        try:
            request_id = str(UUID(request_id))
        except ValueError:
            abort(400, description="The submission ID is invalid.")

    mission = find_mission(lang, mission_id)
    previous = None
    if "previous_attempt_id" in request.form:
        previous = find_attempt(lang, positive_id(request.form["previous_attempt_id"], "first attempt"))
        if previous["mission_id"] != mission_id or previous["round_num"] != 1:
            abort(400, description="The retry must follow the first attempt for this mission.")

    with coach_lock, tempfile.TemporaryDirectory(dir=db.RECORDINGS_DIR) as directory:
        saved = existing_submission(lang, request_id)
        if saved is not None:
            if saved["mission_id"] != mission_id or saved["round_num"] != (2 if previous is not None else 1):
                abort(409, description="This submission ID was already used for another attempt.")
            return jsonify(attempt=present_attempt(lang, saved))

        wav_path = None
        if upload is not None:
            wav_path, duration = convert_recording(upload, Path(directory))
            try:
                text = audio.transcribe_audio(wav_path, lang=lang).strip()
            except Exception:
                app.logger.exception("Speak transcription failed for %s", lang)
                abort(503, description="Transcription is temporarily unavailable. Try again or enter text.")
        else:
            duration = round(max(10, len(text) / 3), 1) if lang == "ja" else round(max(15, len(text.split()) / 2.2), 1)
        if (len(text) < 2 if lang == "ja" else len(text.split()) < 3):
            abort(422, description="There wasn't enough speech to review. Try a longer response.")
        saved = save_review(lang, mission, text, duration, wav_path, previous, request_id)
    return jsonify(attempt=present_attempt(lang, saved)), 201


@app.get("/api/audio")
def playback():
    lang = language()
    kind = request.args.get("kind")
    if kind == "recording":
        row = find_attempt(lang, positive_id(request.args.get("attempt_id"), "attempt"))
        path = recording_path(row["audio_path"])
        if path is None:
            abort(404, description="This recording is unavailable.")
        return send_file(path, mimetype="audio/wav")
    if lang != "ja":
        abort(400, description="Model audio is available for Japanese practice.")
    if kind == "model":
        mission = find_mission(lang, positive_id(request.args.get("mission_id"), "mission"))
        text = mission["model_japanese"]
    elif kind == "polished":
        row = find_attempt(lang, positive_id(request.args.get("attempt_id"), "attempt"))
        text = json.loads(row["review_json"]).get("native_model_version", "")
    else:
        abort(400, description="Choose a recording, model passage, or polished version.")
    try:
        audio_path = audio.get_ja_tts_path(text, rate="-22%" if request.args.get("slow") == "1" else "-10%")
    except ValueError:
        abort(404, description="There is no text to play for this attempt.")
    except Exception:
        app.logger.exception("Speak Japanese speech synthesis failed")
        abort(503, description="Japanese audio is temporarily unavailable. Try again in a moment.")
    return send_file(audio_path, mimetype="audio/mpeg")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    options = parser.parse_args()
    db.init_db()
    serve(app, host="127.0.0.1", port=options.port, max_request_body_size=MAX_UPLOAD_SIZE)


if __name__ == "__main__":
    main()
