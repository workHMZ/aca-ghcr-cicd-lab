from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.chunking import TextChunk, chunk_document, chunk_text, detect_toc_pages, is_heading


class CharacterTokenizer:
    """One token per character, with offsets like a fast tokenizer."""

    def encode(self, text: str, *, add_special_tokens: bool = False) -> SimpleNamespace:
        assert add_special_tokens is False
        return SimpleNamespace(offsets=[(index, index + 1) for index in range(len(text))])


class WhitespaceAbsorbingTokenizer:
    """SentencePiece-style: a token owns the whitespace in front of it."""

    def encode(self, text: str, *, add_special_tokens: bool = False) -> SimpleNamespace:
        offsets: list[tuple[int, int]] = []
        start = 0
        for index, character in enumerate(text):
            if not character.isspace():
                offsets.append((start, index + 1))
                start = index + 1
        return SimpleNamespace(offsets=offsets)


TOKENIZER = CharacterTokenizer()


def test_chunks_are_bounded_and_overlap_when_a_section_is_split() -> None:
    chunks = chunk_text("abcdefghij", TOKENIZER, max_tokens=6, min_tokens=2, overlap_tokens=2)

    assert [chunk.text for chunk in chunks] == ["abcdef", "efghij"]
    assert all(chunk.token_count <= 6 for chunk in chunks)


def test_top_level_headings_end_chunks_without_overlap() -> None:
    text = "1、First question\nanswer one\n2、Second question\nanswer two"
    chunks = chunk_text(text, TOKENIZER, max_tokens=40, min_tokens=5, overlap_tokens=4)

    assert [chunk.text for chunk in chunks] == [
        "1、First question\nanswer one",
        "2、Second question\nanswer two",
    ]
    assert [chunk.title for chunk in chunks] == ["1、First question", "2、Second question"]


def test_numbered_sub_points_stay_inside_their_question() -> None:
    text = "12、Why HashMap?\n1、buckets\n2、trees\n13、Next question\nbody"
    chunks = chunk_text(text, TOKENIZER, max_tokens=60, min_tokens=5, overlap_tokens=0)

    assert chunks[0].text == "12、Why HashMap?\n1、buckets\n2、trees"
    assert chunks[1].text.startswith("13、Next question")


def test_continuation_chunks_carry_the_heading_path() -> None:
    text = "7、Long question\n" + "x" * 30 + "\n" + "y" * 30
    chunks = chunk_text(text, TOKENIZER, max_tokens=32, min_tokens=5, overlap_tokens=4)

    assert len(chunks) > 1
    assert all(chunk.title == "7、Long question" for chunk in chunks)
    assert chunks[1].embedding_text().startswith("7、Long question\n")
    assert chunks[0].embedding_text() == chunks[0].text


def test_sub_point_titles_include_their_parent_question() -> None:
    text = "3、Parent\n" + "a" * 20 + "\n1、child point\n" + "b" * 40
    chunks = chunk_text(text, TOKENIZER, max_tokens=40, min_tokens=5, overlap_tokens=0)

    assert chunks[-1].title == "3、Parent > 1、child point"


def test_question_headings_restart_the_top_level_sequence() -> None:
    text = "\n".join(
        [
            "33、Last question of chapter one?",
            "answer",
            "1、说说Java中实现多线程有几种方法",
            "1. extend Thread",
            "2. implement Runnable",
            "2、如何停止一个正在运行的线程",
            "answer",
        ]
    )
    chunks = chunk_text(text, TOKENIZER, max_tokens=200, min_tokens=5, overlap_tokens=0)

    assert [chunk.title for chunk in chunks] == [
        "33、Last question of chapter one?",
        "1、说说Java中实现多线程有几种方法",
        "2、如何停止一个正在运行的线程",
    ]
    assert "2. implement Runnable" in chunks[1].text


def test_chunks_span_pages_and_drop_page_number_footers() -> None:
    pages = [(5, "1、Question\nstart of answer\n5"), (6, "rest of answer\n6")]
    chunks = chunk_document(pages, TOKENIZER, max_tokens=200, min_tokens=5, overlap_tokens=0)

    assert len(chunks) == 1
    assert chunks[0].text == "1、Question\nstart of answer\nrest of answer"
    assert (chunks[0].page_start, chunks[0].page_end) == (5, 6)


def test_table_of_contents_pages_are_detected_and_skipped() -> None:
    toc = "\n".join(f"{number}、Question number {number}" for number in range(1, 7))
    body = [(page, f"{page - 1}、Question number {page - 1}\nanswer {page - 1}") for page in range(2, 8)]
    pages = [(1, toc), *body]

    assert detect_toc_pages(pages) == {1}
    chunks = chunk_document(pages, TOKENIZER, max_tokens=200, min_tokens=5, overlap_tokens=0)
    assert all(chunk.page_start >= 2 for chunk in chunks)
    assert chunks[0].text.startswith("1、Question number 1")


def test_numbered_lists_inside_answers_are_not_a_table_of_contents() -> None:
    answer = "\n".join(f"{number}. unique step {number} of the answer" for number in range(1, 9))
    assert detect_toc_pages([(1, answer), (2, "unrelated text")]) == set()


def test_markdown_headings_define_sections() -> None:
    text = "# Guide\nintro text\n## Install\nrun uv sync\n## Deploy\npush to main"
    chunks = chunk_text(text, TOKENIZER, max_tokens=200, min_tokens=5, overlap_tokens=0)

    assert [chunk.title for chunk in chunks] == ["# Guide", "# Guide > ## Install", "# Guide > ## Deploy"]


def test_whitespace_absorbing_tokens_do_not_shift_headings() -> None:
    text = "1、First question\nanswer one\n2、Second question\nanswer two"
    chunks = chunk_text(text, WhitespaceAbsorbingTokenizer(), max_tokens=40, min_tokens=5, overlap_tokens=0)

    assert chunks[1].text.startswith("2、Second question")
    assert chunks[1].title == "2、Second question"


def test_chunk_text_preserves_original_characters() -> None:
    text = "全角（括号）与 ﬁnally 保留"
    assert chunk_text(text, TOKENIZER)[0].text == text


@pytest.mark.parametrize(
    ("max_tokens", "min_tokens", "overlap_tokens"),
    [(0, 1, 0), (10, 0, 0), (10, 11, 0), (10, 5, -1), (10, 5, 10), (10, 5, 11)],
)
def test_invalid_windows_are_rejected(max_tokens: int, min_tokens: int, overlap_tokens: int) -> None:
    with pytest.raises(ValueError):
        chunk_document(
            [(1, "content")],
            TOKENIZER,
            max_tokens=max_tokens,
            min_tokens=min_tokens,
            overlap_tokens=overlap_tokens,
        )


def test_empty_content_produces_no_chunks() -> None:
    assert chunk_text(" \n\n ", TOKENIZER) == []
    assert chunk_document([], TOKENIZER) == []


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("12、HashMap和HashTable的区别", True),
        ("3 、八种基本数据类型", True),
        ("8， Zookeeper集群中是怎样选举leader的？", True),
        ("## Deploy", True),
        ("第三章 并发", True),
        ("一、概述", True),
        ("HashMap uses buckets.", False),
        ("1" + "、" + "x" * 90, False),
        ("", False),
    ],
)
def test_heading_detection(line: str, expected: bool) -> None:
    assert is_heading(line) is expected


def test_embedding_text_without_title_is_the_chunk() -> None:
    chunk = TextChunk(text="body", title=None, token_count=1, page_start=1, page_end=1)
    assert chunk.embedding_text() == "body"
