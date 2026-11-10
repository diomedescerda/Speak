#!/usr/bin/env python3
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import typer
from rich.box import ROUNDED
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

# Ensure local imports work regardless of working directory or symlink
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ai
import audio
import db
import fetcher
import ja_curriculum

app = typer.Typer(
    help="Automated Daily Speaking System (English & Japanese) — Daily Input + Scaffolding + AI Review.",
    invoke_without_command=True,
    no_args_is_help=False,
)
ja_app = typer.Typer(
    help="🇯🇵 Japanese Speaking Coach — Progressive N5→N4 Curriculum, Furigana Scaffolding, Native TTS Shadowing & AI Review.",
    invoke_without_command=True,
    no_args_is_help=False,
)
app.add_typer(ja_app, name="ja")
console = Console()


def _auto_sync_if_diomedes(reason: str = "session", pull_first: bool = False) -> None:
    if not db.IS_DIOMEDES:
        return
    with console.status("[bold cyan]☁️ Syncing Diomedes progress to GitHub (data/diomedes/)...[/bold cyan]"):
        res = db.sync_diomedes_data(reason=reason, pull_first=pull_first)
    if res.get("synced"):
        console.print(f"[dim]☁️ {res.get('message')}[/dim]")
    else:
        console.print(f"[dim yellow]☁️ {res.get('message')}[/dim yellow]")


def _prepare_mission(force_new: bool = False, category: Optional[str] = None, quiet: bool = False) -> Dict[str, Any]:
    db.init_db()
    if not force_new and not category:
        existing = db.get_today_mission()
        if existing:
            return existing

    used_urls = db.get_used_urls()
    speaking_mode = db.get_next_speaking_mode()
    crutch_words = db.get_top_crutch_words(5)
    unmastered = db.get_unmastered_phrases(2)

    if quiet:
        article = fetcher.fetch_fresh_article(used_urls, preferred_category=category)
        mission_data = ai.build_daily_mission(article, speaking_mode, crutch_words, unmastered)
        mission_id = db.save_mission(mission_data)
        return db.get_mission_by_id(mission_id)  # type: ignore

    with console.status("[bold cyan]Fetching fresh web content & building today's speaking mission...[/bold cyan]"):
        article = fetcher.fetch_fresh_article(used_urls, preferred_category=category)
        mission_data = ai.build_daily_mission(article, speaking_mode, crutch_words, unmastered)
        mission_id = db.save_mission(mission_data)
        mission = db.get_mission_by_id(mission_id)
    return mission  # type: ignore


def render_mission_card(mission: Dict[str, Any]) -> None:
    console.print()
    header = (
        f"[bold cyan]{mission['date']}[/bold cyan]  •  "
        f"[bold magenta]{mission['category']}[/bold magenta]  •  "
        f"Mode: [bold yellow]{mission['speaking_mode']}[/bold yellow]\n"
        f"[bold white]{mission['source_title']}[/bold white] [dim]({mission['source_name']} — {mission['source_url']})[/dim]"
    )
    console.print(Panel(header, title="[bold green]🌐 TODAY'S SPEAKING INPUT[/bold green]", box=ROUNDED))

    # Reading excerpt
    console.print(
        Panel(
            f"{mission['reading_excerpt']}\n\n"
            f"[bold yellow]🎙️ YOUR PROMPT ({mission['speaking_mode']}):[/bold yellow]\n"
            f"[bold white]{mission['speaking_prompt']}[/bold white]\n"
            f"[dim]{mission['speaking_mode_desc']}[/dim]",
            title="[bold cyan]1. Read & Absorb (60s)[/bold cyan]",
            box=ROUNDED,
        )
    )

    # Constraints table: Target phrases + Connector + Forbidden words
    grid = Table(box=ROUNDED, show_header=True, header_style="bold cyan", expand=True)
    grid.add_column("🎯 Target Expressions (Use 2+)", ratio=5)
    grid.add_column("🚫 Forbidden Words (Taboo)", ratio=3)

    targets_lines = []
    for i, tp in enumerate(mission.get("target_phrases", []), 1):
        targets_lines.append(
            f"[bold green]{i}. \"{tp.get('phrase', '')}\"[/bold green] — {tp.get('meaning', '')}\n"
            f"   [dim]Ex: \"{tp.get('example', '')}\"[/dim]"
        )
    conn = mission.get("connector_challenge", {})
    if conn.get("phrase"):
        targets_lines.append(
            f"\n[bold yellow]🔗 Structure Challenge:[/bold yellow] [bold white]\"{conn.get('phrase')}\"[/bold white]\n"
            f"   [dim]{conn.get('usage_tip', '')} (Ex: \"{conn.get('example', '')}\")[/dim]"
        )

    forbidden_lines = []
    for fw in mission.get("forbidden_words", []):
        forbidden_lines.append(
            f"❌ [bold red]{fw.get('word', '')}[/bold red]\n"
            f"   [green]→ Try:[/green] {fw.get('instead_use', '')}"
        )

    grid.add_row("\n".join(targets_lines), "\n\n".join(forbidden_lines) or "None today")
    console.print(grid)


