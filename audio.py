import collections
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from rich.console import Console

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "over", "after", "is",
    "am", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "shall", "should", "can", "could",
    "may", "might", "must", "it", "its", "this", "that", "these", "those",
    "i", "you", "he", "she", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "our", "their", "mine", "yours", "ours", "theirs",
    "as", "not", "no", "yes", "all", "any", "both", "each", "few", "more",
    "most", "other", "some", "such", "than", "too", "same", "what", "which",
    "who", "whom", "when", "where", "why", "how", "there", "here", "out",
    "don", "t", "s", "re", "ve", "ll", "d", "m",
}

FILLER_CRUTCH_WORDS = {
    "like", "really", "very", "just", "actually", "basically", "literally",
    "thing", "things", "stuff", "good", "bad", "think", "so", "because",
    "maybe", "kind", "sort", "know", "mean", "honestly", "obviously",
}

_ASR_PIPE = None


def _get_wav_duration(wav_path: Path) -> float:
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return round(frames / float(rate), 1)
    except Exception:
        pass
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(wav_path),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return round(float(proc.stdout.strip()), 1)
    except Exception:
        return 0.0


def record_audio(output_path: Path, console: Console, target_seconds: int = 90) -> float:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    if shutil.which("pw-record"):
        cmd = [
            "pw-record",
            "--rate", "16000",
            "--channels", "1",
            "--format", "s16",
            str(output_path),
        ]
    elif shutil.which("parecord"):
        cmd = [
            "parecord",
            "--rate=16000",
            "--channels=1",
            "--format=s16le",
            "--file-format=wav",
            str(output_path),
        ]
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "alsa",
            "-i", "default",
            "-ar", "16000",
            "-ac", "1",
            str(output_path),
        ]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    start_t = time.time()
    console.print(
        "\n[bold red]● RECORDING LIVE[/bold red] — Speak out loud! "
        "Press [bold green][Enter][/bold green] or [bold yellow][Ctrl+C][/bold yellow] when finished.\n"
    )

    try:
        while proc.poll() is None:
            elapsed = int(time.time() - start_t)
            mins, secs = divmod(elapsed, 60)
            t_mins, t_secs = divmod(target_seconds, 60)
            bar_filled = min(20, int((elapsed / max(1, target_seconds)) * 20))
            bar = "█" * bar_filled + "░" * (20 - bar_filled)
            sys.stdout.write(
                f"\r  🎙️  {mins:02d}:{secs:02d} / {t_mins:02d}:{t_secs:02d}  [{bar}]  (Press Enter to stop) "
            )
            sys.stdout.flush()

            if sys.stdin.isatty():
                rlist, _, _ = select.select([sys.stdin], [], [], 0.25)
                if rlist:
                    sys.stdin.readline()
                    break
            else:
                time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\n")
        sys.stdout.flush()
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait(timeout=2)

    duration = _get_wav_duration(output_path)
    if duration <= 0.1:
        duration = round(time.time() - start_t, 1)
    return duration


def _load_asr_pipeline():
    global _ASR_PIPE
    if _ASR_PIPE is not None:
        return _ASR_PIPE

    cache_dir = Path.home() / ".cache" / "huggingface" / "hub" / "models--openai--whisper-base.en"
    if cache_dir.exists():
        os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_VERBOSITY"] = "error"

    import warnings
    warnings.filterwarnings("ignore")
    from transformers import pipeline
    from transformers.utils import logging as hf_logging
    hf_logging.set_verbosity_error()

    _ASR_PIPE = pipeline(
        "automatic-speech-recognition",
        model="openai/whisper-base.en",
        device="cpu",
    )
    return _ASR_PIPE


