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


def generate_ja_mission(
    stage_bundle: Dict[str, Any],
    unmastered_vocab: List[Dict[str, Any]],
    top_traps: List[Dict[str, Any]],
) -> Dict[str, Any]:
    topic = stage_bundle["topic"]
    stage_num = stage_bundle["stage"]
    stage_name = stage_bundle["stage_name"]
    target_seconds = stage_bundle["target_seconds"]
    grammar_scope = stage_bundle["grammar_scope"]

    trap_list = [t["trap"] for t in top_traps] if top_traps else ["Mixing up に vs で for location of action", "Dropping を or は"]
    recycle_list = [f"{v['word']} ({v['meaning']})" for v in unmastered_vocab] if unmastered_vocab else []

    prompt = f"""Do NOT call any tools or read any files. Respond with ONLY a valid JSON object.

You are a warm, structured Japanese speaking coach designing a daily speaking mission for a beginner who can read Hiragana, Katakana, and basic Kanji (with Furigana), and is learning to speak Japanese out loud step by step.

CURRICULUM CONTEXT:
- Stage: {stage_name}
- Allowed Grammar Scope: {grammar_scope}
- Today's Topic: {topic['title']}
- Scenario: {topic['scenario']}
- Suggested Core Grammar Pattern: {topic['focus_grammar']}
- Target Speaking Duration: {target_seconds} seconds
- Past Particle/Grammar Traps to Watch Out For: {json.dumps(trap_list, ensure_ascii=False)}
- Previously Unmastered Vocab to Optionally Recycle (pick at most 1 if relevant): {json.dumps(recycle_list, ensure_ascii=False)}

FURIGANA RULE (CRITICAL):
Whenever you write Japanese containing Kanji in ANY field (`model_japanese`, `speaking_prompt_ja`, `starter_template`, `grammar_frame`, `vocab_blocks`, `particle_traps`), attach inline furigana in square brackets immediately after the kanji word, e.g. `私[わたし]は毎朝[まいあさ]七時[しちじ]に起[お]きます。` Do NOT put furigana on pure hiragana/katakana words.

Return ONLY raw JSON matching this exact schema:
{{
  "model_japanese": "A natural 3-4 sentence Japanese model monologue for this scenario at Stage {stage_num} level, using polite です/ます form and inline furigana 漢字[かんじ].",
  "model_english": "Natural English translation of model_japanese.",
  "speaking_prompt_ja": "A friendly prompt question in Japanese (with inline furigana 漢字[かんじ]) asking the user about today's scenario.",
  "speaking_prompt_en": "Clear English prompt telling the user what to say in their {target_seconds}-second recording.",
  "starter_template": "A fill-in-the-blank Japanese sentence skeleton with [___] placeholders and inline furigana 漢字[かんじ] so the user can start speaking right away without freezing.",
  "grammar_frame": {{
    "pattern": "{topic['focus_grammar']}",
    "meaning": "Clear English meaning of this grammar frame",
    "structure": "How to conjugate/attach nouns, verbs, or adjectives to this frame",
    "example_ja": "One natural example sentence with inline furigana 漢字[かんじ]",
    "example_en": "English translation of example_ja"
  }},
  "vocab_blocks": [
    {{
      "word": "Japanese word/expression 1 with inline furigana 漢字[かんじ]",
      "reading": "pure hiragana/katakana reading without brackets",
      "meaning": "concise English meaning",
      "example_ja": "Short example phrase/sentence with inline furigana 漢字[かんじ]"
    }},
    {{
      "word": "Japanese word/expression 2 with inline furigana 漢字[かんじ]",
      "reading": "pure hiragana/katakana reading without brackets",
      "meaning": "concise English meaning",
      "example_ja": "Short example phrase/sentence with inline furigana 漢字[かんじ]"
    }},
    {{
      "word": "Japanese word/expression 3 with inline furigana 漢字[かんじ]",
      "reading": "pure hiragana/katakana reading without brackets",
      "meaning": "concise English meaning",
      "example_ja": "Short example phrase/sentence with inline furigana 漢字[かんじ]"
    }}
  ],
  "particle_traps": [
    {{
      "trap_title": "Name of particle or conjugation watchout (e.g. に vs で for place, or ます-stem + たい)",
      "wrong": "Common beginner mistake in Japanese (with inline furigana)",
      "right": "Correct natural Japanese (with inline furigana)",
      "explanation": "1-sentence clear explanation in English"
    }},
    {{
      "trap_title": "Second watchout relevant to this topic",
      "wrong": "Common mistake",
      "right": "Correct Japanese",
      "explanation": "1-sentence explanation in English"
    }}
  ]
}}"""

    res = _run_opencode_json(prompt, timeout=90)
    if not res or "model_japanese" not in res or "vocab_blocks" not in res:
        res = {
            "model_japanese": (
                "はじめまして。私[わたし]はエンジニアです。"
                "毎日[まいにち]、家[いえ]で仕事[しごと]をします。"
                "コーヒーがとても好[す]きです。どうぞよろしくお願[ねが]いします。"
            ),
            "model_english": (
                "Nice to meet you. I am an engineer. "
                "Every day, I work at home. "
                "I like coffee very much. Nice to meet you."
            ),
            "speaking_prompt_ja": "あなたについて少[すこ]し話[はな]してください。仕事[しごと]や好[す]きなものは何[なん]ですか？",
            "speaking_prompt_en": f"{topic['scenario']} Aim for {target_seconds} seconds using polite です/ます sentences.",
            "starter_template": "わたしは [___] です。毎日[まいにち] [___] をします。[___] が好[す]きです。",
            "grammar_frame": {
                "pattern": topic["focus_grammar"],
                "meaning": "Core sentence structure for today's topic",
                "structure": "Noun + は + Noun + です / Verb-ます",
                "example_ja": "私[わたし]は毎日[まいにち]日本語[にほんご]を勉強[べんきょう]します。",
                "example_en": "I study Japanese every day.",
            },
            "vocab_blocks": [
                {
                    "word": "毎日[まいにち]",
                    "reading": "まいにち",
                    "meaning": "every day",
                    "example_ja": "毎日[まいにち]コーヒーを飲[の]みます。",
                },
                {
                    "word": "仕事[しごと]",
                    "reading": "しごと",
                    "meaning": "work / job",
                    "example_ja": "九時[くじ]に仕事[しごと]を始[はじ]めます。",
                },
                {
                    "word": "少[すこ]しずつ",
                    "reading": "すこしずつ",
                    "meaning": "little by little",
                    "example_ja": "少[すこ]しずつ日本語[にほんご]を話[はな]します。",
                },
            ],
            "particle_traps": [
                {
                    "trap_title": "が with 好[す]きです (likes)",
                    "wrong": "コーヒーを好[す]きです",
                    "right": "コーヒーが好[す]きです",
                    "explanation": "好[す]き (suki) is an adjective in Japanese, so mark the thing you like with が (or は), not を.",
                },
                {
                    "trap_title": "で vs に for where an action happens",
                    "wrong": "家[いえ]に仕事[しごと]をします",
                    "right": "家[いえ]で仕事[しごと]をします",
                    "explanation": "Use で to mark the location where an active action (like working or eating) takes place.",
                },
            ],
        }

    return {
        "stage": stage_num,
        "stage_name": stage_name,
        "topic_id": topic["id"],
        "topic_title": topic["title"],
        "scenario": topic["scenario"],
        "target_seconds": target_seconds,
        "model_japanese": res["model_japanese"],
        "model_english": res["model_english"],
        "speaking_prompt_en": res["speaking_prompt_en"],
        "speaking_prompt_ja": res["speaking_prompt_ja"],
        "starter_template": res.get("starter_template", ""),
        "grammar_frame": res.get("grammar_frame", {}),
        "vocab_blocks": res.get("vocab_blocks", [])[:3],
        "particle_traps": res.get("particle_traps", [])[:2],
    }


