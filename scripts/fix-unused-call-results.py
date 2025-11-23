#!/usr/bin/env python3
"""Fix unused call results by adding '_ = ' prefix.

This script parses Pyright output for reportUnusedCallResult warnings
and automatically fixes them by prefixing the call with '_ = '.
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple


class UnusedCallResult(NamedTuple):
    """Represents an unused call result location."""

    file_path: Path
    line_num: int
    column: int


def get_pyright_output(repo_root: Path) -> str:
    """Run Pyright and return output."""
    cync_controller = repo_root / "cync-controller"
    if not cync_controller.exists():
        print(f"Error: {cync_controller} not found")
        sys.exit(1)

    result = subprocess.run(
        ["basedpyright", "--project", "pyrightconfig.json"],
        cwd=cync_controller,
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr


def parse_unused_call_results(output: str, repo_root: Path) -> list[UnusedCallResult]:
    """Parse Pyright output for unused call result warnings."""
    results = []
    # Pattern matches: /workspaces/hass-addons/cync-controller/src/...:line:col - warning: ... (reportUnusedCallResult)
    pattern = re.compile(
        r"^\s+([^:]+):(\d+):(\d+)\s+-\s+warning:.*\(reportUnusedCallResult\)"
    )

    for line in output.splitlines():
        match = pattern.match(line)
        if match:
            file_path_str = match.group(1)
            line_num = int(match.group(2))
            column = int(match.group(3))

            # Use absolute path directly
            file_path = Path(file_path_str)
            if file_path.exists():
                results.append(UnusedCallResult(file_path, line_num, column))

    return results


def fix_unused_call_result(file_path: Path, line_num: int) -> bool:
    """Fix unused call result by adding '_ = ' prefix.

    Returns True if fix was applied, False otherwise.
    """
    try:
        with file_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return False

    if line_num < 1 or line_num > len(lines):
        print(f"Warning: Line {line_num} out of range in {file_path}")
        return False

    line = lines[line_num - 1]
    original_line = line

    # Skip if already has '_ = ' prefix
    stripped = line.lstrip()
    if stripped.startswith("_ = ") or stripped.startswith("_= "):
        return False

    # Skip if it's a comment or empty line
    if stripped.startswith("#") or not stripped.strip():
        return False

    # Find the actual call expression - look for common patterns
    # Pattern 1: await expression
    if "await " in line:
        # Find the await keyword
        await_pos = line.find("await ")
        if await_pos != -1:
            # Check if it's already assigned
            before_await = line[:await_pos].strip()
            if not before_await.endswith("=") and not before_await.endswith("_ ="):
                # Add '_ = ' before 'await'
                indent = len(line) - len(line.lstrip())
                new_line = " " * indent + "_ = " + line[await_pos:].lstrip()
                lines[line_num - 1] = new_line
                print(f"Fixed: {file_path}:{line_num} - added '_ = ' before await")
                with file_path.open("w", encoding="utf-8") as f:
                    f.writelines(lines)
                return True

    # Pattern 2: Regular function call (not await)
    # Look for patterns like: function_call() or obj.method()
    # But skip if it's part of an assignment, if statement, etc.
    stripped_line = line.strip()
    if (
        not stripped_line.startswith("if ")
        and not stripped_line.startswith("elif ")
        and not stripped_line.startswith("while ")
        and not stripped_line.startswith("for ")
        and not stripped_line.startswith("return ")
        and not stripped_line.startswith("yield ")
        and not stripped_line.startswith("raise ")
        and not stripped_line.startswith("assert ")
        and "=" not in stripped_line.split()[0] if stripped_line.split() else False
        and not stripped_line.startswith("with ")
        and not stripped_line.startswith("except ")
        and "(" in stripped_line
        and not stripped_line.startswith("#")
    ):
        # Check if it's a standalone call
        # Look for patterns like: function() or obj.method()
        if re.search(r"\w+\([^)]*\)", stripped_line):
            indent = len(line) - len(line.lstrip())
            new_line = " " * indent + "_ = " + stripped_line + "\n"
            lines[line_num - 1] = new_line
            print(f"Fixed: {file_path}:{line_num} - added '_ = ' before call")
            with file_path.open("w", encoding="utf-8") as f:
                f.writelines(lines)
            return True

    return False


def main():
    """Main entry point."""
    repo_root = Path(__file__).parent.parent
    print(f"Repository root: {repo_root}")

    print("Running Pyright to find unused call results...")
    output = get_pyright_output(repo_root)

    print("Parsing unused call results...")
    unused_results = parse_unused_call_results(output, repo_root)

    print(f"Found {len(unused_results)} unused call results")

    if not unused_results:
        print("No unused call results found!")
        return

    # Group by file for efficiency
    by_file: dict[Path, list[UnusedCallResult]] = {}
    for result in unused_results:
        if result.file_path not in by_file:
            by_file[result.file_path] = []
        by_file[result.file_path].append(result)

    # Fix each file
    fixed_count = 0
    for file_path, results in sorted(by_file.items()):
        print(f"\nProcessing {file_path} ({len(results)} issues)...")
        # Sort by line number (descending) to avoid line number shifts
        for result in sorted(results, key=lambda x: x.line_num, reverse=True):
            if fix_unused_call_result(result.file_path, result.line_num):
                fixed_count += 1

    print(f"\nFixed {fixed_count} unused call results")


if __name__ == "__main__":
    main()