def render_review_card(
    mission: Dict[str, Any],
    metrics: Dict[str, Any],
    transcript: str,
    review: Dict[str, Any],
    round_num: int,
) -> None:
    console.print()
    console.print(
        Panel(
            f"[italic white]\"{transcript}\"[/italic white]",
            title=f"[bold cyan]📝 Round {round_num} Transcript ({metrics['duration_sec']}s • {metrics['wpm']} WPM • {round(metrics['unique_word_ratio']*100, 1)}% Unique Words)[/bold cyan]",
            box=ROUNDED,
        )
    )

    targets_hit = ", ".join(metrics.get("targets_used", [])) or "None auto-detected"
    forbidden_hit = (
        ", ".join(f"{w} ({c}x)" for w, c in metrics.get("forbidden_used", {}).items())
        or "0 slipped (Clean!)"
    )
    rep_words = (
        ", ".join(f"{r['word']} ({r['count']}x)" for r in metrics.get("repeated_words", []))
        or "None excessive"
    )

    habits_bullets = "\n".join(f"• {h}" for h in review.get("repetitive_habits_spotted", []))
    overview_body = (
        f"[bold green]Coach Score:[/bold green] [bold white]{review.get('score', '—')}/100[/bold white]\n"
        f"{review.get('summary_feedback', '')}\n\n"
        f"[bold cyan]Constraint Check:[/bold cyan] {review.get('constraint_check', '')}\n"
        f"  • [green]Targets Detected:[/green] {targets_hit}\n"
        f"  • [red]Forbidden Words:[/red] {forbidden_hit}\n"
        f"  • [yellow]Repeated Words in Take:[/yellow] {rep_words}\n\n"
        f"[bold yellow]🔍 Repetitive Habits Spotted:[/bold yellow]\n{habits_bullets}"
    )
    console.print(Panel(overview_body, title=f"[bold green]🧠 AI Speaking Review (Round {round_num})[/bold green]", box=ROUNDED))

    # Sentence upgrades
    upgrades = review.get("sentence_upgrades", [])
    if upgrades:
        up_table = Table(title="🚀 Top Sentence Upgrades (Stop Saying It the Basic Way)", box=ROUNDED, expand=True)
        up_table.add_column("What You Said & Why", style="dim", ratio=3)
        up_table.add_column("Natural Upgrades (Say This Instead)", ratio=5)
        for u in upgrades:
            left = f"[bold red]\"{u.get('original', '')}\"[/bold red]\n[yellow]Why:[/yellow] {u.get('why_upgrade', '')}"
            right = (
                f"[bold green]Casual:[/bold green] \"{u.get('natural_casual', '')}\"\n\n"
                f"[bold cyan]Articulate:[/bold cyan] \"{u.get('natural_articulate', '')}\""
            )
            up_table.add_row(left, right)
        console.print(up_table)

    # Native model version
    if review.get("native_model_version"):
        console.print(
            Panel(
                f"[bold white]{review['native_model_version']}[/bold white]\n\n"
                f"[dim]💡 Tip: Read the paragraph above out loud right now to feel the rhythm and phrasing![/dim]",
                title="[bold magenta]🗣️ Polished Native Version of Your Exact Thoughts[/bold magenta]",
                box=ROUNDED,
            )
        )

    if review.get("round2_challenge"):
        console.print(
            Panel(
                f"[bold yellow]{review['round2_challenge']}[/bold yellow]",
                title="[bold yellow]🔥 Next Step / Round 2 Focus[/bold yellow]",
                box=ROUNDED,
            )
        )


def save_markdown_report(
    mission: Dict[str, Any],
    metrics: Dict[str, Any],
    transcript: str,
    review: Dict[str, Any],
    round_num: int,
) -> Path:
    db.ensure_dirs()
    md_path = db.REVIEWS_DIR / f"{mission['date']}.md"
    mode = "a" if md_path.exists() and round_num > 1 else "w"

    lines = []
    if mode == "w":
        lines.extend(
            [
                f"# Daily Speaking Practice — {mission['date']}",
                f"- **Source:** [{mission['source_title']}]({mission['source_url']}) ({mission['source_name']})",
                f"- **Category:** {mission['category']}",
                f"- **Speaking Mode:** {mission['speaking_mode']}",
                "",
                "## Reading Input",
                f"> {mission['reading_excerpt']}",
                "",
                f"**Prompt:** {mission['speaking_prompt']}",
                "",
                "### Target Expressions",
            ]
        )
        for tp in mission.get("target_phrases", []):
            lines.append(f"- **{tp.get('phrase')}**: {tp.get('meaning')} *(Ex: \"{tp.get('example')}\")*")
        conn = mission.get("connector_challenge", {})
        if conn.get("phrase"):
            lines.append(f"- **Connector Challenge (`{conn.get('phrase')}`)**: {conn.get('usage_tip')}")
        lines.append("")

    lines.extend(
        [
            f"## Round {round_num} Attempt",
            f"- **Score:** {review.get('score', '—')}/100 | **Duration:** {metrics['duration_sec']}s | **Pace:** {metrics['wpm']} WPM | **Unique Words:** {round(metrics['unique_word_ratio']*100, 1)}%",
            f"- **Targets Used:** {', '.join(metrics.get('targets_used', [])) or 'None'}",
            f"- **Forbidden Words Slipped:** {', '.join(metrics.get('forbidden_used', {}).keys()) or 'None'}",
            "",
            "### Your Transcript",
            f"> {transcript}",
            "",
            "### Coach Feedback",
            review.get("summary_feedback", ""),
            "",
            "### Sentence Upgrades",
        ]
    )
    for u in review.get("sentence_upgrades", []):
        lines.extend(
            [
                f"- **Original:** \"{u.get('original', '')}\"",
                f"  - *Why:* {u.get('why_upgrade', '')}",
                f"  - *Casual Upgrade:* \"{u.get('natural_casual', '')}\"",
                f"  - *Articulate Upgrade:* \"{u.get('natural_articulate', '')}\"",
            ]
        )
    lines.extend(
        [
            "",
            "### Polished Native Version (Read Aloud)",
            f"> {review.get('native_model_version', '')}",
            "",
            "---",
            "",
        ]
    )

    with open(md_path, mode, encoding="utf-8") as f:
        f.write("\n".join(lines))
    return md_path


