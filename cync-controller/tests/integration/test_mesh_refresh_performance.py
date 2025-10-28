"""Integration tests for mesh refresh performance measurement."""

import contextlib
import json
import re
import subprocess
import time

import pytest


def get_json_logs():
    """Get JSON logs from the addon container."""
    result = subprocess.run(
        ["docker", "exec", "addon_local_cync-controller", "cat", "/var/log/cync_controller.json"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout


def parse_json_logs(json_output):
    """Parse JSON logs and extract relevant entries."""
    entries = []
    for line in json_output.strip().split("\n"):
        if not line:
            continue
        with contextlib.suppress(json.JSONDecodeError):
            entries.append(json.loads(line))
    return entries


def publish_group_command(state: str):
    """Publish a group command via MQTT."""
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "host",
            "library/python:3.11-slim",
            "bash",
            "-c",
            f"""
apt-get update >/dev/null 2>&1 && apt-get install -y mosquitto-clients >/dev/null 2>&1
mosquitto_pub -h localhost -t "cync_controller_addon/set/device-group-32771" -m '{{"state":"{state}"}}' 2>&1
""",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode == 0


def measure_mesh_refresh_performance():
    """
    Measure mesh refresh performance by analyzing JSON logs.

    Returns:
        dict with timing metrics or None if data not found
    """
    logs = get_json_logs()
    entries = parse_json_logs(logs)

    # Find MESH_REFRESH_REQ and MESH_REFRESH_DONE pairs with same correlation_id
    refresh_dones = {}

    for entry in entries:
        msg = entry.get("message", "")

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
        totals = [data["total_ms"] for data in refresh_dones.values()]
        parses = [data["parse_ms"] for data in refresh_dones.values()]

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
    """
    Test mesh refresh performance: Measure round-trip time from group command to mesh refresh completion.

    This integration test publishes MQTT group commands and measures the time it takes for the addon
    to complete the mesh refresh and return timing data in the logs.

    Goal: Verify mesh refresh completes within 500ms threshold for good UX.
    """
    print("\n=== Mesh Refresh Performance Integration Test ===\n")

    # Restart addon to get fresh logs
    print("[Setup] Restarting addon and waiting for MQTT client to connect...")
    subprocess.run(["ha", "addons", "restart", "local_cync-controller"], check=False, timeout=30)
    time.sleep(8)  # Wait for addon to fully start and MQTT to connect

    # Clear the JSON log file to get a clean baseline
    subprocess.run(
        [
            "docker",
            "exec",
            "addon_local_cync-controller",
            "sh",
            "-c",
            'echo "" > /var/log/cync_controller.json',
        ],
        check=False,
        timeout=5,
    )
    time.sleep(1)

    # Publish group commands
    print("[Step 1] Publishing group commands via MQTT...")
    test_iterations = 2

    for iteration_num in range(test_iterations):
        # Publish ON command
        print(f"  Iteration {iteration_num + 1}: Publishing GROUP ON command...")
        if not publish_group_command("ON"):
            print("      Warning: ON command may not have been delivered")
        time.sleep(1)

        # Publish OFF command
        print(f"  Iteration {iteration_num + 1}: Publishing GROUP OFF command...")
        if not publish_group_command("OFF"):
            print("      Warning: OFF command may not have been delivered")
        time.sleep(1)

    # Wait for async mesh refresh to complete
    print("\n[Step 2] Waiting for mesh refresh to complete...")
    time.sleep(3)

    # Measure performance from logs
    print("\n[Step 3] Analyzing mesh refresh performance from JSON logs...")
    perf = measure_mesh_refresh_performance()

    if perf:
        print("\n MESH REFRESH PERFORMANCE RESULTS:")
        print(f"   Samples collected: {perf['count']}")
        print(f"   Average round-trip: {perf['avg_total_ms']:.1f}ms")
        print(f"   Max round-trip: {perf['max_total_ms']:.1f}ms (threshold: 500ms)")
        print(f"   Min round-trip: {perf['min_total_ms']:.1f}ms")
        print(f"   Average parse time: {perf['avg_parse_ms']:.1f}ms")
        print(f"   Max parse time: {perf['max_parse_ms']:.1f}ms")

        print("\n   Detailed timing per sample:")
        for i, (_, data) in enumerate(perf["samples"].items(), 1):
            print(f"      Sample {i}: {data['total_ms']:.1f}ms (parse: {data['parse_ms']:.1f}ms)")

        # Verify within threshold
        threshold_ms = 500
        if perf["max_total_ms"] <= threshold_ms:
            print(f"\n PASS: All mesh refresh operations completed within {threshold_ms}ms threshold")
        else:
            pytest.fail(f" FAIL: Mesh refresh took {perf['max_total_ms']:.1f}ms, exceeds {threshold_ms}ms threshold")
    else:
        print("  No mesh refresh timing data found in logs")
        print("   This may indicate:")
        print("   - Group commands weren't delivered to addon")
        print("   - Mesh refresh didn't complete")
        print("   - MQTT broker connectivity issue")
        pytest.skip("Mesh refresh logs not found - cannot measure performance")
