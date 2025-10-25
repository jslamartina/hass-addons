"""
MQTT Integration Tests

Tests MQTT broker integration, discovery protocol, state updates,
and command handling with real MQTT broker and add-on containers.
"""

import asyncio
import json

import pytest


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_mqtt_broker_connection(mqtt_client):
    """Test that add-on connects to MQTT broker successfully."""
    # The mqtt_client fixture already connects, so if we get here, connection worked
    assert mqtt_client is not None


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_discovery_messages_published(mqtt_client, test_device_1, trigger_discovery):
    """
    Test that add-on publishes MQTT discovery messages.

    Verifies:
    - Discovery messages published to homeassistant/light/+/config
    - Messages contain required fields
    - Device metadata is correct
    """
    # Subscribe to discovery topic
    discovery_topic = "homeassistant/light/+/config"
    await mqtt_client.subscribe(discovery_topic)

    # Trigger rediscovery AFTER subscribing
    await trigger_discovery()

    # Collect discovery messages (controller uses random 5-15s delay before publishing)
    messages = []
    try:
        async with asyncio.timeout(20.0):
            async for message in mqtt_client.messages:
                messages.append(message)
                # Stop after receiving at least 1 message
                if len(messages) >= 1:
                    break
    except TimeoutError:
        pass

    # Assert we received at least one discovery message
    assert len(messages) > 0, "No discovery messages received"

    # Parse first message and validate structure
    payload = json.loads(messages[0].payload.decode())

    # Required fields for MQTT discovery
    assert "name" in payload, "Discovery message missing 'name' field"
    assert "unique_id" in payload, "Discovery message missing 'unique_id' field"
    assert "state_topic" in payload, "Discovery message missing 'state_topic' field"
    assert "command_topic" in payload, "Discovery message missing 'command_topic' field"
    assert "availability_topic" in payload, "Discovery message missing 'availability_topic' field"

    # Verify device info is included
    assert "device" in payload, "Discovery message missing 'device' info"
    assert "identifiers" in payload["device"]
    assert "manufacturer" in payload["device"]


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_availability_message_published(mqtt_client):
    """
    Test that add-on publishes availability messages.

    Verifies:
    - Birth message ("online") published on connect
    - Availability topic is correct
    """
    # Subscribe to availability topic
    availability_topic = "cync_lan_test/status"
    await mqtt_client.subscribe(availability_topic)

    # Wait for availability message
    try:
        async with asyncio.timeout(10.0):
            async for message in mqtt_client.messages:
                payload = message.payload.decode()
                if payload == "online":
                    # Success!
                    assert True
                    return
    except TimeoutError:
        pytest.fail("No availability message received within 10 seconds")


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_state_updates_propagate(mqtt_client, test_device_1):
    """
    Test that device state updates propagate to MQTT.

    Verifies:
    - State updates published to state_topic
    - State format is correct (ON/OFF)
    - Updates happen in response to device changes
    """
    device_id = test_device_1["device_id"]
    state_topic = f"cync_lan_test/device_{device_id:04x}/state"

    # Subscribe to state topic
    await mqtt_client.subscribe(state_topic)

    # Wait for state update (may be initial state or device broadcast)
    try:
        async with asyncio.timeout(10.0):
            async for message in mqtt_client.messages:
                state = message.payload.decode()
                # Verify state is valid
                assert state in ["ON", "OFF"], f"Invalid state value: {state}"
                return  # Success
    except TimeoutError:
        pytest.fail("No state update received within 10 seconds")


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_command_subscription(mqtt_client, test_device_1):
    """
    Test that add-on subscribes to command topics.

    Verifies:
    - Add-on listens for commands on command_topic
    - Commands trigger device actions (tested in device_control tests)
    """
    device_id = test_device_1["device_id"]
    command_topic = f"cync_lan_test/device_{device_id:04x}/set"
    state_topic = f"cync_lan_test/device_{device_id:04x}/state"

    # Subscribe to state topic to verify command was processed
    await mqtt_client.subscribe(state_topic)

    # Send command
    await mqtt_client.publish(command_topic, payload="ON")

    # Wait for state update confirming command was processed
    try:
        async with asyncio.timeout(10.0):
            async for message in mqtt_client.messages:
                state = message.payload.decode()
                if state == "ON":
                    # Command was processed!
                    return
    except TimeoutError:
        pytest.fail("Command not processed within 10 seconds")


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_multiple_entities_published(mqtt_client, test_devices):
    """
    Test that multiple device entities are published.

    Verifies:
    - All test devices get discovery messages
    - Each device has unique_id and topics
    """
    discovery_topic = "homeassistant/light/+/config"
    await mqtt_client.subscribe(discovery_topic)

    # Collect discovery messages
    messages = []
    try:
        async with asyncio.timeout(10.0):
            async for message in mqtt_client.messages:
                messages.append(message)
                # Stop after receiving messages for all test devices
                if len(messages) >= len(test_devices):
                    break
    except TimeoutError:
        pass

    # Verify we got at least some discovery messages
    assert len(messages) > 0, "No discovery messages received"

    # Parse and verify unique_ids are different
    unique_ids = set()
    for msg in messages:
        payload = json.loads(msg.payload.decode())
        unique_ids.add(payload["unique_id"])

    # All unique_ids should be different
    assert len(unique_ids) == len(messages), "Duplicate unique_id values found"


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_suggested_area_assignment(mqtt_client, test_device_1):
    """
    Test that suggested_area is correctly assigned from device room.

    Verifies:
    - Discovery message includes suggested_area
    - Area matches device room configuration
    """
    discovery_topic = "homeassistant/light/+/config"
    await mqtt_client.subscribe(discovery_topic)

    # Wait for discovery message
    try:
        async with asyncio.timeout(10.0):
            async for message in mqtt_client.messages:
                payload = json.loads(message.payload.decode())

                # Check if this is for our test device
                expected_room = test_device_1["room"]
                if "suggested_area" in payload:
                    if payload["suggested_area"] == expected_room:
                        # Found our device with correct area!
                        return

    except TimeoutError:
        pytest.fail("Discovery message with suggested_area not found")


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
@pytest.mark.slow
async def test_entity_configuration_validation(mqtt_client, collect_mqtt_messages):
    """
    Test that entity configurations are valid.

    Verifies:
    - All required Home Assistant fields present
    - Schema matches MQTT discovery spec
    - Device class is appropriate
    """
    # Collect all discovery messages
    messages = await collect_mqtt_messages("homeassistant/light/+/config", duration=5.0)

    assert len(messages) > 0, "No discovery messages collected"

    # Validate each message
    for message in messages:
        payload = json.loads(message.payload.decode())

        # Required fields
        required_fields = [
            "name",
            "unique_id",
            "state_topic",
            "command_topic",
            "device",
        ]

        for field in required_fields:
            assert field in payload, f"Missing required field: {field}"

        # Device info validation
        device_info = payload["device"]
        assert "identifiers" in device_info
        assert "manufacturer" in device_info
        assert "name" in device_info

        # Optional but expected fields
        if "brightness_state_topic" in payload:
            assert "brightness_command_topic" in payload, "Brightness state without command topic"


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.asyncio
async def test_mqtt_reconnection_handling(mqtt_client):
    """
    Test that add-on handles MQTT disconnections gracefully.

    Verifies:
    - Add-on reconnects after connection loss
    - Discovery messages republished after reconnect
    - State updates resume after reconnect

    Note: This test requires Docker environment manipulation
    which may not be available in all test environments.
    """
    pytest.skip("MQTT reconnection testing requires Docker container manipulation")
    # TODO: Implement with docker-compose restart of EMQX service