def _execute_round(
    mission: Dict[str, Any],
    round_num: int,
    use_text: bool = False,
    provided_text: Optional[str] = None,
    prev_transcript: Optional[str] = None,
) -> Optional[str]:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    audio_path: Optional[Path] = None
    duration_sec = 0.0

    if provided_text is not None:
        transcript = provided_text.strip()
        duration_sec = round(max(15.0, len(transcript.split()) / 2.2), 1)
    elif use_text:
        console.print("\n[bold cyan]Type or paste your spoken response below and press [Enter]:[/bold cyan]")
        transcript = Prompt.ask("[bold green]Your response[/bold green]").strip()
        duration_sec = round(max(15.0, len(transcript.split()) / 2.2), 1)
    else:
        audio_path = db.RECORDINGS_DIR / f"{timestamp}_m{mission['id']}_r{round_num}.wav"
        target_secs = 90 if round_num == 1 else 60
        duration_sec = audio.record_audio(audio_path, console, target_seconds=target_secs)
        if duration_sec < 1.5:
            console.print("[bold yellow]⚠️ Recording was too short (<1.5s). Let's try again or press [t] to type.[/bold yellow]")
            return None
        with console.status("[bold cyan]Transcribing your voice locally with Whisper...[/bold cyan]"):
            transcript = audio.transcribe_audio(audio_path)

    if not transcript or len(transcript.split()) < 3:
        console.print("[bold red]⚠️ Could not detect enough speech in that take. Check your mic or try [t] to type.[/bold red]")
        return None

    metrics = audio.analyze_transcript(transcript, duration_sec, mission)

    with console.status("[bold magenta]Analyzing your phrasing, crutch words & building natural upgrades...[/bold magenta]"):
        review = ai.review_attempt(
            mission,
            metrics,
            transcript,
            round_num=round_num,
            prev_transcript=prev_transcript,
        )
        db.save_attempt(
            mission["id"],
            round_num=round_num,
            audio_path=str(audio_path) if audio_path else None,
            metrics=metrics,
            transcript=transcript,
            review=review,
        )
        md_path = save_markdown_report(mission, metrics, transcript, review, round_num)

    render_review_card(mission, metrics, transcript, review, round_num)
    console.print(f"[dim]📄 Saved review to {md_path}[/dim]")
    return transcript


def run_interactive_session(force_new: bool = False, category: Optional[str] = None) -> None:
    mission = _prepare_mission(force_new=force_new, category=category)

    while True:
        render_mission_card(mission)
        choice = Prompt.ask(
            "\n[bold green]Ready?[/bold green] Press [bold white][Enter][/bold white] to record mic, "
            "[bold cyan][t][/bold cyan] to type/dictate text, "
            "[bold yellow][n][/bold yellow] for a new topic, or "
            "[bold red][q][/bold red] to quit",
            default="",
            show_default=False,
        ).strip().lower()

        if choice == "q":
            console.print("[dim]See you tomorrow![/dim]")
            return
        if choice == "n":
            mission = _prepare_mission(force_new=True, category=category)
            continue

        use_text = choice == "t"
        r1_transcript = _execute_round(mission, round_num=1, use_text=use_text)
        if not r1_transcript:
            continue

        # Prompt for Round 2 (The Upgrade Loop)
        r2_choice = Prompt.ask(
            "\n[bold yellow]🔥 Lock in your upgrades![/bold yellow] Press [bold green][r][/bold green] to record Round 2 (60s retry using the upgrades above), "
            "[bold cyan][t][/bold cyan] to type Round 2, or [bold white][Enter][/bold white] to finish for today",
            default="",
            show_default=False,
        ).strip().lower()

        if r2_choice in ("r", "t"):
            _execute_round(
                mission,
                round_num=2,
                use_text=(r2_choice == "t"),
                prev_transcript=r1_transcript,
            )
            console.print("\n[bold green]✅ Awesome session! Round 1 + Round 2 completed and logged.[/bold green]")
        else:
            console.print("\n[bold green]✅ Daily speaking session saved! Keep the streak alive tomorrow.[/bold green]")
        _auto_sync_if_diomedes(reason="en-session")
        return


@app.callback()
def main(
    ctx: typer.Context,
    new: bool = typer.Option(False, "--new", "-n", help="Fetch a brand new web article & mission right now."),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter topic category (e.g. psychology, tech, wisdom, life)."),
) -> None:
    if ctx.invoked_subcommand is None:
        run_interactive_session(force_new=new, category=category)


@app.command("today")
def cmd_today(
    new: bool = typer.Option(False, "--new", "-n", help="Fetch a brand new web article & mission."),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter topic category."),
) -> None:
    """Start today's daily input, speaking recording, and AI coaching review."""
    run_interactive_session(force_new=new, category=category)


@app.command("new")
def cmd_new(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter topic category."),
) -> None:
    """Force-fetch a brand new real-world article and start a fresh speaking mission."""
    run_interactive_session(force_new=True, category=category)


@app.command("prep")
def cmd_prep(
    force: bool = typer.Option(False, "--force", "-f", help="Prepare a new mission even if today's already exists."),
) -> None:
    """Pre-fetch and cache today's daily input in the background (used by the daily timer)."""
    mission = _prepare_mission(force_new=force, quiet=True)
    console.print(
        f"[green]✓ Prepared daily mission #{mission['id']} for {mission['date']}:[/green] "
        f"{mission['source_title']} ({mission['source_name']})"
    )


@app.command("review-text")
def cmd_review_text(
    text: str = typer.Argument(..., help="Spoken or dictated text to review against today's mission."),
    round_num: int = typer.Option(1, "--round", "-r", help="Round number (1 or 2)."),
) -> None:
    """Review a text/dictated response directly against today's mission."""
    mission = _prepare_mission(force_new=False)
    render_mission_card(mission)
    _execute_round(mission, round_num=round_num, provided_text=text)
    _auto_sync_if_diomedes(reason="en-review")


@app.command("sync")
def cmd_sync() -> None:
    """Sync Diomedes personal progress (data/diomedes/) with the Git repository."""
    if not db.IS_DIOMEDES:
        console.print("[yellow]Repo persistence is only enabled for user Diomedes (using local ~/.local/share/speak/).[/yellow]")
        return
    _auto_sync_if_diomedes(reason="manual-sync", pull_first=True)


