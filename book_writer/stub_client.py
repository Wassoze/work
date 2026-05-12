"""A stub AgentClient that returns canned responses — for tests and dry runs.

It implements the same `.complete(...)` surface as `AgentClient`, so the
orchestrator works end-to-end without hitting the network or burning credits.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from book_writer.agents import (
    ARCHITECT_SYSTEM,
    PROOFREADER_SYSTEM,
    STYLE_ANALYZER_SYSTEM,
    SUMMARIZER_SYSTEM,
)


def _stub_outline(num_chapters: int = 3) -> dict[str, Any]:
    return {
        "title": "Stub Title",
        "genre": "stub",
        "premise": "A stub premise.",
        "themes": ["testing"],
        "setting": "A test fixture.",
        "tone": "neutral",
        "style_notes": "deterministic",
        "characters": [
            {
                "name": "Alice",
                "role": "protagonist",
                "description": "A test subject.",
                "arc": "Learns nothing, by design.",
            }
        ],
        "chapters": [
            {
                "number": i + 1,
                "title": f"Chapter {i + 1}",
                "summary": f"Stub summary for chapter {i + 1}.",
                "pov": "Alice",
                "beats": ["beat a", "beat b"],
            }
            for i in range(num_chapters)
        ],
    }


@dataclass
class StubClient:
    """Drop-in replacement for AgentClient used in tests / dry runs."""

    num_chapters: int = 3

    def complete(
        self,
        *,
        model: str,
        system: list[dict[str, Any]] | str,
        messages: list[dict[str, Any]],
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        system_text = system if isinstance(system, str) else "".join(
            block.get("text", "") for block in system
        )

        if ARCHITECT_SYSTEM in system_text:
            return json.dumps(_stub_outline(self.num_chapters))
        if STYLE_ANALYZER_SYSTEM in system_text:
            return "STUB STYLE PROFILE: short sentences; close third; wry."
        if "WRITER agent" in system_text:
            return "Stub chapter prose. " * 20
        if "EDITOR agent" in system_text:
            user = messages[-1]["content"]
            return f"[edited] {user[-60:]}"
        if PROOFREADER_SYSTEM in system_text:
            return messages[-1]["content"]
        if SUMMARIZER_SYSTEM in system_text:
            return "Stub summary."
        return "stub"
