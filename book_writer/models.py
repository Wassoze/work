from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Character(BaseModel):
    name: str
    role: str = Field(description="protagonist, antagonist, supporting, etc.")
    description: str
    arc: str = Field(description="how this character changes through the story")


class ChapterPlan(BaseModel):
    number: int
    title: str
    summary: str
    pov: Optional[str] = Field(default=None, description="point-of-view character")
    beats: list[str] = Field(default_factory=list, description="key narrative beats")


class Outline(BaseModel):
    title: str
    genre: str
    premise: str
    themes: list[str] = Field(default_factory=list)
    setting: str
    tone: str
    style_notes: str = ""
    characters: list[Character] = Field(default_factory=list)
    chapters: list[ChapterPlan] = Field(default_factory=list)

    def as_brief(self) -> str:
        """Compact textual brief used to prime writer/editor agents."""
        chars = "\n".join(
            f"- {c.name} ({c.role}): {c.description} | Arc: {c.arc}"
            for c in self.characters
        )
        chap_lines = "\n".join(
            f"  {c.number}. {c.title} — {c.summary}" for c in self.chapters
        )
        return (
            f"TITLE: {self.title}\n"
            f"GENRE: {self.genre}\n"
            f"PREMISE: {self.premise}\n"
            f"THEMES: {', '.join(self.themes)}\n"
            f"SETTING: {self.setting}\n"
            f"TONE: {self.tone}\n"
            f"STYLE NOTES: {self.style_notes}\n"
            f"CHARACTERS:\n{chars}\n"
            f"CHAPTERS:\n{chap_lines}"
        )


class Chapter(BaseModel):
    number: int
    title: str
    text: str
    summary: str = ""


class Book(BaseModel):
    outline: Outline
    chapters: list[Chapter] = Field(default_factory=list)

    def to_markdown(self) -> str:
        parts = [f"# {self.outline.title}\n", f"_{self.outline.genre}_\n"]
        parts.append("\n## Synopsis\n\n" + self.outline.premise + "\n")
        for ch in self.chapters:
            parts.append(f"\n## Chapter {ch.number}: {ch.title}\n\n{ch.text}\n")
        return "\n".join(parts)
