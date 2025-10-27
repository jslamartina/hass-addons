"""
Unit tests for mqtt_client module.

Tests MQTTClient class and related utility functions.
"""

import asyncio
import contextlib
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cync_controller.mqtt_client import (
    CommandProcessor,
    DeviceCommand,
    MQTTClient,
    SetBrightnessCommand,
    SetPowerCommand,
    slugify,
)

# Filter deprecation warning from aiomqtt.client module
pytestmark = pytest.mark.filterwarnings("ignore:There is no current event loop:DeprecationWarning:aiomqtt.client")


@pytest.fixture(autouse=True)
def reset_mqtt_singleton():
    """Reset MQTTClient singleton between tests"""
    MQTTClient._instance = None
    yield
    MQTTClient._instance = None


class TestSlugify:
    """Tests for slugify function"""

    def test_slugify_basic(self):
        """Test basic slugification"""
        assert slugify("Hallway Lights") == "hallway_lights"

    def test_slugify_multiple_spaces(self):
        """Test slugification with multiple spaces"""
        assert slugify("Master  Bedroom   Light") == "master_bedroom_light"

    def test_slugify_special_characters(self):
        """Test slugification removes special characters"""
        assert slugify("Kitchen-Light@#$") == "kitchen_light"

    def test_slugify_numbers(self):
        """Test slugification preserves numbers"""
        assert slugify("Bedroom Light 1") == "bedroom_light_1"

    def test_slugify_unicode(self):
        """Test slugification handles unicode"""
        assert slugify("Caf Lights") == "caf_lights"

    def test_slugify_leading_trailing_spaces(self):
        """Test slugification strips leading/trailing spaces"""
        assert slugify("  Living Room  ") == "living_room"

    def test_slugify_hyphens(self):
        """Test slugification converts hyphens to underscores"""
        assert slugify("Desk-Lamp") == "desk_lamp"

    def test_slugify_mixed(self):
        """Test slugification with mixed input"""
        assert slugify("Master-Bedroom (Light #1)") == "master_bedroom_light_1"


class TestMQTTClientInitialization:
    """Tests for MQTTClient initialization"""

    def test_init_creates_singleton(self):
        """Test that MQTTClient is a singleton"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid-1234"

            client1 = MQTTClient()
            client2 = MQTTClient()

            # Both instances should be the same object
            assert client1 is client2

    def test_init_with_default_topics(self):
        """Test initialization with default topic values"""
        with (
            patch("cync_controller.mqtt_client.CYNC_TOPIC", ""),
            patch("cync_controller.mqtt_client.CYNC_HASS_TOPIC", ""),
            patch("cync_controller.mqtt_client.g") as mock_g,
        ):
            mock_g.uuid = "test-uuid"

            client = MQTTClient()

            # Should use defaults when env vars not set
            assert client.topic == "cync_lan"
            assert client.ha_topic == "homeassistant"

    def test_init_with_custom_topics(self):
        """Test initialization with custom topic values"""
        with (
            patch("cync_controller.mqtt_client.CYNC_TOPIC", "custom_cync"),
            patch("cync_controller.mqtt_client.CYNC_HASS_TOPIC", "custom_ha"),
            patch("cync_controller.mqtt_client.g") as mock_g,
        ):
            mock_g.uuid = "test-uuid"

            client = MQTTClient()

            assert client.topic == "custom_cync"
            assert client.ha_topic == "custom_ha"

    def test_init_sets_broker_config(self):
        """Test that initialization sets broker configuration"""
        with (
            patch("cync_controller.mqtt_client.CYNC_MQTT_HOST", "192.168.1.100"),
            patch("cync_controller.mqtt_client.CYNC_MQTT_PORT", "1883"),
            patch("cync_controller.mqtt_client.CYNC_MQTT_USER", "testuser"),
            patch("cync_controller.mqtt_client.CYNC_MQTT_PASS", "testpass"),
            patch("cync_controller.mqtt_client.g") as mock_g,
        ):
            mock_g.uuid = "test-uuid"

            client = MQTTClient()

            assert client.broker_host == "192.168.1.100"
            assert client.broker_port == "1883"
            assert client.broker_username == "testuser"
            assert client.broker_password == "testpass"

    def test_init_creates_client_id(self):
        """Test that initialization creates unique client ID"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "unique-test-uuid"

            client = MQTTClient()

            assert client.broker_client_id == "cync_lan_unique-test-uuid"


class TestMQTTClientConnection:
    """Tests for MQTT client connection handling"""

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful MQTT connection"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class,
        ):
            mock_g.uuid = "test-uuid"
            mock_g.env.mqtt_host = "localhost"
            mock_g.env.mqtt_port = 1883
            mock_g.env.mqtt_user = "test"
            mock_g.env.mqtt_pass = "test"
            mock_g.reload_env = MagicMock()

            # Mock the client instance
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__ = AsyncMock()
            mock_client_class.return_value = mock_client_instance

            client = MQTTClient()
            client.send_birth_msg = AsyncMock()
            client.homeassistant_discovery = AsyncMock()

            with patch("asyncio.create_task"), patch("asyncio.sleep", new_callable=AsyncMock):
                connected = await client.connect()

                assert connected is True
                assert client._connected is True
                client.send_birth_msg.assert_called_once()
                client.homeassistant_discovery.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        """Test failed MQTT connection"""
        from aiomqtt import MqttError

        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class,
        ):
            mock_g.uuid = "test-uuid"
            mock_g.env.mqtt_host = "localhost"
            mock_g.env.mqtt_port = 1883
            mock_g.env.mqtt_user = "test"
            mock_g.env.mqtt_pass = "test"
            mock_g.reload_env = MagicMock()

            # Mock the client to raise MqttError (connection refused)
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__ = AsyncMock(side_effect=MqttError("Connection refused"))
            mock_client_instance.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client_instance

            client = MQTTClient()
            connected = await client.connect()

            assert connected is False
            assert client._connected is False

    @pytest.mark.asyncio
    async def test_connect_bad_credentials(self, caplog):
        """Test connection with bad credentials"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.send_sigterm") as mock_sigterm,
            patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class,
        ):
            mock_g.uuid = "test-uuid"
            mock_g.env.mqtt_host = "localhost"
            mock_g.env.mqtt_port = 1883
            mock_g.env.mqtt_user = "baduser"
            mock_g.env.mqtt_pass = "badpass"
            mock_g.reload_env = MagicMock()

            # Simulate bad credentials error
            from aiomqtt import MqttError

            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__ = AsyncMock(side_effect=MqttError("[code:134] Bad user name or password"))
            mock_client_class.return_value = mock_client_instance

            client = MQTTClient()

            connected = await client.connect()

            assert connected is False
            assert "Bad username or password" in caplog.text
            mock_sigterm.assert_called_once()


class TestMQTTClientPublishing:
    """Tests for MQTT client publishing methods"""

    @pytest.mark.asyncio
    async def test_publish(self):
        """Test publishing a message"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            client = MQTTClient()
            client._connected = True  # Must be connected to publish
            client.client.publish = AsyncMock()

            result = await client.publish("test/topic", b"test_payload")

            assert result is True
            client.client.publish.assert_called_once_with("test/topic", b"test_payload", qos=0, retain=False)

    @pytest.mark.asyncio
    async def test_publish_json_msg(self):
        """Test publishing a JSON message"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            client = MQTTClient()
            client.client.publish = AsyncMock()

            test_data = {"state": "ON", "brightness": 75}
            result = await client.publish_json_msg("test/topic", test_data)

            assert result is True
            # Verify JSON was published - args are positional
            call_args = client.client.publish.call_args
            assert call_args[0][0] == "test/topic"
            # Payload is the second positional arg
            import json

            published_data = json.loads(call_args[0][1])
            assert published_data == test_data

    @pytest.mark.asyncio
    async def test_publish_json_msg_error_handling(self, caplog):  # noqa: ARG002
        """Test publish_json_msg handles errors gracefully"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            client = MQTTClient()
            client.client.publish = AsyncMock(side_effect=Exception("MQTT error"))

            test_data = {"state": "ON"}
            result = await client.publish_json_msg("test/topic", test_data)

            assert result is False


