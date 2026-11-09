import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def _find_opencode_bin() -> str:
    found = shutil.which("opencode")
    if found:
        return found
    fallback = Path.home() / ".opencode" / "bin" / "opencode"
    return str(fallback) if fallback.exists() else "opencode"


def _extract_json(raw_text: str) -> Optional[Dict[str, Any]]:
    if not raw_text:
        return None
    # Remove ANSI escape sequences
    cleaned = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", raw_text)
    # Try code fence first
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except Exception:
            pass

    # Find outermost JSON object
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start : end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass
    return None


def _run_opencode_json(prompt: str, timeout: int = 75) -> Optional[Dict[str, Any]]:
    workdir = Path("/tmp/opencode")
    workdir.mkdir(parents=True, exist_ok=True)
    cmd = [_find_opencode_bin(), "run", prompt]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "NO_COLOR": "1"},
        )
        parsed = _extract_json(proc.stdout) or _extract_json(proc.stderr)
        return parsed
    except Exception:
        return None


def build_daily_mission(
    article: Dict[str, Any],
    speaking_mode: Dict[str, str],
    crutch_words: List[Dict[str, Any]],
    unmastered_phrases: List[Dict[str, Any]],
) -> Dict[str, Any]:
    crutch_list = [c["word"] for c in crutch_words[:4]]
    review_phrase_hint = ""
    if unmastered_phrases:
        up = unmastered_phrases[0]
        review_phrase_hint = (
            f"If natural, include this previously unmastered expression as one of the 3 target_phrases: "
            f"'{up['phrase']}' ({up['meaning']})."
        )

    prompt = f"""Do NOT call any tools or read any files. Respond with ONLY a valid JSON object (no markdown commentary outside JSON).

You are designing a daily English speaking practice mission to stop an intermediate-to-advanced speaker from repeating the same basic vocabulary and sentence structures every day.

SOURCE ARTICLE:
- Category: {article['category']}
- Source: {article['source_name']}
- Title: {article['title']}
- Raw Content: {article['content']}

TODAY'S SPEAKING FORMAT:
- Mode Name: {speaking_mode['name']}
- Mode Description: {speaking_mode['description']}

USER'S HISTORICAL OVERUSED CRUTCH WORDS: {crutch_list if crutch_list else ['very', 'really', 'good', 'think', 'thing']}
{review_phrase_hint}

Return ONLY raw JSON with this exact schema:
{{
  "reading_excerpt": "A tight, engaging 120-160 word excerpt/digest of the article above, keeping rich, natural English idioms and phrasing so the user has great input to read before speaking.",
  "speaking_prompt": "A specific 1-2 sentence speaking challenge tailored to the article and today's Speaking Mode ({speaking_mode['name']}).",
  "target_phrases": [
    {{
      "phrase": "natural multi-word expression, phrasal verb, or collocation from/inspired by the text",
      "meaning": "concise plain-English meaning",
      "example": "natural spoken example sentence"
    }},
    {{
      "phrase": "second expression",
      "meaning": "concise meaning",
      "example": "spoken example sentence"
    }},
    {{
      "phrase": "third expression",
      "meaning": "concise meaning",
      "example": "spoken example sentence"
    }}
  ],
  "connector_challenge": {{
    "phrase": "A natural discourse marker or sentence-framing structure (e.g. 'What stood out to me is...', 'On the flip side...', 'Much as I see why...', 'Come to think of it...')",
    "usage_tip": "How to use it to connect two ideas smoothly",
    "example": "Short spoken example"
  }},
  "forbidden_words": [
    {{
      "word": "single overused basic word to ban today (include 1-2 from user's crutch words + 2 obvious basic words for this topic)",
      "instead_use": "2-3 sharper alternatives"
    }}
  ]
}}"""

    res = _run_opencode_json(prompt)
    if not res or "reading_excerpt" not in res or "target_phrases" not in res:
        # Fallback deterministic mission if LLM fails
        words = article["content"].split()
        excerpt = " ".join(words[:145]) + ("..." if len(words) > 145 else "")
        res = {
            "reading_excerpt": excerpt,
            "speaking_prompt": (
                f"[{speaking_mode['name']}] Summarize the main point of '{article['title']}' in 30 seconds, "
                f"then share your honest perspective on how it applies to everyday life."
            ),
            "target_phrases": [
                {
                    "phrase": "boil down to",
                    "meaning": "to have something as the main or most fundamental part",
                    "example": "At the end of the day, the argument boils down to how we prioritize our attention.",
                },
                {
                    "phrase": "second nature",
                    "meaning": "a habit or skill that has become automatic",
                    "example": "Once you practice with constraints daily, reaching for better phrasing becomes second nature.",
                },
                {
                    "phrase": "put into perspective",
                    "meaning": "to clarify the true importance of something by comparing it to a bigger picture",
                    "example": "Reading this really puts my daily frustrations into perspective.",
                },
            ],
            "connector_challenge": {
                "phrase": "What really stood out to me was...",
                "usage_tip": "Use this to highlight the single most interesting detail instead of saying 'I think X is good'.",
                "example": "What really stood out to me was how counterintuitive the author's conclusion was.",
            },
            "forbidden_words": [
                {"word": "good", "instead_use": "compelling, spot-on, worthwhile"},
                {"word": "very", "instead_use": "remarkably, genuinely, deeply"},
                {"word": "thing", "instead_use": "factor, aspect, takeaway"},
            ],
        }

    return {
        "category": article["category"],
        "speaking_mode": speaking_mode["name"],
        "speaking_mode_desc": speaking_mode["description"],
        "source_name": article["source_name"],
        "source_title": article["title"],
        "source_url": article["url"],
        "reading_excerpt": res["reading_excerpt"],
        "speaking_prompt": res["speaking_prompt"],
        "target_phrases": res["target_phrases"][:3],
        "connector_challenge": res.get("connector_challenge", {}),
        "forbidden_words": res.get("forbidden_words", [])[:4],
    }


