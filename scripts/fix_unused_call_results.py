#!/usr/bin/env python3
"""Fix unused call results by adding '_ = ' prefix.

This script parses Pyright output for reportUnusedCallResult warnings
and automatically fixes them by prefixing the call with '_ = '.
"""

import asyncio
import re
import shutil
import sys
from pathlib import Path
from typing import NamedTuple


class UnusedCallResult(NamedTuple):
    """Represents an unused call result location."""

    file_path: Path
    line_num: int
    column: int


def _get_cli_path(command: str) -> str:
    """Resolve an executable path and ensure it exists."""
    resolved = shutil.which(command)
    if resolved is None:
        msg = f"{command} executable not found in PATH"
        raise FileNotFoundError(msg)
    return str(Path(resolved).resolve())


async def _execute_command(cmd: list[str], cwd: Path) -> str:
    """Execute a command and capture stdout/stderr."""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return (stdout or b"").decode() + (stderr or b"").decode()


def get_pyright_output(repo_root: Path) -> str:
    """Run Pyright and return output."""
    cync_controller = repo_root / "cync-controller"
    if not cync_controller.exists():
        sys.exit(1)

    basedpyright_path = _get_cli_path("basedpyright")
    return asyncio.run(
        _execute_command(
            [basedpyright_path, "--project", "pyrightconfig.json"],
            cwd=cync_controller,
        ),
    )


def parse_unused_call_results(output: str) -> list[UnusedCallResult]:
    """Parse Pyright output for unused call result warnings."""
    results: list[UnusedCallResult] = []
    # Pattern matches: /workspaces/hass-addons/cync-controller/src/...:line:col - warning: ... (reportUnusedCallResult)
    pattern = re.compile(
        r"^\s+([^:]+):(\d+):(\d+)\s+-\s+warning:.*\(reportUnusedCallResult\)",
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


def _fix_await_call(lines: list[str], line_num: int) -> bool:
    """Add an assignment for awaited calls if missing."""
    line = lines[line_num - 1]
    if "await " not in line:
        return False

    await_pos = line.find("await ")
    if await_pos == -1:
        return False

    before_await = line[:await_pos].strip()
    if before_await.endswith(("=", "_ =")):
        return False

    indent = len(line) - len(line.lstrip())
    lines[line_num - 1] = " " * indent + "_ = " + line[await_pos:].lstrip()
    return True


def _fix_regular_call(line: str, line_num: int, lines: list[str]) -> bool:
    """Add an assignment for standard call expressions if needed."""
    stripped_line = line.strip()
    if not stripped_line or stripped_line.startswith("#"):
        return False

    tokens = stripped_line.split()
    if not tokens:
        return False

    first_token = tokens[0]
    skip_control_flow = first_token in {
        "if",
        "elif",
        "while",
        "for",
        "return",
        "yield",
        "raise",
        "assert",
    }
    not_assignment = "=" not in first_token

    if not skip_control_flow and not_assignment and re.search(r"\w+\([^)]*\)", stripped_line):
        indent = len(line) - len(line.lstrip())
        lines[line_num - 1] = " " * indent + "_ = " + stripped_line + "\n"
        return True

    return False


def fix_unused_call_result(file_path: Path, line_num: int) -> bool:
    """Fix unused call result by adding '_ = ' prefix.

    Returns True if fix was applied, False otherwise.
    """
    applied_fix = False
    try:
        with file_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return False

    if line_num < 1 or line_num > len(lines):
        return False

    line = lines[line_num - 1]
    stripped = line.lstrip()

    # Skip if already has '_ = ' prefix or is a comment/empty line
    if stripped.startswith(("_ = ", "_= ", "#")) or not stripped.strip():
        return False

    applied_fix = _fix_await_call(lines, line_num)

    if not applied_fix:
        applied_fix = _fix_regular_call(line, line_num, lines)

    if applied_fix:
        with file_path.open("w", encoding="utf-8") as f:
            f.writelines(lines)

    return applied_fix


def main():
    """Run unused-call-result fixer."""
    repo_root = Path(__file__).parent.parent

    output = get_pyright_output(repo_root)

    unused_results = parse_unused_call_results(output)

    if not unused_results:
        return

    # Group by file for efficiency
    by_file: dict[Path, list[UnusedCallResult]] = {}
    for result in unused_results:
        if result.file_path not in by_file:
            by_file[result.file_path] = []
        by_file[result.file_path].append(result)

    # Fix each file
    fixed_count = 0
    for _file_path, results in sorted(by_file.items()):
        # Sort by line number (descending) to avoid line number shifts
        for result in sorted(results, key=lambda x: x.line_num, reverse=True):
            if fix_unused_call_result(result.file_path, result.line_num):
                fixed_count += 1


if __name__ == "__main__":
    main()