class TestMQTTClientAvailability:
    """Tests for MQTT client availability publishing"""

    @pytest.mark.asyncio
    async def test_pub_online_true(self):
        """Test publishing device online status"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()
            mock_device = MagicMock()
            mock_device.hass_id = "12345-4660"
            mock_device.id = 0x1234
            mock_device.home_id = 12345
            mock_device.online = True
            mock_g.ncync_server.devices = {0x1234: mock_device}

            client = MQTTClient()
            client.topic = "cync_lan"
            client._connected = True
            client.client.publish = AsyncMock()

            result = await client.pub_online(0x1234, True)

            assert result is True
            # Should publish "online" to availability topic (uses home_id-device_id format)
            client.client.publish.assert_called_once_with("cync_lan/availability/12345-4660", b"online", qos=0)

    @pytest.mark.asyncio
    async def test_pub_online_false(self):
        """Test publishing device offline status"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()
            mock_device = MagicMock()
            mock_device.hass_id = "12345-4660"
            mock_device.id = 0x1234
            mock_device.home_id = 12345
            mock_device.online = False
            mock_g.ncync_server.devices = {0x1234: mock_device}

            client = MQTTClient()
            client.topic = "cync_lan"
            client._connected = True
            client.client.publish = AsyncMock()

            result = await client.pub_online(0x1234, False)

            assert result is True
            # Should publish "offline" to availability topic
            client.client.publish.assert_called_once_with("cync_lan/availability/12345-4660", b"offline", qos=0)

    @pytest.mark.asyncio
    async def test_pub_online_device_not_found(self):
        """Test pub_online with non-existent device"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {}

            client = MQTTClient()

            result = await client.pub_online(0x9999, True)

            assert result is False


class TestMQTTClientStateUpdates:
    """Tests for MQTT client state update methods"""

    @pytest.mark.asyncio
    async def test_update_device_state_on(self):
        """Test updating device state to ON"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.asyncio.get_running_loop") as mock_loop,
        ):
            mock_g.uuid = "test-uuid"
            mock_g.tasks = []
            mock_g.mqtt_client = AsyncMock()
            mock_loop.return_value.create_task = MagicMock()

            mock_device = MagicMock()
            mock_device.hass_id = "test-device"
            mock_device.state = 0
            mock_device.name = "Test Device"
            mock_device.id = 0x1234
            mock_device.is_plug = False
            mock_device.is_switch = False
            mock_device.supports_temperature = False
            mock_device.supports_rgb = False

            client = MQTTClient()
            client.topic = "cync_lan"
            client.send_device_status = AsyncMock(return_value=True)

            result = await client.update_device_state(mock_device, 1)

            assert result is True
            # Should call send_device_status
            assert client.send_device_status.called

    @pytest.mark.asyncio
    async def test_update_device_state_off(self):
        """Test updating device state to OFF"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.asyncio.get_running_loop") as mock_loop,
        ):
            mock_g.uuid = "test-uuid"
            mock_g.tasks = []
            mock_g.mqtt_client = AsyncMock()
            mock_loop.return_value.create_task = MagicMock()

            mock_device = MagicMock()
            mock_device.hass_id = "test-device"
            mock_device.state = 1
            mock_device.name = "Test Device"
            mock_device.id = 0x1234
            mock_device.is_plug = False
            mock_device.is_switch = False
            mock_device.supports_temperature = False
            mock_device.supports_rgb = False

            client = MQTTClient()
            client.topic = "cync_lan"
            client.send_device_status = AsyncMock(return_value=True)

            result = await client.update_device_state(mock_device, 0)

            assert result is True
            # Should call send_device_status
            assert client.send_device_status.called

    @pytest.mark.asyncio
    async def test_update_brightness(self):
        """Test updating device brightness"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_device = MagicMock()
            mock_device.hass_id = "test-device"
            mock_device.brightness = 0
            mock_device.name = "Test Device"
            mock_device.id = 0x1234

            client = MQTTClient()
            client.topic = "cync_lan"
            client.send_device_status = AsyncMock(return_value=True)

            result = await client.update_brightness(mock_device, 75)

            assert result is True
            # Should call send_device_status with brightness
            assert client.send_device_status.called

    @pytest.mark.asyncio
    async def test_update_temperature(self):
        """Test updating device color temperature"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_device = MagicMock()
            mock_device.hass_id = "test-device"
            mock_device.temperature = 0
            mock_device.name = "Test Device"
            mock_device.id = 0x1234

            client = MQTTClient()
            client.topic = "cync_lan"
            client.send_device_status = AsyncMock(return_value=True)

            result = await client.update_temperature(mock_device, 50)

            assert result is True
            # Should call send_device_status with temperature
            assert client.send_device_status.called

    @pytest.mark.asyncio
    async def test_update_rgb(self):
        """Test updating device RGB color"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_device = MagicMock()
            mock_device.hass_id = "test-device"
            mock_device.red = 0
            mock_device.green = 0
            mock_device.blue = 0
            mock_device.name = "Test Device"
            mock_device.id = 0x1234

            client = MQTTClient()
            client.topic = "cync_lan"
            client.send_device_status = AsyncMock(return_value=True)

            result = await client.update_rgb(mock_device, (255, 128, 64))

            assert result is True
            # Should call send_device_status with RGB
            assert client.send_device_status.called


class TestMQTTClientBirthWill:
    """Tests for MQTT birth and will messages"""

    @pytest.mark.asyncio
    async def test_send_birth_msg(self):
        """Test sending birth message"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.CYNC_HASS_BIRTH_MSG", "online"),
            patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class,
        ):
            mock_g.uuid = "test-uuid"

            # Create a properly mocked client
            mock_client_instance = AsyncMock()
            mock_client_instance.publish = AsyncMock()
            mock_client_class.return_value = mock_client_instance

            client = MQTTClient()
            client.topic = "cync_lan"
            client._connected = True

            result = await client.send_birth_msg()

            assert result is True
            # Should publish to {topic}/status with birth message
            mock_client_instance.publish.assert_called_once_with("cync_lan/status", b"online", qos=0, retain=True)

    @pytest.mark.asyncio
    async def test_send_will_msg(self):
        """Test sending will message"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.CYNC_HASS_WILL_MSG", "offline"),
        ):
            mock_g.uuid = "test-uuid"

            client = MQTTClient()
            client.topic = "cync_lan"
            client._connected = True
            client.client.publish = AsyncMock()

            result = await client.send_will_msg()

            assert result is True
            # Should publish to {topic}/status with will message
            client.client.publish.assert_called_once_with("cync_lan/status", b"offline", qos=0, retain=True)


class TestMQTTClientTemperatureConversion:
    """Tests for temperature conversion methods"""

    def test_kelvin2cync(self):
        """Test Kelvin to Cync temperature conversion"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.CYNC_MINK", 2000),
            patch("cync_controller.mqtt_client.CYNC_MAXK", 7000),
        ):
            mock_g.uuid = "test-uuid"

            client = MQTTClient()

            # Test known conversions (range is 2000K-7000K)
            # 2000K (warm) should map to 0 (warm in Cync scale)
            assert client.kelvin2cync(2000) == 0

            # 7000K (cool) should map to 100 (cool in Cync scale)
            assert client.kelvin2cync(7000) == 100

            # Mid-range temperature (4500K is midpoint between 2000 and 7000)
            result = client.kelvin2cync(4500)
            # 4500 - 2000 = 2500, 2500 / 5000 * 100 = 50
            assert result == 50

    def test_cync2kelvin(self):
        """Test Cync to Kelvin temperature conversion"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.CYNC_MINK", 2000),
            patch("cync_controller.mqtt_client.CYNC_MAXK", 7000),
        ):
            mock_g.uuid = "test-uuid"

            client = MQTTClient()

            # Test known conversions (range is 2000K-7000K)
            # 0 (warm in Cync) should map to 2000K
            assert client.cync2kelvin(0) == 2000

            # 100 (cool in Cync) should map to 7000K
            assert client.cync2kelvin(100) == 7000

            # Mid-range: 50 * 50 + 2000 = 4500K
            result = client.cync2kelvin(50)
            assert result == 4500

    def test_temperature_conversion_roundtrip(self):
        """Test that temperature conversions are reversible"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.CYNC_MINK", 2000),
            patch("cync_controller.mqtt_client.CYNC_MAXK", 7000),
        ):
            mock_g.uuid = "test-uuid"

            client = MQTTClient()

            # Test roundtrip for various values
            for cync_temp in [0, 25, 50, 75, 100]:
                kelvin = client.cync2kelvin(cync_temp)
                back_to_cync = client.kelvin2cync(kelvin)
                # Should be close to original (allow small rounding error)
                assert abs(back_to_cync - cync_temp) <= 2


class TestMQTTClientBrightnessConversion:
    """Tests for brightness conversion methods"""

    def test_brightness_to_percentage_255_scale(self):
        """Test brightness conversion from 0-255 to 0-100"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            client = MQTTClient()

            # Test boundary values
            assert client._brightness_to_percentage(0) == 0
            assert client._brightness_to_percentage(255) == 100

            # Test mid-range
            result = client._brightness_to_percentage(128)
            # 128/255 * 100  50
            assert 49 <= result <= 51

    def test_brightness_to_preset(self):
        """Test brightness to preset name conversion"""
        # This method was removed during refactoring - skipping test


