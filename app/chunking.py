"""Structure-aware, token-bounded chunking for multi-page documents.

Chunks follow the document outline instead of page breaks: a chunk ends at
the next top-level heading once it holds ``min_tokens``, may span pages, and
carries its heading path as ``title`` so continuation chunks keep their
question/section context. Table-of-contents pages are dropped because they
match every query lexically but contain no answers.

The chunker accepts a tokenizer instead of loading a model, which keeps model
ownership in :mod:`app.embed` and makes the algorithm testable offline. Chunk
text is sliced from the source via token offsets, so it is never re-decoded
(and never normalised) by the tokenizer.
"""

from __future__ import annotations

import bisect
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

DEFAULT_CHUNK_TOKENS = 384
DEFAULT_MIN_CHUNK_TOKENS = 64
DEFAULT_OVERLAP_TOKENS = 48

_STRONG, _LINE, _SENTENCE = 3, 2, 1
_MAX_HEADING_CHARS = 80
_TOC_MIN_HEADINGS = 5
_TOC_REPEATED_RATIO = 0.6

_MARKDOWN = re.compile(r"^(#{1,6})\s+\S")
_NUMBERED = re.compile(r"^(\d{1,3})\s*\.?\s*[、．.，,)）]\s*\S")
_CHAPTER = re.compile(
    r"^(?:第[一二三四五六七八九十百零\d]+[章节部分篇]|[一二三四五六七八九十]{1,3}\s*[、．.])"
)
_PAGE_NUMBER_LINE = re.compile(r"\s*\d{1,4}\s*")
# Numbered headings phrased as questions start a top-level entry even when the
# numbering restarts (a new chapter), instead of nesting under the last one.
_QUESTION = re.compile(
    r"[？?]\s*$|什么|如何|怎么|怎样|为什么|为何|哪些|哪几|区别|异同|说说|谈谈|简述"
    r"|とは|ですか|違い|なぜ"
)
_MAX_SKIPPED_NUMBERS = 3
_SENTENCE_END = re.compile(r"[。！？!?]|\.(?=\s)")

Page = tuple[int, str]


@dataclass(frozen=True, slots=True)
class TextChunk:
    """A source text window, its heading context, and the pages it spans."""

    text: str
    title: str | None
    token_count: int
    page_start: int
    page_end: int

    def embedding_text(self) -> str:
        """Text to embed: the heading path is prepended unless already present."""

        if not self.title or self.text.startswith(self.title):
            return self.text
        return f"{self.title}\n{self.text}"


def is_heading(line: str) -> bool:
    """Return whether a line looks like a markdown, chapter, or numbered heading."""

    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_CHARS:
        return False
    return bool(_MARKDOWN.match(stripped) or _CHAPTER.match(stripped) or _NUMBERED.match(stripped))


def _heading_key(line: str) -> str:
    """Normalise a heading for cross-page comparison (numbering removed)."""

    value = unicodedata.normalize("NFKC", line)
    value = re.sub(
        r"^\s*(?:#{1,6}|\d{1,3}\s*\.?\s*[、.,)]|第\S{1,4}[章节部分篇]|[一二三四五六七八九十]{1,3}[、.])",
        "",
        value,
    )
    return re.sub(r"\s+", "", value)[:16]


def detect_toc_pages(pages: Sequence[Page]) -> set[int]:
    """Detect table-of-contents pages.

    A TOC page lists headings that reappear as real headings later in the
    document. Numbered lists inside answers rarely repeat later, so this is
    much more precise than a "many short numbered lines" heuristic.
    """

    headings = {
        number: [key for line in text.split("\n") if is_heading(line) and len(key := _heading_key(line)) >= 4]
        for number, text in pages
    }
    later: set[str] = set()
    toc: set[int] = set()
    for number, _text in reversed(pages):
        keys = headings[number]
        if len(keys) >= _TOC_MIN_HEADINGS:
            repeated = sum(1 for key in keys if key in later)
            if repeated / len(keys) >= _TOC_REPEATED_RATIO:
                toc.add(number)
        later.update(keys)
    return toc


class _HeadingTracker:
    """Track the heading path and whether a heading starts a top-level section.

    Numbered outlines restart at 1 for sub-points ("12、Q" → "1、point" →
    "2、point" → "13、Q"). A heading continues whichever open level expects
    its number; otherwise a question-like heading starts a top-level entry
    (this catches chapters whose numbering restarts), a small numbering gap
    continues the nearest level, and anything else opens a child level.
    Markdown, chapter, and Chinese-numeral ("一、") headings reset the numbered
    levels beneath them.
    """

    def __init__(self) -> None:
        self._outline: list[str] = []
        self._numbered: list[tuple[int, str]] = []

    def observe(self, line: str) -> bool:
        text = line.strip()
        markdown = _MARKDOWN.match(text)
        numbered = _NUMBERED.match(text)
        if markdown:
            depth = len(markdown.group(1))
            self._outline = [*self._outline[: depth - 1], text]
            self._numbered = []
            return depth <= 3
        if not numbered:
            self._outline = [text]
            self._numbered = []
            return True
        value = int(numbered.group(1))
        level = self._level_expecting(value, gap=1)
        if level is None and _QUESTION.search(text):
            self._numbered = [(value, text)]
        elif level is None and (level := self._level_expecting(value, gap=_MAX_SKIPPED_NUMBERS)) is None:
            self._numbered.append((value, text))
        else:
            self._numbered = [*self._numbered[:level], (value, text)]
        return len(self._numbered) == 1

    def _level_expecting(self, value: int, *, gap: int) -> int | None:
        """Deepest open level whose next number(s) include ``value``."""

        for level in range(len(self._numbered) - 1, -1, -1):
            if 0 < value - self._numbered[level][0] <= gap:
                return level
        return None

    def title(self) -> str:
        # Numbered entries are the reliable question path in extracted PDF
        # text; free-standing outline lines are used only when there is none.
        path = [text for _value, text in self._numbered] or self._outline
        return " > ".join(path[-2:])


