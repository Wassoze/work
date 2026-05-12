"""High-level orchestrator that runs the full multi-agent pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from book_writer.agents import (
    AgentClient,
    run_architect,
    run_editor,
    run_proofreader,
    run_style_analyzer,
    run_summarizer,
    run_writer,
)
from book_writer.models import Book, Chapter, Outline

ProgressFn = Callable[[str], None]


@dataclass
class BookWriter:
    """Coordinates the architect → writer → editor → proofreader pipeline."""

    client: AgentClient = field(default_factory=AgentClient)
    target_chapter_words: int = 1500
    language: str = "English"
    enable_editor: bool = True
    enable_proofreader: bool = True
    progress: Optional[ProgressFn] = None
    style_profile: Optional[str] = None

    def _log(self, msg: str) -> None:
        if self.progress:
            self.progress(msg)

    def learn_style(self, samples: list[str]) -> str:
        """Run the style analyzer on user samples and store the resulting profile."""
        self._log(f"style: analysing {len(samples)} sample(s)")
        profile = run_style_analyzer(self.client, samples=samples)
        self.style_profile = profile
        self._log("style: profile ready")
        return profile

    def plan(
        self,
        *,
        premise: str,
        genre: str,
        num_chapters: int,
        style: str = "",
    ) -> Outline:
        self._log(f"architect: planning {num_chapters}-chapter {genre} book")
        outline = run_architect(
            self.client,
            premise=premise,
            genre=genre,
            num_chapters=num_chapters,
            style=style,
            language=self.language,
        )
        self._log(f"architect: outline ready — \"{outline.title}\"")
        return outline

    def draft_chapter(
        self,
        outline: Outline,
        chapter_index: int,
        previous_summaries: list[str],
    ) -> Chapter:
        plan = outline.chapters[chapter_index]
        self._log(f"writer: drafting Ch.{plan.number} {plan.title!r}")
        draft = run_writer(
            self.client,
            outline=outline,
            chapter_plan=plan,
            previous_summaries=previous_summaries,
            target_words=self.target_chapter_words,
            language=self.language,
            style_profile=self.style_profile,
        )

        text = draft
        if self.enable_editor:
            self._log(f"editor: revising Ch.{plan.number}")
            text = run_editor(
                self.client,
                outline=outline,
                chapter_plan=plan,
                draft=text,
                style_profile=self.style_profile,
            )
        if self.enable_proofreader:
            self._log(f"proofreader: polishing Ch.{plan.number}")
            text = run_proofreader(self.client, text=text)

        self._log(f"summarizer: condensing Ch.{plan.number}")
        summary = run_summarizer(self.client, chapter_text=text)

        return Chapter(number=plan.number, title=plan.title, text=text, summary=summary)

    def write(
        self,
        *,
        premise: str,
        genre: str,
        num_chapters: int = 8,
        style: str = "",
        outline: Optional[Outline] = None,
        style_samples: Optional[list[str]] = None,
    ) -> Book:
        if style_samples and self.style_profile is None:
            self.learn_style(style_samples)

        if outline is None:
            outline = self.plan(
                premise=premise,
                genre=genre,
                num_chapters=num_chapters,
                style=style,
            )

        chapters: list[Chapter] = []
        summaries: list[str] = []
        for i in range(len(outline.chapters)):
            chapter = self.draft_chapter(outline, i, summaries)
            chapters.append(chapter)
            summaries.append(chapter.summary)

        return Book(outline=outline, chapters=chapters)
