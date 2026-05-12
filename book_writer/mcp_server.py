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
def write_chapter(
    outline: dict[str, Any],
    chapter_index: int,
    previous_summaries: list[str] | None = None,
    target_words: int = 1500,
    language: str = "English",
) -> str:
    """Writer agent: draft a single chapter from an outline.

    `chapter_index` is zero-based. `previous_summaries` (optional) is a list of
    short summaries of the chapters already written, used for continuity.
    """
    o = Outline(**outline)
    return run_writer(
        _client,
        outline=o,
        chapter_plan=o.chapters[chapter_index],
        previous_summaries=previous_summaries or [],
        target_words=target_words,
        language=language,
    )


@mcp.tool()
def edit_chapter(
    outline: dict[str, Any],
    chapter_index: int,
    draft: str,
) -> str:
    """Editor agent: revise a draft chapter for prose quality and consistency."""
    o = Outline(**outline)
    return run_editor(
        _client,
        outline=o,
        chapter_plan=o.chapters[chapter_index],
        draft=draft,
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
) -> str:
    """Orchestrator: run the full architect → writer → editor → proofreader pipeline
    and return the finished book as Markdown.

    Warning: this issues many model calls and can take several minutes for a
    full-length book.
    """
    writer = BookWriter(
        client=_client,
        target_chapter_words=target_chapter_words,
        language=language,
        enable_editor=enable_editor,
        enable_proofreader=enable_proofreader,
    )
    book = writer.write(
        premise=premise,
        genre=genre,
        num_chapters=num_chapters,
        style=style,
    )
    return book.to_markdown()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
