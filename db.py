import json
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_DIR = Path.home() / ".local" / "share" / "speak"
RECORDINGS_DIR = DATA_DIR / "recordings"
REVIEWS_DIR = DATA_DIR / "reviews"
DB_PATH = DATA_DIR / "speak.db"

SPEAKING_MODES = [
    {
        "name": "Summarize & Take a Stance",
        "description": "Spend ~30s summarizing the core idea of the excerpt in your own words, then spend ~60s explaining whether you agree or disagree and why.",
    },
    {
        "name": "Devil's Advocate (Both Sides)",
        "description": "Argue strongly IN FAVOR of the perspective in the text for ~45s, then flip and argue AGAINST it for ~45s using contrasting transitions.",
    },
    {
        "name": "Teach & Connect to Life",
        "description": "Explain the main concept as if teaching a curious friend, then connect it to a real story, habit, or observation from your own life.",
    },
    {
        "name": "Problem & Actionable Pitch",
        "description": "Break down the underlying problem or tension in the piece, and propose a concrete rule of thumb or solution someone could apply today.",
    },
    {
        "name": "Storytelling & Reflection",
        "description": "Use the reading as a springboard to tell a specific past experience or turning point, focusing on vivid details and what changed your mind.",
    },
]


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)


def get_conn() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS missions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                category TEXT NOT NULL,
                speaking_mode TEXT NOT NULL,
                speaking_mode_desc TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_title TEXT NOT NULL,
                source_url TEXT NOT NULL,
                reading_excerpt TEXT NOT NULL,
                speaking_prompt TEXT NOT NULL,
                target_phrases_json TEXT NOT NULL,
                connector_challenge_json TEXT NOT NULL,
                forbidden_words_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id INTEGER NOT NULL,
                round_num INTEGER NOT NULL,
                audio_path TEXT,
                duration_sec REAL NOT NULL,
                transcript TEXT NOT NULL,
                wpm REAL NOT NULL,
                unique_word_ratio REAL NOT NULL,
                targets_used_json TEXT NOT NULL,
                forbidden_used_json TEXT NOT NULL,
                repeated_words_json TEXT NOT NULL,
                review_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (mission_id) REFERENCES missions(id)
            );

            CREATE TABLE IF NOT EXISTS crutch_words (
                word TEXT PRIMARY KEY,
                hit_count INTEGER NOT NULL DEFAULT 1,
                last_seen TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS phrase_bank (
                phrase TEXT PRIMARY KEY,
                meaning TEXT NOT NULL,
                example TEXT NOT NULL,
                times_assigned INTEGER NOT NULL DEFAULT 1,
                times_used INTEGER NOT NULL DEFAULT 0,
                last_seen TEXT NOT NULL
            );
            """
        )


def get_next_speaking_mode() -> Dict[str, str]:
    init_db()
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM missions").fetchone()
        idx = (row["cnt"] if row else 0) % len(SPEAKING_MODES)
        return SPEAKING_MODES[idx]


def get_used_urls() -> List[str]:
    init_db()
    with get_conn() as conn:
        rows = conn.execute("SELECT source_url FROM missions").fetchall()
        return [r["source_url"] for r in rows]


def get_top_crutch_words(limit: int = 6) -> List[Dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT word, hit_count, last_seen FROM crutch_words ORDER BY hit_count DESC, last_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_unmastered_phrases(limit: int = 2) -> List[Dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT phrase, meaning, example, times_assigned, times_used
            FROM phrase_bank
            WHERE times_used == 0
            ORDER BY last_seen ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def save_mission(mission_data: Dict[str, Any], for_date: Optional[str] = None) -> int:
    init_db()
    today_str = for_date or date.today().isoformat()
    now_str = datetime.now().isoformat(timespec="seconds")
    target_phrases = mission_data.get("target_phrases", [])

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO missions (
                date, category, speaking_mode, speaking_mode_desc,
                source_name, source_title, source_url,
                reading_excerpt, speaking_prompt,
                target_phrases_json, connector_challenge_json, forbidden_words_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                today_str,
                mission_data["category"],
                mission_data["speaking_mode"],
                mission_data["speaking_mode_desc"],
                mission_data["source_name"],
                mission_data["source_title"],
                mission_data["source_url"],
                mission_data["reading_excerpt"],
                mission_data["speaking_prompt"],
                json.dumps(target_phrases, ensure_ascii=False),
                json.dumps(mission_data.get("connector_challenge", {}), ensure_ascii=False),
                json.dumps(mission_data.get("forbidden_words", []), ensure_ascii=False),
                now_str,
            ),
        )
        mission_id = cur.lastrowid

        for tp in target_phrases:
            phrase = tp.get("phrase", "").strip()
            if not phrase:
                continue
            conn.execute(
                """
                INSERT INTO phrase_bank (phrase, meaning, example, times_assigned, times_used, last_seen)
                VALUES (?, ?, ?, 1, 0, ?)
                ON CONFLICT(phrase) DO UPDATE SET
                    times_assigned = times_assigned + 1,
                    last_seen = excluded.last_seen
                """,
                (phrase, tp.get("meaning", ""), tp.get("example", ""), now_str),
            )
    return int(mission_id)


def _hydrate_mission(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["target_phrases"] = json.loads(d.get("target_phrases_json") or "[]")
    d["connector_challenge"] = json.loads(d.get("connector_challenge_json") or "{}")
    d["forbidden_words"] = json.loads(d.get("forbidden_words_json") or "[]")
    return d


def get_today_mission() -> Optional[Dict[str, Any]]:
    init_db()
    today_str = date.today().isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM missions WHERE date = ? ORDER BY id DESC LIMIT 1",
            (today_str,),
        ).fetchone()
        return _hydrate_mission(row) if row else None


def get_mission_by_id(mission_id: int) -> Optional[Dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()
        return _hydrate_mission(row) if row else None


def save_attempt(
    mission_id: int,
    round_num: int,
    audio_path: Optional[str],
    metrics: Dict[str, Any],
    transcript: str,
    review: Dict[str, Any],
) -> int:
    init_db()
    now_str = datetime.now().isoformat(timespec="seconds")
    targets_used = metrics.get("targets_used", [])
    forbidden_used = metrics.get("forbidden_used", {})
    repeated_words = metrics.get("repeated_words", [])

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO attempts (
                mission_id, round_num, audio_path, duration_sec,
                transcript, wpm, unique_word_ratio,
                targets_used_json, forbidden_used_json, repeated_words_json,
                review_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mission_id,
                round_num,
                audio_path,
                float(metrics.get("duration_sec", 0.0)),
                transcript,
                float(metrics.get("wpm", 0.0)),
                float(metrics.get("unique_word_ratio", 0.0)),
                json.dumps(targets_used, ensure_ascii=False),
                json.dumps(forbidden_used, ensure_ascii=False),
                json.dumps(repeated_words, ensure_ascii=False),
                json.dumps(review, ensure_ascii=False),
                now_str,
            ),
        )
        attempt_id = cur.lastrowid

        # Update mastered phrases
        for phrase in targets_used:
            conn.execute(
                "UPDATE phrase_bank SET times_used = times_used + 1, last_seen = ? WHERE LOWER(phrase) = LOWER(?)",
                (now_str, phrase),
            )

        # Update crutch words from both objective repetition and AI-detected crutch words
        crutch_candidates = set()
        for item in repeated_words[:3]:
            if isinstance(item, dict) and item.get("word"):
                crutch_candidates.add(item["word"].lower())
        for w in review.get("new_crutch_words", []):
            if isinstance(w, str) and len(w.strip()) >= 3:
                crutch_candidates.add(w.strip().lower())

        for w in crutch_candidates:
            conn.execute(
                """
                INSERT INTO crutch_words (word, hit_count, last_seen)
                VALUES (?, 1, ?)
                ON CONFLICT(word) DO UPDATE SET
                    hit_count = hit_count + 1,
                    last_seen = excluded.last_seen
                """,
                (w, now_str),
            )

    return int(attempt_id)


def get_stats_summary() -> Dict[str, Any]:
    init_db()
    with get_conn() as conn:
        total_attempts = conn.execute("SELECT COUNT(*) as c FROM attempts").fetchone()["c"]
        distinct_days = [
            r["d"]
            for r in conn.execute(
                "SELECT DISTINCT substr(created_at, 1, 10) as d FROM attempts ORDER BY d DESC"
            ).fetchall()
        ]
        avg_row = conn.execute(
            "SELECT AVG(wpm) as avg_wpm, AVG(unique_word_ratio) as avg_uwr, SUM(duration_sec) as total_sec FROM attempts"
        ).fetchone()
        phrase_stats = conn.execute(
            "SELECT COUNT(*) as total, SUM(CASE WHEN times_used > 0 THEN 1 ELSE 0 END) as used FROM phrase_bank"
        ).fetchone()
        recent_attempts = [
            dict(r)
            for r in conn.execute(
                """
                SELECT a.*, m.source_title, m.category, m.speaking_mode, m.date
                FROM attempts a
                JOIN missions m ON m.id = a.mission_id
                ORDER BY a.id DESC
                LIMIT 10
                """
            ).fetchall()
        ]

    # Compute streak
    streak = 0
    if distinct_days:
        today_d = date.today()
        latest_d = date.fromisoformat(distinct_days[0])
        if (today_d - latest_d).days <= 1:
            streak = 1
            curr = latest_d
            for d_str in distinct_days[1:]:
                prev = date.fromisoformat(d_str)
                if (curr - prev).days == 1:
                    streak += 1
                    curr = prev
                else:
                    break

    return {
        "total_attempts": total_attempts,
        "practice_days": len(distinct_days),
        "streak": streak,
        "avg_wpm": round(avg_row["avg_wpm"] or 0.0, 1),
        "avg_unique_ratio": round((avg_row["avg_uwr"] or 0.0) * 100, 1),
        "total_minutes": round((avg_row["total_sec"] or 0.0) / 60.0, 1),
        "phrases_assigned": phrase_stats["total"] or 0,
        "phrases_mastered": phrase_stats["used"] or 0,
        "top_crutch_words": get_top_crutch_words(8),
        "recent_attempts": recent_attempts,
    }