@app.command("stats")
def cmd_stats() -> None:
    """Show your speaking streak, WPM, vocabulary variety, mastered phrases, and top crutch words."""
    s = db.get_stats_summary()
    console.print()
    storage_label = "Repo (data/diomedes/)" if db.IS_DIOMEDES else "Local (~/.local/share/speak/)"
    summary = (
        f"🔥 [bold yellow]Current Streak:[/bold yellow] {s['streak']} day(s)   •   "
        f"📅 [bold cyan]Practice Days:[/bold cyan] {s['practice_days']}   •   "
        f"🎙️ [bold green]Total Takes:[/bold green] {s['total_attempts']} ({s['total_minutes']} mins)\n"
        f"⚡ [bold white]Avg Pace:[/bold white] {s['avg_wpm']} WPM   •   "
        f"🌈 [bold magenta]Avg Vocab Variety:[/bold magenta] {s['avg_unique_ratio']}%   •   "
        f"🎯 [bold green]Target Phrases Mastered:[/bold green] {s['phrases_mastered']}/{s['phrases_assigned']}   •   "
        f"💾 [dim]{storage_label}[/dim]"
    )
    console.print(Panel(summary, title="[bold cyan]📊 Your Speaking Progress[/bold cyan]", box=ROUNDED))

    crutches = s.get("top_crutch_words", [])
    if crutches:
        ct = Table(title="🚫 Your Personal Crutch Words (Auto-Banned in Future Missions)", box=ROUNDED)
        ct.add_column("Overused Word", style="bold red")
        ct.add_column("Sessions Flagged", justify="right")
        ct.add_column("Last Seen", style="dim")
        for c in crutches:
            ct.add_row(c["word"], str(c["hit_count"]), c["last_seen"][:10])
        console.print(ct)

    recent = s.get("recent_attempts", [])
    if recent:
        rt = Table(title="🕒 Recent Speaking Sessions", box=ROUNDED, expand=True)
        rt.add_column("Date", style="cyan")
        rt.add_column("Round", justify="center")
        rt.add_column("Mode", style="yellow")
        rt.add_column("Topic", ratio=3)
        rt.add_column("WPM", justify="right")
        rt.add_column("Score", justify="right", style="bold green")
        for r in recent:
            rev = json.loads(r.get("review_json") or "{}")
            rt.add_row(
                r["date"],
                f"R{r['round_num']}",
                r["speaking_mode"],
                r["source_title"][:48],
                str(r["wpm"]),
                f"{rev.get('score', '—')}/100",
            )
        console.print(rt)


@app.command("history")
def cmd_history() -> None:
    """List saved Markdown reviews and audio recordings."""
    db.ensure_dirs()
    reviews = sorted(db.REVIEWS_DIR.glob("*.md"), reverse=True)
    console.print(f"\n[bold cyan]📁 Markdown Reviews Directory:[/bold cyan] {db.REVIEWS_DIR}")
    console.print(f"[bold cyan]🎙️ Audio Recordings Directory:[/bold cyan] {db.RECORDINGS_DIR}\n")
    if not reviews:
        console.print("[dim]No saved reviews yet. Run `speak` to complete your first session![/dim]")
        return
    for p in reviews[:15]:
        console.print(f"  • [bold white]{p.name}[/bold white]  →  [dim]{p}[/dim]")


# =====================================================================
# 🇯🇵 JAPANESE SPEAKING MODULE (`speak ja` / `speak-ja`)
# =====================================================================


def _fmt_furigana(text: str) -> str:
    """Convert inline furigana `漢字[かんじ]` into Rich-safe `漢字[dim](かんじ)[/dim]`."""
    if not text:
        return ""
    return re.sub(r"\[(?![lrtqn]\])([^\]]+)\]", r"[dim](\1)[/dim]", text)


def _prepare_ja_mission(
    force_new: bool = False,
    stage_override: Optional[int] = None,
    quiet: bool = False,
) -> Dict[str, Any]:
    db.init_db()
    if not force_new and stage_override is None:
        existing = db.get_today_ja_mission()
        if existing:
            return existing

    prog = db.get_ja_progression_state()
    target_stage = stage_override if stage_override is not None else prog["stage"]
    stage_bundle = ja_curriculum.pick_ja_topic(target_stage, prog["used_topics"])

    if not quiet:
        with console.status(
            f"[bold magenta]🇯🇵 Crafting your Japanese mission ({stage_bundle['short_name']} — {stage_bundle['topic']['title']})...[/bold magenta]",
            spinner="dots",
        ):
            mission_data = ai.generate_ja_mission(
                stage_bundle,
                unmastered_vocab=prog["unmastered_vocab"],
                top_traps=prog["top_traps"],
            )
            mission_id = db.save_ja_mission(mission_data)
    else:
        mission_data = ai.generate_ja_mission(
            stage_bundle,
            unmastered_vocab=prog["unmastered_vocab"],
            top_traps=prog["top_traps"],
        )
        mission_id = db.save_ja_mission(mission_data)

    mission = db.get_ja_mission_by_id(mission_id)
    assert mission is not None
    return mission


