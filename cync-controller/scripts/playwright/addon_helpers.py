"""Playwright Helper Functions for Add-on Testing.

Python utilities for Supervisor API interactions, Docker operations, and log parsing.
These helpers work with pytest-playwright and enable comprehensive e2e testing.
"""

import json
import os
import time
from functools import lru_cache
from typing import cast

import httpx
from httpx import Client

JSONDict = dict[str, object]
LogEntry = JSONDict
HTTP_OK = 200
SUPERVISOR_BASE_URL = "http://supervisor"
SUPERVISOR_TIMEOUT = 30.0


def _supervisor_headers(token: str) -> dict[str, str]:
    """Build headers for Supervisor API calls."""
    return {"Authorization": f"Bearer {token}"}


def _supervisor_request(
    method: str,
    path: str,
    token: str,
    json: object | None = None,
) -> httpx.Response:
    """Perform a Supervisor API request."""
    with Client(
        base_url=SUPERVISOR_BASE_URL,
        timeout=SUPERVISOR_TIMEOUT,
    ) as client:
        response: httpx.Response = client.request(
            method,
            path,
            headers=_supervisor_headers(token),
            json=json,
        )
    _ = response.raise_for_status()
    return response


@lru_cache(maxsize=1)
def get_supervisor_token() -> str:
    """Get Supervisor API token from environment."""
    token = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")
    if token:
        return token

    msg = "Supervisor token not found; set SUPERVISOR_TOKEN in the environment"
    raise RuntimeError(msg)


def get_addon_config(addon_slug: str) -> JSONDict:
    """Get current add-on configuration via Supervisor API.

    Args:
        addon_slug: Add-on slug (e.g., "local_cync-controller")

    Returns:
        Dictionary containing add-on configuration options

    """
    token = get_supervisor_token()

    response = _supervisor_request("GET", f"/addons/{addon_slug}/info", token)
    raw_data: object = cast(object, response.json())
    if not isinstance(raw_data, dict):
        return {}
    data: JSONDict = cast(JSONDict, raw_data)
    data_section_obj = data.get("data")
    if not isinstance(data_section_obj, dict):
        return {}
    data_section: JSONDict = cast(JSONDict, data_section_obj)
    options_val = data_section.get("options")
    if not isinstance(options_val, dict):
        return {}
    return cast(JSONDict, options_val)


def update_addon_config(addon_slug: str, config: JSONDict) -> bool:
    """Update add-on configuration via Supervisor API.

    Args:
        addon_slug: Add-on slug
        config: Complete configuration dictionary to apply

    Returns:
        True if successful, False otherwise

    """
    token = get_supervisor_token()
    try:
        response = _supervisor_request(
            "POST",
            f"/addons/{addon_slug}/options",
            token,
            json={"options": config},
        )
    except httpx.HTTPError:
        return False
    return response.status_code == HTTP_OK


