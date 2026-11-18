"""Small text helpers shared by parsers, chunkers and enrichment.

Token counts use tiktoken's `cl100k_base`. It is not the tokenizer of our embedding model, but it
is a stable, fast yardstick: what matters for chunk sizing is a consistent unit that reflects that
German is denser than English (docs/vector-db-design.md §3: "measure, don't count characters").
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import tiktoken

_WS_RE = re.compile(r"[ \t   ]+")
_ZERO_WIDTH_RE = re.compile(r"[​‌‍﻿­]")
_MANY_NEWLINES_RE = re.compile(r"\n{3,}")
_SENTENCE_RE = re.compile(r"(?<=[.!?;:])\s+(?=[A-ZÄÖÜ0-9(„\"])")


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text))


def normalize_whitespace(text: str) -> str:
    """Collapse runs of spaces (incl. non-breaking), drop zero-width chars, trim each line.

    Newlines are kept (they separate list items and paragraphs), but at most one blank line.
    """
    text = unicodedata.normalize("NFC", text)
    text = _ZERO_WIDTH_RE.sub("", text)
    lines = [_WS_RE.sub(" ", line).strip() for line in text.replace("\r", "").split("\n")]
    return _MANY_NEWLINES_RE.sub("\n\n", "\n".join(lines)).strip()


_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"})


def slugify(text: str, max_len: int = 60) -> str:
    """'Höhe des Elterngeldes' -> 'hoehe-des-elterngeldes' (lowercase ascii, '-' separated)."""
    text = text.translate(_UMLAUTS).lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return slug[:max_len].rstrip("-") or "section"


def markdown_table(header: list[str], rows: list[list[str]]) -> str:
    """Render a table as GitHub markdown. Pipes inside cells are escaped."""

    def cell(value: str) -> str:
        return normalize_whitespace(value).replace("\n", " ").replace("|", "\\|")

    width = max([len(header)] + [len(r) for r in rows]) if (header or rows) else 0
    header = (header + [""] * width)[:width] if header else [""] * width
    lines = ["| " + " | ".join(cell(h) for h in header) + " |", "|" + "---|" * width]
    for row in rows:
        padded = (row + [""] * width)[:width]
        lines.append("| " + " | ".join(cell(c) for c in padded) + " |")
    return "\n".join(lines)


def split_markdown_table(table: str, max_tokens: int) -> list[str]:
    """Split a markdown table into row groups, repeating the header row in every part.

    A table without its header is meaningless to both an embedding model and a reader
    ("12,60 €" of *what*?), so every part starts with the header + separator line.
    """
    lines = table.strip().split("\n")
    if count_tokens(table) <= max_tokens or len(lines) <= 3:
        return [table.strip()]
    head, rows = lines[:2], lines[2:]
    parts: list[str] = []
    current: list[str] = []
    for row in rows:
        candidate = "\n".join(head + current + [row])
        if current and count_tokens(candidate) > max_tokens:
            parts.append("\n".join(head + current))
            current = []
        current.append(row)
    if current:
        parts.append("\n".join(head + current))
    return parts


def split_text(text: str, max_tokens: int) -> list[str]:
    """Split text into pieces of at most `max_tokens`, preferring natural boundaries.

    Order of preference: blank lines (paragraphs) -> single newlines (list items) -> sentences
    -> hard token windows. Pieces are greedily packed back together up to the limit, so we do
    not produce a swarm of tiny fragments.
    """
    text = text.strip()
    if count_tokens(text) <= max_tokens:
        return [text] if text else []
    for separator, splitter in (
        ("\n\n", lambda t: t.split("\n\n")),
        ("\n", lambda t: t.split("\n")),
        (" ", lambda t: _SENTENCE_RE.split(t)),
    ):
        units = [u.strip() for u in splitter(text) if u.strip()]
        if len(units) > 1:
            pieces: list[str] = []
            for unit in units:
                pieces.extend(split_text(unit, max_tokens))
            return _pack(pieces, max_tokens, separator)
    # One giant "sentence": cut by tokens.
    tokens = _encoding().encode(text)
    return [_encoding().decode(tokens[i : i + max_tokens]).strip() for i in range(0, len(tokens), max_tokens)]


def _pack(pieces: list[str], max_tokens: int, separator: str) -> list[str]:
    packed: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}{separator}{piece}" if current else piece
        if current and count_tokens(candidate) > max_tokens:
            packed.append(current)
            current = piece
        else:
            current = candidate
    if current:
        packed.append(current)
    return packed


def tail_tokens(text: str, n_tokens: int) -> str:
    """The last ~n tokens of a text, cut at a word boundary (used for chunk overlap)."""
    tokens = _encoding().encode(text)
    if len(tokens) <= n_tokens:
        return text
    tail = _encoding().decode(tokens[-n_tokens:])
    first_space = tail.find(" ")
    return tail[first_space + 1 :] if 0 <= first_space < len(tail) - 1 else tail