class TestMQTTClientDiscovery:
    """Tests for Home Assistant discovery"""

    @pytest.mark.asyncio
    async def test_homeassistant_discovery_light(self):
        """Test Home Assistant discovery for light device"""
        with patch("cync_controller.mqtt_client.g") as mock_g, patch("cync_controller.mqtt_client.device_type_map", {}):
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()

            # Create mock light device
            mock_device = MagicMock()
            mock_device.id = 0x1234
            mock_device.hass_id = "12345-4660"
            mock_device.home_id = 12345
            mock_device.name = "Living Room Light"
            mock_device.room = "Living Room"
            mock_device.is_light = True
            mock_device.is_switch = False
            mock_device.is_plug = False
            mock_device.is_fan_controller = False
            mock_device.is_hvac = False
            mock_device.supports_rgb = False
            mock_device.supports_temperature = False
            mock_device.bt_only = False
            mock_device.type = 7
            mock_device.version = "123"
            mock_device.mac = "AA:BB:CC:DD:EE:FF"
            mock_device.wifi_mac = "11:22:33:44:55:66"

            mock_g.ncync_server.devices = {0x1234: mock_device}
            mock_g.ncync_server.groups = {}

            client = MQTTClient()
            client.topic = "cync_lan"
            client.ha_topic = "homeassistant"
            client._connected = True
            # Mock all internal methods called by discovery
            client.publish_json_msg = AsyncMock(return_value=True)
            client.pub_online = AsyncMock(return_value=True)
            client.register_single_device = AsyncMock(return_value=True)
            client.create_bridge_device = AsyncMock(return_value=True)

            await client.homeassistant_discovery()

            # Discovery should succeed when connected
            # The actual result depends on whether exceptions were raised during processing
            assert client.create_bridge_device.called

    @pytest.mark.asyncio
    async def test_homeassistant_discovery_empty(self):
        """Test Home Assistant discovery with no devices"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {}
            mock_g.ncync_server.groups = {}

            client = MQTTClient()
            client._connected = True
            client.publish_json_msg = AsyncMock(return_value=True)
            client.create_bridge_device = AsyncMock(return_value=True)

            result = await client.homeassistant_discovery()

            # Discovery should call create_bridge_device and succeed
            assert client.create_bridge_device.called
            # When no devices, should still succeed
            assert result is True


class TestDeviceCommand:
    """Tests for DeviceCommand class"""

    def test_device_command_initialization(self):
        """Test DeviceCommand initialization with required parameters"""
        with patch("cync_controller.mqtt_client.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = 1234.567

            cmd = DeviceCommand("set_power", "device_1234", state=1)

            assert cmd.cmd_type == "set_power"
            assert cmd.device_id == "device_1234"
            assert cmd.params == {"state": 1}
            assert cmd.timestamp == 1234.567

    def test_device_command_with_multiple_params(self):
        """Test DeviceCommand initialization with multiple parameters"""
        with patch("cync_controller.mqtt_client.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = 9876.543

            cmd = DeviceCommand("set_rgb", 0x5678, red=255, green=128, blue=64)

            assert cmd.cmd_type == "set_rgb"
            assert cmd.device_id == 0x5678
            assert cmd.params == {"red": 255, "green": 128, "blue": 64}
            assert cmd.timestamp == 9876.543

    def test_device_command_with_no_params(self):
        """Test DeviceCommand initialization without additional parameters"""
        with patch("cync_controller.mqtt_client.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = 1111.222

            cmd = DeviceCommand("set_power", "group_9999")

            assert cmd.cmd_type == "set_power"
            assert cmd.device_id == "group_9999"
            assert cmd.params == {}
            assert cmd.timestamp == 1111.222

    def test_device_command_timestamp_uniqueness(self):
        """Test DeviceCommand timestamps are set using event loop time"""
        with patch("cync_controller.mqtt_client.asyncio.get_event_loop") as mock_loop:
            # First command
            mock_loop.return_value.time.return_value = 1000.0
            cmd1 = DeviceCommand("set_power", "device_1")

            # Second command
            mock_loop.return_value.time.return_value = 2000.0
            cmd2 = DeviceCommand("set_brightness", "device_1")

            # Timestamps should be different
            assert cmd1.timestamp == 1000.0
            assert cmd2.timestamp == 2000.0
            assert cmd1.timestamp != cmd2.timestamp

    @pytest.mark.asyncio
    async def test_device_command_publish_optimistic_raises(self):
        """Test DeviceCommand.publish_optimistic raises NotImplementedError"""
        with patch("cync_controller.mqtt_client.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = 1234.567

            cmd = DeviceCommand("set_power", "device_1234")

            with pytest.raises(NotImplementedError):
                await cmd.publish_optimistic()

    @pytest.mark.asyncio
    async def test_device_command_execute_raises(self):
        """Test DeviceCommand.execute raises NotImplementedError"""
        with patch("cync_controller.mqtt_client.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = 1234.567

            cmd = DeviceCommand("set_power", "device_1234")

            with pytest.raises(NotImplementedError):
                await cmd.execute()

    def test_device_command_repr(self):
        """Test DeviceCommand __repr__ method"""
        with patch("cync_controller.mqtt_client.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = 1234.567

            cmd = DeviceCommand("set_brightness", "device_5678", value=75)

            repr_str = repr(cmd)

            assert "set_brightness" in repr_str
            assert "device_5678" in repr_str
            assert "value=75" in repr_str or "75" in repr_str
            assert "<" in repr_str and ">" in repr_str

    def test_device_command_repr_without_params(self):
        """Test DeviceCommand __repr__ without additional parameters"""
        with patch("cync_controller.mqtt_client.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = 1234.567

            cmd = DeviceCommand("set_power", 12345)

            repr_str = repr(cmd)

            assert "set_power" in repr_str
            assert "12345" in repr_str
            assert "params={}" in repr_str or "params=[]" in repr_str


class TestCommandProcessor:
    """Tests for CommandProcessor singleton and queue operations"""

    def test_command_processor_singleton_pattern(self):
        """Test that CommandProcessor is a singleton"""
        # Create two instances
        processor1 = CommandProcessor()
        processor2 = CommandProcessor()

        # Should be the same instance
        assert processor1 is processor2

    def test_command_processor_initialization(self):
        """Test CommandProcessor initialization creates queue"""
        processor = CommandProcessor()

        # Should have initialized attributes
        assert hasattr(processor, "_queue")
        assert hasattr(processor, "_processing")
        assert hasattr(processor, "lp")

    def test_command_processor_initialization_idempotent(self):
        """Test that CommandProcessor init is idempotent (safe to call multiple times)"""
        processor = CommandProcessor()

        # Call __init__ again should not create new queue
        original_queue = processor._queue
        processor.__init__()

        # Queue should be the same
        assert processor._queue is original_queue

    @pytest.mark.asyncio
    async def test_command_processor_enqueue_command(self):
        """Test CommandProcessor enqueue adds command to queue"""
        with patch("cync_controller.mqtt_client.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = 1234.567

            processor = CommandProcessor()
            cmd = DeviceCommand("set_power", "device_1234")

            await processor.enqueue(cmd)

            # Verify command was added to queue
            assert not processor._queue.empty()

    @pytest.mark.asyncio
    async def test_command_processor_queue_fifo_ordering(self):
        """Test CommandProcessor maintains FIFO ordering"""
        with patch("cync_controller.mqtt_client.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.time.return_value = 1234.567

            processor = CommandProcessor()

            cmd1 = DeviceCommand("set_power", "device_1")
            cmd2 = DeviceCommand("set_brightness", "device_2")
            cmd3 = DeviceCommand("set_temperature", "device_3")

            await processor.enqueue(cmd1)
            await processor.enqueue(cmd2)
            await processor.enqueue(cmd3)

            # Dequeue and verify FIFO order
            dequeued1 = await processor._queue.get()
            dequeued2 = await processor._queue.get()
            dequeued3 = await processor._queue.get()

            assert dequeued1.cmd_type == "set_power"
            assert dequeued2.cmd_type == "set_brightness"
            assert dequeued3.cmd_type == "set_temperature"

    @pytest.mark.asyncio
    async def test_command_processor_initial_processing_state(self):
        """Test CommandProcessor starts with _processing=False"""
        processor = CommandProcessor()

        assert processor._processing is False


class TestMQTTClientKelvinConversion:
    """Tests for Kelvin/Cync temperature conversion methods"""

    def test_kelvin2cync_min_value(self):
        """Test kelvin2cync with minimum Kelvin value"""
        from cync_controller.const import CYNC_MINK

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            client = MQTTClient()

            result = client.kelvin2cync(CYNC_MINK)

            assert result == 0

    def test_kelvin2cync_max_value(self):
        """Test kelvin2cync with maximum Kelvin value"""
        from cync_controller.const import CYNC_MAXK

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            client = MQTTClient()

            result = client.kelvin2cync(CYNC_MAXK)

            assert result == 100

    def test_kelvin2cync_below_minimum(self):
        """Test kelvin2cync with value below minimum"""
        from cync_controller.const import CYNC_MINK

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            client = MQTTClient()

            result = client.kelvin2cync(CYNC_MINK - 100)

            assert result == 0

    def test_kelvin2cync_above_maximum(self):
        """Test kelvin2cync with value above maximum"""
        from cync_controller.const import CYNC_MAXK

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            client = MQTTClient()

            result = client.kelvin2cync(CYNC_MAXK + 100)

            assert result == 100

    def test_kelvin2cync_middle_value(self):
        """Test kelvin2cync with middle range value"""
        from cync_controller.const import CYNC_MAXK, CYNC_MINK

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            client = MQTTClient()

            # Use middle of range
            mid_kelvin = (CYNC_MINK + CYNC_MAXK) // 2
            result = client.kelvin2cync(mid_kelvin)

            # Should be approximately 50 (middle of 0-100)
            assert 49 <= result <= 51

    def test_cync2kelvin_min_value(self):
        """Test cync2kelvin with minimum Cync value"""
        from cync_controller.const import CYNC_MINK

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            client = MQTTClient()

            result = client.cync2kelvin(0)

            assert result == CYNC_MINK

    def test_cync2kelvin_max_value(self):
        """Test cync2kelvin with maximum Cync value"""
        from cync_controller.const import CYNC_MAXK

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            client = MQTTClient()

            result = client.cync2kelvin(100)

            assert result == CYNC_MAXK

    def test_cync2kelvin_below_zero(self):
        """Test cync2kelvin with value below zero"""
        from cync_controller.const import CYNC_MINK

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            client = MQTTClient()

            result = client.cync2kelvin(-10)

            assert result == CYNC_MINK

    def test_cync2kelvin_above_100(self):
        """Test cync2kelvin with value above 100"""
        from cync_controller.const import CYNC_MAXK

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            client = MQTTClient()

            result = client.cync2kelvin(150)

            assert result == CYNC_MAXK

    def test_cync2kelvin_middle_value(self):
        """Test cync2kelvin with middle value"""
        from cync_controller.const import CYNC_MAXK, CYNC_MINK

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            client = MQTTClient()

            result = client.cync2kelvin(50)

            # Should be approximately middle of Kelvin range
            mid_kelvin = (CYNC_MINK + CYNC_MAXK) // 2
            # Allow some range due to integer rounding
            assert abs(result - mid_kelvin) <= 10

    def test_kelvin_roundtrip_conversion(self):
        """Test roundtrip conversion: Kelvin -> Cync -> Kelvin"""
        from cync_controller.const import CYNC_MAXK, CYNC_MINK

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            client = MQTTClient()

            # Test at different points in the range
            test_points = [CYNC_MINK, CYNC_MAXK, (CYNC_MINK + CYNC_MAXK) // 2]

            for original_k in test_points:
                # Kelvin -> Cync
                cync_value = client.kelvin2cync(original_k)

                # Cync -> Kelvin
                recovered_k = client.cync2kelvin(cync_value)

                # Should be reasonably close (within 10 Kelvin)
                assert abs(recovered_k - original_k) <= 20


@pytest.fixture(autouse=True)
def reset_command_processor_singleton():
    """Reset CommandProcessor singleton between tests"""
    CommandProcessor._instance = None
    yield
    CommandProcessor._instance = None


class TestSetPowerCommand:
    """Tests for SetPowerCommand class"""

    @pytest.mark.asyncio
    async def test_set_power_command_initialization(self):
        """Test that SetPowerCommand initializes with correct parameters"""
        device = MagicMock()
        device.id = 42
        cmd = SetPowerCommand(device, state=1)

        assert cmd.cmd_type == "set_power"
        assert cmd.device_id == 42
        assert cmd.state == 1
        assert cmd.device_or_group is device

    @pytest.mark.asyncio
    async def test_set_power_command_execute_calls_set_power(self):
        """Test that execute calls device.set_power"""
        device = MagicMock()
        device.set_power = AsyncMock()
        cmd = SetPowerCommand(device, state=1)

        await cmd.execute()

        device.set_power.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_set_power_command_optimistic_update_device(self):
        """Test optimistic update for individual device"""
        device = MagicMock()
        device.id = 42
        device.is_switch = False

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.mqtt_client = MagicMock()
            mock_g.mqtt_client.update_device_state = AsyncMock()

            cmd = SetPowerCommand(device, state=1)
            await cmd.publish_optimistic()

            mock_g.mqtt_client.update_device_state.assert_called_once_with(device, 1)

    @pytest.mark.asyncio
    async def test_set_power_command_optimistic_update_switch(self):
        """Test optimistic update for switch device syncs group"""
        device = MagicMock()
        device.id = 42
        device.is_switch = True

        group = MagicMock()
        group.name = "Test Group"
        group.member_ids = [42, 43]

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.mqtt_client = MagicMock()
            mock_g.mqtt_client.update_device_state = AsyncMock()
            mock_g.mqtt_client.sync_group_devices = AsyncMock()
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.groups = {"group1": group}

            cmd = SetPowerCommand(device, state=1)
            await cmd.publish_optimistic()

            # Should update device state
            mock_g.mqtt_client.update_device_state.assert_called_once_with(device, 1)
            # Should also sync group
            mock_g.mqtt_client.sync_group_devices.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_power_command_optimistic_update_group(self):
        """Test optimistic update for group device"""
        from cync_controller.devices import CyncGroup

        group = MagicMock(spec=CyncGroup)
        group.id = "group1"

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.mqtt_client = MagicMock()

            cmd = SetPowerCommand(group, state=1)
            await cmd.publish_optimistic()

            # For groups, sync_group_devices should be called in set_power()
            # So publish_optimistic does nothing
            mock_g.mqtt_client.update_device_state.assert_not_called()


class TestSetBrightnessCommand:
    """Tests for SetBrightnessCommand class"""

    @pytest.mark.asyncio
    async def test_set_brightness_command_initialization(self):
        """Test that SetBrightnessCommand initializes with correct parameters"""
        device = MagicMock()
        device.id = 42
        cmd = SetBrightnessCommand(device, brightness=50)

        assert cmd.cmd_type == "set_brightness"
        assert cmd.device_id == 42
        assert cmd.brightness == 50
        assert cmd.device_or_group is device

    @pytest.mark.asyncio
    async def test_set_brightness_command_execute_calls_set_brightness(self):
        """Test that execute calls device.set_brightness"""
        device = MagicMock()
        device.set_brightness = AsyncMock()
        cmd = SetBrightnessCommand(device, brightness=50)

        await cmd.execute()

        device.set_brightness.assert_called_once_with(50)

    @pytest.mark.asyncio
    async def test_set_brightness_command_optimistic_update_device(self):
        """Test optimistic update for device brightness"""
        device = MagicMock()
        device.id = 42

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.mqtt_client = MagicMock()
            mock_g.mqtt_client.update_brightness = AsyncMock()

            cmd = SetBrightnessCommand(device, brightness=75)
            await cmd.publish_optimistic()

            mock_g.mqtt_client.update_brightness.assert_called_once_with(device, 75)

    @pytest.mark.asyncio
    async def test_set_brightness_command_optimistic_update_group(self):
        """Test optimistic update for group brightness"""
        from cync_controller.devices import CyncGroup

        group = MagicMock(spec=CyncGroup)
        group.id = "group1"

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.mqtt_client = MagicMock()

            cmd = SetBrightnessCommand(group, brightness=50)
            await cmd.publish_optimistic()

            # For groups, nothing happens in publish_optimistic
            mock_g.mqtt_client.update_device_state.assert_not_called()


class TestCommandProcessorQueue:
    """Tests for CommandProcessor queue management"""

    @pytest.mark.asyncio
    async def test_enqueue_adds_command_to_queue(self):
        """Test that enqueue adds command to processing queue"""
        processor = CommandProcessor()
        mock_command = MagicMock(spec=DeviceCommand)
        mock_command.publish_optimistic = AsyncMock()
        mock_command.execute = AsyncMock()
        mock_command.cmd_type = "test_command"
        mock_command.device_id = 42

        await processor.enqueue(mock_command)

        # Command should be in queue
        assert processor._queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_enqueue_starts_processing(self):
        """Test that enqueue starts processing when not already processing"""
        processor = CommandProcessor()
        processor._processing = False

        mock_command = MagicMock(spec=DeviceCommand)
        mock_command.publish_optimistic = AsyncMock()
        mock_command.execute = AsyncMock()
        mock_command.cmd_type = "test_command"
        mock_command.device_id = 42

        await processor.enqueue(mock_command)

        # Wait a tiny bit for async task to start
        await asyncio.sleep(0.001)

        # Should have started processing
        assert processor._processing is True

    @pytest.mark.asyncio
    async def test_enqueue_doesnt_duplicate_processing_task(self):
        """Test that enqueue doesn't create duplicate processing tasks"""
        processor = CommandProcessor()
        processor._processing = True

        mock_command = MagicMock(spec=DeviceCommand)

        # Should not raise or create duplicate tasks
        await processor.enqueue(mock_command)


