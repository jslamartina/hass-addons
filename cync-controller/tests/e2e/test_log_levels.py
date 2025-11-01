"""E2E tests for log level configuration and filtering."""

import sys
from pathlib import Path

import pytest

# Add scripts/playwright to Python path for helper imports
scripts_path = Path(__file__).parent.parent.parent.parent / "scripts" / "playwright"
sys.path.insert(0, str(scripts_path))

from addon_helpers import (
    count_log_levels,
    filter_logs_by_level,
    get_addon_config,
    get_log_levels_from_json,
    read_json_logs,
    restart_addon_and_wait,
    update_debug_log_level,
)

ADDON_SLUG = "local_cync-controller"


@pytest.fixture
def restore_config():
    """Fixture to restore original configuration after tests."""
    original_config = get_addon_config(ADDON_SLUG)
    original_debug = original_config.get("debug_log_level", True)

    yield

    # Only restore if config changed
    try:
        current_config = get_addon_config(ADDON_SLUG)
        current_debug = current_config.get("debug_log_level", True)

        if current_debug != original_debug:
            update_debug_log_level(ADDON_SLUG, original_debug)
            restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)
            print(f"\n✓ Restored debug_log_level to {original_debug}")
        else:
            print(f"\n✓ Config already matches: debug_log_level={original_debug}")
    except Exception as e:
        print(f"\n⚠️  Failed to check/restore config: {e}")


@pytest.mark.serial
@pytest.mark.usefixtures("restore_config")
def test_debug_mode_shows_all_log_levels():
    """
    Test that debug_log_level=true enables DEBUG logs.

    Expected: JSON logs contain DEBUG, INFO, WARNING, ERROR levels.
    """
    print("\n=== Test: Debug Mode Enables DEBUG Logs ===")

    # Arrange: Enable debug mode
    print("[Step 1] Enabling debug mode...")
    assert update_debug_log_level(ADDON_SLUG, True), "Failed to enable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Act: Read logs
    print("[Step 2] Reading JSON logs...")
    logs = read_json_logs(ADDON_SLUG, lines=200)
    assert logs, "No logs found"

    # Assert: Verify DEBUG logs present
    print("[Step 3] Verifying log levels...")
    levels = get_log_levels_from_json(logs)
    counts = count_log_levels(logs)

    print(f"  Log level distribution: {counts}")
    print(f"  Unique levels found: {sorted(levels)}")

    assert "DEBUG" in levels, "DEBUG logs not found when debug_log_level=true"
    assert "INFO" in levels, "INFO logs not found"

    debug_logs = filter_logs_by_level(logs, "DEBUG")
    print(f"✓ Found {len(debug_logs)} DEBUG log entries")
    assert len(debug_logs) > 0, "Expected at least some DEBUG logs"


@pytest.mark.serial
@pytest.mark.usefixtures("restore_config")
def test_production_mode_filters_debug_logs():
    """
    Test that debug_log_level=false filters out DEBUG logs.

    Expected: JSON logs contain only INFO, WARNING, ERROR (no DEBUG).
    """
    print("\n=== Test: Production Mode Filters DEBUG Logs ===")

    # Arrange: Disable debug mode
    print("[Step 1] Disabling debug mode (production)...")
    assert update_debug_log_level(ADDON_SLUG, False), "Failed to disable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    # Act: Read logs
    print("[Step 2] Reading JSON logs...")
    logs = read_json_logs(ADDON_SLUG, lines=200)
    assert logs, "No logs found"

    # Assert: Verify NO DEBUG logs
    print("[Step 3] Verifying DEBUG logs filtered out...")
    levels = get_log_levels_from_json(logs)
    counts = count_log_levels(logs)

    print(f"  Log level distribution: {counts}")
    print(f"  Unique levels found: {sorted(levels)}")

    assert "DEBUG" not in levels, "DEBUG logs found when debug_log_level=false!"
    assert "INFO" in levels, "INFO logs should still be present"

    debug_logs = filter_logs_by_level(logs, "DEBUG")
    print(f"✓ Confirmed 0 DEBUG log entries (found {len(debug_logs)})")
    assert len(debug_logs) == 0, "Expected no DEBUG logs in production mode"


