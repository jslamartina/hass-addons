#!/usr/bin/env python3
"""Transform shellcheck output for VS Code problem matcher.

Reads shellcheck output from stdin, transforms it to the format expected by
the VS Code problem matcher: file:line:column: message
"""

import re
import subprocess

# ANSI escape sequence pattern
ANSI_PATTERN = re.compile(r'\x1b\[[0-9;]*m')

# Pattern to match shellcheck gcc format: file:line:column: severity: message
SHELLCHECK_PATTERN = re.compile(
    r'^([^:]+):(\d+):(\d+):\s+(error|warning|note|info):\s+(.+)$'
)

# Severity mapping: shellcheck -> VS Code severity integer
# 0 = error, 1 = warning, 2 = info
SEVERITY_MAP = {
    'error': 0,
    'warning': 1,
    'note': 2,
    'info': 2,
}


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return ANSI_PATTERN.sub('', text)


def transform_shellcheck_line(line: str) -> str | None:
    """Transform a shellcheck output line to VS Code problem matcher format.

    Input format (gcc): file:line:column: severity: message
    Output format: file:line:column: message (with severity prefix)
    """
    line = strip_ansi(line.strip())

    # Match shellcheck gcc format
    match = SHELLCHECK_PATTERN.match(line)
    if not match:
        return None

    file_path, line_num, column_num, severity, message = match.groups()

    # Format: file:line:column: message
    # Include severity in message for visibility, but use default severity in matcher
    severity_label = severity.upper()
    return f"{file_path}:{line_num}:{column_num}: [{severity_label}] {message}"


def main():
    """Main entry point."""
    # Run shellcheck
    try:
        # Get shell files from git
        git_result = subprocess.run(
            ['git', 'ls-files', '*.sh'],
            capture_output=True,
            text=True,
            check=False
        )

        if not git_result.stdout.strip():
            # No shell files found
            return

        shell_files = git_result.stdout.strip().split('\n')

        # Run shellcheck on all files
        result = subprocess.run(
            ['shellcheck', '--severity=info', '--format=gcc'] + shell_files,
            capture_output=True,
            text=True,
            check=False  # Don't fail on linting errors
        )
        output = result.stdout + result.stderr
    except FileNotFoundError:
        # shellcheck not installed
        return
    except Exception:
        # If shellcheck fails, return empty output
        return

    # Process each line
    for line in output.splitlines():
        transformed = transform_shellcheck_line(line)
        if transformed:
            print(transformed, flush=True)


if __name__ == '__main__':
    main()

