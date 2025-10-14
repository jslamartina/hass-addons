#!/usr/bin/env python3
"""
Delete Home Assistant devices via WebSocket API

This removes devices from the device registry entirely, allowing them to be
recreated with fresh configuration (including suggested_area).

Usage:
    python3 scripts/delete-devices.py "Device Name 1" "Device Name 2"

Environment variables:
    HA_BASE_URL - Home Assistant URL (default: http://localhost:8123)
    HA_TOKEN    - Long-lived access token (required)
"""

import asyncio
import json
import os
import sys
import websockets

HA_BASE_URL = os.getenv("HA_BASE_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN")


async def delete_devices(device_names: list[str]):
    """Delete devices by name using WebSocket API"""

    if not HA_TOKEN:
        print("❌ ERROR: HA_TOKEN environment variable not set")
        print("   Create a long-lived access token:")
        print(
            "   1. Set HA_TOKEN environment variable to the long-lived access token in the hass-credentials.env file"
        )
        print("   2. Rerun the script.")
        sys.exit(1)

    ws_url = (
        HA_BASE_URL.replace("http://", "ws://").replace("https://", "wss://")
        + "/api/websocket"
    )

    async with websockets.connect(ws_url) as websocket:
        # Auth phase
        msg = await websocket.recv()
        auth_required = json.loads(msg)
        print(f"✅ Connected to HA {auth_required['ha_version']}")

        await websocket.send(json.dumps({"type": "auth", "access_token": HA_TOKEN}))

        auth_response = json.loads(await websocket.recv())
        if auth_response["type"] != "auth_ok":
            print(f"❌ Authentication failed: {auth_response}")
            return

        print("✅ Authenticated")

        # Get device list
        await websocket.send(
            json.dumps({"id": 1, "type": "config/device_registry/list"})
        )

        response = json.loads(await websocket.recv())
        if not response.get("success"):
            print(f"❌ Failed to get device list: {response}")
            return

        devices = response["result"]
        print(f"ℹ️  Found {len(devices)} total devices")

        # Find devices to delete
        to_delete = []
        for device in devices:
            if any(
                name.lower() in device.get("name", "").lower() for name in device_names
            ):
                to_delete.append(device)
                print(f"🎯 Matched: {device['name']} (ID: {device['id']})")

        if not to_delete:
            print(f"⚠️  No devices found matching: {device_names}")
            return

        # Delete each device
        msg_id = 2
        for device in to_delete:
            await websocket.send(
                json.dumps(
                    {
                        "id": msg_id,
                        "type": "config/device_registry/remove",
                        "device_id": device["id"],
                    }
                )
            )

            response = json.loads(await websocket.recv())
            if response.get("success"):
                print(f"✅ Deleted: {device['name']}")
            else:
                print(
                    f"❌ Failed to delete {device['name']}: {response.get('error', {}).get('message', 'Unknown error')}"
                )

            msg_id += 1

        print(
            f"\n✅ Device deletion complete. Restart addon to recreate with new areas."
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 delete-devices.py 'Device Name 1' 'Device Name 2'")
        print("")
        print("Example:")
        print("  export HA_TOKEN='your_token_here'")
        print(
            "  python3 scripts/delete-devices.py 'Hallway Front Switch' 'Hallway Counter Switch'"
        )
        sys.exit(1)

    device_names = sys.argv[1:]
    asyncio.run(delete_devices(device_names))