def render_ja_mission_card(mission: Dict[str, Any]) -> None:
    console.print()
    header = Text()
    header.append("🇯🇵 NIHONGO SPEAKING MISSION ", style="bold white on red")
    header.append(f"  {mission['date']}  ", style="bold cyan")
    header.append(f"•  Stage {mission['stage']}/5: {mission['stage_name']}  ", style="bold yellow")
    header.append(f"•  Target: {mission['target_seconds']}s", style="bold green")
    console.print(header)

    model_body = (
        f"[bold white]{_fmt_furigana(mission['model_japanese'])}[/bold white]\n\n"
        f"[dim]English: {mission['model_english']}[/dim]\n\n"
        f"[bold magenta]🎧 Tip:[/bold magenta] Press [bold magenta]\\[l][/bold magenta] to hear native Japanese audio & shadow aloud before recording!"
    )
    console.print(
        Panel(
            model_body,
            title=f"[bold cyan]📖 Model Reading: {mission['topic_title']}[/bold cyan]",
            subtitle=f"[dim]{mission['scenario']}[/dim]",
            box=ROUNDED,
            border_style="cyan",
            padding=(1, 2),
        )
    )

    prompt_body = (
        f"[bold yellow]Speaking Prompt (JA):[/bold yellow] [bold white]{_fmt_furigana(mission['speaking_prompt_ja'])}[/bold white]\n"
        f"[bold green]Goal ({mission['target_seconds']}s):[/bold green] {mission['speaking_prompt_en']}"
    )
    if mission.get("starter_template"):
        prompt_body += (
            f"\n\n[bold cyan]🗣️ Sentence Starter Skeleton (fill in the blanks if you get stuck):[/bold cyan]\n"
            f"  [white]{_fmt_furigana(mission['starter_template'])}[/white]"
        )
    console.print(
        Panel(
            prompt_body,
            title="[bold green]🎙️ Your Speaking Task[/bold green]",
            box=ROUNDED,
            border_style="green",
        )
    )

    gf = mission.get("grammar_frame", {})
    if gf.get("pattern"):
        gf_text = (
            f"[bold magenta]{_fmt_furigana(gf['pattern'])}[/bold magenta]  —  [white]{gf.get('meaning', '')}[/white]\n"
            f"[dim]How to form:[/dim] {_fmt_furigana(gf.get('structure', ''))}\n"
            f"[cyan]Example:[/cyan] {_fmt_furigana(gf.get('example_ja', ''))}  [dim]({gf.get('example_en', '')})[/dim]"
        )
        console.print(
            Panel(
                gf_text,
                title="[bold magenta]🧱 Core Grammar Frame (Use at least once)[/bold magenta]",
                box=ROUNDED,
                border_style="magenta",
            )
        )

    vb_table = Table(
        title="🎯 3 Vocab / Expression Building Blocks",
        box=ROUNDED,
        border_style="yellow",
        show_lines=True,
        expand=True,
    )
    vb_table.add_column("#", style="bold yellow", width=3)
    vb_table.add_column("Word (Furigana)", style="bold white", ratio=2)
    vb_table.add_column("Reading", style="cyan", ratio=1)
    vb_table.add_column("Meaning", style="green", ratio=2)
    vb_table.add_column("Example in Context", style="italic dim", ratio=3)

    for idx, vb in enumerate(mission.get("vocab_blocks", []), start=1):
        vb_table.add_row(
            str(idx),
            _fmt_furigana(vb.get("word", "")),
            vb.get("reading", ""),
            vb.get("meaning", ""),
            _fmt_furigana(vb.get("example_ja", "")),
        )
    console.print(vb_table)

    traps = mission.get("particle_traps", [])
    if traps:
        trap_table = Table(
            title="⚠️ Particle & Conjugation Watchouts",
            box=ROUNDED,
            border_style="red",
            expand=True,
        )
        trap_table.add_column("Watchout", style="bold yellow", ratio=2)
        trap_table.add_column("Avoid (✗)", style="bold red", ratio=2)
        trap_table.add_column("Say Instead (✓)", style="bold green", ratio=2)
        trap_table.add_column("Why", style="white", ratio=3)
        for tr in traps:
            trap_table.add_row(
                _fmt_furigana(tr.get("trap_title", "")),
                _fmt_furigana(tr.get("wrong", "")),
                _fmt_furigana(tr.get("right", "")),
                tr.get("explanation", ""),
            )
        console.print(trap_table)


def render_ja_review_card(
    mission: Dict[str, Any],
    metrics: Dict[str, Any],
    transcript: str,
    review: Dict[str, Any],
    round_num: int,
) -> None:
    console.print()
    score = review.get("score", 78)
    score_color = "green" if score >= 80 else ("yellow" if score >= 65 else "red")

    console.print(
        Panel(
            f"[white]{transcript}[/white]",
            title=(
                f"[bold cyan]📝 Round {round_num} Japanese Transcript[/bold cyan] "
                f"[dim]({metrics['duration_sec']}s • {metrics['char_count']} chars • {metrics['cpm']} CPM)[/dim]"
            ),
            box=ROUNDED,
            border_style="cyan",
        )
    )

    vocab_used_str = ", ".join(_fmt_furigana(w) for w in metrics.get("vocab_used", [])) or "None auto-detected"
    grammar_status = (
        f"[bold green]✓ Hit ({_fmt_furigana(metrics.get('grammar_pattern', ''))})[/bold green]"
        if metrics.get("grammar_used")
        else f"[yellow]○ Missed ({_fmt_furigana(metrics.get('grammar_pattern', ''))})[/yellow]"
    )

    summary_text = (
        f"[bold {score_color}]Overall Score: {score}/100[/bold {score_color}]\n\n"
        f"[bold white]{review.get('summary_feedback', '')}[/bold white]\n\n"
        f"[bold yellow]Scaffolding Check:[/bold yellow] {_fmt_furigana(review.get('scaffolding_check', ''))}\n"
        f"  • [cyan]Grammar Frame:[/cyan] {grammar_status}\n"
        f"  • [green]Vocab Blocks Used:[/green] {vocab_used_str}"
    )

    traps_spotted = review.get("traps_spotted", [])
    if traps_spotted:
        summary_text += "\n\n[bold magenta]🔍 Particle & Grammar Notes from Your Take:[/bold magenta]"
        for t in traps_spotted:
            summary_text += f"\n  • {_fmt_furigana(t)}"

    console.print(
        Panel(
            summary_text,
            title=f"[bold {score_color}]🎯 Japanese Coach Diagnosis (Round {round_num})[/bold {score_color}]",
            box=ROUNDED,
            border_style=score_color,
        )
    )

    upgrades = review.get("sentence_upgrades", [])
    if upgrades:
        up_table = Table(
            title="🚀 Sentence Upgrades (How a Native Speaker Phrases Your Thoughts)",
            box=ROUNDED,
            border_style="green",
            show_lines=True,
            expand=True,
        )
        up_table.add_column("What You Said", style="yellow", ratio=2)
        up_table.add_column("Coach Note", style="dim", ratio=2)
        up_table.add_column("Polite (です/ます) & Casual Upgrades", style="white", ratio=4)

        for u in upgrades:
            upgrades_col = (
                f"[bold green]Polite:[/bold green] {_fmt_furigana(u.get('natural_polite', ''))}\n"
                f"[bold cyan]Casual:[/bold cyan] {_fmt_furigana(u.get('natural_casual', ''))}"
            )
            up_table.add_row(
                _fmt_furigana(u.get("original", "")),
                u.get("why_upgrade", ""),
                upgrades_col,
            )
        console.print(up_table)

    if review.get("native_model_version"):
        native_body = (
            f"[bold white]{_fmt_furigana(review['native_model_version'])}[/bold white]\n\n"
            f"[dim]English: {review.get('native_model_english', '')}[/dim]\n\n"
            f"[bold magenta]🎧 Press \\[l] at the prompt below to hear this spoken aloud & shadow it![/bold magenta]"
        )
        console.print(
            Panel(
                native_body,
                title="[bold magenta]🗣️ Polished Native Version of Your Thoughts (Read & Shadow Aloud!)[/bold magenta]",
                box=ROUNDED,
                border_style="magenta",
                padding=(1, 2),
            )
        )

    if review.get("round2_challenge"):
        ch_text = _fmt_furigana(review["round2_challenge"]).replace("[l]", "\\[l]").replace("[r]", "\\[r]")
        console.print(
            Panel(
                f"[bold yellow]{ch_text}[/bold yellow]",
                title="[bold yellow]🔥 Next Step / Round 2 Challenge[/bold yellow]",
                box=ROUNDED,
                border_style="yellow",
            )
        )


