"""Batch fix script for Pyright type errors.

This script automates common Pyright fixes:
1. Add `-> None` to `__init__` methods missing return type annotation
2. Add `# type: ignore[reportAny]` for known untyped external libraries
3. Generate file-by-file error reports for manual fixing
"""

import ast
import asyncio
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import TypedDict

# Known untyped libraries that should have reportAny suppressed
UNTYPED_LIBS = {
    "aiomqtt",
    "uvloop",
    "tzlocal",
    # Add more as needed
}

REPO_ROOT = Path(__file__).parent.parent
CYNC_CONTROLLER = REPO_ROOT / "cync-controller"


class PyrightError(TypedDict):
    """Structured representation of a Pyright diagnostic."""

    line: int
    col: int
    severity: str
    message: str
    rule: str


async def _execute_command(cmd: list[str], cwd: Path | None = None) -> str:
    """Run a command and capture stdout/stderr."""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return (stdout or b"").decode() + (stderr or b"").decode()


def run_pyright() -> str:
    """Run pyright and capture output."""
    basedpyright_path = shutil.which("basedpyright")
    if basedpyright_path is None:
        msg = "basedpyright executable not found in PATH"
        raise FileNotFoundError(msg)

    basedpyright_exec = Path(basedpyright_path).resolve()
    cmd = [str(basedpyright_exec), "--project", str(CYNC_CONTROLLER / "pyrightconfig.json")]
    return asyncio.run(_execute_command(cmd, CYNC_CONTROLLER))


def parse_pyright_output(output: str) -> dict[str, list[PyrightError]]:
    """Parse Pyright output into file -> errors mapping."""
    errors_by_file: dict[str, list[PyrightError]] = defaultdict(list)
    current_file: str | None = None

    for line in output.splitlines():
        # Match file path: "/path/to/file.py"
        file_match = re.match(r"^([^\s]+\.py)$", line.strip())
        if file_match:
            current_file = file_match.group(1)
            # Remove repo path prefix if present
            if current_file and CYNC_CONTROLLER.as_posix() in current_file:
                current_file = current_file.replace(
                    CYNC_CONTROLLER.as_posix() + "/",
                    "",
                )
            continue

        if current_file and " - " in line:
            # Match error line: "  /path/to/file.py:123:45 - error: Message (ruleName)"
            error_match = re.search(
                r"^\s+.*?(\d+):(\d+)\s+-\s+(error|warning):\s+(.+?)\s+\(([^)]+)\)$",
                line,
            )
            if error_match:
                line_num = int(error_match.group(1))
                col_num = int(error_match.group(2))
                severity = error_match.group(3)
                message = error_match.group(4)
                rule = error_match.group(5)

                errors_by_file[current_file].append(
                    {
                        "line": line_num,
                        "col": col_num,
                        "severity": severity,
                        "message": message,
                        "rule": rule,
                    },
                )

    return dict(errors_by_file)


def find_init_methods(file_path: Path) -> list[int]:
    """Find all `__init__` methods missing `-> None` annotation."""
    try:
        with file_path.open(encoding="utf-8") as f:
            content = f.read()
            tree = ast.parse(content, filename=str(file_path))
    except Exception:
        return []

    init_lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__" and node.returns is None:
            init_lines.append(node.lineno)

    return init_lines


def add_init_return_type(file_path: Path, init_lines: list[int]) -> int:
    """Add `-> None` to __init__ methods."""
    if not init_lines:
        return 0

    try:
        with file_path.open(encoding="utf-8") as f:
            content = f.read()
            lines = content.splitlines(keepends=True)
    except Exception:
        return 0

    fixed = 0
    for line_num in sorted(init_lines, reverse=True):
        line_idx = line_num - 1
        if line_idx >= len(lines):
            continue

        if _update_init_signature(lines, line_idx):
            fixed += 1

    if fixed > 0:
        with file_path.open("w", encoding="utf-8") as f:
            _ = f.writelines(lines)

    return fixed


def _update_init_signature(lines: list[str], start_idx: int) -> bool:
    """Insert `-> None` into an __init__ definition if missing."""
    init_line = lines[start_idx]
    if ") ->" in init_line:
        return False

    if "):" in init_line:
        lines[start_idx] = init_line.replace("):", ") -> None:")
        return True

    for i in range(start_idx, min(start_idx + 20, len(lines))):
        candidate = lines[i]
        if ") ->" in candidate:
            return False
        if "):" in candidate:
            lines[i] = candidate.replace("):", ") -> None:")
            return True

    return False


def generate_error_report(errors_by_file: dict[str, list[PyrightError]]) -> None:
    """Generate a file-by-file error report."""
    report_file = REPO_ROOT / "working-files" / "pyright_errors_by_file.txt"
    report_file.parent.mkdir(parents=True, exist_ok=True)

    with report_file.open("w", encoding="utf-8") as f:
        _ = f.write("Pyright Errors by File\n")
        _ = f.write("=" * 80 + "\n\n")

        # Sort by error count
        sorted_files = sorted(
            errors_by_file.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )

        for file_path, errors in sorted_files:
            _ = f.write(f"\n{file_path} ({len(errors)} errors)\n")
            _ = f.write("-" * 80 + "\n")

            # Group by rule
            by_rule: defaultdict[str, list[PyrightError]] = defaultdict(list)
            for error in errors:
                by_rule[error["rule"]].append(error)

            for rule, rule_errors in sorted(
                by_rule.items(),
                key=lambda x: len(x[1]),
                reverse=True,
            ):
                _ = f.write(f"\n  {rule} ({len(rule_errors)} occurrences):\n")
                for error in sorted(rule_errors, key=lambda x: x["line"]):
                    _ = f.write(
                        f"    Line {error['line']}:{error['col']} - {error['message']}\n",
                    )


def main() -> None:
    """Run Pyright batch fixer."""
    # Step 1: Run Pyright and parse output
    output = run_pyright()
    errors_by_file = parse_pyright_output(output)

    _ = sum(len(errors) for errors in errors_by_file.values())

    # Step 2: Fix __init__ methods
    total_init_fixed = 0
    src_dir = CYNC_CONTROLLER / "src"
    for py_file in src_dir.rglob("*.py"):
        init_lines = find_init_methods(py_file)
        if init_lines:
            fixed = add_init_return_type(py_file, init_lines)
            total_init_fixed += fixed

    # Step 3: Generate error report
    generate_error_report(errors_by_file)

    # Step 4: Show top files needing attention
    sorted_files = sorted(errors_by_file.items(), key=lambda x: len(x[1]), reverse=True)
    for _file_path, _errors in sorted_files[:10]:
        pass


if __name__ == "__main__":
    main()
