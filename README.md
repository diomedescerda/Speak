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
| `speak user set diomedes` | Select the Diomedes profile and enable Git sync after practice. |
| `speak user` | Show the active profile and its storage and sync settings. |

## 🇯🇵 Japanese Speaking Coach (`speak ja` / `speak-ja`)

Built for progressing from beginner (N5) to connected conversational Japanese (N4+) step by step, with inline Furigana, native neural TTS shadowing, and local Japanese Whisper ASR (`openai/whisper-base`).

```bash
speak ja        # or simply: speak-ja
```

### Japanese Daily Flow
1. **Read & Shadow (`[l]`):** Read the short Japanese model passage with inline furigana `漢字(かんじ)` and English translation. Press `[l]` to hear it spoken aloud by a native Japanese neural voice (`ja-JP-NanamiNeural`) and shadow along.
2. **Use Your Scaffolding:** Review the **Sentence Starter Skeleton**, **Core Grammar Frame**, **3 Vocab Building Blocks**, and **Particle & Conjugation Watchouts**.
3. **Speak Round 1 (25s–65s):** Press `[Enter]` to record your voice in Japanese (or `[t]` to type Japanese text).
4. **Shadow Your Upgraded Thoughts & Retry Round 2:**
   - Receive particle/conjugation feedback, **Polite (`です/ます`) & Casual Sentence Upgrades**, and a **Polished Native Japanese Version** of your exact ideas.
   - Press `[l]` to listen to your Polished Native Japanese Version spoken aloud via TTS, shadow it, and press `[r]` to record Round 2!

### Japanese Commands

| Command | Description |
| :--- | :--- |
| `speak ja` / `speak-ja` | Start today's Japanese speaking mission (auto-scales across Stages 1–5). |
| `speak ja new` | Generate a brand-new Japanese mission right now. |
| `speak ja -s 2` | Practice a specific curriculum stage (`1`=Early N5, `2`=Mid N5, `3`=Complete N5, `4`=N5→N4 Bridge, `5`=N4+ Conversational). |
| `speak ja listen` | Play today's Japanese model passage aloud (`--slow` for slower `-22%` shadowing). |
| `speak ja stats` | View your current Japanese stage, streak, CPM (Characters Per Minute), mastered grammar/vocab, and personal particle watchouts. |
| `speak ja history` | List saved Japanese Markdown reviews (`~/.local/share/speak/reviews/ja/`). |
| `speak ja prep` | Pre-generate today's Japanese mission in the background. |
| `speak ja review-text "..."` | Directly review typed or dictated Japanese text against today's mission. |
| `speak sync` / `speak ja sync` | Manually pull/commit/push personal progress (`data/diomedes/`) to GitHub. |

## Where Data Is Stored
- **Default (Any User):**
  - **Database:** `~/.local/share/speak/speak.db`
  - **Markdown Reviews:** `~/.local/share/speak/reviews/` (English) and `~/.local/share/speak/reviews/ja/` (Japanese)
- **Owner Repo Persistence (`Diomedes`):**
  - Run `speak user set diomedes` once per install. Speak saves the profile in local `data/config.json`, stores `speak.db` and `reviews/` under `<repo>/data/diomedes/`, and commits and pushes completed sessions and reviews. The Git author name remains the fallback when no profile is selected. `SPEAK_USER` can override the selected profile.
  - Run `speak user set local` to use `~/.local/share/speak/` for your progress.
- **Audio Recordings & TTS Cache (Always Local):** `~/.local/share/speak/recordings/` & `~/.local/share/speak/tts_cache/`
- **Daily Timer:** `~/.config/systemd/user/speak-prep.timer` (`systemctl --user status speak-prep.timer`)

## Practice from an iPhone

The mobile web app offers today's English and Japanese missions, microphone recording or keyboard dictation, coaching feedback, a second round, and saved practice history. Japanese model passages and polished responses can be played on the phone.

Tap **Stop and save** to submit a microphone recording. If the timer stops the recording, or saving fails, the preview shows **Save and get feedback** so you can submit the same take. Wait for **Practice saved to your history** before leaving the page. Pillars credits saved attempts, not recordings still in preview.

### Run the web service

On the Linux host, install FFmpeg and set up OpenCode as for the CLI. Create a Python 3.12 environment with CPU PyTorch and the web dependencies.

```bash
uv venv --python 3.12
uv pip install --index https://download.pytorch.org/whl/cpu torch
uv pip install -r requirements-web.txt
.venv/bin/python -m speak_web --port 8765
```

The app listens at `http://127.0.0.1:8765`. It uses the CLI's default database and audio directories. When the CLI runs from a separate checkout, set `SPEAK_DATA_DIR` to its active data directory, the one with `speak.db`. Web submissions save to the shared database and write their own Markdown reports. A user-level systemd service can keep the web process running under the same Linux account as the CLI. Leave the host awake for phone access.

### Open it privately

1. Join the Linux host and iPhone to the same [Tailscale network](https://tailscale.com/docs/install/ios). Enable HTTPS certificates in Tailscale if prompted.
2. Configure the web service with `SPEAK_TAILSCALE_HOST` set to the host's full `.ts.net` name and `SPEAK_ALLOWED_LOGIN` set to your Tailscale login. Restart the service with those settings. The proxy supplies the signed-in user's identity.
3. Run `sudo tailscale serve --bg 8765` on a system-managed Tailscale installation. Open the HTTPS URL it prints in Safari. From Safari's share menu, choose **Add to Home Screen** and allow microphone access when recording. [Tailscale Serve setup](https://tailscale.com/docs/features/tailscale-serve)

### Verify the mobile flow

```bash
uv pip install -r tests/requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python -m unittest discover -s tests -v
```
