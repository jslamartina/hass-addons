#!/usr/bin/env python3
"""Run ESLint and emit VS Code-friendly problem matcher output.

Outputs lines in the format:
  file:line:column: severity message (ruleId)

Severity is rendered as \"error\" or \"warning\" to match the tasks.json matcher.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

# Severity mapping from ESLint numeric severity to text
SEVERITY = {2: "error", 1: "warning"}


def run_eslint(fix: bool) -> str:
    """Run eslint and return stdout+stderr."""
    cmd = [
        "npx",
        "eslint",
        ".",
        "--ext",
        ".ts,.tsx",
        "--format",
        "json",
    ]
    if fix:
        cmd.append("--fix")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,  # eslint exits non-zero on findings
        )
    except FileNotFoundError:
        return ""

    return f"{proc.stdout}{proc.stderr}"


def parse_messages(eslint_output: str, cwd: Path) -> list[str]:
    """Yield lines formatted for VS Code problem matcher."""
    if not eslint_output.strip():
        return []

    try:
        results_obj = cast(object, json.loads(eslint_output))
    except json.JSONDecodeError:
        return []

    if not isinstance(results_obj, list):
        return []

    results_list = cast(list[object], results_obj)

    output: list[str] = []

    for file_result_obj in results_list:
        if not isinstance(file_result_obj, dict):
            continue

        file_result_obj_dict = cast(dict[str, object], file_result_obj)
        file_result: dict[str, object] = dict(file_result_obj_dict)

        file_path_value = file_result.get("filePath")
        file_path_str = file_path_value if isinstance(file_path_value, str) else str(file_path_value or "")
        file_path = Path(file_path_str)
        rel_path = file_path.relative_to(cwd) if file_path.is_absolute() else file_path

        messages_obj = file_result.get("messages")
        if not isinstance(messages_obj, list):
            continue
        messages_list = cast(list[object], messages_obj)

        for message_obj in messages_list:
            if not isinstance(message_obj, dict):
                continue

            message_obj_dict = cast(dict[str, object], message_obj)
            msg: dict[str, object] = dict(message_obj_dict)

            line_raw = msg.get("line", 1)
            col_raw = msg.get("column", 1)
            severity_raw = msg.get("severity", 1)
            rule_id_raw = msg.get("ruleId")
            message_text_raw = msg.get("message")

            line = int(line_raw) if isinstance(line_raw, (int, float, str)) else 1
            col = int(col_raw) if isinstance(col_raw, (int, float, str)) else 1
            severity_int = int(severity_raw) if isinstance(severity_raw, (int, float, str)) else 1
            severity = SEVERITY.get(severity_int, "warning")
            rule_id = str(rule_id_raw) if rule_id_raw is not None else "unknown"
            text = str(message_text_raw or "").strip()
            output.append(f"{rel_path}:{line}:{col}: {severity} {text} ({rule_id})")

    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="ESLint runner for VS Code tasks")
    _ = parser.add_argument("--fix", action="store_true", help="Run ESLint with --fix")
    args: argparse.Namespace = parser.parse_args()

    cwd = Path(os.getcwd())
    fix_flag: bool = bool(getattr(args, "fix", False))
    output = run_eslint(fix=fix_flag)

    for line in parse_messages(output, cwd):
        print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())

