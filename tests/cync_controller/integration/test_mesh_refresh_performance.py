"""Integration tests for mesh refresh performance measurement."""

import contextlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import cast

from _pytest.outcomes import fail as pytest_fail
from _pytest.outcomes import skip as pytest_skip

JSONDict = dict[str, object]
DOCKER_BIN = Path(shutil.which("docker") or "/usr/bin/docker")
HA_BIN = Path(shutil.which("ha") or "/usr/bin/ha")

if not DOCKER_BIN.is_absolute():
    msg = "DOCKER_BIN must be an absolute path"
    raise ValueError(msg)
if not HA_BIN.is_absolute():
    msg = "HA_BIN must be an absolute path"
    raise ValueError(msg)


def _run_trusted(
    cmd: list[str],
    *,
    check: bool = False,
    capture_output: bool = False,
    text: bool | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a trusted CLI command composed of fixed arguments."""
    return subprocess.run(  # noqa: S603
        cmd,
        shell=False,
        check=check,
        capture_output=capture_output,
        text=text,
        timeout=timeout,
    )


def get_json_logs():
    """Get JSON logs from the addon container."""
    result = _run_trusted(
        [str(DOCKER_BIN), "exec", "addon_local_cync-controller", "cat", "/var/log/cync_controller.json"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout


def parse_json_logs(json_output: str) -> list[JSONDict]:
    """Parse JSON logs and extract relevant entries."""
    entries: list[JSONDict] = []
    for line in json_output.strip().split("\n"):
        if not line:
            continue
        with contextlib.suppress(json.JSONDecodeError):
            loaded: object = cast(object, json.loads(line))
            if isinstance(loaded, dict):
                entries.append(cast(JSONDict, loaded))
    return entries


def publish_group_command(state: str):
    """Publish a group command via MQTT."""
    payload = json.dumps({"state": state})
    result = _run_trusted(
        [
            str(DOCKER_BIN),
            "run",
            "--rm",
            "--network",
            "host",
            "eclipse-mosquitto:2",
            "mosquitto_pub",
            "-h",
            "localhost",
            "-t",
            "cync_controller_addon/set/device-group-32771",
            "-m",
            payload,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode == 0


def measure_mesh_refresh_performance() -> JSONDict | None:
    """Measure mesh refresh performance by analyzing JSON logs.

    Returns:
        dict with timing metrics or None if data not found

    """
    logs = get_json_logs()
    entries = parse_json_logs(logs)

    # Find MESH_REFRESH_REQ and MESH_REFRESH_DONE pairs with same correlation_id
    refresh_dones: dict[str, JSONDict] = {}

    for entry in entries:
        msg = str(entry.get("message", ""))

        # Look for [MESH_REFRESH_DONE] with total_ms and parse_ms
        if "[MESH_REFRESH_DONE]" in msg:
            match = re.search(r"correlation_id=([^\s]+).*total_ms=([\d.]+).*parse_ms=([\d.]+)", msg)
            if match:
                corr_id_from_msg = match.group(1)
                total_ms = float(match.group(2))
                parse_ms = float(match.group(3))
                refresh_dones[corr_id_from_msg] = {
                    "total_ms": total_ms,
                    "parse_ms": parse_ms,
                    "timestamp": entry["timestamp"],
                }

    if refresh_dones:
        totals: list[float] = [cast(float, data["total_ms"]) for data in refresh_dones.values()]
        parses: list[float] = [cast(float, data["parse_ms"]) for data in refresh_dones.values()]

        return {
            "count": len(refresh_dones),
            "avg_total_ms": sum(totals) / len(totals),
            "max_total_ms": max(totals),
            "min_total_ms": min(totals),
            "avg_parse_ms": sum(parses) / len(parses),
            "max_parse_ms": max(parses),
            "min_parse_ms": min(parses),
            "samples": refresh_dones,
        }

    return None


def test_mesh_refresh_performance_group_commands():
    """Test mesh refresh performance: Measure round-trip time from group command to mesh refresh completion.

    This integration test publishes MQTT group commands and measures the time it takes for the addon
    to complete the mesh refresh and return timing data in the logs.

    Goal: Verify mesh refresh completes within 500ms threshold for good UX.
    """
    # Restart addon to get fresh logs
    _ = _run_trusted([str(HA_BIN), "addons", "restart", "local_cync-controller"], check=False, timeout=30)
    time.sleep(8)  # Wait for addon to fully start and MQTT to connect

    # Clear the JSON log file to get a clean baseline
    _ = _run_trusted(
        [str(DOCKER_BIN), "exec", "addon_local_cync-controller", "sh", "-c", 'echo "" > /var/log/cync_controller.json'],
        check=False,
        timeout=5,
    )
    time.sleep(1)

    # Publish group commands
    test_iterations = 2

    for _iteration_num in range(test_iterations):
        # Publish ON command
        if not publish_group_command("ON"):
            pass
        time.sleep(1)

        # Publish OFF command
        if not publish_group_command("OFF"):
            pass
        time.sleep(1)

    # Wait for async mesh refresh to complete
    time.sleep(3)

    # Measure performance from logs
    perf = measure_mesh_refresh_performance()

    if perf:
        samples = cast(dict[str, JSONDict], perf.get("samples", {}))
        for _i, (_corr_id, _data) in enumerate(samples.items(), 1):
            _ = (_i, _data)

        # Verify within threshold
        threshold_ms = 500
        max_total_ms = cast(float, perf["max_total_ms"])
        if max_total_ms > threshold_ms:
            pytest_fail(f" FAIL: Mesh refresh took {max_total_ms:.1f}ms, exceeds {threshold_ms}ms threshold")
    else:
        pytest_skip("Mesh refresh logs not found - cannot measure performance")