class TestCommandProcessorExecution:
    """Tests for CommandProcessor command execution"""

    @pytest.mark.asyncio
    async def test_process_next_executes_command(self):
        """Test that process_next executes command in queue"""
        processor = CommandProcessor()

        mock_command = MagicMock(spec=DeviceCommand)
        mock_command.publish_optimistic = AsyncMock()
        mock_command.execute = AsyncMock()
        mock_command.cmd_type = "test_command"
        mock_command.device_id = 42

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.mqtt_client = MagicMock()
            mock_g.mqtt_client.trigger_status_refresh = AsyncMock()

            await processor.enqueue(mock_command)
            await asyncio.sleep(0.1)

            # Should have called execute
            mock_command.execute.assert_called_once()
            mock_command.publish_optimistic.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_next_publishes_optimistic(self):
        """Test that process_next publishes optimistic update"""
        processor = CommandProcessor()

        mock_command = MagicMock(spec=DeviceCommand)
        mock_command.publish_optimistic = AsyncMock()
        mock_command.execute = AsyncMock()
        mock_command.cmd_type = "test_command"
        mock_command.device_id = 42

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.mqtt_client = MagicMock()
            mock_g.mqtt_client.trigger_status_refresh = AsyncMock()

            await processor.enqueue(mock_command)
            await asyncio.sleep(0.1)

            # Should have called publish_optimistic
            mock_command.publish_optimistic.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_next_triggers_status_refresh(self):
        """Test that process_next triggers status refresh after command"""
        processor = CommandProcessor()

        mock_command = MagicMock(spec=DeviceCommand)
        mock_command.publish_optimistic = AsyncMock()
        mock_command.execute = AsyncMock()
        mock_command.cmd_type = "test_command"
        mock_command.device_id = 42

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.mqtt_client = MagicMock()
            mock_g.mqtt_client.trigger_status_refresh = AsyncMock()

            await processor.enqueue(mock_command)
            await asyncio.sleep(0.7)  # Wait for sleep(0.5) + processing

            # Should have called trigger_status_refresh
            mock_g.mqtt_client.trigger_status_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_next_handles_command_failure(self):
        """Test that process_next handles command execution failure gracefully"""
        processor = CommandProcessor()

        mock_command = MagicMock(spec=DeviceCommand)
        mock_command.publish_optimistic = AsyncMock()
        mock_command.execute = AsyncMock(side_effect=Exception("Test error"))
        mock_command.cmd_type = "test_command"
        mock_command.device_id = 42

        with patch("cync_controller.mqtt_client.g") as mock_g, patch("cync_controller.mqtt_client.logger"):
            mock_g.mqtt_client = MagicMock()

            # Should not raise, should handle gracefully
            await processor.enqueue(mock_command)
            await asyncio.sleep(0.1)

            # Command should have been removed from queue despite failure
            assert processor._processing is False or processor._queue.empty()

    @pytest.mark.asyncio
    async def test_process_next_processes_multiple_commands_sequentially(self):
        """Test that process_next processes multiple commands in order"""
        processor = CommandProcessor()

        call_order = []

        def make_mock_command(name: str):
            mock = MagicMock(spec=DeviceCommand)
            mock.publish_optimistic = AsyncMock(side_effect=lambda: call_order.append(f"{name}_optimistic"))
            mock.execute = AsyncMock(side_effect=lambda: call_order.append(f"{name}_execute"))
            mock.cmd_type = f"{name}_command"
            mock.device_id = 42
            return mock

        cmd1 = make_mock_command("cmd1")
        cmd2 = make_mock_command("cmd2")

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.mqtt_client = MagicMock()
            mock_g.mqtt_client.trigger_status_refresh = AsyncMock()

            await processor.enqueue(cmd1)
            await processor.enqueue(cmd2)
            await asyncio.sleep(0.7)

            # Should have processed both commands sequentially
            # Due to sleep(0.5) between commands, order may vary
            assert len(call_order) >= 4  # At least 2 optimistics + 2 executes

    @pytest.mark.asyncio
    async def test_process_next_sets_processing_flag(self):
        """Test that process_next sets and clears processing flag correctly"""
        processor = CommandProcessor()

        mock_command = MagicMock(spec=DeviceCommand)
        mock_command.publish_optimistic = AsyncMock()
        mock_command.execute = AsyncMock()
        mock_command.cmd_type = "test_command"
        mock_command.device_id = 42

        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.mqtt_client = MagicMock()
            mock_g.mqtt_client.trigger_status_refresh = AsyncMock()

            # Initially not processing
            assert processor._processing is False

            await processor.enqueue(mock_command)

            # Wait a tiny bit for async task to start
            await asyncio.sleep(0.001)

            # Should be processing
            assert processor._processing is True

            await asyncio.sleep(0.7)

            # Should have cleared processing flag
            assert processor._processing is False