def transcribe_audio(audio_path: Path) -> str:
    if not audio_path.exists():
        return ""

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        cleaned_wav = Path(tmp.name)

    try:
        # Normalize voice & strip dead silence at start/end so Whisper is fast and accurate
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", str(audio_path),
                "-ar", "16000",
                "-ac", "1",
                "-af",
                "highpass=f=80,silenceremove=start_periods=1:start_silence=0.3:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_silence=0.3:start_threshold=-45dB,areverse,loudnorm",
                str(cleaned_wav),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
        target_wav = cleaned_wav if cleaned_wav.exists() and _get_wav_duration(cleaned_wav) > 0.4 else audio_path
        pipe = _load_asr_pipeline()
        res = pipe(str(target_wav), return_timestamps=True)
        text = (res.get("text") or "").strip()
        return re.sub(r"\s+", " ", text)
    finally:
        if cleaned_wav.exists():
            cleaned_wav.unlink()


def _stem_token(w: str) -> str:
    w = w.lower().strip(".,!?;:\"'()-[]")
    for suffix in ("ing", "ed", "es", "s"):
        if len(w) > len(suffix) + 2 and w.endswith(suffix):
            return w[: -len(suffix)]
    return w


def _phrase_matches(phrase: str, transcript: str) -> bool:
    clean_p = re.sub(r"[^a-zA-Z\s']", " ", phrase.lower())
    p_tokens = [t for t in clean_p.split() if len(t) > 1 and t not in {"something", "someone", "one", "your"}]
    if not p_tokens:
        return False
    if clean_p.strip() in transcript.lower():
        return True

    t_tokens = [_stem_token(t) for t in re.findall(r"[a-zA-Z']+", transcript.lower())]
    p_stems = [_stem_token(t) for t in p_tokens]

    # Check if all stems of the target phrase appear within a small window (len + 3 tokens)
    window = len(p_stems) + 3
    for i in range(max(1, len(t_tokens) - len(p_stems) + 1)):
        slice_stems = t_tokens[i : i + window]
        if all(ps in slice_stems for ps in p_stems):
            return True
    return False


def analyze_transcript(
    transcript: str,
    duration_sec: float,
    mission: Dict[str, Any],
) -> Dict[str, Any]:
    tokens = re.findall(r"[a-zA-Z']+", transcript.lower())
    word_count = len(tokens)
    effective_dur = max(duration_sec, max(10.0, word_count / 2.2)) if duration_sec <= 1.0 else duration_sec
    wpm = round((word_count / effective_dur) * 60.0, 1) if effective_dur > 0 else 0.0
    unique_ratio = round(len(set(tokens)) / float(word_count), 3) if word_count > 0 else 0.0

    # Check target phrases + connector challenge
    targets_used: List[str] = []
    for tp in mission.get("target_phrases", []):
        p = tp.get("phrase", "").strip()
        if p and _phrase_matches(p, transcript):
            targets_used.append(p)

    conn_p = mission.get("connector_challenge", {}).get("phrase", "").strip()
    if conn_p and _phrase_matches(conn_p, transcript):
        targets_used.append(conn_p)

    # Check forbidden words
    token_counts = collections.Counter(tokens)
    stem_counts = collections.Counter(_stem_token(t) for t in tokens)
    forbidden_used: Dict[str, int] = {}
    for fw in mission.get("forbidden_words", []):
        w = fw.get("word", "").strip().lower()
        if not w:
            continue
        cnt = token_counts.get(w, 0) or stem_counts.get(_stem_token(w), 0)
        if cnt > 0:
            forbidden_used[w] = cnt

    # Find repeated content/crutch words
    repeated_words: List[Dict[str, Any]] = []
    for word, count in token_counts.most_common(25):
        if len(word) < 3:
            continue
        if word in STOPWORDS and word not in FILLER_CRUTCH_WORDS:
            continue
        threshold = 2 if word in FILLER_CRUTCH_WORDS else 3
        if count >= threshold:
            repeated_words.append({"word": word, "count": count})

    return {
        "duration_sec": round(effective_dur, 1),
        "word_count": word_count,
        "wpm": wpm,
        "unique_word_ratio": unique_ratio,
        "targets_used": targets_used,
        "forbidden_used": forbidden_used,
        "repeated_words": repeated_words[:6],
    }
