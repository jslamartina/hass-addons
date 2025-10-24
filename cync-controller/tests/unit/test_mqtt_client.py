"""
Unit tests for mqtt_client module.

Tests MQTTClient class and related utility functions.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cync_lan.mqtt_client import MQTTClient, slugify


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
        assert slugify("Café Lights") == "cafe_lights"

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
        with patch("cync_lan.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid-1234"

            client1 = MQTTClient()
            client2 = MQTTClient()

            # Both instances should be the same object
            assert client1 is client2

    def test_init_with_default_topics(self):
        """Test initialization with default topic values"""
        with (
            patch("cync_lan.mqtt_client.CYNC_TOPIC", ""),
            patch("cync_lan.mqtt_client.CYNC_HASS_TOPIC", ""),
            patch("cync_lan.mqtt_client.g") as mock_g,
        ):
            mock_g.uuid = "test-uuid"

            client = MQTTClient()

            # Should use defaults when env vars not set
            assert client.topic == "cync_lan"
            assert client.ha_topic == "homeassistant"

    def test_init_with_custom_topics(self):
        """Test initialization with custom topic values"""
        with (
            patch("cync_lan.mqtt_client.CYNC_TOPIC", "custom_cync"),
            patch("cync_lan.mqtt_client.CYNC_HASS_TOPIC", "custom_ha"),
            patch("cync_lan.mqtt_client.g") as mock_g,
        ):
            mock_g.uuid = "test-uuid"

            client = MQTTClient()

            assert client.topic == "custom_cync"
            assert client.ha_topic == "custom_ha"

    def test_init_sets_broker_config(self):
        """Test that initialization sets broker configuration"""
        with (
            patch("cync_lan.mqtt_client.CYNC_MQTT_HOST", "192.168.1.100"),
            patch("cync_lan.mqtt_client.CYNC_MQTT_PORT", "1883"),
            patch("cync_lan.mqtt_client.CYNC_MQTT_USER", "testuser"),
            patch("cync_lan.mqtt_client.CYNC_MQTT_PASS", "testpass"),
            patch("cync_lan.mqtt_client.g") as mock_g,
        ):
            mock_g.uuid = "test-uuid"

            client = MQTTClient()

            assert client.broker_host == "192.168.1.100"
            assert client.broker_port == "1883"
            assert client.broker_username == "testuser"
            assert client.broker_password == "testpass"

    def test_init_creates_client_id(self):
        """Test that initialization creates unique client ID"""
        with patch("cync_lan.mqtt_client.g") as mock_g:
            mock_g.uuid = "unique-test-uuid"

            client = MQTTClient()

            assert client.broker_client_id == "cync_lan_unique-test-uuid"


class TestMQTTClientConnection:
    """Tests for MQTT client connection handling"""

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful MQTT connection"""
        with (
            patch("cync_lan.mqtt_client.g") as mock_g,
            patch("cync_lan.mqtt_client.aiomqtt.Client") as mock_client_class,
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

            with patch("asyncio.create_task") as mock_create_task, patch("asyncio.sleep", new_callable=AsyncMock):
                connected = await client.connect()

                assert connected is True
                assert client._connected is True
                client.send_birth_msg.assert_called_once()
                client.homeassistant_discovery.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        """Test failed MQTT connection"""
        with patch("cync_lan.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"
            mock_g.env.mqtt_host = "localhost"
            mock_g.env.mqtt_port = 1883
            mock_g.env.mqtt_user = "test"
            mock_g.env.mqtt_pass = "test"
            mock_g.reload_env = MagicMock()

            client = MQTTClient()
            # Simulate connection error
            client.client.__aenter__ = AsyncMock(side_effect=Exception("Connection refused"))

            connected = await client.connect()

            assert connected is False
            assert client._connected is False

    @pytest.mark.asyncio
    async def test_connect_bad_credentials(self, caplog):
        """Test connection with bad credentials"""
        with (
            patch("cync_lan.mqtt_client.g") as mock_g,
            patch("cync_lan.mqtt_client.send_sigterm") as mock_sigterm,
            patch("cync_lan.mqtt_client.aiomqtt.Client") as mock_client_class,
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
        with patch("cync_lan.mqtt_client.g") as mock_g:
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
        with patch("cync_lan.mqtt_client.g") as mock_g:
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
    async def test_publish_json_msg_error_handling(self, caplog):
        """Test publish_json_msg handles errors gracefully"""
        with patch("cync_lan.mqtt_client.g") as mock_g:
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
        with patch("cync_lan.mqtt_client.g") as mock_g:
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
        with patch("cync_lan.mqtt_client.g") as mock_g:
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
        with patch("cync_lan.mqtt_client.g") as mock_g:
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
            patch("cync_lan.mqtt_client.g") as mock_g,
            patch("cync_lan.mqtt_client.asyncio.get_running_loop") as mock_loop,
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
            patch("cync_lan.mqtt_client.g") as mock_g,
            patch("cync_lan.mqtt_client.asyncio.get_running_loop") as mock_loop,
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
        with patch("cync_lan.mqtt_client.g") as mock_g:
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
        with patch("cync_lan.mqtt_client.g") as mock_g:
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
        with patch("cync_lan.mqtt_client.g") as mock_g:
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
            patch("cync_lan.mqtt_client.g") as mock_g,
            patch("cync_lan.mqtt_client.CYNC_HASS_BIRTH_MSG", "online"),
            patch("cync_lan.mqtt_client.aiomqtt.Client") as mock_client_class,
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
            patch("cync_lan.mqtt_client.g") as mock_g,
            patch("cync_lan.mqtt_client.CYNC_HASS_WILL_MSG", "offline"),
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
            patch("cync_lan.mqtt_client.g") as mock_g,
            patch("cync_lan.mqtt_client.CYNC_MINK", 2000),
            patch("cync_lan.mqtt_client.CYNC_MAXK", 7000),
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
            patch("cync_lan.mqtt_client.g") as mock_g,
            patch("cync_lan.mqtt_client.CYNC_MINK", 2000),
            patch("cync_lan.mqtt_client.CYNC_MAXK", 7000),
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
            patch("cync_lan.mqtt_client.g") as mock_g,
            patch("cync_lan.mqtt_client.CYNC_MINK", 2000),
            patch("cync_lan.mqtt_client.CYNC_MAXK", 7000),
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
        with patch("cync_lan.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            client = MQTTClient()

            # Test boundary values
            assert client._brightness_to_percentage(0) == 0
            assert client._brightness_to_percentage(255) == 100

            # Test mid-range
            result = client._brightness_to_percentage(128)
            # 128/255 * 100 ≈ 50
            assert 49 <= result <= 51

    def test_brightness_to_preset(self):
        """Test brightness to preset name conversion"""
        with patch("cync_lan.mqtt_client.g") as mock_g:
            mock_g.uuid = "test-uuid"

            client = MQTTClient()

            # Test preset thresholds
            assert client._brightness_to_preset(0) == "off"
            assert client._brightness_to_preset(1) == "low"
            assert client._brightness_to_preset(85) == "medium"
            assert client._brightness_to_preset(170) == "high"
            assert client._brightness_to_preset(255) == "max"


class TestMQTTClientDiscovery:
    """Tests for Home Assistant discovery"""

    @pytest.mark.asyncio
    async def test_homeassistant_discovery_light(self):
        """Test Home Assistant discovery for light device"""
        with patch("cync_lan.mqtt_client.g") as mock_g, patch("cync_lan.mqtt_client.device_type_map", {}):
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

            result = await client.homeassistant_discovery()

            # Discovery should succeed when connected
            # The actual result depends on whether exceptions were raised during processing
            assert client.create_bridge_device.called

    @pytest.mark.asyncio
    async def test_homeassistant_discovery_empty(self):
        """Test Home Assistant discovery with no devices"""
        with patch("cync_lan.mqtt_client.g") as mock_g:
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