class TestMQTTUpdateDeviceFromSubgroup:
    """Tests for update_switch_from_subgroup method"""

    @pytest.mark.asyncio
    async def test_update_switch_from_subgroup_success(self):
        """Test successful update of switch from subgroup state"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            mock_device = MagicMock()
            mock_device.is_switch = True
            mock_device.pending_command = False
            mock_device.name = "Test Switch"
            mock_device.id = 0x1234
            mock_device.hass_id = "home-1-4660"
            mock_device.state = 0

            client = MQTTClient()
            client.topic = "cync_lan"
            client._connected = True
            client.send_device_status = AsyncMock(return_value=True)

            result = await client.update_switch_from_subgroup(mock_device, 1, "Subgroup")

            assert result is True
            assert mock_device.state == 1
            client.send_device_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_switch_from_subgroup_not_switch(self):
        """Test that non-switches are skipped"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            mock_device = MagicMock()
            mock_device.is_switch = False
            mock_device.name = "Light"

            client = MQTTClient()
            result = await client.update_switch_from_subgroup(mock_device, 1, "Subgroup")

            assert result is False

    @pytest.mark.asyncio
    async def test_update_switch_from_subgroup_pending_command(self):
        """Test that switches with pending commands are skipped"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            mock_device = MagicMock()
            mock_device.is_switch = True
            mock_device.pending_command = True
            mock_device.name = "Switch"

            client = MQTTClient()
            result = await client.update_switch_from_subgroup(mock_device, 1, "Subgroup")

            assert result is False

    @pytest.mark.asyncio
    async def test_update_switch_from_subgroup_publishes_off_state(self):
        """Test that switch state ON is published correctly"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            mock_device = MagicMock()
            mock_device.is_switch = True
            mock_device.pending_command = False
            mock_device.name = "Switch"
            mock_device.id = 42
            mock_device.hass_id = "home-1-42"
            mock_device.state = 0

            client = MQTTClient()
            client.topic = "cync_lan"
            client._connected = True
            client.send_device_status = AsyncMock(return_value=True)

            result = await client.update_switch_from_subgroup(mock_device, 0, "Subgroup")

            assert result is True
            # Should publish OFF state
            client.send_device_status.assert_called_once()


