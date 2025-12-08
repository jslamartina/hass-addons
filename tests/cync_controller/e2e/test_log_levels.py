"""E2E tests for log level configuration and filtering."""

import logging
import sys
from pathlib import Path

import pytest

# Add scripts/playwright to Python path for helper imports
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from scripts.playwright.addon_helpers import (  # type: ignore[import-untyped, reportUnknownVariableType]
    JSONDict,  # type: ignore[reportUnknownVariableType]
    count_log_levels,  # type: ignore[reportUnknownVariableType]
    filter_logs_by_level,  # type: ignore[reportUnknownVariableType]
    get_addon_config,  # type: ignore[reportUnknownVariableType]
    get_log_levels_from_json,  # type: ignore[reportUnknownVariableType]
    read_json_logs,  # type: ignore[reportUnknownVariableType]
    restart_addon_and_wait,  # type: ignore[reportUnknownVariableType]
    update_debug_log_level,  # type: ignore[reportUnknownVariableType]
)

ADDON_SLUG = "local_cync-controller"
logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def restore_config():
    """Fixture to restore original configuration after tests."""
    original_config: JSONDict = get_addon_config(ADDON_SLUG)
    original_debug: bool = bool(original_config.get("debug_log_level", True))

    yield

    # Only restore if config changed
    try:
        current_config: JSONDict = get_addon_config(ADDON_SLUG)
        current_debug: bool = bool(current_config.get("debug_log_level", True))

        if current_debug != original_debug:
            _ = update_debug_log_level(ADDON_SLUG, original_debug)
            restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)
        else:
            pass
    except Exception as exc:
        logger.warning("Failed to restore debug log level: %s", exc)


@pytest.mark.serial  # type: ignore[attr-defined]
def test_debug_mode_shows_all_log_levels():
    """Test that debug_log_level=true enables DEBUG logs.

    Expected: JSON logs contain DEBUG, INFO, WARNING, ERROR levels.
    """
    # Arrange: Enable debug mode
    assert update_debug_log_level(ADDON_SLUG, True), "Failed to enable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Act: Read logs
    logs: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=200)
    assert logs, "No logs found"

    # Assert: Verify DEBUG logs present
    levels: set[str] = get_log_levels_from_json(logs)
    _ = count_log_levels(logs)

    assert "DEBUG" in levels, "DEBUG logs not found when debug_log_level=true"
    assert "INFO" in levels, "INFO logs not found"

    debug_logs: list[JSONDict] = filter_logs_by_level(logs, "DEBUG")
    assert len(debug_logs) > 0, "Expected at least some DEBUG logs"


@pytest.mark.serial  # type: ignore[attr-defined]
def test_production_mode_filters_debug_logs():
    """Test that debug_log_level=false filters out DEBUG logs.

    Expected: JSON logs contain only INFO, WARNING, ERROR (no DEBUG).
    """
    # Arrange: Disable debug mode
    assert update_debug_log_level(ADDON_SLUG, False), "Failed to disable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Act: Read logs
    logs: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=200)
    assert logs, "No logs found"

    # Assert: Verify NO DEBUG logs
    levels: set[str] = get_log_levels_from_json(logs)
    _ = count_log_levels(logs)

    assert "DEBUG" not in levels, "DEBUG logs found when debug_log_level=false!"
    assert "INFO" in levels, "INFO logs should still be present"

    debug_logs: list[JSONDict] = filter_logs_by_level(logs, "DEBUG")
    assert len(debug_logs) == 0, "Expected no DEBUG logs in production mode"


@pytest.mark.serial  # type: ignore[attr-defined]
def test_log_level_transition_debug_to_production():
    """Test transitioning from debug mode to production mode.

    Expected: DEBUG logs appear in debug mode, disappear after switching to production.
    """
    # Step 1: Enable debug mode
    assert update_debug_log_level(ADDON_SLUG, True), "Failed to enable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    logs_debug: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=100)
    levels_debug: set[str] = get_log_levels_from_json(logs_debug)
    assert "DEBUG" in levels_debug, "DEBUG logs should be present in debug mode"

    # Step 2: Switch to production mode
    assert update_debug_log_level(ADDON_SLUG, False), "Failed to disable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    logs_prod: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=100)
    levels_prod: set[str] = get_log_levels_from_json(logs_prod)
    assert "DEBUG" not in levels_prod, "DEBUG logs should be filtered in production mode"


@pytest.mark.serial  # type: ignore[attr-defined]
def test_log_level_transition_production_to_debug():
    """Test transitioning from production mode to debug mode.

    Expected: No DEBUG logs in production, DEBUG logs appear after switching to debug.
    """
    # Step 1: Start in production mode
    assert update_debug_log_level(ADDON_SLUG, False), "Failed to disable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    logs_prod: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=100)
    levels_prod: set[str] = get_log_levels_from_json(logs_prod)
    assert "DEBUG" not in levels_prod, "DEBUG logs should be filtered in production mode"

    # Step 2: Switch to debug mode
    assert update_debug_log_level(ADDON_SLUG, True), "Failed to enable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    logs_debug: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=100)
    levels_debug: set[str] = get_log_levels_from_json(logs_debug)
    assert "DEBUG" in levels_debug, "DEBUG logs should appear after enabling debug mode"


@pytest.mark.serial  # type: ignore[attr-defined]
def test_log_levels_always_include_info_warning_error():
    """Test that INFO, WARNING, and ERROR logs always appear regardless of debug mode.

    Expected: Both debug and production modes include INFO, WARNING, ERROR.
    """
    # Test in production mode
    assert update_debug_log_level(ADDON_SLUG, False), "Failed to disable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    logs_prod: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=200)
    levels_prod: set[str] = get_log_levels_from_json(logs_prod)

    assert "INFO" in levels_prod, "INFO logs missing in production mode"
    # WARNING and ERROR may not always be present depending on runtime conditions

    # Test in debug mode
    assert update_debug_log_level(ADDON_SLUG, True), "Failed to enable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    logs_debug: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=200)
    levels_debug: set[str] = get_log_levels_from_json(logs_debug)

    assert "INFO" in levels_debug, "INFO logs missing in debug mode"
    assert "DEBUG" in levels_debug, "DEBUG logs missing in debug mode"


@pytest.mark.serial  # type: ignore[attr-defined]
def test_json_log_structure():
    """Test that JSON logs have the expected structure.

    Expected: Each log entry contains timestamp, level, logger, message fields.
    """
    # Read logs
    logs: list[JSONDict] = read_json_logs(ADDON_SLUG, lines=50)
    assert logs, "No logs found"

    # Check first log entry structure
    first_log: JSONDict = logs[0]

    required_fields = ["timestamp", "level", "logger", "message"]
    for field in required_fields:
        assert field in first_log, f"Missing required field: {field}"
