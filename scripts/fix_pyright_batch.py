#!/usr/bin/env python3
"""Batch fix script for Pyright type errors.

This script automates common Pyright fixes:
1. Add `-> None` to `__init__` methods missing return type annotation
2. Add `# type: ignore[reportAny]` for known untyped external libraries
3. Generate file-by-file error reports for manual fixing
"""

import ast
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

# Known untyped libraries that should have reportAny suppressed
UNTYPED_LIBS = {
    "aiomqtt",
    "uvloop",
    "tzlocal",
    # Add more as needed
}

REPO_ROOT = Path(__file__).parent.parent
CYNC_CONTROLLER = REPO_ROOT / "cync-controller"


def run_pyright() -> str:
    """Run pyright and capture output."""
    print("Running Pyright to collect errors...")
    result = subprocess.run(
        ["basedpyright", "--project", str(CYNC_CONTROLLER / "pyrightconfig.json")],
        check=False,
        cwd=str(CYNC_CONTROLLER),
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr


def parse_pyright_output(output: str) -> dict[str, list[dict[str, Any]]]:
    """Parse Pyright output into file -> errors mapping."""
    errors_by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    current_file = None

    for line in output.splitlines():
        # Match file path: "/path/to/file.py"
        file_match = re.match(r"^([^\s]+\.py)$", line.strip())
        if file_match:
            current_file = file_match.group(1)
            # Remove repo path prefix if present
            if CYNC_CONTROLLER.as_posix() in current_file:
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
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
            tree = ast.parse(content, filename=str(file_path))
    except Exception as e:
        print(f"Warning: Could not parse {file_path}: {e}")
        return []

    init_lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            # Check if it has a return annotation
            if node.returns is None:
                init_lines.append(node.lineno)

    return init_lines


def add_init_return_type(file_path: Path, init_lines: list[int]) -> int:
    """Add `-> None` to __init__ methods."""
    if not init_lines:
        return 0

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
            lines = content.splitlines(keepends=True)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return 0

    fixed = 0
    for line_num in sorted(
        init_lines,
        reverse=True,
    ):  # Process backwards to preserve line numbers
        line_idx = line_num - 1
        if line_idx >= len(lines):
            continue

        # Find the line with "def __init__" and track until we find the closing "):"
        start_idx = line_idx
        init_line = lines[start_idx]

        # Check if it's a single-line definition
        if "):" in init_line or ") ->" in init_line:
            # Single line: "def __init__(self, ...):" or "async def __init__(self, ...):"
            if ") ->" in init_line:
                continue  # Already has return type
            # Replace "):" with " -> None):"
            new_line = init_line.replace("):", ") -> None:")
            lines[start_idx] = new_line
            fixed += 1
        else:
            # Multi-line definition - find the closing "):"
            for i in range(
                start_idx,
                min(start_idx + 20, len(lines)),
            ):  # Look ahead max 20 lines
                if ") ->" in lines[i]:
                    break  # Already has return type
                if "):" in lines[i]:
                    # Found closing, insert -> None before the colon
                    lines[i] = lines[i].replace("):", ") -> None:")
                    fixed += 1
                    break

    if fixed > 0:
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"  Fixed {fixed} __init__ methods in {file_path.name}")

    return fixed


def generate_error_report(errors_by_file: dict[str, list[dict[str, Any]]]) -> None:
    """Generate a file-by-file error report."""
    report_file = REPO_ROOT / "working-files" / "pyright_errors_by_file.txt"
    report_file.parent.mkdir(parents=True, exist_ok=True)

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("Pyright Errors by File\n")
        f.write("=" * 80 + "\n\n")

        # Sort by error count
        sorted_files = sorted(
            errors_by_file.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )

        for file_path, errors in sorted_files:
            f.write(f"\n{file_path} ({len(errors)} errors)\n")
            f.write("-" * 80 + "\n")

            # Group by rule
            by_rule: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
            for error in errors:
                by_rule[error["rule"]].append(error)

            for rule, rule_errors in sorted(
                by_rule.items(),
                key=lambda x: len(x[1]),
                reverse=True,
            ):
                f.write(f"\n  {rule} ({len(rule_errors)} occurrences):\n")
                for error in sorted(rule_errors, key=lambda x: x["line"]):
                    f.write(
                        f"    Line {error['line']}:{error['col']} - {error['message']}\n",
                    )

    print(f"\nError report saved to: {report_file}")


def main() -> None:
    """Main entry point."""
    print("Pyright Batch Fix Script")
    print("=" * 80)

    # Step 1: Run Pyright and parse output
    output = run_pyright()
    errors_by_file = parse_pyright_output(output)

    total_errors = sum(len(errors) for errors in errors_by_file.values())
    print(f"\nFound {total_errors} errors across {len(errors_by_file)} files")

    # Step 2: Fix __init__ methods
    print("\nStep 1: Adding `-> None` to __init__ methods...")
    total_init_fixed = 0
    src_dir = CYNC_CONTROLLER / "src"
    for py_file in src_dir.rglob("*.py"):
        init_lines = find_init_methods(py_file)
        if init_lines:
            fixed = add_init_return_type(py_file, init_lines)
            total_init_fixed += fixed

    print(f"\nFixed {total_init_fixed} __init__ methods")

    # Step 3: Generate error report
    print("\nStep 2: Generating error report...")
    generate_error_report(errors_by_file)

    # Step 4: Show top files needing attention
    print("\nTop 10 files with most errors:")
    sorted_files = sorted(errors_by_file.items(), key=lambda x: len(x[1]), reverse=True)
    for file_path, errors in sorted_files[:10]:
        print(f"  {file_path}: {len(errors)} errors")

    print("\nDone! Review the error report and fix remaining issues manually.")


if __name__ == "__main__":
    main()
