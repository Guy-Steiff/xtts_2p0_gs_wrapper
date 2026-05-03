#!/usr/bin/env python3
"""
Narration parser — extracts only NARRATION: blocks from structured script files.

Input format example:
    ONSCREEN:
    - some visual description
    FOOTAGE KEYWORDS:
    some keywords here

    NARRATION:
    The actual spoken text goes here.

    [pause:500]

    More spoken text.

    SCENE 14 — END STATE OF CHAPTER 16

    ONSCREEN:
    ...

Output: clean narration-only text, preserving [pause:N] markers and blank lines
        between narration blocks (so the podcast generator treats them as pauses).

Usage:
    python parse_narration.py input.txt               # prints to stdout
    python parse_narration.py input.txt output.txt    # saves to file
    python parse_narration.py input.txt --preview     # preview first 500 chars

    Or as a library:
        from parse_narration import extract_narration
        text = extract_narration(Path("script.txt"))
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Matches the start of a non-narration section header
_SECTION_HEADER_RE = re.compile(
    r"^\s*(ONSCREEN|FOOTAGE\s+KEYWORDS?|SCENE\s+\d+|={3,}|END\s+CHAPTER)",
    re.IGNORECASE,
)

# Matches NARRATION: label (with optional whitespace / colon variants)
_NARRATION_START_RE = re.compile(r"^\s*NARRATION\s*:\s*$", re.IGNORECASE)


def extract_narration(source: str | Path) -> str:
    """
    Extract all NARRATION: block content from a structured script.

    Args:
        source: Either a file path (str or Path) or raw text content (str).
                If the string is an existing file path it will be read;
                otherwise it is treated as raw text.

    Returns:
        Clean narration text with [pause:N] markers preserved,
        blocks separated by a blank line.
    """
    if isinstance(source, Path) or (isinstance(source, str) and Path(source).exists()):
        text = Path(source).read_text(encoding="utf-8")
    else:
        text = source

    lines = text.splitlines()
    narration_blocks: list[list[str]] = []
    current_block: list[str] | None = None
    in_narration = False

    for line in lines:
        # Detect NARRATION: header → start collecting
        if _NARRATION_START_RE.match(line):
            in_narration = True
            current_block = []
            continue

        # Detect any other section header → stop collecting
        if in_narration and _SECTION_HEADER_RE.match(line):
            in_narration = False
            if current_block is not None:
                # Strip leading/trailing blank lines from block
                stripped = _strip_blank_edges(current_block)
                if stripped:
                    narration_blocks.append(stripped)
            current_block = None
            continue

        if in_narration and current_block is not None:
            current_block.append(line)

    # Flush last open block (file ends without a section header after narration)
    if in_narration and current_block is not None:
        stripped = _strip_blank_edges(current_block)
        if stripped:
            narration_blocks.append(stripped)

    # Join blocks with a single blank line between them
    result = "\n\n".join("\n".join(block) for block in narration_blocks)
    return result.strip()


def _strip_blank_edges(lines: list[str]) -> list[str]:
    """Remove leading and trailing blank lines from a block."""
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    end = len(lines) - 1
    while end >= start and not lines[end].strip():
        end -= 1
    return lines[start: end + 1]


def extract_narration_to_file(input_path: str | Path, output_path: str | Path) -> Path:
    """Extract narration from input_path and save to output_path."""
    text = extract_narration(input_path)
    output_path: Path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    print(f"✅ Narration extracted → {output_path}  ({len(text)} chars)")
    return output_path


# ─── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    input_file = Path(args[0])
    if not input_file.exists():
        print(f"❌ File not found: {input_file}", file=sys.stderr)
        sys.exit(1)

    narration = extract_narration(input_file)

    if "--preview" in args:
        preview = narration[:500]
        print(f"\n─── NARRATION PREVIEW (first 500 chars) ───\n")
        print(preview)
        if len(narration) > 500:
            print(f"\n... ({len(narration) - 500} more chars)")
        print(f"\n─── Total: {len(narration)} chars ───")
        sys.exit(0)

    if len(args) >= 2 and not args[1].startswith("--"):
        output_file = Path(args[1])
        extract_narration_to_file(input_file, output_file)
    else:
        print(narration)