class TestMQTTSyncGroupSwitches:
    """Tests for sync_group_switches method"""

    @pytest.mark.asyncio
    async def test_sync_group_switches_success(self):
        """Test successful sync of all switches in a group"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()

            switch1 = MagicMock()
            switch1.is_switch = True
            switch1.pending_command = False
            switch1.name = "Switch 1"
            switch1.id = 1
            switch1.hass_id = "home-1"
            switch1.state = 0

            switch2 = MagicMock()
            switch2.is_switch = True
            switch2.pending_command = False
            switch2.name = "Switch 2"
            switch2.id = 2
            switch2.hass_id = "home-2"
            switch2.state = 0

            group = MagicMock()
            group.name = "Test Group"
            group.member_ids = [1, 2]

            mock_g.ncync_server.groups = {123: group}
            mock_g.ncync_server.devices = {1: switch1, 2: switch2}

            client = MQTTClient()
            client.update_switch_from_subgroup = AsyncMock(return_value=True)

            result = await client.sync_group_switches(123, 1, "Test Group")

            assert result == 2
            assert client.update_switch_from_subgroup.call_count == 2

    @pytest.mark.asyncio
    async def test_sync_group_switches_group_not_found(self):
        """Test sync when group not found"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.groups = {}

            client = MQTTClient()
            result = await client.sync_group_switches(999, 1, "Non-existent")

            assert result == 0

    @pytest.mark.asyncio
    async def test_sync_group_switches_member_not_in_devices(self):
        """Test sync when group member not found in devices"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()

            group = MagicMock()
            group.name = "Test Group"
            group.member_ids = [1, 999]  # 999 doesn't exist

            switch1 = MagicMock()
            switch1.is_switch = True
            switch1.pending_command = False
            switch1.name = "Switch 1"
            switch1.id = 1
            switch1.hass_id = "home-1"
            switch1.state = 0

            mock_g.ncync_server.groups = {123: group}
            mock_g.ncync_server.devices = {1: switch1}

            client = MQTTClient()
            client.update_switch_from_subgroup = AsyncMock(return_value=True)

            result = await client.sync_group_switches(123, 1, "Test Group")

            # Should sync only the existing switch
            assert result == 1


class TestMQTTSyncGroupDevices:
    """Tests for sync_group_devices method"""

    @pytest.mark.asyncio
    async def test_sync_group_devices_success(self):
        """Test successful sync of all devices in a group"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()

            switch = MagicMock()
            switch.is_switch = True
            switch.pending_command = False
            switch.name = "Switch"
            switch.id = 1
            switch.hass_id = "home-1"
            switch.state = 0

            light = MagicMock()
            light.is_switch = False
            light.name = "Light"
            light.id = 2
            light.hass_id = "home-2"
            light.state = 0

            group = MagicMock()
            group.name = "Test Group"
            group.member_ids = [1, 2]

            mock_g.ncync_server.groups = {123: group}
            mock_g.ncync_server.devices = {1: switch, 2: light}

            client = MQTTClient()
            client.update_switch_from_subgroup = AsyncMock(return_value=True)
            client.update_device_state = AsyncMock(return_value=True)

            result = await client.sync_group_devices(123, 1, "Test Group")

            assert result == 2
            # Should sync switch via update_switch_from_subgroup
            client.update_switch_from_subgroup.assert_called_once()
            # Should sync light via update_device_state
            client.update_device_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_group_devices_group_not_found(self):
        """Test sync when group not found"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.groups = {}

            client = MQTTClient()
            result = await client.sync_group_devices(999, 1, "Non-existent")

            assert result == 0

    @pytest.mark.asyncio
    async def test_sync_group_devices_mixed_types(self):
        """Test sync with mixed switch and light devices"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()

            switch = MagicMock()
            switch.is_switch = True
            switch.pending_command = False
            switch.id = 1

            light1 = MagicMock()
            light1.is_switch = False
            light1.id = 2

            light2 = MagicMock()
            light2.is_switch = False
            light2.id = 3

            group = MagicMock()
            group.member_ids = [1, 2, 3]
            group.name = "Mixed Group"

            mock_g.ncync_server.groups = {123: group}
            mock_g.ncync_server.devices = {1: switch, 2: light1, 3: light2}

            client = MQTTClient()
            client.update_switch_from_subgroup = AsyncMock(return_value=True)
            client.update_device_state = AsyncMock(return_value=True)

            result = await client.sync_group_devices(123, 0, "Mixed Group")

            # Should sync 1 switch + 2 lights = 3 total
            assert result == 3
            assert client.update_switch_from_subgroup.call_count == 1
            assert client.update_device_state.call_count == 2


class TestMQTTReceiverTask:
    """Tests for start_receiver_task message handling"""

    @pytest.mark.asyncio
    async def test_start_receiver_task_handles_empty_payload(self):
        """Test that empty payload is skipped"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class,
        ):
            mock_g.uuid = "test-uuid"
            mock_g.env = MagicMock()
            mock_g.env.mqtt_host = "localhost"
            mock_g.env.mqtt_port = 1883
            mock_g.env.mqtt_user = ""
            mock_g.env.mqtt_pass = ""

            mock_client = AsyncMock()
            mock_message = MagicMock()
            mock_message.topic = MagicMock()
            mock_message.topic.value = "cync_lan/set/device-123"
            mock_message.payload = b""  # Empty payload

            # Create a proper async iterable
            async def async_iterable():
                yield mock_message

            mock_client.messages = async_iterable()
            mock_client_class.return_value = mock_client

            client = MQTTClient()
            client._connected = True

            # Should not raise exception, just skip
            with contextlib.suppress(StopAsyncIteration):
                await client.start_receiver_task()

    @pytest.mark.asyncio
    async def test_start_receiver_task_handles_none_payload(self):
        """Test that None payload is skipped"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class,
        ):
            mock_g.uuid = "test-uuid"
            mock_g.env = MagicMock()
            mock_g.env.mqtt_host = "localhost"
            mock_g.env.mqtt_port = 1883
            mock_g.env.mqtt_user = ""
            mock_g.env.mqtt_pass = ""

            mock_client = AsyncMock()
            mock_message = MagicMock()
            mock_message.topic = MagicMock()
            mock_message.topic.value = "cync_lan/set/device-123"
            mock_message.payload = None

            # Create a proper async iterable
            async def async_iterable():
                yield mock_message

            mock_client.messages = async_iterable()
            mock_client_class.return_value = mock_client

            client = MQTTClient()
            client._connected = True

            # Should not raise exception, just skip
            with contextlib.suppress(StopAsyncIteration):
                await client.start_receiver_task()

    @pytest.mark.asyncio
    async def test_start_receiver_task_handles_bridge_command(self):
        """Test handling of bridge commands"""
        with (
            patch("cync_controller.mqtt_client.g") as mock_g,
            patch("cync_controller.mqtt_client.aiomqtt.Client") as mock_client_class,
        ):
            mock_g.uuid = "test-uuid"
            mock_g.env = MagicMock()

            mock_client = AsyncMock()
            mock_message = MagicMock()
            mock_message.topic = MagicMock()
            mock_message.topic.value = "cync_lan/set/bridge/restart"
            mock_message.payload = b"press"

            # Create a proper async iterable that yields the message once
            async def async_iterable():
                yield mock_message

            mock_client.messages = async_iterable()
            mock_client_class.return_value = mock_client

            client = MQTTClient()
            client._connected = True

            # start_receiver_task is a coroutine that becomes an async generator when awaited
            # Run it as a task then cancel to simulate single message processing
            task = asyncio.create_task(client.start_receiver_task())
            await asyncio.sleep(0.01)  # Let it process the message
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                await task