def review_ja_attempt(
    mission: Dict[str, Any],
    metrics: Dict[str, Any],
    transcript: str,
    round_num: int = 1,
    prev_transcript: Optional[str] = None,
) -> Dict[str, Any]:
    vocab_list = [f"{vb.get('word', '')} ({vb.get('meaning', '')})" for vb in mission.get("vocab_blocks", [])]
    grammar_pattern = mission.get("grammar_frame", {}).get("pattern", "")

    round_context = (
        "This is Round 1."
        if round_num == 1
        else f"This is Round 2 (the user's retry after listening to native audio & reviewing feedback). Their Round 1 transcript was: {json.dumps(prev_transcript or '', ensure_ascii=False)}. Highlight specifically how Round 2 improved over Round 1!"
    )

    prompt = f"""Do NOT call any tools or read any files. Respond with ONLY a valid JSON object.

You are an encouraging, sharp Japanese speaking coach helping a beginner build confidence speaking Japanese out loud.

MISSION CONTEXT:
- Stage: {mission['stage_name']}
- Topic: {mission['topic_title']} — {mission['scenario']}
- Prompt (EN): {mission['speaking_prompt_en']}
- Prompt (JA): {mission['speaking_prompt_ja']}
- Core Grammar Frame: {grammar_pattern}
- 3 Target Vocab Building Blocks: {json.dumps(vocab_list, ensure_ascii=False)}

OBJECTIVE SPEECH METRICS:
- Duration: {metrics.get('duration_sec')}s (Target: {mission.get('target_seconds')}s)
- Spoken Characters: {metrics.get('char_count')} chars | Pace: {metrics.get('cpm')} CPM (Characters Per Minute)
- Auto-detected Grammar Frame Used: {metrics.get('grammar_used')}
- Auto-detected Vocab Blocks Used: {json.dumps(metrics.get('vocab_used', []), ensure_ascii=False)}

{round_context}

USER'S SPOKEN TRANSCRIPT (transcribed by Whisper ASR — note that minor homophone kanji choices are from ASR, so judge spoken pronunciation/particles/conjugation):
\"\"\"{transcript}\"\"\"

FURIGANA RULE (CRITICAL):
Whenever you write Japanese with Kanji in `sentence_upgrades` or `native_model_version`, attach inline furigana in square brackets immediately after each kanji word, e.g. `私[わたし]は毎日[まいにち]日本語[にほんご]を勉強[べんきょう]しています。`

Return ONLY raw JSON matching this exact schema:
{{
  "score": 84,
  "summary_feedback": "2-3 sentences of warm, specific English feedback on what they communicated well, their pacing, and clarity.",
  "scaffolding_check": "Brief English assessment of how they used today's Core Grammar Frame and the 3 Vocab Building Blocks.",
  "traps_spotted": [
    "Specific particle, verb conjugation, or word-order fix 1 (written in English with short Japanese examples)",
    "Specific observation 2"
  ],
  "sentence_upgrades": [
    {{
      "original": "Quote or phrase from user's transcript",
      "why_upgrade": "Clear English explanation of the particle/conjugation fix or how to make it sound more natural",
      "natural_polite": "Polite です/ます version with inline furigana 漢字[かんじ]",
      "natural_casual": "Casual conversational version with inline furigana 漢字[かんじ]"
    }},
    {{
      "original": "Second quote or phrase from user's transcript",
      "why_upgrade": "English explanation",
      "natural_polite": "Polite です/ます version with inline furigana 漢字[かんじ]",
      "natural_casual": "Casual conversational version with inline furigana 漢字[かんじ]"
    }}
  ],
  "native_model_version": "A natural 3-5 sentence polite Japanese paragraph (with inline furigana 漢字[かんじ]) expressing the USER'S exact personal ideas from their transcript while smoothly weaving in today's grammar frame and vocab blocks. The user will listen to this via TTS and shadow it!",
  "native_model_english": "Natural English translation of native_model_version.",
  "round2_challenge": "One concrete, encouraging instruction in English for their Round 2 retry (tell them to press [l] to listen & shadow the Polished Native Version first!)."
}}"""

    res = _run_opencode_json(prompt, timeout=90)
    if not res or "sentence_upgrades" not in res or "native_model_version" not in res:
        res = {
            "score": 78,
            "summary_feedback": (
                f"Great job speaking Japanese out loud for {metrics.get('duration_sec')}s "
                f"({metrics.get('char_count')} chars at {metrics.get('cpm')} CPM)! "
                f"You used {len(metrics.get('vocab_used', []))}/3 target vocab blocks."
            ),
            "scaffolding_check": (
                f"Grammar frame ({grammar_pattern}): {'Used!' if metrics.get('grammar_used') else 'Try weaving it in on Round 2'}. "
                f"Vocab used: {', '.join(metrics.get('vocab_used', [])) or 'None detected yet'}."
            ),
            "traps_spotted": [
                "Watch your particles (は, が, を, に, で) between nouns and verbs.",
                "Keep a steady rhythm and finish each sentence clearly with です or ます.",
            ],
            "sentence_upgrades": [
                {
                    "original": transcript[:80] if transcript else "（発話なし）",
                    "why_upgrade": "Connect your ideas smoothly using today's core grammar frame.",
                    "natural_polite": mission.get("model_japanese", ""),
                    "natural_casual": mission.get("model_japanese", ""),
                }
            ],
            "native_model_version": mission.get("model_japanese", ""),
            "native_model_english": mission.get("model_english", ""),
            "round2_challenge": "Press [l] to listen to the native audio once, shadow it out loud, and record Round 2!",
        }
    return res
