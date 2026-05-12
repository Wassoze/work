# AI Book Writer

A multi-agent AI system that writes a complete book, with a built-in **MCP
server** so each agent can also be called as a tool from Claude Desktop,
Claude Code, or any MCP client.

Five specialised agents collaborate:

| Agent           | Model                | Job                                                          |
| --------------- | -------------------- | ------------------------------------------------------------ |
| Style Analyzer  | `claude-sonnet-4-6`  | (Optional) Reads YOUR past writing and extracts a style profile the writer/editor will imitate |
| Architect       | `claude-opus-4-7`    | Turns a premise into a full outline (characters, arcs, beats) |
| Writer          | `claude-sonnet-4-6`  | Drafts each chapter from the outline and prior summaries     |
| Editor          | `claude-sonnet-4-6`  | Revises the draft for prose, pacing, and consistency         |
| Proofreader     | `claude-haiku-4-5`   | Fixes typos, grammar, and punctuation — no rewrites          |

A summarizer agent (Haiku) condenses each finished chapter into a few
sentences that are fed forward as context, so continuity holds across long
books without blowing up the prompt.

Prompt caching is applied to the outline brief, which is reused on every
chapter call — so a 20-chapter book only pays for that brief once.

## Install

```bash
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...
```

## CLI — write a full book

```bash
book-writer \
  --premise "A retired cartographer is hired to map a city that only appears at night." \
  --genre "magical realism" \
  --chapters 10 \
  --words-per-chapter 1800 \
  --out my_book.md \
  --outline-out my_book.outline.json
```

Useful flags:

- `--language French` (or any language — the agents write in it natively)
- `--style "noir, terse, present tense"`
- `--no-editor` / `--no-proofread` to skip passes for a faster/cheaper draft
- `--resume-from-outline path/to/outline.json` to skip the architect step and iterate on chapters with the same plan
- `--dry-run` runs the whole pipeline against a stub client (no API calls) — useful for wiring and CI

### Imitate your own writing style

Give the agents one or more of your past writing samples. The Style Analyzer
distils a profile (voice, rhythm, diction, dialogue habits, signature moves)
that the Writer and Editor then imitate on every chapter.

```bash
# Point at individual files...
book-writer --premise "..." \
  --style-sample ~/writing/story1.txt \
  --style-sample ~/writing/essay.md

# ...or a whole directory of .txt/.md samples
book-writer --premise "..." --style-samples-dir ~/writing/

# Save the derived profile for reuse, so you only pay for the analyzer once:
book-writer --premise "..." --style-samples-dir ~/writing/ \
  --save-style-profile my_voice.txt

# Then reuse it directly (skips the analyzer):
book-writer --premise "..." --style-profile my_voice.txt
```

The profile is cached in the Writer/Editor system prompts, so a long book
only pays for it once.

## Tests

```bash
pip install pytest
python -m pytest
```

All tests use the bundled `StubClient`, so they run without an API key.

## MCP server — use the agents as tools

Start the server:

```bash
book-writer-mcp
```

Register it in your MCP client (Claude Desktop / Claude Code config):

```json
{
  "mcpServers": {
    "book-writer": {
      "command": "book-writer-mcp",
      "env": { "ANTHROPIC_API_KEY": "sk-ant-..." }
    }
  }
}
```

Exposed tools:

| Tool                | Purpose                                                 |
| ------------------- | ------------------------------------------------------- |
| `analyze_style`     | Style Analyzer: user samples → reusable style profile   |
| `create_outline`    | Architect: premise → full outline                       |
| `write_chapter`     | Writer: outline + chapter index → chapter prose (accepts `style_profile`) |
| `edit_chapter`      | Editor: draft → revised chapter (accepts `style_profile`) |
| `proofread`         | Proofreader: fix typos/grammar without rewriting        |
| `summarize_chapter` | 3-5 sentence summary for continuity                     |
| `write_book`        | Orchestrator: end-to-end; accepts `style_samples` or `style_profile` |

Once registered, you can ask Claude things like *"use book-writer to outline a
heist novel set in 1920s Shanghai, then write the first chapter"* and it will
call the tools in sequence.

## Python API

```python
from book_writer import BookWriter
from book_writer.agents import AgentClient

writer = BookWriter(client=AgentClient(), language="English")
book = writer.write(
    premise="An archivist discovers a diary that finishes itself overnight.",
    genre="literary mystery",
    num_chapters=8,
)
print(book.to_markdown())
```

## Configuration

Override any model via env var:

- `BOOK_WRITER_ARCHITECT_MODEL`
- `BOOK_WRITER_WRITER_MODEL`
- `BOOK_WRITER_EDITOR_MODEL`
- `BOOK_WRITER_PROOFREADER_MODEL`

## How it works

```
premise ──► [architect] ──► Outline ─┐
                                     │
       ┌─────────────────────────────┘
       ▼
  for each chapter:
     [writer] ──► draft
        │
        ▼
     [editor] ──► revised
        │
        ▼
   [proofreader] ──► clean
        │
        ▼
   [summarizer] ──► summary ──► feeds back into the next chapter's context
```

The outline brief sits at the top of the writer/editor system prompts and is
cached, so it isn't re-billed on every chapter call.
