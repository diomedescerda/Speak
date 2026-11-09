# `speak` — Automated Daily English Speaking CLI

An anti-repetition daily speaking practice system that pulls fresh real-world web articles, extracts target expressions & sentence connectors, bans your personal overused "crutch words," records and transcribes your voice locally with Whisper, and delivers instant sentence-by-sentence AI upgrades.

## Quick Start

Run from anywhere in your terminal:

```bash
speak
```

### Daily 5–10 Minute Flow
1. **Read & Absorb (60s):** Read today's short real-world excerpt, speaking prompt, **3 Target Expressions**, **1 Connector Challenge**, and **Forbidden (Taboo) Words**.
2. **Speak Round 1 (60–90s):** Press `[Enter]` to record from your microphone (or `[t]` to type/dictate text). Press `[Enter]` when finished.
3. **Instant Local Transcription + AI Review:**
   - Transcribes locally on CPU via `openai/whisper-base.en`
   - Detects which target phrases you used, which forbidden words slipped in, and which words you repeated
   - Gives **3 Sentence-by-Sentence Upgrades** (Casual & Articulate) + a **Polished Native Version** of your exact thoughts to read aloud
4. **Round 2 Upgrade Retry (60s):** Press `[r]` right after reading the upgrades to re-record a 60-second version using the upgraded phrasing.

## Commands

| Command | Description |
| :--- | :--- |
| `speak` | Start today's pre-fetched speaking session (instant load). |
| `speak new` | Fetch a brand-new web article and generate a fresh mission right now. |
| `speak -c psychology` | Start a new session filtered by topic (`psychology`, `wisdom`, `tech`, `life`, `current`). |
| `speak stats` | View your streak, average WPM, vocabulary variety, mastered phrases, and top personal crutch words. |
| `speak history` | List saved Markdown coaching reports (`~/.local/share/speak/reviews/`) and audio files. |
| `speak prep` | Pre-fetch today's mission in the background (runs automatically every day via `systemd --user` timer `speak-prep.timer`). |
| `speak review-text "..."` | Directly review a text/dictated paragraph against today's mission. |

## Where Data Is Stored
- **Database:** `~/.local/share/speak/speak.db`
- **Markdown Daily Reviews:** `~/.local/share/speak/reviews/YYYY-MM-DD.md`
- **Audio Recordings:** `~/.local/share/speak/recordings/`
- **Daily Timer:** `~/.config/systemd/user/speak-prep.timer` (`systemctl --user status speak-prep.timer`)