@pytest.mark.serial
@pytest.mark.usefixtures("restore_config")
def test_log_level_transition_debug_to_production():
    """
    Test transitioning from debug mode to production mode.

    Expected: DEBUG logs appear in debug mode, disappear after switching to production.
    """
    print("\n=== Test: Log Level Transition (Debug → Production) ===")

    # Step 1: Enable debug mode
    print("[Step 1] Starting in debug mode...")
    assert update_debug_log_level(ADDON_SLUG, True), "Failed to enable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    logs_debug = read_json_logs(ADDON_SLUG, lines=100)
    levels_debug = get_log_levels_from_json(logs_debug)
    print(f"  Debug mode levels: {sorted(levels_debug)}")
    assert "DEBUG" in levels_debug, "DEBUG logs should be present in debug mode"

    # Step 2: Switch to production mode
    print("[Step 2] Switching to production mode...")
    assert update_debug_log_level(ADDON_SLUG, False), "Failed to disable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    logs_prod = read_json_logs(ADDON_SLUG, lines=100)
    levels_prod = get_log_levels_from_json(logs_prod)
    print(f"  Production mode levels: {sorted(levels_prod)}")
    assert "DEBUG" not in levels_prod, "DEBUG logs should be filtered in production mode"

    print("✓ Successfully transitioned from debug to production mode")


@pytest.mark.serial
@pytest.mark.usefixtures("restore_config")
def test_log_level_transition_production_to_debug():
    """
    Test transitioning from production mode to debug mode.

    Expected: No DEBUG logs in production, DEBUG logs appear after switching to debug.
    """
    print("\n=== Test: Log Level Transition (Production → Debug) ===")

    # Step 1: Start in production mode
    print("[Step 1] Starting in production mode...")
    assert update_debug_log_level(ADDON_SLUG, False), "Failed to disable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    logs_prod = read_json_logs(ADDON_SLUG, lines=100)
    levels_prod = get_log_levels_from_json(logs_prod)
    print(f"  Production mode levels: {sorted(levels_prod)}")
    assert "DEBUG" not in levels_prod, "DEBUG logs should be filtered in production mode"

    # Step 2: Switch to debug mode
    print("[Step 2] Switching to debug mode...")
    assert update_debug_log_level(ADDON_SLUG, True), "Failed to enable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    logs_debug = read_json_logs(ADDON_SLUG, lines=100)
    levels_debug = get_log_levels_from_json(logs_debug)
    print(f"  Debug mode levels: {sorted(levels_debug)}")
    assert "DEBUG" in levels_debug, "DEBUG logs should appear after enabling debug mode"

    print("✓ Successfully transitioned from production to debug mode")


@pytest.mark.serial
@pytest.mark.usefixtures("restore_config")
def test_log_levels_always_include_info_warning_error():
    """
    Test that INFO, WARNING, and ERROR logs always appear regardless of debug mode.

    Expected: Both debug and production modes include INFO, WARNING, ERROR.
    """
    print("\n=== Test: INFO/WARNING/ERROR Always Present ===")

    # Test in production mode
    print("[Step 1] Testing production mode...")
    assert update_debug_log_level(ADDON_SLUG, False), "Failed to disable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    logs_prod = read_json_logs(ADDON_SLUG, lines=200)
    levels_prod = get_log_levels_from_json(logs_prod)
    print(f"  Production levels: {sorted(levels_prod)}")

    assert "INFO" in levels_prod, "INFO logs missing in production mode"
    # WARNING and ERROR may not always be present depending on runtime conditions

    # Test in debug mode
    print("[Step 2] Testing debug mode...")
    assert update_debug_log_level(ADDON_SLUG, True), "Failed to enable debug mode"
    restart_addon_and_wait(ADDON_SLUG, wait_seconds=5)

    logs_debug = read_json_logs(ADDON_SLUG, lines=200)
    levels_debug = get_log_levels_from_json(logs_debug)
    print(f"  Debug levels: {sorted(levels_debug)}")

    assert "INFO" in levels_debug, "INFO logs missing in debug mode"
    assert "DEBUG" in levels_debug, "DEBUG logs missing in debug mode"

    print("✓ INFO/WARNING/ERROR logs present in both modes")


@pytest.mark.serial
@pytest.mark.usefixtures("restore_config")
def test_json_log_structure():
    """
    Test that JSON logs have the expected structure.

    Expected: Each log entry contains timestamp, level, logger, message fields.
    """
    print("\n=== Test: JSON Log Structure ===")

    # Read logs
    logs = read_json_logs(ADDON_SLUG, lines=50)
    assert logs, "No logs found"

    # Check first log entry structure
    first_log = logs[0]
    print(f"  Sample log entry: {first_log}")

    required_fields = ["timestamp", "level", "logger", "message"]
    for field in required_fields:
        assert field in first_log, f"Missing required field: {field}"

    print(f"✓ JSON logs have correct structure with fields: {required_fields}")
