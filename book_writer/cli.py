"""CLI entry point — write a complete book from the command line."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console

from book_writer.agents import AgentClient
from book_writer.models import Outline
from book_writer.orchestrator import BookWriter
from book_writer.stub_client import StubClient


_SAMPLE_SUFFIXES = {".txt", ".md", ".markdown", ".rst"}


def _collect_samples(
    files: list[Path], directory: Path | None
) -> list[str]:
    paths: list[Path] = list(files)
    if directory:
        if not directory.is_dir():
            raise SystemExit(f"--style-samples-dir not a directory: {directory}")
        paths.extend(
            p for p in sorted(directory.rglob("*")) if p.suffix.lower() in _SAMPLE_SUFFIXES
        )
    return [p.read_text(encoding="utf-8") for p in paths if p.is_file()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="book-writer",
        description="Multi-agent AI book writer (architect → writer → editor → proofreader).",
    )
    parser.add_argument(
        "--premise",
        default="",
        help="One- or two-sentence premise of the book. Required unless --resume-from-outline is set.",
    )
    parser.add_argument("--genre", default="literary fiction", help="Genre.")
    parser.add_argument("--chapters", type=int, default=8, help="Number of chapters to plan.")
    parser.add_argument("--style", default="", help="Optional style guidance.")
    parser.add_argument("--language", default="English", help="Output language.")
    parser.add_argument("--words-per-chapter", type=int, default=1500)
    parser.add_argument("--no-editor", action="store_true", help="Skip the editor pass.")
    parser.add_argument("--no-proofread", action="store_true", help="Skip the proofreader pass.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("book.md"),
        help="Output path for the Markdown manuscript.",
    )
    parser.add_argument(
        "--outline-out",
        type=Path,
        default=None,
        help="Optional path to also write the outline as JSON.",
    )
    parser.add_argument(
        "--resume-from-outline",
        type=Path,
        default=None,
        help="Skip the architect step; load an existing outline JSON file instead.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use a stub client (no API calls). Useful for testing the pipeline.",
    )
    parser.add_argument(
        "--style-sample",
        type=Path,
        action="append",
        default=[],
        help="Path to a text file containing one of YOUR past writing samples. "
        "Repeat the flag for multiple samples. The style analyzer will derive a "
        "profile and the writer/editor will imitate it.",
    )
    parser.add_argument(
        "--style-samples-dir",
        type=Path,
        default=None,
        help="Directory containing .txt/.md writing samples (read recursively).",
    )
    parser.add_argument(
        "--style-profile",
        type=Path,
        default=None,
        help="Path to a pre-computed style profile (skips the analyzer step).",
    )
    parser.add_argument(
        "--save-style-profile",
        type=Path,
        default=None,
        help="If set, save the derived style profile to this path for reuse.",
    )
    args = parser.parse_args(argv)

    if not args.premise and not args.resume_from_outline:
        parser.error("--premise is required unless --resume-from-outline is provided")

    console = Console(stderr=True)

    client = StubClient(num_chapters=args.chapters) if args.dry_run else AgentClient()

    writer = BookWriter(
        client=client,
        target_chapter_words=args.words_per_chapter,
        language=args.language,
        enable_editor=not args.no_editor,
        enable_proofreader=not args.no_proofread,
        progress=lambda msg: console.print(f"[dim]·[/dim] {msg}"),
    )

    existing_outline = None
    if args.resume_from_outline:
        existing_outline = Outline(
            **json.loads(args.resume_from_outline.read_text(encoding="utf-8"))
        )
        console.print(
            f"[cyan]i[/cyan] resuming from outline [bold]{args.resume_from_outline}[/bold] "
            f"({len(existing_outline.chapters)} chapters)"
        )

    if args.style_profile:
        writer.style_profile = args.style_profile.read_text(encoding="utf-8")
        console.print(
            f"[cyan]i[/cyan] loaded style profile from [bold]{args.style_profile}[/bold]"
        )

    samples = _collect_samples(args.style_sample, args.style_samples_dir)
    if samples and not writer.style_profile:
        console.print(f"[cyan]i[/cyan] learning style from {len(samples)} sample(s)")
        profile = writer.learn_style(samples)
        if args.save_style_profile:
            args.save_style_profile.write_text(profile, encoding="utf-8")
            console.print(
                f"[green]✓[/green] style profile saved to [bold]{args.save_style_profile}[/bold]"
            )

    book = writer.write(
        premise=args.premise,
        genre=args.genre,
        num_chapters=args.chapters,
        style=args.style,
        outline=existing_outline,
    )

    args.out.write_text(book.to_markdown(), encoding="utf-8")
    console.print(f"[green]✓[/green] manuscript written to [bold]{args.out}[/bold]")

    if args.outline_out:
        args.outline_out.write_text(
            json.dumps(book.outline.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        console.print(f"[green]✓[/green] outline written to [bold]{args.outline_out}[/bold]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
