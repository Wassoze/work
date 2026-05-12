"""Specialized agents that collaborate to write a book.

Each agent wraps a single Claude API call with a focused system prompt.
Prompt caching is applied to the parts that are reused across many calls
(the outline brief, the style guide) so a long book is fast and cheap.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

from anthropic import Anthropic

from book_writer.models import Chapter, ChapterPlan, Character, Outline

# Default models — architect uses Opus for deeper planning, the rest use
# Sonnet for speed and cost.
ARCHITECT_MODEL = os.environ.get("BOOK_WRITER_ARCHITECT_MODEL", "claude-opus-4-7")
WRITER_MODEL = os.environ.get("BOOK_WRITER_WRITER_MODEL", "claude-sonnet-4-6")
EDITOR_MODEL = os.environ.get("BOOK_WRITER_EDITOR_MODEL", "claude-sonnet-4-6")
PROOFREADER_MODEL = os.environ.get("BOOK_WRITER_PROOFREADER_MODEL", "claude-haiku-4-5-20251001")
STYLE_ANALYZER_MODEL = os.environ.get("BOOK_WRITER_STYLE_MODEL", "claude-sonnet-4-6")


def _extract_json(text: str) -> str:
    """Pull a JSON object out of a model response, tolerating code fences."""
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


@dataclass
class AgentClient:
    """Thin wrapper around the Anthropic SDK with sane defaults."""

    api_key: Optional[str] = None
    _client: Optional[Anthropic] = None

    def client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic(api_key=self.api_key) if self.api_key else Anthropic()
        return self._client

    def complete(
        self,
        *,
        model: str,
        system: list[dict[str, Any]] | str,
        messages: list[dict[str, Any]],
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        resp = self.client().messages.create(
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        chunks: list[str] = []
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                chunks.append(block.text)
        return "".join(chunks).strip()


# ----- Architect -------------------------------------------------------------

ARCHITECT_SYSTEM = """You are the ARCHITECT agent in a multi-agent novel-writing team.
Your job: turn a premise into a coherent, structurally sound book outline.

You must return a SINGLE JSON object — no prose, no markdown fences — with this shape:
{
  "title": str,
  "genre": str,
  "premise": str,
  "themes": [str, ...],
  "setting": str,
  "tone": str,
  "style_notes": str,
  "characters": [
    {"name": str, "role": str, "description": str, "arc": str}
  ],
  "chapters": [
    {"number": int, "title": str, "summary": str, "pov": str|null, "beats": [str, ...]}
  ]
}

Quality bar:
- Characters must have real interiority and clear arcs.
- Each chapter advances plot, character, or theme — ideally all three.
- Beats inside a chapter should escalate; the book as a whole should have rising stakes and a satisfying climax.
- Avoid genre clichés unless deliberately subverted."""


def run_architect(
    client: AgentClient,
    *,
    premise: str,
    genre: str,
    num_chapters: int,
    style: str = "",
    language: str = "English",
) -> Outline:
    user = (
        f"Write the outline for a {genre} book in {language}.\n"
        f"Premise: {premise}\n"
        f"Number of chapters: {num_chapters}\n"
    )
    if style:
        user += f"Style guidance: {style}\n"
    user += "\nReturn the JSON object only."

    raw = client.complete(
        model=ARCHITECT_MODEL,
        system=ARCHITECT_SYSTEM,
        messages=[{"role": "user", "content": user}],
        max_tokens=4096,
        temperature=0.8,
    )
    data = json.loads(_extract_json(raw))
    return Outline(**data)


# ----- Style analyzer --------------------------------------------------------

STYLE_ANALYZER_SYSTEM = """You are the STYLE ANALYZER agent.
You receive one or more prose excerpts written by the user and produce a
concise style profile that another writer agent will imitate.

The profile must cover:
- VOICE: narrative stance, persona, distance from characters
- SENTENCE STRUCTURE: average length, common patterns, use of fragments
- RHYTHM & PACING: how the prose moves; punctuation habits
- DICTION: register, vocabulary level, recurring word choices or images
- DIALOGUE: how it's tagged, punctuated, blended with action
- TROPES & TICS: signature moves, motifs, things this author tends to do
- WHAT TO AVOID: things this author conspicuously does NOT do

Be specific and prescriptive — the profile will be used as instructions.
Keep it under 400 words. Output the profile only, no preamble."""


def run_style_analyzer(client: AgentClient, *, samples: list[str]) -> str:
    """Turn user-provided writing samples into a reusable style profile."""
    if not samples:
        raise ValueError("at least one sample is required")
    joined = "\n\n=== SAMPLE BREAK ===\n\n".join(s.strip() for s in samples if s.strip())
    user = (
        "Analyse the following excerpt(s) and produce the style profile.\n\n"
        f"{joined}"
    )
    return client.complete(
        model=STYLE_ANALYZER_MODEL,
        system=STYLE_ANALYZER_SYSTEM,
        messages=[{"role": "user", "content": user}],
        max_tokens=1024,
        temperature=0.3,
    )


def _style_block(style_profile: Optional[str]) -> str:
    if not style_profile:
        return ""
    return (
        "\n=== AUTHOR STYLE PROFILE (imitate closely) ===\n"
        f"{style_profile.strip()}\n"
        "=== END STYLE PROFILE ===\n"
    )


# ----- Writer ----------------------------------------------------------------

WRITER_SYSTEM_TEMPLATE = """You are the WRITER agent on a novel-writing team.
You draft one chapter at a time, in flowing prose.