def save_ja_markdown_report(
    mission: Dict[str, Any],
    metrics: Dict[str, Any],
    transcript: str,
    review: Dict[str, Any],
    round_num: int,
) -> Path:
    db.ensure_dirs()
    md_path = db.JA_REVIEWS_DIR / f"{mission['date']}_ja_mission{mission['id']}.md"
    mode = "a" if md_path.exists() else "w"

    lines = []
    if mode == "w":
        gf = mission.get("grammar_frame", {})
        lines.extend(
            [
                f"# 🇯🇵 Japanese Speaking Session — {mission['date']}",
                "",
                f"- **Stage:** Stage {mission['stage']}/5 ({mission['stage_name']})",
                f"- **Topic:** {mission['topic_title']} — {mission['scenario']}",
                f"- **Prompt (JA):** {mission['speaking_prompt_ja']}",
                f"- **Prompt (EN):** {mission['speaking_prompt_en']}",
                f"- **Core Grammar Frame:** `{gf.get('pattern', '')}` — {gf.get('meaning', '')}",
                "",
                "## 📖 Model Japanese",
                f"> {mission['model_japanese']}",
                f"> ({mission['model_english']})",
                "",
                "## 🎯 Vocab Building Blocks",
            ]
        )
        for vb in mission.get("vocab_blocks", []):
            lines.append(f"- **{vb.get('word')}** (`{vb.get('reading')}`) — {vb.get('meaning')} *(e.g. {vb.get('example_ja')})*")
        lines.append("")

    lines.extend(
        [
            f"## 🎙️ Round {round_num} Attempt (Score: {review.get('score', 78)}/100)",
            f"- **Duration:** {metrics['duration_sec']}s | **Characters:** {metrics['char_count']} | **Pace:** {metrics['cpm']} CPM",
            f"- **Grammar Frame Used:** {'Yes' if metrics.get('grammar_used') else 'No'}",
            f"- **Vocab Blocks Used:** {', '.join(metrics.get('vocab_used', [])) or 'None'}",
            "",
            "### Your Transcript",
            f"> {transcript}",
            "",
            "### Coach Feedback",
            review.get("summary_feedback", ""),
            "",
            f"**Scaffolding Check:** {review.get('scaffolding_check', '')}",
            "",
            "### Particle & Grammar Notes",
        ]
    )
    for t in review.get("traps_spotted", []):
        lines.append(f"- {t}")

    lines.extend(["", "### Sentence Upgrades"])
    for idx, u in enumerate(review.get("sentence_upgrades", []), start=1):
        lines.extend(
            [
                f"#### {idx}. \"{u.get('original', '')}\"",
                f"- **Why:** {u.get('why_upgrade', '')}",
                f"- **Polite (です/ます):** {u.get('natural_polite', '')}",
                f"- **Casual:** {u.get('natural_casual', '')}",
                "",
            ]
        )

    lines.extend(
        [
            "### Polished Native Version (Shadow Aloud)",
            f"> {review.get('native_model_version', '')}",
            f"> ({review.get('native_model_english', '')})",
            "",
            "---",
            "",
        ]
    )

    with open(md_path, mode, encoding="utf-8") as f:
        f.write("\n".join(lines))
    return md_path


