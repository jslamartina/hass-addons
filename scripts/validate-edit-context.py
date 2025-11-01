#!/usr/bin/env python3
"""
Validate edit_file context by comparing extracted context against actual file content.

This utility performs byte-to-byte comparison to catch mismatches before edit_file calls.
Useful for debugging whitespace, encoding, and context extraction issues.

DEPRECATED: With formatOnSave disabled, this tool is no longer necessary.
The linter-first approach is now the recommended workflow.

Usage:
    python3 scripts/validate-edit-context.py <file> <context_string> [start_line]

Example:
    python3 scripts/validate-edit-context.py src/app.py "def foo():" 10
"""

import argparse
import difflib
import sys
from pathlib import Path
from typing import List, Optional, Tuple


class EditContextValidator:
    """Validates edit_file context by comparing against actual file content."""

    def __init__(self, file_path: str):
        """Initialize validator with file path."""
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)

        # Read file with explicit encoding detection
        self.content = self._read_file()
        self.lines = self.content.splitlines(keepends=True)
        self.bytes_content = self.content.encode("utf-8")

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
        start_line: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Validate that context matches file content at the expected location.

        Args:
            context: The context string to validate (as it would appear in old_string)
            start_line: Optional starting line number (1-indexed) to search from

        Returns:
            Tuple of (is_valid, message)
        """
        context_bytes = context.encode("utf-8")

        # Search for the context in the file
        try:
            position = self.bytes_content.find(context_bytes)
        except Exception as e:
            return False, f"Error searching file: {e}"

        if position == -1:
            # Context not found - provide helpful debugging info
            return False, self._generate_not_found_message(context)

        # Context found - verify byte-by-byte
        extracted = self.bytes_content[position : position + len(context_bytes)]

        if extracted == context_bytes:
            # Calculate line number for user info
            line_num = self.bytes_content[:position].count(b"\n") + 1
            return True, f"✓ Context matches at line {line_num}"
        else:
            return False, "Bytes match but content differs (encoding issue?)"

    def validate_with_context_lines(
        self,
        old_string: str,
        start_line: int,
        context_before: int = 3,
        context_after: int = 3,
    ) -> Tuple[bool, str]:
        """
        Validate old_string with surrounding context lines.

        Args:
            old_string: The exact string to match
            start_line: Starting line number (1-indexed)
            context_before: Lines to show before match
            context_after: Lines to show after match

        Returns:
            Tuple of (is_valid, message with context)
        """
        is_valid, msg = self.validate_context(old_string, start_line)

        if not is_valid:
            return False, msg

        # Get context for display
        position = self.bytes_content.find(old_string.encode("utf-8"))
        line_num = self.bytes_content[:position].count(b"\n") + 1

        # Extract surrounding lines
        start = max(0, line_num - context_before - 1)
        end = min(
            len(self.lines), line_num + len(old_string.splitlines()) + context_after
        )

        context_display = self._format_context(start, end, line_num)
        return True, f"✓ Valid at line {line_num}\n{context_display}"

    def _generate_not_found_message(self, context: str) -> str:
        """Generate helpful message when context not found."""
        lines = context.split("\n")
        first_line = lines[0][:50]

        # Try to find similar lines
        similar = self._find_similar_lines(first_line)

        msg = "✗ Context not found in file\n"
        msg += f"  Searching for: {repr(first_line)}...\n"

        if similar:
            msg += "\n  Similar lines found:\n"
            for line_num, line_content in similar[:3]:
                msg += f"    Line {line_num}: {repr(line_content[:60])}\n"

        msg += "\n  Check for:\n"
        msg += "    - Whitespace differences (tabs vs spaces)\n"
        msg += "    - Extra/missing newlines\n"
        msg += "    - Encoding issues\n"
        msg += "    - Wrong line number\n"

        return msg

    def _find_similar_lines(
        self, search_term: str, max_results: int = 3
    ) -> List[Tuple[int, str]]:
        """Find lines similar to search_term using difflib."""
        similar = []
        for i, line in enumerate(self.lines, 1):
            clean_line = line.rstrip("\n\r")
            ratio = difflib.SequenceMatcher(None, search_term, clean_line).ratio()
            if ratio > 0.5 and len(similar) < max_results:
                similar.append((i, clean_line))
        return sorted(
            similar,
            key=lambda x: -difflib.SequenceMatcher(None, search_term, x[1]).ratio(),
        )

    def _format_context(
        self, start_line: int, end_line: int, highlight_line: int
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

        # Show character-by-character diff
        report += "Character differences:\n"
        for i, (c1, c2) in enumerate(zip(old_string, file_extraction)):
            if c1 != c2:
                report += f"  Position {i}: {repr(c1)} != {repr(c2)}\n"
                if i >= 5:  # Show first 5 differences
                    remaining = sum(
                        1
                        for a, b in zip(old_string[i + 1 :], file_extraction[i + 1 :])
                        if a != b
                    )
                    if remaining > 0:
                        report += f"  ... and {remaining} more differences\n"
                    break

        return report


def main():
    """CLI interface for validation."""
    parser = argparse.ArgumentParser(
        description="Validate edit_file context by byte-to-byte comparison",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate a context string exists in the file
  python3 scripts/validate-edit-context.py src/app.py "def foo():"

  # Validate with specific starting line
  python3 scripts/validate-edit-context.py src/app.py "def foo():" 10

  # Validate multiline context
  python3 scripts/validate-edit-context.py src/app.py "def foo():\\n    pass"
        """,
    )

    parser.add_argument("file", help="File to validate")
    parser.add_argument("context", help="Context string to validate")
    parser.add_argument(
        "--line", "-l", type=int, help="Starting line number (1-indexed)"
    )
    # TEST: This is a deliberately long line that should be wrapped by the linter to test if auto-formatting is still happening even though we disabled it xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    try:
        validator = EditContextValidator(args.file)
        is_valid, message = validator.validate_context(args.context, args.line)

        print(message)

        if not is_valid:
            sys.exit(1)

    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
