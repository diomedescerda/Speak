"""Run the real web server with sample missions and offline coaching providers."""

import runpy
import subprocess
import sys
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ai
import audio
import db


def seed_missions():
    db.save_mission({
        "category": "life",
        "speaking_mode": "Storytelling & Reflection",
        "speaking_mode_desc": "Tell a story about something you tried.",
        "source_name": "The Daily Practice",
        "source_title": "Little habits, lasting results",
        "source_url": "https://example.com/little-habits",
        "reading_excerpt": "A small habit can be easier to keep than a large commitment.",
        "speaking_prompt": "Describe a small habit you have kept.",
        "target_phrases": [{
            "phrase": "build momentum",
            "meaning": "make steady progress",
            "example": "A short walk helped me build momentum.",
        }],
    })
    db.save_ja_mission({
        "stage": 1,
        "stage_name": "Early N5",
        "topic_id": "morning",
        "topic_title": "A morning routine",
        "scenario": "Describe your morning.",
        "target_seconds": 30,
        "model_japanese": "朝[あさ]はお茶[ちゃ]を飲[の]みます。",
        "model_english": "I drink tea in the morning.",
        "speaking_prompt_en": "What do you do in the morning?",
        "speaking_prompt_ja": "朝は何をしますか。",
    })


def coach(prompt, timeout):
    if "Japanese speaking coach" in prompt:
        return {
            "score": 88,
            "summary_feedback": "The particle を fits here.",
            "sentence_upgrades": [],
            "native_model_version": "毎朝[まいあさ]コーヒーを飲[の]みます。",
        }
    feedback = "Keep your opening short and concrete."
    if "This is Round 2" in prompt:
        if "I walk after lunch to clear my head." not in prompt:
            raise AssertionError("The retry omitted the first round from the coaching prompt")
        feedback = "You carried the first round into a stronger retry."
    return {
        "score": 86,
        "summary_feedback": feedback,
        "sentence_upgrades": [],
        "native_model_version": "I take a quick walk after lunch to reset my focus.",
    }


def transcribe(path, lang="en"):
    with wave.open(str(path), "rb") as recording:
        if recording.getnframes() < recording.getframerate():
            raise AssertionError("The uploaded microphone recording is too short")
    if lang != "en":
        raise AssertionError("The English recording was sent to the wrong language model")
    return "The microphone recording reached the coach."


async def synthesize(text, output, voice, rate):
    if text not in ["朝はお茶を飲みます。", "毎朝コーヒーを飲みます。"]:
        raise AssertionError(f"Unexpected Japanese shadowing text: {text}")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-f", "mp3", str(output),
    ], check=True, timeout=10)


if __name__ == "__main__":
    seed_missions()
    with (
        patch.object(ai, "_run_opencode_json", coach),
        patch.object(audio, "transcribe_audio", transcribe),
        patch.object(audio, "_synthesize_edge_tts", synthesize),
    ):
        runpy.run_module("speak_web", run_name="__main__")
