from __future__ import annotations

import pytest

from app.chunking import chunk_text


class CharacterTokenizer:
    def encode(self, text: str, *, add_special_tokens: bool = False) -> list[int]:
        assert add_special_tokens is False
        return [ord(character) for character in text]

    def decode(
        self,
        token_ids: list[int],
        *,
        skip_special_tokens: bool,
        clean_up_tokenization_spaces: bool,
    ) -> str:
        assert skip_special_tokens is True
        assert clean_up_tokenization_spaces is False
        return "".join(chr(token_id) for token_id in token_ids)


def test_chunk_text_is_bounded_and_overlapping() -> None:
    tokenizer = CharacterTokenizer()
    chunks = chunk_text("abcdefghij", tokenizer, max_tokens=6, overlap_tokens=2)

    assert [chunk.text for chunk in chunks] == ["abcdef", "efghij"]
    assert [chunk.token_count for chunk in chunks] == [6, 6]
    assert chunks[0].token_end - chunks[1].token_start == 2


def test_chunk_text_prefers_paragraph_boundary() -> None:
    tokenizer = CharacterTokenizer()
    chunks = chunk_text("alpha\n\nbeta\n\ngamma", tokenizer, max_tokens=13, overlap_tokens=2)

    assert chunks[0].text == "alpha\n\nbeta"
    assert chunks[-1].text.endswith("gamma")


@pytest.mark.parametrize(
    ("max_tokens", "overlap_tokens"),
    [(0, 0), (10, -1), (10, 10), (10, 11)],
)
def test_chunk_text_rejects_invalid_windows(max_tokens: int, overlap_tokens: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("content", CharacterTokenizer(), max_tokens=max_tokens, overlap_tokens=overlap_tokens)


def test_chunk_text_ignores_empty_content() -> None:
    assert chunk_text(" \n\n ", CharacterTokenizer()) == []