def update_debug_log_level(addon_slug: str, enabled: bool) -> bool:
    """Toggle debug_log_level configuration option.

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
    """Restart add-on via Supervisor API.

    Args:
        addon_slug: Add-on slug

    Returns:
        True if restart initiated successfully

    """
    token = get_supervisor_token()
    try:
        response = _supervisor_request(
            "POST",
            f"/addons/{addon_slug}/restart",
            token,
        )
    except httpx.HTTPError:
        return False
    return response.status_code == HTTP_OK


def restart_addon_and_wait(addon_slug: str, wait_seconds: int = 5) -> None:
    """Restart add-on and wait for it to start up.

    Args:
        addon_slug: Add-on slug
        wait_seconds: Seconds to wait after restart (default: 5)

    """
    if not restart_addon(addon_slug):
        msg = f"Failed to restart add-on: {addon_slug}"
        raise RuntimeError(msg)

    time.sleep(wait_seconds)


def get_addon_status(addon_slug: str) -> JSONDict:
    """Get add-on status information via Supervisor API.

    Args:
        addon_slug: Add-on slug

    Returns:
        Dictionary with status info (state, version, etc.)

    """
    token = get_supervisor_token()
    response = _supervisor_request("GET", f"/addons/{addon_slug}/info", token)
    raw_data = cast(object, response.json())
    if not isinstance(raw_data, dict):
        return {}
    data = cast(JSONDict, raw_data)
    info = data.get("data")
    return cast(JSONDict, info) if isinstance(info, dict) else {}


def read_json_logs(addon_slug: str, lines: int = 100) -> list[LogEntry]:
    """Read JSON logs from add-on container.

    Args:
        addon_slug: Add-on slug
        lines: Number of lines to read from end of log file

    Returns:
        List of log entry dictionaries

    """
    token = get_supervisor_token()
    try:
        response = _supervisor_request(
            "GET",
            f"/addons/{addon_slug}/logs",
            token,
        )
    except httpx.HTTPError:
        return []

    logs: list[LogEntry] = []
    for raw_line in response.text.splitlines()[-lines:]:
        line = raw_line.strip()
        if not line:
            continue
        try:
            parsed = cast(object, json.loads(line))
            if isinstance(parsed, dict):
                logs.append(cast(LogEntry, parsed))
        except json.JSONDecodeError:
            # Skip malformed lines
            continue

    return logs


def read_human_logs(addon_slug: str, lines: int = 100) -> str:
    """Read human-readable logs via ha CLI.

    Args:
        addon_slug: Add-on slug
        lines: Number of lines to retrieve (approximate)

    Returns:
        Log output as string

    """
    token = get_supervisor_token()
    response = _supervisor_request(
        "GET",
        f"/addons/{addon_slug}/logs",
        token,
    )

    all_lines = response.text.splitlines()
    return "\n".join(all_lines[-lines:])


def get_log_levels_from_json(logs: list[LogEntry]) -> set[str]:
    """Extract unique log levels from parsed JSON logs.

    Args:
        logs: List of log entry dictionaries

    Returns:
        Set of log level strings (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    """
    levels: set[str] = set()
    for entry in logs:
        level_val = entry.get("level")
        if isinstance(level_val, str):
            levels.add(level_val)
    return levels


def count_log_levels(logs: list[LogEntry]) -> dict[str, int]:
    """Count occurrences of each log level.

    Args:
        logs: List of log entry dictionaries

    Returns:
        Dictionary mapping log level to count

    """
    counts: dict[str, int] = {}
    for entry in logs:
        level_val = entry.get("level")
        if isinstance(level_val, str):
            counts[level_val] = counts.get(level_val, 0) + 1
    return counts


def filter_logs_by_level(
    logs: list[LogEntry],
    level: str,
) -> list[LogEntry]:
    """Filter logs to only entries of a specific level.

    Args:
        logs: List of log entry dictionaries
        level: Log level to filter for (e.g., "DEBUG", "ERROR")

    Returns:
        Filtered list of log entries

    """
    return [entry for entry in logs if entry.get("level") == level]


def filter_logs_by_logger(
    logs: list[LogEntry],
    logger_name: str,
) -> list[LogEntry]:
    """Filter logs to only entries from a specific logger.

    Args:
        logs: List of log entry dictionaries
        logger_name: Logger name to filter for

    Returns:
        Filtered list of log entries

    """
    return [entry for entry in logs if entry.get("logger") == logger_name]


def apply_addon_preset(
    preset_name: str,
    addon_slug: str = "local_cync-controller",
) -> bool:
    """Apply a configuration preset by updating config directly.

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
            },
        },
        "preset-relay-with-forward": {
            "cloud_relay": {
                "enabled": True,
                "forward_to_cloud": True,
                "debug_packet_logging": False,
            },
        },
        "preset-relay-debug": {
            "cloud_relay": {
                "enabled": True,
                "forward_to_cloud": True,
                "debug_packet_logging": True,
            },
        },
        "preset-lan-only": {
            "cloud_relay": {
                "enabled": True,
                "forward_to_cloud": False,
                "debug_packet_logging": False,
            },
        },
    }

    if preset_name not in presets:
        return False

    # Merge preset into current config
    config_updates = presets[preset_name]
    for key, value in config_updates.items():
        existing_value = current_config.get(key)
        if isinstance(existing_value, dict):
            existing_dict = cast(dict[str, object], existing_value)
            existing_dict.update(value)
        else:
            current_config[key] = value

    # Update config
    success = update_addon_config(addon_slug, current_config)
    if success:
        pass
    else:
        pass
    return success


def stop_addon(addon_slug: str) -> bool:
    """Stop add-on via ha CLI.

    Args:
        addon_slug: Add-on slug

    Returns:
        True if stop initiated successfully

    """
    token = get_supervisor_token()
    try:
        response = _supervisor_request(
            "POST",
            f"/addons/{addon_slug}/stop",
            token,
        )
    except httpx.HTTPError:
        return False
    return response.status_code == HTTP_OK


def start_addon(addon_slug: str) -> bool:
    """Start add-on via ha CLI (non-blocking).

    Args:
        addon_slug: Add-on slug

    Returns:
        True if start initiated successfully

    """
    token = get_supervisor_token()
    try:
        response = _supervisor_request(
            "POST",
            f"/addons/{addon_slug}/start",
            token,
        )
    except httpx.HTTPError:
        return False
    return response.status_code == HTTP_OK
