"""Tokenizer-aware text chunking with paragraph-aligned boundaries.

The chunker deliberately accepts a tokenizer instead of loading a model. This
keeps model ownership in :mod:`app.embed` and makes the algorithm easy to test
without network access.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

DEFAULT_CHUNK_TOKENS = 384
DEFAULT_OVERLAP_TOKENS = 48


@dataclass(frozen=True, slots=True)
class TextChunk:
    """A decoded text window and its location in the page token stream."""

    text: str
    token_count: int
    token_start: int
    token_end: int


def _normalise_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text).strip()


def _paragraphs(text: str) -> list[str]:
    """Return approximate paragraphs without language-specific assumptions."""

    normalised = _normalise_text(text)
    if not normalised:
        return []
    return [part.strip() for part in re.split(r"\n\s*\n+", normalised) if part.strip()]


def _encode(tokenizer: Any, text: str) -> list[int]:
    try:
        token_ids = tokenizer.encode(text, add_special_tokens=False, verbose=False)
    except TypeError:
        # Lightweight test tokenizers and some older implementations do not
        # accept the Hugging Face `verbose` keyword.
        token_ids = tokenizer.encode(text, add_special_tokens=False)
    if hasattr(token_ids, "tolist"):
        token_ids = token_ids.tolist()
    return [int(token_id) for token_id in token_ids]


def _decode(tokenizer: Any, token_ids: Sequence[int]) -> str:
    return str(
        tokenizer.decode(
            list(token_ids),
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
    ).strip()


def chunk_text(
    text: str,
    tokenizer: Any,
    *,
    max_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[TextChunk]:
    """Split text into token-bounded, approximately paragraph-aligned chunks.

    Paragraph ends are preferred when they fall in the latter half of a token
    window. Oversized paragraphs are split at the hard token limit. Adjacent
    chunks overlap by ``overlap_tokens`` to preserve boundary context.
    """

    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than zero")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens cannot be negative")
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")

    paragraphs = _paragraphs(text)
    if not paragraphs:
        return []

    separator_ids = _encode(tokenizer, "\n\n")
    all_token_ids: list[int] = []
    paragraph_ends: list[int] = []

    for paragraph in paragraphs:
        paragraph_ids = _encode(tokenizer, paragraph)
        if not paragraph_ids:
            continue
        if all_token_ids and separator_ids:
            all_token_ids.extend(separator_ids)
        all_token_ids.extend(paragraph_ids)
        paragraph_ends.append(len(all_token_ids))

    if not all_token_ids:
        return []

    chunks: list[TextChunk] = []
    start = 0
    total_tokens = len(all_token_ids)

    while start < total_tokens:
        hard_end = min(start + max_tokens, total_tokens)
        end = hard_end

        if hard_end < total_tokens:
            preferred_minimum = start + max(1, max_tokens // 2)
            preferred_ends = [
                boundary for boundary in paragraph_ends if preferred_minimum <= boundary <= hard_end
            ]
            if preferred_ends:
                end = preferred_ends[-1]

        chunk_value = _decode(tokenizer, all_token_ids[start:end])
        if chunk_value:
            chunks.append(
                TextChunk(
                    text=chunk_value,
                    token_count=end - start,
                    token_start=start,
                    token_end=end,
                )
            )

        if end >= total_tokens:
            break

        next_start = end - overlap_tokens
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks
