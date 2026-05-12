"""MCP server exposing each agent (and the orchestrator) as a callable tool.

Run with: `book-writer-mcp` (registered console_script) or
`python -m book_writer.mcp_server`.

Wire it into Claude Desktop / Claude Code via your MCP settings, e.g.:

    {
      "mcpServers": {
        "book-writer": {
          "command": "book-writer-mcp",
          "env": {"ANTHROPIC_API_KEY": "sk-ant-..."}
        }
      }
    }
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from book_writer.agents import (
    AgentClient,
    run_architect,
    run_editor,
    run_proofreader,
    run_style_analyzer,
    run_summarizer,
    run_writer,
)
from book_writer.models import ChapterPlan, Outline
from book_writer.orchestrator import BookWriter

mcp = FastMCP("book-writer")
_client = AgentClient()


@mcp.tool()
def create_outline(
    premise: str,
    genre: str = "literary fiction",
    num_chapters: int = 8,
    style: str = "",
    language: str = "English",
) -> dict[str, Any]:
    """Architect agent: turn a premise into a full book outline.

    Returns a JSON-serialisable outline with title, characters, and a
    per-chapter plan that the writer tool can consume.
    """
    outline = run_architect(
        _client,
        premise=premise,
        genre=genre,
        num_chapters=num_chapters,
        style=style,
        language=language,
    )
    return outline.model_dump()


@mcp.tool()
def analyze_style(samples: list[str]) -> str:
    """Style analyzer agent: turn the user's past writing samples into a reusable
    style profile (voice, rhythm, diction, dialogue habits, signature moves).

    Pass the resulting string as `style_profile` to `write_chapter`,
    `edit_chapter`, or `write_book` to make the writer/editor imitate this voice.
    """
    return run_style_analyzer(_client, samples=samples)


@mcp.tool()
def write_chapter(
    outline: dict[str, Any],
    chapter_index: int,
    previous_summaries: list[str] | None = None,
    target_words: int = 1500,
    language: str = "English",
    style_profile: str | None = None,
) -> str:
    """Writer agent: draft a single chapter from an outline.

    `chapter_index` is zero-based. `previous_summaries` (optional) is a list of
    short summaries of the chapters already written, used for continuity.
    `style_profile` (optional) is the output of `analyze_style` — if given, the
    writer will imitate that voice.
    """
    o = Outline(**outline)
    return run_writer(
        _client,
        outline=o,
        chapter_plan=o.chapters[chapter_index],
        previous_summaries=previous_summaries or [],
        target_words=target_words,
        language=language,
        style_profile=style_profile,
    )


@mcp.tool()
def edit_chapter(
    outline: dict[str, Any],
    chapter_index: int,
    draft: str,
    style_profile: str | None = None,
) -> str:
    """Editor agent: revise a draft chapter for prose quality and consistency.

    If `style_profile` is given (from `analyze_style`), the editor will revise
    the prose toward that voice.
    """
    o = Outline(**outline)
    return run_editor(
        _client,
        outline=o,
        chapter_plan=o.chapters[chapter_index],
        draft=draft,
        style_profile=style_profile,
    )


@mcp.tool()
def proofread(text: str) -> str:
    """Proofreader agent: fix typos, grammar, and punctuation only — no rewrites."""
    return run_proofreader(_client, text=text)


@mcp.tool()
def summarize_chapter(chapter_text: str) -> str:
    """Summarize a chapter in 3-5 sentences for continuity tracking."""
    return run_summarizer(_client, chapter_text=chapter_text)


@mcp.tool()
def write_book(
    premise: str,
    genre: str = "literary fiction",
    num_chapters: int = 8,
    style: str = "",
    language: str = "English",
    target_chapter_words: int = 1500,
    enable_editor: bool = True,
    enable_proofreader: bool = True,
    style_samples: list[str] | None = None,
    style_profile: str | None = None,
) -> str:
    """Orchestrator: run the full architect → writer → editor → proofreader pipeline
    and return the finished book as Markdown.

    To imitate the user's own voice, pass either:
      - `style_samples`: a list of the user's past writing excerpts (the
        analyzer will derive a profile once at the start), OR
      - `style_profile`: a pre-computed profile string (from `analyze_style`).

    Warning: this issues many model calls and can take several minutes for a
    full-length book.
    """
    writer = BookWriter(
        client=_client,
        target_chapter_words=target_chapter_words,
        language=language,
        enable_editor=enable_editor,
        enable_proofreader=enable_proofreader,
        style_profile=style_profile,
    )
    book = writer.write(
        premise=premise,
        genre=genre,
        num_chapters=num_chapters,
        style=style,
        style_samples=style_samples,
    )
    return book.to_markdown()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