def review_attempt(
    mission: Dict[str, Any],
    metrics: Dict[str, Any],
    transcript: str,
    round_num: int = 1,
    prev_transcript: Optional[str] = None,
) -> Dict[str, Any]:
    target_list = [tp.get("phrase", "") for tp in mission.get("target_phrases", [])]
    connector_phrase = mission.get("connector_challenge", {}).get("phrase", "")
    forbidden_list = [fw.get("word", "") for fw in mission.get("forbidden_words", [])]

    round_context = (
        f"This is Round 1."
        if round_num == 1
        else f"This is Round 2 (the user's immediate retry after feedback). Their Round 1 transcript was: {json.dumps(prev_transcript or '')}. Highlight specifically how Round 2 improved over Round 1!"
    )

    prompt = f"""Do NOT call any tools or read any files. Respond with ONLY a valid JSON object.

You are an expert English speaking coach helping the user break out of repeating the same basic words and sentence patterns.

MISSION CONTEXT:
- Topic: {mission['source_title']} ({mission['category']})
- Speaking Mode: {mission['speaking_mode']}
- Prompt: {mission['speaking_prompt']}
- Target Expressions to Use: {target_list}
- Connector Challenge: {connector_phrase}
- Forbidden (Taboo) Words: {forbidden_list}

OBJECTIVE SPEECH METRICS:
- Duration: {metrics.get('duration_sec')}s | Pace: {metrics.get('wpm')} WPM | Unique Word Ratio: {round(metrics.get('unique_word_ratio', 0)*100, 1)}%
- Auto-detected Targets Used: {metrics.get('targets_used')}
- Auto-detected Forbidden Words Slipped: {metrics.get('forbidden_used')}
- Most Repeated Words in Transcript: {metrics.get('repeated_words')}

{round_context}

USER'S SPOKEN TRANSCRIPT:
\"\"\"{transcript}\"\"\"

Return ONLY raw JSON matching this exact schema:
{{
  "score": 82,
  "summary_feedback": "2-3 sentences of direct, insightful feedback on their ideas, flow, and how well they broke out of repetitive phrasing.",
  "constraint_check": "Brief assessment of how naturally they used (or missed) the target expressions and connector, and whether they avoided the forbidden words.",
  "repetitive_habits_spotted": [
    "Specific observation 1 about a word, filler, or sentence starter they leaned on too much in this recording",
    "Specific observation 2 about grammar or structure monotony"
  ],
  "new_crutch_words": ["1 to 3 single basic/filler words they overused in this transcript to ban in future sessions"],
  "sentence_upgrades": [
    {{
      "original": "Exact quote or slightly clunky sentence from user's transcript",
      "why_upgrade": "Brief explanation of why it sounds basic, repetitive, or awkward",
      "natural_casual": "How a fluent speaker would say this naturally in casual conversation",
      "natural_articulate": "How an articulate speaker would phrase this in a deeper discussion"
    }},
    {{
      "original": "Second quote from user's transcript",
      "why_upgrade": "Why to upgrade it",
      "natural_casual": "Casual upgrade",
      "natural_articulate": "Articulate upgrade"
    }},
    {{
      "original": "Third quote from user's transcript",
      "why_upgrade": "Why to upgrade it",
      "natural_casual": "Casual upgrade",
      "natural_articulate": "Articulate upgrade"
    }}
  ],
  "native_model_version": "A 4-5 sentence cohesive, natural spoken paragraph expressing the USER'S exact points from their transcript, while smoothly weaving in today's target phrases so the user can read it aloud to feel the rhythm.",
  "round2_challenge": "One concrete, actionable instruction for their 60-second Round 2 retry (or celebratory note if Round 2)."
}}"""

    res = _run_opencode_json(prompt, timeout=90)
    if not res or "sentence_upgrades" not in res:
        rep_words = [r["word"] for r in metrics.get("repeated_words", [])[:3]]
        res = {
            "score": 75,
            "summary_feedback": (
                f"Good effort speaking for {metrics.get('duration_sec')}s at {metrics.get('wpm')} WPM. "
                f"You hit {len(metrics.get('targets_used', []))} target expression(s)."
            ),
            "constraint_check": (
                f"Used targets: {', '.join(metrics.get('targets_used', [])) or 'None yet'}. "
                f"Forbidden words slipped: {', '.join(metrics.get('forbidden_used', {}).keys()) or 'None (great job!)'}."
            ),
            "repetitive_habits_spotted": [
                f"Most repeated content words in this take: {', '.join(rep_words) if rep_words else 'None prominent'}.",
                "Try varying how you start each sentence by using today's connector challenge.",
            ],
            "new_crutch_words": rep_words[:2],
            "sentence_upgrades": [
                {
                    "original": transcript[:120] + ("..." if len(transcript) > 120 else ""),
                    "why_upgrade": "Weave in one of today's target expressions to make your opening hook sharper.",
                    "natural_casual": f"{connector_phrase} how this applies to everyday habits.",
                    "natural_articulate": f"Looking closely at the argument, {target_list[0] if target_list else 'the core idea'} shapes how we approach the problem.",
                }
            ],
            "native_model_version": (
                f"{connector_phrase} the main takeaway from this piece. "
                f"Try re-recording once more while deliberately working in: {', '.join(target_list)}."
            ),
            "round2_challenge": f"Re-record for 60 seconds and force yourself to include at least 2 of: {', '.join(target_list)}.",
        }
    return res
