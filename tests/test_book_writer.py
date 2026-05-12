"""Tests that exercise the full pipeline using StubClient — no API calls."""

from __future__ import annotations

import json

from book_writer.agents import _extract_json
from book_writer.models import Book, Outline
from book_writer.orchestrator import BookWriter
from book_writer.stub_client import StubClient, _stub_outline


def test_extract_json_handles_fences():
    raw = 'Here you go:\n```json\n{"a": 1}\n```'
    assert json.loads(_extract_json(raw)) == {"a": 1}


def test_extract_json_handles_bare_object():
    raw = 'noise before {"x": [1,2]} noise after'
    assert json.loads(_extract_json(raw)) == {"x": [1, 2]}


def test_outline_brief_includes_characters_and_chapters():
    outline = Outline(**_stub_outline(num_chapters=2))
    brief = outline.as_brief()
    assert "Alice" in brief
    assert "Chapter 1" in brief
    assert "Chapter 2" in brief


def test_pipeline_end_to_end_with_stub():
    writer = BookWriter(client=StubClient(num_chapters=2))
    book = writer.write(premise="anything", genre="stub", num_chapters=2)
    assert isinstance(book, Book)
    assert len(book.chapters) == 2
    assert all(ch.text for ch in book.chapters)
    assert all(ch.summary for ch in book.chapters)
    md = book.to_markdown()
    assert "# Stub Title" in md
    assert "Chapter 1" in md and "Chapter 2" in md


def test_pipeline_can_resume_from_outline():
    outline = Outline(**_stub_outline(num_chapters=1))
    writer = BookWriter(client=StubClient(num_chapters=1))
    book = writer.write(premise="", genre="stub", outline=outline)
    assert len(book.chapters) == 1
    assert book.outline.title == "Stub Title"


def test_pipeline_skips_editor_and_proofreader_when_disabled():
    calls: list[str] = []

    class TracingStub(StubClient):
        def complete(self, *, model, system, messages, **kw):
            system_text = system if isinstance(system, str) else "".join(
                b.get("text", "") for b in system
            )
            if "EDITOR agent" in system_text:
                calls.append("editor")
            elif "PROOFREADER agent" in system_text:
                calls.append("proofreader")
            return super().complete(
                model=model, system=system, messages=messages, **kw
            )

    writer = BookWriter(
        client=TracingStub(num_chapters=1),
        enable_editor=False,
        enable_proofreader=False,
    )
    writer.write(premise="anything", genre="stub", num_chapters=1)
    assert "editor" not in calls
    assert "proofreader" not in calls