def _clean_page(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and (not lines[-1].strip() or _PAGE_NUMBER_LINE.fullmatch(lines[-1])):
        lines.pop()
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", "\n".join(lines)).strip()


def _token_offsets(tokenizer: Any, text: str) -> list[tuple[int, int]]:
    encoding = tokenizer.encode(text, add_special_tokens=False)
    return [(int(start), int(end)) for start, end in encoding.offsets]


def chunk_document(
    pages: Sequence[Page],
    tokenizer: Any,
    *,
    max_tokens: int = DEFAULT_CHUNK_TOKENS,
    min_tokens: int = DEFAULT_MIN_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    skip_toc: bool = True,
) -> list[TextChunk]:
    """Split ``(page_number, text)`` pages into outline-aligned chunks.

    Preferred cut points, strongest first: the first top-level heading after
    ``min_tokens``; otherwise the last line break, then sentence end, in the
    second half of the window; otherwise the hard token limit. Only cuts that
    split a section carry ``overlap_tokens`` of context into the next chunk.
    """

    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than zero")
    if not 0 < min_tokens <= max_tokens:
        raise ValueError("min_tokens must be between 1 and max_tokens")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens cannot be negative")
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")

    toc = detect_toc_pages(pages) if skip_toc else set()
    parts: list[str] = []
    page_offsets: list[int] = []
    page_numbers: list[int] = []
    position = 0
    for number, raw_text in pages:
        text = _clean_page(raw_text)
        if not text or number in toc:
            continue
        page_offsets.append(position)
        page_numbers.append(number)
        parts.append(text)
        position += len(text) + 1
    if not parts:
        return []
    document = "\n".join(parts)

    offsets = _token_offsets(tokenizer, document)
    if not offsets:
        return []
    token_ends = [end for _start, end in offsets]
    total = len(offsets)

    def token_at(char: int) -> int:
        # First token whose span extends past ``char``. SentencePiece tokens
        # absorb the preceding whitespace, so a start-offset lookup would cut
        # one token late.
        return bisect.bisect_right(token_ends, char)

    def page_at(char: int) -> int:
        return page_numbers[max(bisect.bisect_right(page_offsets, char) - 1, 0)]

    strength = bytearray(total + 1)
    tracker = _HeadingTracker()
    title_starts: list[int] = []
    titles: list[str] = []
    line_start = 0
    for line in document.split("\n"):
        index = token_at(line_start)
        strength[index] = max(strength[index], _LINE)
        if is_heading(line):
            if tracker.observe(line):
                strength[index] = _STRONG
            title_starts.append(line_start)
            titles.append(tracker.title())
        line_start += len(line) + 1
    for match in _SENTENCE_END.finditer(document):
        index = token_at(match.end())
        strength[index] = max(strength[index], _SENTENCE)

    def title_at(char: int) -> str | None:
        index = bisect.bisect_right(title_starts, char) - 1
        return titles[index] if index >= 0 else None

    chunks: list[TextChunk] = []
    start = 0
    while start < total:
        hard_end = min(start + max_tokens, total)
        end = next(
            (i for i in range(start + min_tokens, hard_end) if strength[i] == _STRONG),
            hard_end,
        )
        if end == hard_end < total and strength[end] != _STRONG:
            window_start = start + max(1, max_tokens // 2)
            for level in (_LINE, _SENTENCE):
                candidate = next(
                    (i for i in range(hard_end, window_start - 1, -1) if strength[i] >= level),
                    None,
                )
                if candidate is not None:
                    end = candidate
                    break
        # Overlap only when a section is split; a heading cut needs no carry-over.
        carry_overlap = strength[end] != _STRONG
        char_start = offsets[start][0]
        char_end = offsets[end - 1][1]
        raw = document[char_start:char_end]
        text = raw.strip()
        if text:
            # Attribute title/page from the first visible character, not from
            # whitespace a leading token absorbed from the previous line.
            text_start = char_start + len(raw) - len(raw.lstrip())
            chunks.append(
                TextChunk(
                    text=text,
                    title=title_at(text_start),
                    token_count=end - start,
                    page_start=page_at(text_start),
                    page_end=page_at(max(text_start, char_end - 1)),
                )
            )
        if end >= total:
            break
        start = max(end - overlap_tokens, start + 1) if carry_overlap else end
    return chunks


def chunk_text(
    text: str,
    tokenizer: Any,
    *,
    max_tokens: int = DEFAULT_CHUNK_TOKENS,
    min_tokens: int = DEFAULT_MIN_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[TextChunk]:
    """Chunk a single-page text (Markdown or plain text)."""

    return chunk_document(
        [(1, text)],
        tokenizer,
        max_tokens=max_tokens,
        min_tokens=min(min_tokens, max_tokens),
        overlap_tokens=overlap_tokens,
        skip_toc=False,
    )
