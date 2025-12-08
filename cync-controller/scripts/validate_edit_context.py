"""Validate edit_file context by comparing extracted context against actual file content.

This utility performs byte-to-byte comparison to catch mismatches before edit_file calls.
Useful for debugging whitespace, encoding, and context extraction issues.

Usage:
    python3 -m scripts.validate_edit_context <file> <context_string> [start_line]
    python3 scripts/validate_edit_context.py <file> <context_string> [start_line]
"""

from __future__ import annotations

import argparse
import difflib
from pathlib import Path
from typing import cast

SIMILARITY_THRESHOLD = 0.5
BYTE_DIFF_LIMIT = 5


class EditContextValidator:
    """Validates edit_file context by comparing against actual file content."""

    def __init__(self, file_path: str):
        """Initialize validator with file path."""
        self.file_path: Path = Path(file_path)
        if not self.file_path.exists():
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)

        self.content: str = self._read_file()
        self.lines: list[str] = self.content.splitlines(keepends=True)
        self.bytes_content: bytes = self.content.encode("utf-8")

    def _read_file(self) -> str:
        """Read file content, detecting encoding."""
        try:
            return self.file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                return self.file_path.read_text(encoding="latin-1")
            except UnicodeDecodeError:
                return self.file_path.read_text(encoding="utf-8", errors="replace")

    def validate_context(
        self,
        context: str,
        start_line: int | None = None,
    ) -> tuple[bool, str]:
        """Validate that context matches file content at the expected location.

        Args:
            context: The context string to validate (as it would appear in old_string)
            start_line: Optional starting line number (1-indexed) to search from

        Returns:
            Tuple of (is_valid, message)

        """
        _ = start_line  # maintained for compatibility; not used directly
        context_bytes = context.encode("utf-8")

        try:
            position = self.bytes_content.find(context_bytes)
        except Exception as e:  # pragma: no cover - defensive
            return False, f"Error searching file: {e}"

        if position == -1:
            return False, self._generate_not_found_message(context)

        extracted = self.bytes_content[position : position + len(context_bytes)]
        if extracted == context_bytes:
            line_num = self.bytes_content[:position].count(b"\n") + 1
            return True, f"✓ Context matches at line {line_num}"
        return False, "Bytes match but content differs (encoding issue?)"

    def validate_with_context_lines(
        self,
        old_string: str,
        start_line: int,
        context_before: int = 3,
        context_after: int = 3,
    ) -> tuple[bool, str]:
        """Validate old_string with surrounding context lines."""
        is_valid, msg = self.validate_context(old_string, start_line)
        if not is_valid:
            return False, msg

        position = self.bytes_content.find(old_string.encode("utf-8"))
        line_num = self.bytes_content[:position].count(b"\n") + 1

        start = max(0, line_num - context_before - 1)
        end = min(len(self.lines), line_num + len(old_string.splitlines()) + context_after)

        context_display = self._format_context(start, end, line_num)
        return True, f"✓ Valid at line {line_num}\n{context_display}"

    def _generate_not_found_message(self, context: str) -> str:
        """Generate helpful message when context not found."""
        lines = context.split("\n")
        first_line = lines[0][:50]
        similar = self._find_similar_lines(first_line)

        msg = "✗ Context not found in file\n"
        msg += f"  Searching for: {first_line!r}...\n"

        if similar:
            msg += "\n  Similar lines found:\n"
            for line_num, line_content in similar[:3]:
                msg += f"    Line {line_num}: {line_content[:60]!r}\n"

        msg += "\n  Check for:\n"
        msg += "    - Whitespace differences (tabs vs spaces)\n"
        msg += "    - Extra/missing newlines\n"
        msg += "    - Encoding issues\n"
        msg += "    - Wrong line number\n"
        return msg

    def _find_similar_lines(
        self,
        search_term: str,
        max_results: int = 3,
    ) -> list[tuple[int, str]]:
        """Find lines similar to search_term using difflib."""
        similar: list[tuple[int, str]] = []
        for i, line in enumerate(self.lines, 1):
            clean_line = line.rstrip("\n\r")
            ratio = difflib.SequenceMatcher(None, search_term, clean_line).ratio()
            if ratio > SIMILARITY_THRESHOLD and len(similar) < max_results:
                similar.append((i, clean_line))
        return sorted(similar, key=lambda x: -difflib.SequenceMatcher(None, search_term, x[1]).ratio())

    def _format_context(
        self,
        start_line: int,
        end_line: int,
        highlight_line: int,
    ) -> str:
        """Format context lines with syntax highlighting."""
        output = "  Context:\n"
        for i in range(start_line, end_line):
            if i >= len(self.lines):
                break
            line = self.lines[i].rstrip("\n\r")
            marker = ">>>" if (i + 1) == highlight_line else "   "
            line_num = i + 1
            output += f"  {marker} {line_num:4d} | {line}\n"
        return output

    def byte_diff_report(self, old_string: str, file_extraction: str) -> str:
        """Generate detailed byte-level diff report."""
        old_bytes = old_string.encode("utf-8")
        file_bytes = file_extraction.encode("utf-8")

        report = "Byte-level comparison:\n"
        report += f"  Expected: {len(old_bytes)} bytes\n"
        report += f"  Actual:   {len(file_bytes)} bytes\n"

        if old_bytes == file_bytes:
            report += "  ✓ Bytes match exactly\n"
            return report

        report += "  ✗ Bytes differ\n\n"
        report += "Character differences:\n"
        for i, (c1, c2) in enumerate(zip(old_string, file_extraction, strict=False)):
            if c1 != c2:
                report += f"  Position {i}: {c1!r} != {c2!r}\n"
                if i >= BYTE_DIFF_LIMIT:
                    break
        return report


def main() -> int:
    """CLI entry point for context validation."""
    parser = argparse.ArgumentParser(description="Validate edit_file context against file content.")
    _ = parser.add_argument("file_path", help="Path to the file to validate")
    _ = parser.add_argument("context_string", help="Context string to search for")
    _ = parser.add_argument(
        "start_line",
        nargs="?",
        type=int,
        default=None,
        help="Optional starting line number (1-based)",
    )
    args = parser.parse_args()

    file_arg = cast(str, args.file_path)
    context_arg = cast(str, args.context_string)
    line_arg = cast(int | None, args.start_line)

    validator = EditContextValidator(file_arg)
    is_valid, _message = validator.validate_context(context_arg, line_arg)
    return 0 if is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