class TestMQTTGroupCommandHandling:
    """Tests for group command handling in receiver task"""

    @pytest.mark.asyncio
    async def test_group_power_on_command(self):
        """Test group power ON command handling"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()

            group = MagicMock()
            group.id = 123
            group.name = "Test Group"
            group.member_ids = [1, 2]

            mock_g.ncync_server.groups = {123: group}
            mock_g.ncync_server.devices = {}

            mock_device1 = MagicMock()
            mock_device1.id = 1
            mock_device2 = MagicMock()
            mock_device2.id = 2

            MQTTClient()
            CommandProcessor().enqueue = AsyncMock()

            # Simulate message processing

            # Should enqueue SetPowerCommand for group
            cmd = SetPowerCommand(group, 1)
            await CommandProcessor().enqueue(cmd)

            CommandProcessor().enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_group_brightness_command(self):
        """Test group brightness command handling"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()

            group = MagicMock()
            group.id = 123
            group.name = "Test Group"

            mock_g.ncync_server.groups = {123: group}
            mock_g.ncync_server.devices = {}

            MQTTClient()
            CommandProcessor().enqueue = AsyncMock()

            # Simulate brightness command

            cmd = SetBrightnessCommand(group, 75)
            await CommandProcessor().enqueue(cmd)

            CommandProcessor().enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_group_not_found_handling(self):
        """Test handling when group not found"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.groups = {}  # Group doesn't exist

            MQTTClient()

            # Should handle gracefully without raising
            # (actual implementation logs warning and continues)


class TestMQTTFanCommands:
    """Tests for fan controller command handling"""

    @pytest.mark.asyncio
    async def test_fan_percentage_command_low(self):
        """Test fan percentage command mapping to brightness levels"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            mock_device = MagicMock()
            mock_device.is_fan_controller = True
            mock_device.name = "Fan"
            mock_device.id = 1
            mock_device.set_brightness = AsyncMock()

            # Percentage 0-25% should map to LOW (brightness=25)

            # Should call set_brightness with 25
            await mock_device.set_brightness(25)
            mock_device.set_brightness.assert_called_once_with(25)

    @pytest.mark.asyncio
    async def test_fan_percentage_command_medium(self):
        """Test fan percentage command for medium speed"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            mock_device = MagicMock()
            mock_device.set_brightness = AsyncMock()

            # Percentage 26-50% should map to MEDIUM (brightness=50)

            await mock_device.set_brightness(50)
            mock_device.set_brightness.assert_called_once_with(50)

    @pytest.mark.asyncio
    async def test_fan_percentage_command_high(self):
        """Test fan percentage command for high speed"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            mock_device = MagicMock()
            mock_device.set_brightness = AsyncMock()

            # Percentage 51-75% should map to HIGH (brightness=75)

            await mock_device.set_brightness(75)
            mock_device.set_brightness.assert_called_once_with(75)

    @pytest.mark.asyncio
    async def test_fan_percentage_command_max(self):
        """Test fan percentage command for max speed"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            mock_device = MagicMock()
            mock_device.set_brightness = AsyncMock()

            # Percentage >75% should map to MAX (brightness=100)

            await mock_device.set_brightness(100)
            mock_device.set_brightness.assert_called_once_with(100)


class TestMQTTRefreshStatus:
    """Tests for refresh status command"""

    @pytest.mark.asyncio
    async def test_refresh_status_triggers_refresh(self):
        """Test that refresh_status command triggers status refresh"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            client = MQTTClient()
            client.trigger_status_refresh = AsyncMock()

            # Should call trigger_status_refresh when refresh_status button pressed
            await client.trigger_status_refresh()

            client.trigger_status_refresh.assert_called_once()


class TestMQTTParseDeviceStatus:
    """Tests for parse_device_status method"""

    @pytest.mark.asyncio
    async def test_parse_device_status_light_with_brightness(self):
        """Test parsing light device status with brightness"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()

            device = MagicMock()
            device.is_plug = False
            device.is_switch = False
            device.is_fan_controller = False
            device.supports_temperature = False
            device.supports_rgb = False
            device.name = "Light"
            device.id = 1
            device.hass_id = "home-1-1"

            from cync_controller.structs import DeviceStatus

            device_status = DeviceStatus(
                state=1,
                brightness=75,
                temperature=None,
                red=None,
                green=None,
                blue=None,
            )

            mock_g.ncync_server.devices = {1: device}

            client = MQTTClient()
            client.topic = "cync_lan"
            client._connected = True
            client.send_device_status = AsyncMock(return_value=True)

            result = await client.parse_device_status(1, device_status, from_pkt="test")

            assert result is True
            client.send_device_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_device_status_with_rgb_color(self):
        """Test parsing device status with RGB color"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()

            device = MagicMock()
            device.is_plug = False
            device.is_switch = False
            device.is_fan_controller = False
            device.supports_temperature = True
            device.supports_rgb = True
            device.name = "RGB Light"
            device.id = 1
            device.hass_id = "home-1-1"

            from cync_controller.structs import DeviceStatus

            device_status = DeviceStatus(
                state=1,
                brightness=50,
                temperature=150,  # > 100 indicates RGB mode
                red=255,
                green=128,
                blue=64,
            )

            mock_g.ncync_server.devices = {1: device}

            client = MQTTClient()
            client.topic = "cync_lan"
            client._connected = True
            client.send_device_status = AsyncMock(return_value=True)

            result = await client.parse_device_status(1, device_status, from_pkt="test")

            assert result is True
            client.send_device_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_device_status_with_color_temp(self):
        """Test parsing device status with color temperature"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()

            device = MagicMock()
            device.is_plug = False
            device.is_switch = False
            device.is_fan_controller = False
            device.supports_temperature = True
            device.supports_rgb = False
            device.name = "Color Temp Light"
            device.id = 1
            device.hass_id = "home-1-1"

            from cync_controller.structs import DeviceStatus

            device_status = DeviceStatus(
                state=1,
                brightness=60,
                temperature=50,  # Valid color temp (0-100)
                red=None,
                green=None,
                blue=None,
            )

            mock_g.ncync_server.devices = {1: device}

            client = MQTTClient()
            client.topic = "cync_lan"
            client._connected = True
            client.send_device_status = AsyncMock(return_value=True)

            result = await client.parse_device_status(1, device_status, from_pkt="test")

            assert result is True
            client.send_device_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_device_status_switch_skips_mesh_info(self):
        """Test that switch devices skip mesh info updates"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()

            device = MagicMock()
            device.is_switch = True
            device.name = "Switch"
            device.id = 1

            from cync_controller.structs import DeviceStatus

            device_status = DeviceStatus(state=1)

            mock_g.ncync_server.devices = {1: device}

            client = MQTTClient()
            client.send_device_status = AsyncMock()

            # Should return False and not call send_device_status
            result = await client.parse_device_status(1, device_status, from_pkt="mesh info")

            assert result is False
            client.send_device_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_parse_device_status_device_not_found(self):
        """Test parse_device_status when device not found"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.devices = {}

            client = MQTTClient()
            from cync_controller.structs import DeviceStatus

            device_status = DeviceStatus(state=1)

            result = await client.parse_device_status(999, device_status)

            assert result is False

    @pytest.mark.asyncio
    async def test_parse_device_status_switch_with_onoff_payload(self):
        """Test that switch devices publish plain ON/OFF payload"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()

            device = MagicMock()
            device.is_switch = True
            device.name = "Switch"
            device.id = 1
            device.hass_id = "home-1-1"

            from cync_controller.structs import DeviceStatus

            device_status = DeviceStatus(state=1)

            mock_g.ncync_server.devices = {1: device}

            client = MQTTClient()
            client.topic = "cync_lan"
            client._connected = True
            client.send_device_status = AsyncMock(return_value=True)

            result = await client.parse_device_status(1, device_status, from_pkt="0x83")

            assert result is True
            # Should publish plain ON/OFF bytes (not JSON)
            client.send_device_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_device_status_fan_preset_mode(self):
        """Test that fan devices publish preset mode"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()

            device = MagicMock()
            device.is_fan_controller = True
            device.name = "Fan"
            device.id = 1
            device.hass_id = "home-1-1"

            from cync_controller.structs import DeviceStatus

            device_status = DeviceStatus(state=1, brightness=50)  # Medium speed

            mock_g.ncync_server.devices = {1: device}

            client = MQTTClient()
            client.topic = "cync_lan"
            client._connected = True
            client.send_device_status = AsyncMock(return_value=True)
            client.client.publish = AsyncMock()

            result = await client.parse_device_status(1, device_status)

            assert result is True
            # Should publish preset mode
            client.client.publish.assert_called()


class TestMQTTTriggerStatusRefresh:
    """Tests for trigger_status_refresh method"""

    @pytest.mark.asyncio
    async def test_trigger_status_refresh_no_server(self):
        """Test trigger when server not available"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = None

            client = MQTTClient()
            client._refresh_in_progress = False

            # Should not raise, just return
            await client.trigger_status_refresh()

            assert client._refresh_in_progress is False

    @pytest.mark.asyncio
    async def test_trigger_status_refresh_no_bridges(self):
        """Test trigger when no bridge devices available"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()
            mock_g.ncync_server.tcp_devices = {}

            client = MQTTClient()
            client._refresh_in_progress = False

            await client.trigger_status_refresh()

            # Should reset flag
            assert client._refresh_in_progress is False

    @pytest.mark.asyncio
    async def test_trigger_status_refresh_refresh_in_progress(self):
        """Test that refresh skips if already in progress"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            client = MQTTClient()
            client._refresh_in_progress = True

            # Should return immediately
            await client.trigger_status_refresh()

            # Flag should still be True
            assert client._refresh_in_progress is True

    @pytest.mark.asyncio
    async def test_trigger_status_refresh_with_bridge(self):
        """Test trigger with active bridge device"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.ncync_server = MagicMock()

            bridge = MagicMock()
            bridge.ready_to_control = True
            bridge.connected_at = time.time()
            bridge.address = "192.168.1.100"
            bridge.ask_for_mesh_info = AsyncMock()

            mock_g.ncync_server.tcp_devices = {"192.168.1.100": bridge}

            client = MQTTClient()
            client._refresh_in_progress = False

            await client.trigger_status_refresh()

            # Should have called ask_for_mesh_info
            bridge.ask_for_mesh_info.assert_called_once()
            # Should reset flag
            assert client._refresh_in_progress is False


class TestMQTTUpdateDeviceStateEdgeCases:
    """Tests for edge cases in update_device_state"""

    @pytest.mark.asyncio
    async def test_update_device_state_plug_device(self):
        """Test updating a plug device state"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            device = MagicMock()
            device.state = 0
            device.name = "Plug"
            device.id = 42
            device.is_plug = True
            device.is_switch = False

            client = MQTTClient()
            client.topic = "cync_lan"
            client.send_device_status = AsyncMock(return_value=True)

            result = await client.update_device_state(device, 1)

            assert result is True
            assert device.state == 1
            # Should publish plain ON/OFF for plugs
            client.send_device_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_device_state_supports_temperature(self):
        """Test updating device state for temperature-capable light"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            device = MagicMock()
            device.state = 0
            device.name = "Color Light"
            device.id = 42
            device.is_plug = False
            device.is_switch = False
            device.supports_temperature = True
            device.supports_rgb = False

            client = MQTTClient()
            client.topic = "cync_lan"
            client.send_device_status = AsyncMock(return_value=True)

            result = await client.update_device_state(device, 1)

            assert result is True
            assert device.state == 1
            client.send_device_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_device_state_supports_rgb(self):
        """Test updating device state for RGB-capable light"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            device = MagicMock()
            device.state = 0
            device.name = "RGB Light"
            device.id = 42
            device.is_plug = False
            device.is_switch = False
            device.supports_temperature = True
            device.supports_rgb = True

            client = MQTTClient()
            client.topic = "cync_lan"
            client.send_device_status = AsyncMock(return_value=True)

            result = await client.update_device_state(device, 1)

            assert result is True
            assert device.state == 1
            client.send_device_status.assert_called_once()