def _execute_ja_round(
    mission: Dict[str, Any],
    round_num: int,
    use_text: bool = False,
    provided_text: Optional[str] = None,
    prev_transcript: Optional[str] = None,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    audio_path: Optional[Path] = None
    duration_sec = 0.0
    target_secs = int(mission.get("target_seconds", 30))

    if provided_text is not None:
        transcript = provided_text.strip()
        duration_sec = round(max(10.0, len(transcript) / 3.0), 1)
    elif use_text:
        console.print("\n[bold cyan]Type or paste your Japanese response below (hiragana/kanji) and press [Enter]:[/bold cyan]")
        transcript = Prompt.ask("[bold green]日本語 response[/bold green]").strip()
        duration_sec = round(max(10.0, len(transcript) / 3.0), 1)
    else:
        audio_path = db.RECORDINGS_DIR / f"{timestamp}_ja_m{mission['id']}_r{round_num}.wav"
        duration_sec = audio.record_audio(audio_path, console, target_seconds=target_secs)
        if duration_sec < 1.2:
            console.print("[bold yellow]⚠️ Recording was too short (<1.2s). Let's try again or press [t] to type.[/bold yellow]")
            return None
        with console.status("[bold cyan]Transcribing your Japanese speech locally with Whisper...[/bold cyan]"):
            transcript = audio.transcribe_audio(audio_path, lang="ja")

    if not transcript or len(transcript.strip()) < 2:
        console.print("[bold red]⚠️ Could not detect enough Japanese speech in that take. Check your mic or press [t] to type.[/bold red]")
        return None

    metrics = audio.analyze_ja_transcript(transcript, duration_sec, mission)

    with console.status("[bold magenta]🇯🇵 Analyzing particles, grammar frame & crafting natural Japanese upgrades...[/bold magenta]"):
        review = ai.review_ja_attempt(
            mission,
            metrics,
            transcript,
            round_num=round_num,
            prev_transcript=prev_transcript,
        )
        db.save_ja_attempt(
            mission["id"],
            round_num=round_num,
            audio_path=str(audio_path) if audio_path else None,
            metrics=metrics,
            transcript=transcript,
            review=review,
        )
        md_path = save_ja_markdown_report(mission, metrics, transcript, review, round_num)

    render_ja_review_card(mission, metrics, transcript, review, round_num)
    console.print(f"[dim]📄 Saved Japanese review to {md_path}[/dim]")
    return transcript, review


def run_ja_interactive_session(force_new: bool = False, stage_override: Optional[int] = None) -> None:
    mission = _prepare_ja_mission(force_new=force_new, stage_override=stage_override)
    render_ja_mission_card(mission)

    while True:
        choice = Prompt.ask(
            "\n[bold green]Ready?[/bold green] Press [bold white]\\[Enter][/bold white] to record mic, "
            "[bold magenta]\\[l][/bold magenta] to listen & shadow native audio, "
            "[bold cyan]\\[t][/bold cyan] to type Japanese, "
            "[bold yellow]\\[n][/bold yellow] for a new mission, or "
            "[bold red]\\[q][/bold red] to quit",
            default="",
            show_default=False,
        ).strip().lower()

        if choice == "q":
            console.print("[dim]また明日！(See you tomorrow!)[/dim]")
            return
        if choice == "l":
            audio.synthesize_and_play_ja_tts(
                mission["model_japanese"],
                console,
                label=f"Model Reading ({mission['topic_title']})",
            )
            continue
        if choice == "n":
            mission = _prepare_ja_mission(force_new=True, stage_override=stage_override)
            render_ja_mission_card(mission)
            continue

        use_text = choice == "t"
        r1_out = _execute_ja_round(mission, round_num=1, use_text=use_text)
        if not r1_out:
            continue
        r1_transcript, r1_review = r1_out

        # Round 2 loop with [l] to listen to the AI's Polished Native Japanese Version!
        while True:
            r2_choice = Prompt.ask(
                "\n[bold yellow]🔥 Shadow & Lock It In![/bold yellow] Press "
                "[bold magenta]\\[l][/bold magenta] to listen to your Polished Native Version, "
                "[bold green]\\[r][/bold green] to record Round 2 retry, "
                "[bold cyan]\\[t][/bold cyan] to type Round 2, or "
                "[bold white]\\[Enter][/bold white] to finish for today",
                default="",
                show_default=False,
            ).strip().lower()

            if r2_choice == "l":
                native_text = r1_review.get("native_model_version") or mission["model_japanese"]
                audio.synthesize_and_play_ja_tts(
                    native_text,
                    console,
                    label="Your Polished Native Japanese Version",
                )
                continue

            if r2_choice in ("r", "t"):
                _execute_ja_round(
                    mission,
                    round_num=2,
                    use_text=(r2_choice == "t"),
                    prev_transcript=r1_transcript,
                )
                console.print("\n[bold green]✅ お疲れ様でした！ (Awesome work! Round 1 + Round 2 completed and logged.)[/bold green]")
            else:
                console.print("\n[bold green]✅ お疲れ様でした！ Daily Japanese speaking session saved.[/bold green]")
            _auto_sync_if_diomedes(reason="ja-session")
            return


@ja_app.callback()
def ja_main(
    ctx: typer.Context,
    new: bool = typer.Option(False, "--new", "-n", help="Generate a brand new Japanese speaking mission right now."),
    stage: Optional[int] = typer.Option(None, "--stage", "-s", min=1, max=5, help="Practice a specific curriculum stage (1=Early N5 .. 5=N4+)."),
) -> None:
    if ctx.invoked_subcommand is None:
        run_ja_interactive_session(force_new=new, stage_override=stage)


@ja_app.command("today")
def ja_cmd_today(
    new: bool = typer.Option(False, "--new", "-n", help="Generate a brand new Japanese speaking mission."),
    stage: Optional[int] = typer.Option(None, "--stage", "-s", min=1, max=5, help="Override curriculum stage (1..5)."),
) -> None:
    """Start today's Japanese speaking mission, TTS shadowing, and AI coaching."""
    run_ja_interactive_session(force_new=new, stage_override=stage)


@ja_app.command("new")
def ja_cmd_new(
    stage: Optional[int] = typer.Option(None, "--stage", "-s", min=1, max=5, help="Override curriculum stage (1..5)."),
) -> None:
    """Force-generate a brand new Japanese speaking mission."""
    run_ja_interactive_session(force_new=True, stage_override=stage)


@ja_app.command("listen")
def ja_cmd_listen(
    slow: bool = typer.Option(False, "--slow", help="Play at slower -22% speed for careful shadowing."),
) -> None:
    """Synthesize and play today's Japanese model passage aloud via native neural TTS."""
    mission = _prepare_ja_mission(force_new=False)
    render_ja_mission_card(mission)
    rate = "-22%" if slow else "-10%"
    audio.synthesize_and_play_ja_tts(
        mission["model_japanese"],
        console,
        label=f"Model Reading ({mission['topic_title']})",
        rate=rate,
    )


@ja_app.command("prep")
def ja_cmd_prep(
    force: bool = typer.Option(False, "--force", "-f", help="Prepare a new Japanese mission even if today's already exists."),
    stage: Optional[int] = typer.Option(None, "--stage", "-s", min=1, max=5, help="Override curriculum stage (1..5)."),
) -> None:
    """Pre-generate and cache today's Japanese mission in the background."""
    mission = _prepare_ja_mission(force_new=force, stage_override=stage, quiet=True)
    console.print(
        f"[green]✓ Prepared Japanese mission #{mission['id']} for {mission['date']}:[/green] "
        f"[Stage {mission['stage']}] {mission['topic_title']}"
    )


@ja_app.command("review-text")
def ja_cmd_review_text(
    text: str = typer.Argument(..., help="Japanese response text to review against today's Japanese mission."),
    round_num: int = typer.Option(1, "--round", "-r", help="Round number (1 or 2)."),
) -> None:
    """Review a typed or dictated Japanese response directly against today's mission."""
    mission = _prepare_ja_mission(force_new=False)
    render_ja_mission_card(mission)
    _execute_ja_round(mission, round_num=round_num, provided_text=text)
    _auto_sync_if_diomedes(reason="ja-review")


@ja_app.command("sync")
def ja_cmd_sync() -> None:
    """Sync Diomedes personal progress (data/diomedes/) with the Git repository."""
    cmd_sync()


@ja_app.command("stats")
def ja_cmd_stats() -> None:
    """Show your Japanese curriculum stage, streak, CPM pace, mastered grammar & vocab, and particle watchouts."""
    s = db.get_ja_stats_summary()
    stage_info = ja_curriculum.get_stage_info(s["stage"])
    next_stage_in = max(0, (s["stage"] * 5) - s["completed_missions"]) if s["stage"] < 5 else 0
    prog_note = (
        f"{next_stage_in} more completed daily mission(s) to unlock Stage {s['stage'] + 1}"
        if s["stage"] < 5
        else "Max Curriculum Stage Reached (Stage 5 N4+)"
    )

    storage_label = "Repo (data/diomedes/)" if db.IS_DIOMEDES else "Local (~/.local/share/speak/)"
    console.print()
    summary = (
        f"🗾 [bold yellow]Current Level:[/bold yellow] {stage_info['name']}   [dim]({prog_note})[/dim]\n"
        f"🔥 [bold yellow]Current Streak:[/bold yellow] {s['streak']} day(s)   •   "
        f"📅 [bold cyan]Practice Days:[/bold cyan] {s['practice_days']}   •   "
        f"🎙️ [bold green]Total Takes:[/bold green] {s['total_attempts']} ({s['total_minutes']} mins)\n"
        f"⚡ [bold white]Avg Speaking Pace:[/bold white] {s['avg_cpm']} CPM (chars/min)   •   "
        f"🧱 [bold magenta]Grammar Frames Used:[/bold magenta] {s['grammar_mastered']}/{s['grammar_assigned']}   •   "
        f"🎯 [bold green]Vocab Blocks Used:[/bold green] {s['vocab_mastered']}/{s['vocab_assigned']}   •   "
        f"💾 [dim]{storage_label}[/dim]"
    )
    console.print(Panel(summary, title="[bold cyan]🇯🇵 Your Japanese Speaking Progress[/bold cyan]", box=ROUNDED))

    traps = s.get("top_traps", [])
    if traps:
        tt = Table(title="⚠️ Personal Particle & Grammar Watchouts Spotted by Coach", box=ROUNDED)
        tt.add_column("Observation / Trap", style="bold yellow")
        tt.add_column("Times Spotted", justify="right")
        tt.add_column("Last Seen", style="dim")
        for t in traps:
            tt.add_row(_fmt_furigana(t["trap"]), str(t["hit_count"]), t["last_seen"][:10])
        console.print(tt)

    recent = s.get("recent_attempts", [])
    if recent:
        rt = Table(title="🕒 Recent Japanese Speaking Sessions", box=ROUNDED, expand=True)
        rt.add_column("Date", style="cyan")
        rt.add_column("Round", justify="center")
        rt.add_column("Stage", style="yellow")
        rt.add_column("Topic", ratio=3)
        rt.add_column("CPM", justify="right")
        rt.add_column("Score", justify="right", style="bold green")
        for r in recent:
            rev = json.loads(r.get("review_json") or "{}")
            rt.add_row(
                r["date"],
                f"R{r['round_num']}",
                f"Stage {r['stage']}",
                r["topic_title"][:48],
                str(r["cpm"]),
                f"{rev.get('score', '—')}/100",
            )
        console.print(rt)


@ja_app.command("history")
def ja_cmd_history() -> None:
    """List saved Japanese Markdown reviews and audio recordings."""
    db.ensure_dirs()
    reviews = sorted(db.JA_REVIEWS_DIR.glob("*.md"), reverse=True)
    console.print(f"\n[bold cyan]📁 Japanese Markdown Reviews Directory:[/bold cyan] {db.JA_REVIEWS_DIR}")
    console.print(f"[bold cyan]🎙️ Audio Recordings Directory:[/bold cyan] {db.RECORDINGS_DIR}\n")
    if not reviews:
        console.print("[dim]No saved Japanese reviews yet. Run `speak ja` (or `speak-ja`) to complete your first session![/dim]")
        return
    for p in reviews[:15]:
        console.print(f"  • [bold white]{p.name}[/bold white]  →  [dim]{p}[/dim]")


if __name__ == "__main__":
    app()
