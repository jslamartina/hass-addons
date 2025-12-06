"""Typed stubs for validate_edit_context module."""

class EditContextValidator:
    """Validates edit_file context by comparing against actual file content."""

    def __init__(self, file_path: str) -> None: ...
    def validate_context(
        self, context: str, start_line: int | None = None
    ) -> tuple[bool, str]: ...
    def validate_with_context_lines(
        self,
        old_string: str,
        start_line: int,
        context_before: int = ...,
        context_after: int = ...,
    ) -> tuple[bool, str]: ...
    def byte_diff_report(self, old_string: str, file_extraction: str) -> str: ...
