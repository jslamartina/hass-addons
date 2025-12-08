#!/usr/bin/env python3
"""Test suite for validate_edit_context.py.

Tests byte-to-byte comparison validation with various scenarios.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from typing import override

from scripts.validate_edit_context import EditContextValidator  # type: ignore[import-untyped]


class TestEditContextValidator(unittest.TestCase):
    """Test cases for EditContextValidator."""

    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    temp_path: Path | None = None

    @override
    def setUp(self):
        """Create temporary test files."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    @override
    def tearDown(self):
        """Clean up temporary files."""
        if self.temp_dir is not None:
            _ = self.temp_dir.cleanup()
        self.temp_dir = None
        self.temp_path = None

    def _create_test_file(self, name: str, content: str) -> Path:
        """Create a temporary test file."""
        if self.temp_path is None:
            msg = "Temporary path not initialized"
            raise RuntimeError(msg)
        file_path = self.temp_path / name
        _ = file_path.write_text(content)
        return file_path

    def _require(self, condition: bool, message: str) -> None:
        """Fail the test with a clear message if condition is False."""
        if not condition:
            self.fail(message)

    # Test 1: Exact match
    def test_exact_match(self):
        """Exact match should succeed."""
        content = "def foo():\n    pass\n"
        file_path = self._create_test_file("test1.py", content)

        validator = EditContextValidator(str(file_path))
        is_valid, msg = validator.validate_context("def foo():")

        self._require(is_valid, f"Failed: {msg}")
        self._require("✓" in msg, "Expected ✓ in message")
        self._require("line" in msg.lower(), "Expected line info in message")

    # Test 2: Multiline exact match
    def test_multiline_exact_match(self):
        """Multiline context should match."""
        content = "def foo():\n    pass\n"
        file_path = self._create_test_file("test2.py", content)

        validator = EditContextValidator(str(file_path))
        is_valid, msg = validator.validate_context("def foo():\n    pass")

        self._require(is_valid, f"Failed: {msg}")

    # Test 3: Tab vs space mismatch
    def test_tab_space_mismatch(self):
        """Tab vs space should fail."""
        content = "def foo():\n\tpass\n"  # Tab
        file_path = self._create_test_file("test3.py", content)

        validator = EditContextValidator(str(file_path))
        is_valid, msg = validator.validate_context("def foo():\n    pass")  # Spaces

        self._require(not is_valid, "Should detect tab vs space mismatch")
        self._require("✗" in msg, "Expected failure marker in message")

    # Test 4: Extra newline
    def test_extra_newline(self):
        """Extra newline should fail."""
        content = "def foo():\n    pass\n"
        file_path = self._create_test_file("test4.py", content)

        validator = EditContextValidator(str(file_path))
        is_valid, _msg = validator.validate_context("def foo():\n\n    pass")

        self._require(not is_valid, "Should detect extra newline")

    # Test 5: Missing newline
    def test_missing_newline(self):
        """Missing newline should fail."""
        content = "def foo():\n    pass\n"
        file_path = self._create_test_file("test5.py", content)

        validator = EditContextValidator(str(file_path))
        is_valid, _msg = validator.validate_context("def foo():\n    pass\n    return None")

        self._require(not is_valid, "Should detect missing content")

    # Test 6: Partial match (should fail, not partial)
    def test_partial_content_not_found(self):
        """Context not in file should fail cleanly."""
        content = "def foo():\n    pass\n"
        file_path = self._create_test_file("test6.py", content)

        validator = EditContextValidator(str(file_path))
        is_valid, msg = validator.validate_context("def bar():")

        self._require(not is_valid, "Should fail when context not found")
        self._require("not found" in msg.lower(), "Missing not-found message")

    # Test 7: Trailing whitespace difference
    def test_trailing_whitespace(self):
        """Trailing whitespace should be detected."""
        content = "def foo():  \n    pass\n"  # Extra spaces after colon
        file_path = self._create_test_file("test7.py", content)

        validator = EditContextValidator(str(file_path))
        is_valid, _msg = validator.validate_context("def foo():\n    pass")

        self._require(not is_valid, "Should detect trailing whitespace")

    # Test 8: Case sensitive
    def test_case_sensitive(self):
        """Search should be case-sensitive."""
        content = "def Foo():\n    pass\n"
        file_path = self._create_test_file("test8.py", content)

        validator = EditContextValidator(str(file_path))
        is_valid, _msg = validator.validate_context("def foo():")

        self._require(not is_valid, "Should be case-sensitive")

    # Test 9: Finding similar lines on failure
    def test_similar_line_suggestions(self):
        """When context not found, should suggest similar lines."""
        content = "def foo():\n    pass\ndef bar():\n    return True\n"
        file_path = self._create_test_file("test9.py", content)

        validator = EditContextValidator(str(file_path))
        is_valid, msg = validator.validate_context("def Foo():")  # Wrong case

        self._require(not is_valid, "Should fail when case does not match")
        self._require("Similar" in msg, "Should suggest similar lines")

    # Test 10: Empty file handling
    def test_empty_file(self):
        """Empty file should handle gracefully."""
        file_path = self._create_test_file("test10.py", "")

        validator = EditContextValidator(str(file_path))
        is_valid, _msg = validator.validate_context("def foo():")

        self._require(not is_valid, "Should fail on empty file")

    # Test 11: Unicode content
    def test_unicode_content(self):
        """Unicode should be handled correctly."""
        content = "# -*- coding: utf-8 -*-\n# Comment with emoji: 🎉\ndef foo():\n    pass\n"
        file_path = self._create_test_file("test11.py", content)

        validator = EditContextValidator(str(file_path))
        is_valid, msg = validator.validate_context("# Comment with emoji: 🎉")

        self._require(is_valid, f"Failed: {msg}")

    # Test 12: Byte-level diff report
    def test_byte_diff_report(self):
        """Byte diff report should show differences clearly."""
        content = "hello"
        file_path = self._create_test_file("test12.py", content)

        validator = EditContextValidator(str(file_path))
        report = validator.byte_diff_report("hello", "hallo")

        self._require("Byte-level comparison" in report, "Missing diff header")
        self._require("Expected" in report, "Missing expected section")
        self._require("Actual" in report, "Missing actual section")

    # Test 13: Large file performance
    def test_large_file_performance(self):
        """Should handle large files efficiently."""
        # Create a file with 10000 lines
        content = "\n".join([f"line {i}" for i in range(10000)])
        content += "\nDEFINE_TARGET = True\n"
        file_path = self._create_test_file("test13.py", content)

        validator = EditContextValidator(str(file_path))
        is_valid, msg = validator.validate_context("DEFINE_TARGET = True")

        self._require(is_valid, f"Failed: {msg}")

    # Test 14: CRLF line endings
    def test_crlf_line_endings(self):
        """CRLF line endings should be detected."""
        content = "def foo():\r\n    pass\r\n"  # Windows line endings
        file_path = self._create_test_file("test14.py", content)
        _ = file_path.write_bytes(content.encode("utf-8"))  # Write as bytes

        validator = EditContextValidator(str(file_path))
        # Should find exact match with CRLF
        is_valid, msg = validator.validate_context("def foo():\r\n    pass")

        self._require(is_valid, f"Failed: {msg}")

    # Test 15: Multiple identical sections
    def test_multiple_identical_sections(self):
        """Should find first occurrence of repeated content."""
        content = "def foo():\n    pass\n\ndef foo():\n    pass\n"
        file_path = self._create_test_file("test15.py", content)

        validator = EditContextValidator(str(file_path))
        is_valid, msg = validator.validate_context("def foo():\n    pass")

        self._require(is_valid, f"Failed: {msg}")
        # Should find it (first occurrence)
        self._require("line" in msg.lower(), "Missing line reference in message")


def run_tests():
    """Run all tests and report results."""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestEditContextValidator)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