Rules:
- Stay strictly consistent with the outline below (characters, setting, tone).
- Show, don't tell. Use scene, dialogue, sensory detail.
- Open the chapter with a hook; close it with momentum into the next.
- Match the requested tone and style. No meta-commentary, no chapter recaps.
- If an AUTHOR STYLE PROFILE is provided, your top priority is to imitate it —
  voice, sentence rhythm, diction, dialogue habits — without copying phrases verbatim.
- Output ONLY the chapter prose — no title line, no "Chapter N:" header.
{style_block}
=== BOOK OUTLINE ===
{brief}
=== END OUTLINE ===
"""


def run_writer(
    client: AgentClient,
    *,
    outline: Outline,
    chapter_plan: ChapterPlan,
    previous_summaries: list[str],
    target_words: int = 1500,
    language: str = "English",
    style_profile: Optional[str] = None,
) -> str:
    system = [
        {
            "type": "text",
            "text": WRITER_SYSTEM_TEMPLATE.format(
                brief=outline.as_brief(),
                style_block=_style_block(style_profile),
            ),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    prior = "\n".join(
        f"- Ch.{i+1}: {s}" for i, s in enumerate(previous_summaries)
    ) or "(none — this is the opening chapter)"
    beats = "\n".join(f"- {b}" for b in chapter_plan.beats) or "(use the summary)"
    user = (
        f"Draft Chapter {chapter_plan.number}: \"{chapter_plan.title}\" in {language}.\n"
        f"Approximate length: {target_words} words.\n"
        f"POV: {chapter_plan.pov or 'author choice (stay consistent)'}\n\n"
        f"Chapter summary:\n{chapter_plan.summary}\n\n"
        f"Beats to hit:\n{beats}\n\n"
        f"Summaries of previous chapters:\n{prior}\n\n"
        f"Write the chapter now."
    )
    return client.complete(
        model=WRITER_MODEL,
        system=system,
        messages=[{"role": "user", "content": user}],
        max_tokens=8192,
        temperature=0.85,
    )


# ----- Editor ----------------------------------------------------------------

EDITOR_SYSTEM_TEMPLATE = """You are the EDITOR agent on a novel-writing team.
You receive a draft chapter and return a revised version that is tighter,
more vivid, and more consistent with the outline.

Rules:
- Preserve the plot beats and POV. Do not invent new events.
- Cut filler, clichés, and weak verbs. Strengthen imagery and dialogue.
- If an AUTHOR STYLE PROFILE is provided, revise the prose to fit it more
  closely — voice, rhythm, dialogue habits — without copying phrases verbatim.
- Otherwise, polish toward the outline's requested tone.
- Output ONLY the revised chapter prose — no notes, no diff markers.
{style_block}
=== BOOK OUTLINE ===
{brief}
=== END OUTLINE ===
"""


def run_editor(
    client: AgentClient,
    *,
    outline: Outline,
    chapter_plan: ChapterPlan,
    draft: str,
    style_profile: Optional[str] = None,
) -> str:
    system = [
        {
            "type": "text",
            "text": EDITOR_SYSTEM_TEMPLATE.format(
                brief=outline.as_brief(),
                style_block=_style_block(style_profile),
            ),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    user = (
        f"Revise Chapter {chapter_plan.number}: \"{chapter_plan.title}\".\n\n"
        f"=== DRAFT ===\n{draft}\n=== END DRAFT ===\n\n"
        f"Return the revised chapter."
    )
    return client.complete(
        model=EDITOR_MODEL,
        system=system,
        messages=[{"role": "user", "content": user}],
        max_tokens=8192,
        temperature=0.5,
    )


# ----- Proofreader -----------------------------------------------------------

PROOFREADER_SYSTEM = """You are the PROOFREADER agent.
You fix only:
- typos and obvious spelling mistakes
- grammar errors
- punctuation and quotation-mark consistency
- malformed dialogue tags

Do NOT rewrite sentences, change vocabulary, or alter meaning.
Output ONLY the corrected text."""


def run_proofreader(client: AgentClient, *, text: str) -> str:
    return client.complete(
        model=PROOFREADER_MODEL,
        system=PROOFREADER_SYSTEM,
        messages=[{"role": "user", "content": text}],
        max_tokens=8192,
        temperature=0.0,
    )


# ----- Summarizer (used between chapters for continuity) ---------------------

SUMMARIZER_SYSTEM = """You compress a chapter into a 3-5 sentence summary that
captures plot events, character changes, and unresolved threads. Output the
summary only — no preamble."""


def run_summarizer(client: AgentClient, *, chapter_text: str) -> str:
    return client.complete(
        model=PROOFREADER_MODEL,
        system=SUMMARIZER_SYSTEM,
        messages=[{"role": "user", "content": chapter_text}],
        max_tokens=512,
        temperature=0.2,
    )
