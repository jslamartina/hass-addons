#!/usr/bin/env python3
import re
from collections import defaultdict


def main():
    lint_file = "lint_output.txt"

    counts = defaultdict(int)
    categories = defaultdict(lambda: defaultdict(int))

    current_linter = "Unknown"

    try:
        with open(lint_file, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"File {lint_file} not found.")
        return

    for line in lines:
        line = line.strip()

        if "=== Running Ruff" in line:
            current_linter = "Ruff"
        elif "=== Running type checker" in line:
            current_linter = "Pyright"
        elif "=== Running ShellCheck" in line:
            current_linter = "ShellCheck"
        elif "=== Running ESLint" in line:
            current_linter = "ESLint"
        elif "=== Running markdownlint" in line:
            current_linter = "Markdownlint"
        elif "=== Running Prettier" in line:
            current_linter = "Prettier"

        if current_linter == "Ruff":
            # Match error codes like "N802 Function name..." or "F841 Local variable..."
            # Regex for ANSI codes is annoying, assume stripped or handle roughly
            # \x1b\[[0-9;]*m is the ANSI escape code pattern
            clean_line = re.sub(r"\x1b\[[0-9;]*m", "", line)
            match = re.search(r"^([A-Z]+[0-9]+)\s+(.*)", clean_line)
            if match:
                code = match.group(1)
                categories["Ruff"][code] += 1
                counts["Ruff"] += 1

        elif current_linter == "Pyright":
            clean_line = re.sub(r"\x1b\[[0-9;]*m", "", line)
            # Matches "... - error: Message (ruleName)" or "... - warning: Message (ruleName)"
            match = re.search(r" - (error|warning): .* \((.*)\)$", clean_line)
            if match:
                rule = match.group(2)
                categories["Pyright"][rule] += 1
                counts["Pyright"] += 1

    print("Error Analysis Summary")
    print("======================")

    total_errors = 0
    for linter, count in counts.items():
        print(f"\n{linter}: {count} issues")
        total_errors += count
        # Sort by count descending
        sorted_rules = sorted(
            categories[linter].items(), key=lambda x: x[1], reverse=True
        )
        for rule, rule_count in sorted_rules:
            print(f"  - {rule}: {rule_count}")

    print(f"\nTotal Issues: {total_errors}")


if __name__ == "__main__":
    main()
