from __future__ import annotations

import re
from typing import Iterable

from config import MAX_CHARS_PER_CHUNK

_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
_CLAUSE_SPLIT_PATTERN = re.compile(r"(?<=[,;:])\s+|\s+[—-]\s+")
_PAUSE_MARKER_PATTERN = re.compile(r"\[pause:(\d+)\]", re.IGNORECASE)

# XTTS hard per-language character limits
XTTS_CHAR_LIMITS: dict[str, int] = {
    "en": 250, "es": 239, "fr": 273, "de": 253, "it": 213,
    "pt": 203, "pl": 224, "tr": 226, "ru": 182, "nl": 251,
    "cs": 186, "ar": 166, "zh-cn": 82, "hu": 224, "ko": 100,
    "ja": 100, "hi": 150,
}
XTTS_DEFAULT_LIMIT = 200

# ── Pause marker dataclass ─────────────────────────────────────────────────

class PauseMarker:
    """Represents a [pause:N] marker — N milliseconds of silence."""
    def __init__(self, ms: int):
        self.ms = ms

    def __repr__(self) -> str:
        return f"PauseMarker({self.ms}ms)"


# ── Internal helpers ───────────────────────────────────────────────────────

def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_into_sentences(text: str) -> list[str]:
    cleaned = _normalize_whitespace(text)
    if not cleaned:
        return []
    return [part.strip() for part in _SENTENCE_SPLIT_PATTERN.split(cleaned) if part.strip()]


def _wrap_by_words(text: str, max_chars: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks


def _split_oversized_sentence(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    clauses = [p.strip() for p in _CLAUSE_SPLIT_PATTERN.split(sentence) if p.strip()]
    if len(clauses) <= 1:
        return _wrap_by_words(sentence, max_chars)
    chunks: list[str] = []
    current = ""
    for clause in clauses:
        candidate = clause if not current else f"{current} {clause}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(clause) <= max_chars:
            current = clause
        else:
            chunks.extend(_wrap_by_words(clause, max_chars))
    if current:
        chunks.append(current)
    return chunks


# ── Public API ─────────────────────────────────────────────────────────────

def parse_script(text: str) -> list[str | PauseMarker]:
    """
    Split a script into a sequence of text segments and PauseMarker objects.

    Recognises [pause:N] markers (N = milliseconds) anywhere in the text.
    Leading/trailing whitespace around markers is absorbed.

    Example input:
        "Welcome back. [pause:500] Today we discuss AI. [pause:1000] Let's begin."

    Returns:
        ["Welcome back.", PauseMarker(500), "Today we discuss AI.", PauseMarker(1000), "Let's begin."]
    """
    parts: list[str | PauseMarker] = []
    last_end = 0

    for match in _PAUSE_MARKER_PATTERN.finditer(text):
        before = text[last_end:match.start()].strip()
        if before:
            parts.append(before)
        parts.append(PauseMarker(int(match.group(1))))
        last_end = match.end()

    tail = text[last_end:].strip()
    if tail:
        parts.append(tail)

    return parts if parts else [text]


def chunk_text(
    text: str,
    max_chars_per_chunk: int = MAX_CHARS_PER_CHUNK,
    language: str = "en",
    min_chars_per_chunk: int = 60,
) -> list[str]:
    """Chunk plain text (no pause markers) into XTTS-safe segments."""
    sentences = split_into_sentences(text)
    if not sentences:
        return []

    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if len(sentence) > max_chars_per_chunk:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_oversized_sentence(sentence, max_chars_per_chunk))
            continue
        candidate = sentence if not current else f"{current} {sentence}"
        if len(candidate) <= max_chars_per_chunk:
            current = candidate
        else:
            chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)

    # Hard-clamp: enforce XTTS per-language limit as final safety net
    hard_limit = XTTS_CHAR_LIMITS.get(language.lower(), XTTS_DEFAULT_LIMIT)
    safe: list[str] = []
    for chunk in chunks:
        if chunk.strip():
            safe.extend(_wrap_by_words(chunk, hard_limit) if len(chunk) > hard_limit else [chunk])

    # Merge short chunks into the previous one to avoid tiny isolated chunks
    # (e.g. "Fast." alone = 5 chars → XTTS generates gibberish tail after a single word).
    # Two passes: forward-merge short chunks into previous; if first chunk is short,
    # merge it into the next one instead.
    merged: list[str] = []
    hard_limit = XTTS_CHAR_LIMITS.get(language.lower(), XTTS_DEFAULT_LIMIT)
    for chunk in safe:
        if (merged
                and len(chunk) < min_chars_per_chunk
                and len(merged[-1]) + 1 + len(chunk) <= hard_limit):
            merged[-1] = merged[-1] + " " + chunk
        else:
            merged.append(chunk)
    # If the very first chunk is short, push it forward into the next chunk
    if len(merged) >= 2 and len(merged[0]) < min_chars_per_chunk:
        if len(merged[0]) + 1 + len(merged[1]) <= hard_limit:
            merged[1] = merged[0] + " " + merged[1]
            merged.pop(0)

    # Ensure every chunk ends with punctuation so XTTS doesn't cut off the final word.
    result: list[str] = []
    for chunk in merged:
        c = chunk.strip()
        if c and c[-1] not in '.!?,;:—-"\u201c\u201d':
            c = c + "."
        result.append(c)
    return result


def chunk_script(
    text: str,
    max_chars_per_chunk: int = MAX_CHARS_PER_CHUNK,
    language: str = "en",
    min_chars_per_chunk: int = 60,
) -> list[str | PauseMarker]:
    """
    Full pipeline: parse [pause:N] markers, then chunk each text segment.
    """
    segments = parse_script(text)
    result: list[str | PauseMarker] = []

    for segment in segments:
        if isinstance(segment, PauseMarker):
            result.append(segment)
        else:
            result.extend(chunk_text(segment, max_chars_per_chunk, language, min_chars_per_chunk))

    return result


def iter_chunks(
    text: str,
    max_chars_per_chunk: int = MAX_CHARS_PER_CHUNK,
    language: str = "en",
) -> Iterable[str]:
    yield from chunk_text(text, max_chars_per_chunk=max_chars_per_chunk, language=language)