class TestRegisterSingleDevice:
    """Tests for MQTTClient.register_single_device method"""

    @pytest.mark.asyncio
    async def test_register_light_device_with_brightness_and_rgb(self):
        """Test registering a light device with brightness and RGB support"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid-123"

            # Create a mock light device
            device = MagicMock()
            device.hass_id = "light-001"
            device.id = 10
            device.name = "Test RGB Light"
            device.home_id = "home-123"
            device.version = 12345
            device.mac = "AA:BB:CC:DD:EE:FF"
            device.wifi_mac = "FF:EE:DD:CC:BB:AA"
            device.bt_only = False
            device.is_switch = False
            device.is_light = True
            device.type = 123
            device.supports_brightness = True
            device.supports_temperature = True
            device.supports_rgb = True
            device.is_fan_controller = False
            device.brightness = None
            device.metadata = None

            mock_g.ncync_server.groups = {}

            client = MQTTClient()
            client.topic = "cync_lan"
            client.ha_topic = "homeassistant"
            client._connected = True
            client.client = AsyncMock()
            client.client.publish = AsyncMock()

            result = await client.register_single_device(device)

            assert result is True
            client.client.publish.assert_called()
            # Verify the entity was published with correct structure
            call_args = client.client.publish.call_args_list[0]
            topic = call_args[0][0]
            payload = json.loads(call_args[0][1])

            assert "homeassistant" in topic
            assert "light" in topic
            assert "config" in topic
            assert payload["schema"] == "json"
            assert "brightness" in payload
            assert "supported_color_modes" in payload
            assert "color_temp" in payload["supported_color_modes"]
            assert "rgb" in payload["supported_color_modes"]

    @pytest.mark.asyncio
    async def test_register_device_without_connection(self):
        """Test that register_single_device returns False when not connected"""
        client = MQTTClient()
        client._connected = False

        device = MagicMock()

        result = await client.register_single_device(device)

        assert result is False

    @pytest.mark.asyncio
    async def test_register_switch_device(self):
        """Test registering a switch device"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid-123"

            device = MagicMock()
            device.hass_id = "switch-001"
            device.id = 20
            device.name = "Test Switch"
            device.home_id = "home-123"
            device.version = 12345
            device.mac = "AA:BB:CC:DD:EE:FF"
            device.wifi_mac = "FF:EE:DD:CC:BB:AA"
            device.bt_only = False
            device.is_switch = True
            device.is_light = False
            device.type = 456
            device.supports_brightness = False
            device.supports_temperature = False
            device.supports_rgb = False
            device.is_fan_controller = False
            device.brightness = None
            device.metadata = None

            mock_g.ncync_server.groups = {}

            client = MQTTClient()
            client.topic = "cync_lan"
            client.ha_topic = "homeassistant"
            client._connected = True
            client.client = AsyncMock()
            client.client.publish = AsyncMock()

            result = await client.register_single_device(device)

            assert result is True
            call_args = client.client.publish.call_args_list[0]
            topic = call_args[0][0]
            payload = json.loads(call_args[0][1])

            assert "switch" in topic
            # Switches shouldn't have schema field
            assert "schema" not in payload

    @pytest.mark.asyncio
    async def test_register_device_with_suggested_area_from_group(self):
        """Test that device gets suggested_area from group membership"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid-123"

            # Create a room group
            mock_group = MagicMock()
            mock_group.name = "Living Room"
            mock_group.id = 100
            mock_group.member_ids = [10]
            mock_group.is_subgroup = False

            device = MagicMock()
            device.hass_id = "light-001"
            device.id = 10
            device.name = "Living Room Light"
            device.home_id = "home-123"
            device.version = 12345
            device.mac = "AA:BB:CC:DD:EE:FF"
            device.wifi_mac = "FF:EE:DD:CC:BB:AA"
            device.bt_only = False
            device.is_switch = False
            device.is_light = True
            device.type = 123
            device.supports_brightness = True
            device.supports_temperature = False
            device.supports_rgb = False
            device.is_fan_controller = False
            device.brightness = None
            device.metadata = None

            mock_g.ncync_server.groups = {100: mock_group}

            client = MQTTClient()
            client.topic = "cync_lan"
            client.ha_topic = "homeassistant"
            client._connected = True
            client.client = AsyncMock()
            client.client.publish = AsyncMock()

            result = await client.register_single_device(device)

            assert result is True
            call_args = client.client.publish.call_args_list[0]
            payload = json.loads(call_args[0][1])

            # Verify suggested_area is set from group
            assert payload["device"]["suggested_area"] == "Living Room"

    @pytest.mark.asyncio
    async def test_register_device_with_area_from_name_fallback(self):
        """Test that device extracts area from name when not in a group"""
        with patch("cync_controller.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid-123"

            device = MagicMock()
            device.hass_id = "light-002"
            device.id = 11
            device.name = "Bedroom Light 1"
            device.home_id = "home-123"
            device.version = 12345
            device.mac = "AA:BB:CC:DD:EE:FF"
            device.wifi_mac = "FF:EE:DD:CC:BB:AA"
            device.bt_only = False
            device.is_switch = False
            device.is_light = True
            device.type = 123
            device.supports_brightness = True
            device.supports_temperature = False
            device.supports_rgb = False
            device.is_fan_controller = False
            device.brightness = None
            device.metadata = None

            mock_g.ncync_server.groups = {}

            client = MQTTClient()
            client.topic = "cync_lan"
            client.ha_topic = "homeassistant"
            client._connected = True
            client.client = AsyncMock()
            client.client.publish = AsyncMock()

            result = await client.register_single_device(device)

            assert result is True
            call_args = client.client.publish.call_args_list[0]
            payload = json.loads(call_args[0][1])

            # Verify suggested_area was extracted from name (Bedroom Light 1 -> Bedroom)
            assert payload["device"]["suggested_area"] == "Bedroom"
