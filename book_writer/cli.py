"""CLI entry point — write a complete book from the command line."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console

from book_writer.agents import AgentClient
from book_writer.orchestrator import BookWriter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="book-writer",
        description="Multi-agent AI book writer (architect → writer → editor → proofreader).",
    )
    parser.add_argument("--premise", required=True, help="One- or two-sentence premise of the book.")
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
    args = parser.parse_args(argv)

    console = Console(stderr=True)

    writer = BookWriter(
        client=AgentClient(),
        target_chapter_words=args.words_per_chapter,
        language=args.language,
        enable_editor=not args.no_editor,
        enable_proofreader=not args.no_proofread,
        progress=lambda msg: console.print(f"[dim]·[/dim] {msg}"),
    )

    book = writer.write(
        premise=args.premise,
        genre=args.genre,
        num_chapters=args.chapters,
        style=args.style,
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
