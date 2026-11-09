#!/usr/bin/env python3
import datetime
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

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

app = typer.Typer(
    help="Automated Daily English Speaking System — Real Web Input + Anti-Repetition Constraints + AI Review.",
    invoke_without_command=True,
    no_args_is_help=False,
)
console = Console()


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


@app.command("stats")
def cmd_stats() -> None:
    """Show your speaking streak, WPM, vocabulary variety, mastered phrases, and top crutch words."""
    s = db.get_stats_summary()
    console.print()
    summary = (
        f"🔥 [bold yellow]Current Streak:[/bold yellow] {s['streak']} day(s)   •   "
        f"📅 [bold cyan]Practice Days:[/bold cyan] {s['practice_days']}   •   "
        f"🎙️ [bold green]Total Takes:[/bold green] {s['total_attempts']} ({s['total_minutes']} mins)\n"
        f"⚡ [bold white]Avg Pace:[/bold white] {s['avg_wpm']} WPM   •   "
        f"🌈 [bold magenta]Avg Vocab Variety:[/bold magenta] {s['avg_unique_ratio']}%   •   "
        f"🎯 [bold green]Target Phrases Mastered:[/bold green] {s['phrases_mastered']}/{s['phrases_assigned']}"
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


if __name__ == "__main__":
    app()
