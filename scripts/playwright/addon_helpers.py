"""
Playwright Helper Functions for Add-on Testing

Python utilities for Supervisor API interactions, Docker operations, and log parsing.
These helpers work with pytest-playwright and enable comprehensive e2e testing.
"""

import json
import subprocess
import time
from typing import Any


def get_supervisor_token() -> str:
    """
    Get Supervisor API token from hassio_cli container.

    Returns:
        Supervisor token string

    Raises:
        RuntimeError: If token cannot be retrieved
    """
    try:
        result = subprocess.run(
            ["docker", "exec", "hassio_cli", "env"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )

        for line in result.stdout.splitlines():
            if line.startswith("SUPERVISOR_TOKEN="):
                token = line.split("=", 1)[1].strip()
                if token:
                    return token

        raise RuntimeError("SUPERVISOR_TOKEN not found in hassio_cli environment")

    except subprocess.CalledProcessError as e:
        msg = f"Failed to get supervisor token: {e}"
        raise RuntimeError(msg) from e


def get_addon_config(addon_slug: str) -> dict[str, Any]:
    """
    Get current add-on configuration via Supervisor API.

    Args:
        addon_slug: Add-on slug (e.g., "local_cync-controller")

    Returns:
        Dictionary containing add-on configuration options
    """
    token = get_supervisor_token()

    result = subprocess.run(
        [
            "docker",
            "exec",
            "hassio_cli",
            "curl",
            "-sSL",
            "-H",
            f"Authorization: Bearer {token}",
            f"http://supervisor/addons/{addon_slug}/info",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    data = json.loads(result.stdout)
    return data.get("data", {}).get("options", {})


def update_addon_config(addon_slug: str, config: dict[str, Any]) -> bool:
    """
    Update add-on configuration via Supervisor API.

    Args:
        addon_slug: Add-on slug
        config: Complete configuration dictionary to apply

    Returns:
        True if successful, False otherwise
    """
    token = get_supervisor_token()
    config_json = json.dumps({"options": config})

    result = subprocess.run(
        [
            "docker",
            "exec",
            "hassio_cli",
            "curl",
            "-sSL",
            "-w",
            "\n%{http_code}",
            "-X",
            "POST",
            "-H",
            f"Authorization: Bearer {token}",
            "-H",
            "Content-Type: application/json",
            "-d",
            config_json,
            f"http://supervisor/addons/{addon_slug}/options",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    lines = result.stdout.strip().splitlines()
    http_code = int(lines[-1]) if lines else 0

    return http_code == 200


def update_debug_log_level(addon_slug: str, enabled: bool) -> bool:
    """
    Toggle debug_log_level configuration option.

    Args:
        addon_slug: Add-on slug
        enabled: True to enable debug logging, False for production mode

    Returns:
        True if successful
    """
    current_config = get_addon_config(addon_slug)
    current_config["debug_log_level"] = enabled
    return update_addon_config(addon_slug, current_config)


def restart_addon(addon_slug: str) -> bool:
    """
    Restart add-on via Supervisor API.

    Args:
        addon_slug: Add-on slug

    Returns:
        True if restart initiated successfully
    """
    token = get_supervisor_token()

    result = subprocess.run(
        [
            "docker",
            "exec",
            "hassio_cli",
            "curl",
            "-sSL",
            "-w",
            "\n%{http_code}",
            "-X",
            "POST",
            "-H",
            f"Authorization: Bearer {token}",
            f"http://supervisor/addons/{addon_slug}/restart",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    lines = result.stdout.strip().splitlines()
    http_code = int(lines[-1]) if lines else 0

    return http_code == 200


def restart_addon_and_wait(addon_slug: str, wait_seconds: int = 5) -> None:
    """
    Restart add-on and wait for it to start up.

    Args:
        addon_slug: Add-on slug
        wait_seconds: Seconds to wait after restart (default: 5)
    """
    if not restart_addon(addon_slug):
        msg = f"Failed to restart add-on: {addon_slug}"
        raise RuntimeError(msg)

    print(f"✓ Add-on restart initiated, waiting {wait_seconds}s for startup...")
    time.sleep(wait_seconds)


def get_addon_status(addon_slug: str) -> dict[str, Any]:
    """
    Get add-on status information via Supervisor API.

    Args:
        addon_slug: Add-on slug

    Returns:
        Dictionary with status info (state, version, etc.)
    """
    token = get_supervisor_token()

    result = subprocess.run(
        [
            "docker",
            "exec",
            "hassio_cli",
            "curl",
            "-sSL",
            "-H",
            f"Authorization: Bearer {token}",
            f"http://supervisor/addons/{addon_slug}/info",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    data = json.loads(result.stdout)
    return data.get("data", {})


def read_json_logs(addon_slug: str, lines: int = 100) -> list[dict[str, Any]]:
    """
    Read JSON logs from add-on container.

    Args:
        addon_slug: Add-on slug
        lines: Number of lines to read from end of log file

    Returns:
        List of log entry dictionaries
    """
    # Container name uses hyphens: "addon_local_cync-controller"
    container_name = f"addon_{addon_slug}"
    log_file = "/var/log/cync_controller.json"

    result = subprocess.run(
        ["docker", "exec", container_name, "tail", f"-{lines}", log_file],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    if result.returncode != 0:
        print(f"Warning: Could not read JSON logs: {result.stderr}")
        return []

    logs = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            logs.append(json.loads(line))
        except json.JSONDecodeError:
            # Skip malformed lines
            continue

    return logs


def read_human_logs(addon_slug: str, lines: int = 100) -> str:
    """
    Read human-readable logs via ha CLI.

    Args:
        addon_slug: Add-on slug
        lines: Number of lines to retrieve (approximate)

    Returns:
        Log output as string
    """
    result = subprocess.run(
        ["ha", "addons", "logs", addon_slug],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    if result.returncode != 0:
        msg = f"Failed to read logs: {result.stderr}"
        raise RuntimeError(msg)

    # Return last N lines
    all_lines = result.stdout.splitlines()
    return "\n".join(all_lines[-lines:])


def get_log_levels_from_json(logs: list[dict[str, Any]]) -> set[str]:
    """
    Extract unique log levels from parsed JSON logs.

    Args:
        logs: List of log entry dictionaries

    Returns:
        Set of log level strings (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    levels = set()
    for entry in logs:
        if "level" in entry:
            levels.add(entry["level"])
    return levels


def count_log_levels(logs: list[dict[str, Any]]) -> dict[str, int]:
    """
    Count occurrences of each log level.

    Args:
        logs: List of log entry dictionaries

    Returns:
        Dictionary mapping log level to count
    """
    counts = {}
    for entry in logs:
        if "level" in entry:
            level = entry["level"]
            counts[level] = counts.get(level, 0) + 1
    return counts


def filter_logs_by_level(logs: list[dict[str, Any]], level: str) -> list[dict[str, Any]]:
    """
    Filter logs to only entries of a specific level.

    Args:
        logs: List of log entry dictionaries
        level: Log level to filter for (e.g., "DEBUG", "ERROR")

    Returns:
        Filtered list of log entries
    """
    return [entry for entry in logs if entry.get("level") == level]


def filter_logs_by_logger(logs: list[dict[str, Any]], logger_name: str) -> list[dict[str, Any]]:
    """
    Filter logs to only entries from a specific logger.

    Args:
        logs: List of log entry dictionaries
        logger_name: Logger name to filter for

    Returns:
        Filtered list of log entries
    """
    return [entry for entry in logs if entry.get("logger") == logger_name]


def apply_addon_preset(
    preset_name: str, addon_slug: str = "local_cync-controller"
) -> bool:
    """
    Apply a configuration preset by updating config directly.

    Args:
        preset_name: Preset name (e.g., "preset-baseline", "preset-relay-debug")
        addon_slug: Add-on slug

    Returns:
        True if successful
    """
    current_config = get_addon_config(addon_slug)

    # Define presets
    presets = {
        "preset-baseline": {
            "cloud_relay": {
                "enabled": False,
                "forward_to_cloud": True,
                "debug_packet_logging": False,
            }
        },
        "preset-relay-with-forward": {
            "cloud_relay": {
                "enabled": True,
                "forward_to_cloud": True,
                "debug_packet_logging": False,
            }
        },
        "preset-relay-debug": {
            "cloud_relay": {
                "enabled": True,
                "forward_to_cloud": True,
                "debug_packet_logging": True,
            }
        },
        "preset-lan-only": {
            "cloud_relay": {
                "enabled": True,
                "forward_to_cloud": False,
                "debug_packet_logging": False,
            }
        },
    }

    if preset_name not in presets:
        print(f"✗ Unknown preset: {preset_name}")
        return False

    # Merge preset into current config
    config_updates = presets[preset_name]
    for key, value in config_updates.items():
        if key in current_config:
            if isinstance(value, dict):
                current_config[key].update(value)
            else:
                current_config[key] = value
        else:
            current_config[key] = value

    # Update config
    success = update_addon_config(addon_slug, current_config)
    if success:
        print(f"✓ Applied preset: {preset_name}")
    else:
        print(f"✗ Failed to apply preset: {preset_name}")
    return success


def stop_addon(addon_slug: str) -> bool:
    """
    Stop add-on via ha CLI.

    Args:
        addon_slug: Add-on slug

    Returns:
        True if stop initiated successfully
    """
    result = subprocess.run(
        ["docker", "exec", "hassio_cli", "ha", "addons", "stop", addon_slug],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    if result.returncode != 0:
        print(
            f"stop_addon failed for {addon_slug}: returncode={result.returncode}, stdout={result.stdout}, stderr={result.stderr}"
        )

    return result.returncode == 0


def start_addon(addon_slug: str) -> bool:
    """
    Start add-on via ha CLI (non-blocking).

    Args:
        addon_slug: Add-on slug

    Returns:
        True if start initiated successfully
    """
    # Start the process and don't wait for completion since EMQX takes a while to start
    process = subprocess.Popen(
        ["docker", "exec", "hassio_cli", "ha", "addons", "start", addon_slug],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Give it a moment to initiate
    time.sleep(0.5)

    # Return true immediately if process is still running (start initiated successfully)
    # If it already exited, check the return code
    if process.poll() is None:
        return True
    else:
        return process.returncode == 0
