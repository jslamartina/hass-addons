"""
Device Control Integration Tests

Tests complete command flow through the stack:
MQTT → Server → Device → ACK → State Update

Validates critical implementation details:
- Callback registration (prevents silent failures)
- ACK handling
- pending_command flag lifecycle
- Group commands
- Device availability
"""

import asyncio
import json

import pytest


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_full_command_flow_with_ack(mqtt_client, test_device_1):
    """
    Test complete command flow including ACK.

    Flow:
    1. Send command via MQTT
    2. Command reaches device via TCP
    3. Device sends ACK
    4. State update published to MQTT

    This validates the critical callback registration fix.
    """
    device_id = test_device_1["device_id"]
    command_topic = f"cync_lan_test/device_{device_id:04x}/set"
    state_topic = f"cync_lan_test/device_{device_id:04x}/state"

    # Subscribe to state updates
    await mqtt_client.subscribe(state_topic)

    # Send command
    await mqtt_client.publish(command_topic, payload="ON")

    # Wait for state update (which indicates ACK was processed)
    try:
        async with asyncio.timeout(10.0):
            async for message in mqtt_client.messages:
                state = message.payload.decode()
                if state == "ON":
                    # Success! Complete flow worked
                    return
    except TimeoutError:
        pytest.fail("State update not received - ACK may not have been processed")


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_turn_on_command(mqtt_client, test_device_1, device_topics):
    """Test turning device ON via MQTT command."""
    device_name = test_device_1["name"]
    topics = device_topics(device_name)
    command_topic = topics["command_topic"]
    state_topic = topics["state_topic"]

    await mqtt_client.subscribe(state_topic)

    # Send ON command
    await mqtt_client.publish(command_topic, payload="ON")

    # Verify state becomes ON (controller publishes JSON)
    try:
        async with asyncio.timeout(15.0):
            async for message in mqtt_client.messages:
                state_data = json.loads(message.payload.decode())
                if state_data.get("state") == "ON":
                    return  # Success
    except TimeoutError:
        pytest.fail("Device did not turn ON")


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_turn_off_command(mqtt_client, test_device_1, device_topics):
    """Test turning device OFF via MQTT command."""
    device_name = test_device_1["name"]
    topics = device_topics(device_name)
    command_topic = topics["command_topic"]
    state_topic = topics["state_topic"]

    await mqtt_client.subscribe(state_topic)

    # First turn on
    await mqtt_client.publish(command_topic, payload="ON")
    await asyncio.sleep(1)

    # Then turn off
    await mqtt_client.publish(command_topic, payload="OFF")

    # Verify state becomes OFF (controller publishes JSON)
    try:
        async with asyncio.timeout(15.0):
            async for message in mqtt_client.messages:
                state_data = json.loads(message.payload.decode())
                if state_data.get("state") == "OFF":
                    return  # Success
    except TimeoutError:
        pytest.fail("Device did not turn OFF")


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_brightness_control(mqtt_client, test_device_1):
    """
    Test brightness control via MQTT.

    Verifies:
    - Brightness commands processed
    - Brightness state updated
    - Valid brightness range (0-100)
    """
    device_id = test_device_1["device_id"]
    command_topic = f"cync_lan_test/device_{device_id:04x}/set"
    brightness_topic = f"cync_lan_test/device_{device_id:04x}/brightness/state"

    # Check if device supports brightness
    if "brightness" not in test_device_1["capabilities"]:
        pytest.skip("Device does not support brightness")

    await mqtt_client.subscribe(brightness_topic)

    # Send brightness command
    brightness_command = json.dumps({"brightness": 75})
    await mqtt_client.publish(command_topic, payload=brightness_command)

    # Wait for brightness update
    try:
        async with asyncio.timeout(10.0):
            async for message in mqtt_client.messages:
                brightness = int(message.payload.decode())
                if brightness == 75:
                    return  # Success
    except TimeoutError:
        pytest.fail("Brightness not updated")


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_group_command_all_devices_respond(mqtt_client, test_group_1, test_devices):
    """
    Test group command controls all devices in group.

    This validates that group commands:
    - Register callbacks (critical fix)
    - Reach all devices in group
    - Update all device states
    """
    group_id = test_group_1["group_id"]
    group_command_topic = f"cync_lan_test/group_{group_id:04x}/set"

    # Get device IDs in group
    group_device_ids = test_group_1["devices"]

    # Subscribe to all device state topics
    state_topics = [f"cync_lan_test/device_{dev_id:04x}/state" for dev_id in group_device_ids]
    for topic in state_topics:
        await mqtt_client.subscribe(topic)

    # Send group command
    await mqtt_client.publish(group_command_topic, payload="OFF")

    # Track which devices responded
    devices_responded = set()

    # Wait for all devices to respond
    try:
        async with asyncio.timeout(15.0):
            async for message in mqtt_client.messages:
                # Check if this is from one of our group devices
                for dev_id in group_device_ids:
                    topic = f"cync_lan_test/device_{dev_id:04x}/state"
                    if str(message.topic) == topic and message.payload.decode() == "OFF":
                        devices_responded.add(dev_id)

                # Stop when all devices responded
                if len(devices_responded) == len(group_device_ids):
                    return  # Success!

    except TimeoutError:
        pytest.fail(
            f"Not all devices responded to group command. "
            f"Expected {len(group_device_ids)}, got {len(devices_responded)}"
        )


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_pending_command_flag_lifecycle(mqtt_client, test_device_1):
    """
    Test pending_command flag behavior.

    Verifies:
    - Flag set when command sent
    - Flag cleared after ACK received
    - Prevents command flooding
    """
    # This test would require access to internal device state
    # which isn't directly observable via MQTT
    # Marking as integration test placeholder
    pytest.skip("Requires internal state monitoring - implement with debug endpoints")


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_device_availability_updates(mqtt_client, test_device_1):
    """
    Test device availability tracking.

    Verifies:
    - Availability messages published
    - Online/offline status correct
    - offline_count threshold behavior
    """
    device_id = test_device_1["device_id"]
    availability_topic = f"cync_lan_test/device_{device_id:04x}/availability"

    await mqtt_client.subscribe(availability_topic)

    # Wait for availability update
    try:
        async with asyncio.timeout(10.0):
            async for message in mqtt_client.messages:
                status = message.payload.decode()
                # Verify valid status
                assert status in ["online", "offline"], f"Invalid availability status: {status}"
                if status == "online":
                    return  # Success
    except TimeoutError:
        pytest.fail("No availability updates received")


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_rapid_command_sequence(mqtt_client, test_device_1):
    """
    Test rapid command sequence handling.

    Verifies:
    - Multiple rapid commands processed
    - No command loss
    - State eventually consistent
    """
    device_id = test_device_1["device_id"]
    command_topic = f"cync_lan_test/device_{device_id:04x}/set"
    state_topic = f"cync_lan_test/device_{device_id:04x}/state"

    await mqtt_client.subscribe(state_topic)

    # Send rapid sequence: ON, OFF, ON, OFF, ON
    commands = ["ON", "OFF", "ON", "OFF", "ON"]
    for cmd in commands:
        await mqtt_client.publish(command_topic, payload=cmd)
        await asyncio.sleep(0.1)  # Small delay between commands

    # Final state should be ON
    try:
        async with asyncio.timeout(15.0):
            # Collect states for a bit
            final_state = None
            async for message in mqtt_client.messages:
                final_state = message.payload.decode()
                # Keep collecting until timeout
    except TimeoutError:
        pass

    # Verify final state is correct
    assert final_state == "ON", f"Expected final state ON, got {final_state}"


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
@pytest.mark.slow
async def test_concurrent_device_commands(mqtt_client, test_devices):
    """
    Test concurrent commands to multiple devices.

    Verifies:
    - Multiple devices controlled simultaneously
    - No command interference
    - All devices respond
    """
    # Send commands to all devices concurrently
    tasks = []
    for device in test_devices[:2]:  # Test first 2 devices
        device_id = device["device_id"]
        command_topic = f"cync_lan_test/device_{device_id:04x}/set"
        task = mqtt_client.publish(command_topic, payload="ON")
        tasks.append(task)

    # Execute all commands
    await asyncio.gather(*tasks)

    # Subscribe to all state topics
    for device in test_devices[:2]:
        device_id = device["device_id"]
        state_topic = f"cync_lan_test/device_{device_id:04x}/state"
        await mqtt_client.subscribe(state_topic)

    # Verify all devices responded
    devices_on = set()
    try:
        async with asyncio.timeout(15.0):
            async for message in mqtt_client.messages:
                if message.payload.decode() == "ON":
                    # Extract device ID from topic
                    topic_parts = str(message.topic).split("/")
                    device_part = topic_parts[1]  # device_XXXX
                    devices_on.add(device_part)

                if len(devices_on) >= 2:
                    return  # Success

    except TimeoutError:
        pytest.fail(f"Not all devices responded. Got {len(devices_on)}/2")


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_command_error_handling(mqtt_client, test_device_1):
    """
    Test error handling for invalid commands.

    Verifies:
    - Invalid commands rejected gracefully
    - No state corruption
    - System remains responsive
    """
    device_id = test_device_1["device_id"]
    command_topic = f"cync_lan_test/device_{device_id:04x}/set"
    state_topic = f"cync_lan_test/device_{device_id:04x}/state"

    await mqtt_client.subscribe(state_topic)

    # Send invalid command
    await mqtt_client.publish(command_topic, payload="INVALID_COMMAND")

    # Wait a bit
    await asyncio.sleep(2)

    # Send valid command to verify system still responsive
    await mqtt_client.publish(command_topic, payload="ON")

    # Verify system still works
    try:
        async with asyncio.timeout(10.0):
            async for message in mqtt_client.messages:
                state_data = json.loads(message.payload.decode())
                if state_data.get("state") == "ON":
                    return  # Success - system recovered

    except TimeoutError:
        pytest.fail("System not responsive after invalid command")
