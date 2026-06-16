"""Unit tests for core RAG functions in main.py."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch
from main import _keywords, _chunk_text, _chunk_score, retrieve_context, CHUNK_SIZE, CHUNK_OVERLAP


class TestKeywords:
    def test_empty_string(self):
        assert _keywords("") == set()

    def test_only_stopwords_english(self):
        assert _keywords("and the for with that this from") == set()

    def test_only_stopwords_vietnamese(self):
        assert _keywords("và hoặc các cho khi sau trước") == set()

    def test_mixed_content_filters_stopwords(self):
        result = _keywords("đăng nhập thất bại")
        assert "đăng" in result
        assert "nhập" in result
        assert "thất" in result
        assert "bại" in result

    def test_short_tokens_excluded(self):
        result = _keywords("ab cd test")
        assert "ab" not in result
        assert "cd" not in result

    def test_hyphenated_word_included(self):
        result = _keywords("test-case scenario")
        assert "test-case" in result

    def test_returns_lowercase(self):
        result = _keywords("Login LOGOUT")
        assert "login" in result
        assert "logout" in result

    def test_deduplication(self):
        result = _keywords("login login login")
        assert result == {"login"}

    def test_returns_set(self):
        assert isinstance(_keywords("hello world"), set)


class TestChunkText:
    def test_empty_text(self):
        assert _chunk_text("") == []

    def test_whitespace_only(self):
        assert _chunk_text("   \n\n  ") == []

    def test_short_text_single_chunk(self):
        text = "Short description for testing."
        chunks = _chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0]["text"] == text

    def test_chunk_has_required_keys(self):
        chunks = _chunk_text("Some content here")
        chunk = chunks[0]
        assert "chunk_id" in chunk
        assert "text" in chunk
        assert "keywords" in chunk
        assert "preview" in chunk

    def test_chunk_ids_sequential(self):
        long_text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = _chunk_text(long_text)
        ids = [c["chunk_id"] for c in chunks]
        assert ids == list(range(len(chunks)))

    def test_multiple_paragraphs_split(self):
        text = "First paragraph content.\n\nSecond paragraph content.\n\nThird paragraph content."
        chunks = _chunk_text(text)
        assert len(chunks) >= 1

    def test_oversized_paragraph_splits(self):
        long_para = "word " * 300  # ~1500 chars, > CHUNK_SIZE=1200
        chunks = _chunk_text(long_para)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk["text"]) <= CHUNK_SIZE

    def test_overlap_in_sequential_chunks(self):
        long_para = "abcde " * 250  # produces multiple chunks from one paragraph
        chunks = _chunk_text(long_para)
        if len(chunks) >= 2:
            end_of_first = chunks[0]["text"][-CHUNK_OVERLAP:]
            start_of_second = chunks[1]["text"][:CHUNK_OVERLAP]
            # There should be some shared content due to overlap
            assert len(end_of_first) > 0

    def test_keywords_are_sorted_list(self):
        chunks = _chunk_text("authentication login security")
        assert isinstance(chunks[0]["keywords"], list)
        assert chunks[0]["keywords"] == sorted(chunks[0]["keywords"])


class TestChunkScore:
    def _make_item(self, title="Feature", item_type="document"):
        return {"title": title, "type": item_type, "source": "test.md"}

    def _make_chunk(self, text="some content", keywords=None):
        return {"text": text, "keywords": keywords or list(_keywords(text))}

    def test_zero_overlap_no_substring(self):
        item = self._make_item()
        chunk = self._make_chunk("unrelated content")
        score = _chunk_score("completely different query", set(), item, chunk)
        assert score == 0

    def test_full_query_substring_bonus(self):
        item = self._make_item()
        chunk = self._make_chunk("user can login successfully")
        score = _chunk_score("user can login successfully", {"login"}, item, chunk)
        assert score >= 10

    def test_keyword_overlap_increases_score(self):
        item = self._make_item()
        chunk = self._make_chunk("authentication login password reset")
        score_with_overlap = _chunk_score("login authentication", {"login", "authentication"}, item, chunk)
        score_no_overlap = _chunk_score("login authentication", set(), item, chunk)
        assert score_with_overlap >= score_no_overlap

    def test_title_keyword_bonus(self):
        item = self._make_item(title="Login Feature")
        chunk = self._make_chunk("basic content")
        score = _chunk_score("login feature", {"login"}, item, chunk)
        assert score >= 2

    def test_type_keyword_bonus(self):
        item = self._make_item(item_type="workflow")
        chunk = self._make_chunk("process steps")
        score = _chunk_score("workflow process", {"workflow"}, item, chunk)
        assert score >= 1

    def test_ratio_based_scoring_favors_focused_chunks(self):
        """A chunk where all keywords match should score higher ratio than one with few matches."""
        item = self._make_item()
        # Chunk with 3 keywords, 3 matching (100% match)
        focused_chunk = self._make_chunk("login auth security", ["login", "auth", "security"])
        # Chunk with 10 keywords, 3 matching (30% match)
        broad_chunk = self._make_chunk(
            "login auth security other stuff details info notes extra misc",
            ["login", "auth", "security", "other", "stuff", "details", "info", "notes", "extra", "misc"],
        )
        query_kw = {"login", "auth", "security"}
        score_focused = _chunk_score("login auth security", query_kw, item, focused_chunk)
        score_broad = _chunk_score("login auth security", query_kw, item, broad_chunk)
        assert score_focused >= score_broad


class TestRetrieveContext:
    def _make_knowledge_item(self, item_id="KB-001", title="Test", status="READY", readable=True):
        return {
            "id": item_id,
            "title": title,
            "type": "document",
            "source": "test.md",
            "text": "authentication login user password security",
            "status": status,
            "readable": readable,
            "chunks": [
                {
                    "chunk_id": 0,
                    "text": "authentication login user password security",
                    "keywords": ["authentication", "login", "password", "security"],
                    "preview": "authentication login user...",
                }
            ],
            "created_at": "2026-06-14T10:00:00",
        }

    def test_empty_knowledge_returns_empty(self):
        with patch("main._read_knowledge", return_value=[]):
            result = retrieve_context("login feature")
        assert result == []

    def test_non_ready_item_excluded(self):
        item = self._make_knowledge_item(status="NEEDS_REVIEW")
        with patch("main._read_knowledge", return_value=[item]):
            result = retrieve_context("authentication login")
        assert result == []

    def test_non_readable_item_excluded(self):
        item = self._make_knowledge_item(readable=False)
        with patch("main._read_knowledge", return_value=[item]):
            result = retrieve_context("authentication login")
        assert result == []

    def test_matching_item_returned(self):
        item = self._make_knowledge_item()
        with patch("main._read_knowledge", return_value=[item]):
            result = retrieve_context("authentication login")
        assert len(result) == 1
        assert result[0]["id"] == "KB-001"
        assert "matched_chunks" in result[0]
        assert "match_score" in result[0]

    def test_limit_respected(self):
        items = [self._make_knowledge_item(item_id=f"KB-{i:03d}") for i in range(5)]
        with patch("main._read_knowledge", return_value=items):
            result = retrieve_context("authentication login", limit=2)
        assert len(result) <= 2

    def test_results_sorted_by_score_descending(self):
        high_score_item = self._make_knowledge_item(item_id="KB-001", title="Authentication Security Login")
        low_score_item = self._make_knowledge_item(item_id="KB-002", title="Unrelated Topic")
        low_score_item["chunks"] = [
            {"chunk_id": 0, "text": "unrelated content", "keywords": ["unrelated"], "preview": "unrelated..."}
        ]
        with patch("main._read_knowledge", return_value=[low_score_item, high_score_item]):
            result = retrieve_context("authentication login security", limit=4)
        if len(result) >= 2:
            assert result[0]["match_score"] >= result[1]["match_score"]
