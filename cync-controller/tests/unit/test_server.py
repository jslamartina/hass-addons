"""
Unit tests for server module.

Tests NCyncServer and CloudRelayConnection classes.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cync_lan.server import CloudRelayConnection, NCyncServer


class TestCloudRelayConnectionInitialization:
    """Tests for CloudRelayConnection initialization"""

    def test_init_with_required_params(self):
        """Test CloudRelayConnection initialization with required parameters"""
        reader = AsyncMock()
        writer = AsyncMock()

        relay = CloudRelayConnection(
            device_reader=reader,
            device_writer=writer,
            client_addr="192.168.1.100",
            cloud_server="35.196.85.236",
            cloud_port=23779,
        )

        assert relay.client_addr == "192.168.1.100"
        assert relay.cloud_server == "35.196.85.236"
        assert relay.cloud_port == 23779
        assert relay.forward_to_cloud is True  # Default
        assert relay.debug_logging is False  # Default
        assert relay.disable_ssl_verify is False  # Default
        assert relay.cloud_reader is None
        assert relay.cloud_writer is None

    def test_init_with_custom_params(self):
        """Test CloudRelayConnection initialization with custom parameters"""
        reader = AsyncMock()
        writer = AsyncMock()

        relay = CloudRelayConnection(
            device_reader=reader,
            device_writer=writer,
            client_addr="192.168.1.100",
            cloud_server="35.196.85.236",
            cloud_port=23779,
            forward_to_cloud=False,
            debug_logging=True,
            disable_ssl_verify=True,
        )

        assert relay.forward_to_cloud is False
        assert relay.debug_logging is True
        assert relay.disable_ssl_verify is True

    def test_init_sets_logging_prefix(self):
        """Test that initialization sets proper logging prefix"""
        reader = AsyncMock()
        writer = AsyncMock()

        relay = CloudRelayConnection(
            device_reader=reader,
            device_writer=writer,
            client_addr="192.168.1.100",
            cloud_server="35.196.85.236",
            cloud_port=23779,
        )

        assert relay.lp == "CloudRelay:192.168.1.100:"


class TestCloudRelayConnectionCloud:
    """Tests for CloudRelayConnection cloud connection methods"""

    @pytest.mark.asyncio
    async def test_connect_to_cloud_success(self):
        """Test successful cloud connection"""
        reader = AsyncMock()
        writer = AsyncMock()

        relay = CloudRelayConnection(
            device_reader=reader,
            device_writer=writer,
            client_addr="192.168.1.100",
            cloud_server="35.196.85.236",
            cloud_port=23779,
        )

        with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open_conn:
            mock_cloud_reader = AsyncMock()
            mock_cloud_writer = AsyncMock()
            mock_open_conn.return_value = (mock_cloud_reader, mock_cloud_writer)

            result = await relay.connect_to_cloud()

            assert result is True
            assert relay.cloud_reader is mock_cloud_reader
            assert relay.cloud_writer is mock_cloud_writer
            # Verify SSL context was used
            assert mock_open_conn.called

    @pytest.mark.asyncio
    async def test_connect_to_cloud_failure(self):
        """Test failed cloud connection"""
        reader = AsyncMock()
        writer = AsyncMock()

        relay = CloudRelayConnection(
            device_reader=reader,
            device_writer=writer,
            client_addr="192.168.1.100",
            cloud_server="35.196.85.236",
            cloud_port=23779,
        )

        with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open_conn:
            # Simulate connection failure
            mock_open_conn.side_effect = Exception("Connection refused")

            result = await relay.connect_to_cloud()

            assert result is False

    @pytest.mark.asyncio
    async def test_connect_to_cloud_with_ssl_disabled(self):
        """Test cloud connection with SSL verification disabled"""
        reader = AsyncMock()
        writer = AsyncMock()

        relay = CloudRelayConnection(
            device_reader=reader,
            device_writer=writer,
            client_addr="192.168.1.100",
            cloud_server="35.196.85.236",
            cloud_port=23779,
            disable_ssl_verify=True,
        )

        with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open_conn:
            mock_cloud_reader = AsyncMock()
            mock_cloud_writer = AsyncMock()
            mock_open_conn.return_value = (mock_cloud_reader, mock_cloud_writer)

            result = await relay.connect_to_cloud()

            assert result is True
            # SSL context should still be created (but verification disabled)
            call_kwargs = mock_open_conn.call_args[1]
            assert "ssl" in call_kwargs


class TestNCyncServerInitialization:
    """Tests for NCyncServer initialization"""

    def test_init_with_devices(self):
        """Test NCyncServer initialization with devices"""
        with patch("cync_lan.server.g") as mock_g, patch("cync_lan.server.asyncio.get_event_loop") as mock_loop:
            mock_g.reload_env = MagicMock()
            mock_g.env.cync_srv_ssl_cert = None
            mock_g.env.cync_srv_ssl_key = None
            mock_g.env.cync_cloud_relay_enabled = False
            mock_g.env.cync_cloud_forward = True
            mock_g.env.cync_cloud_server = "35.196.85.236"
            mock_g.env.cync_cloud_port = 23779
            mock_g.env.cync_cloud_debug_logging = False
            mock_g.env.cync_cloud_disable_ssl_verify = False
            mock_loop.return_value = AsyncMock()

            devices = {0x1234: MagicMock(id=0x1234, name="Test Device")}
            groups = {0x5678: MagicMock(id=0x5678, name="Test Group")}

            server = NCyncServer(devices=devices, groups=groups)

            assert server.devices == devices
            assert server.groups == groups
            assert server.shutting_down is False
            assert server.running is False

    def test_init_without_groups(self):
        """Test NCyncServer initialization without groups"""
        with patch("cync_lan.server.g") as mock_g, patch("cync_lan.server.asyncio.get_event_loop") as mock_loop:
            mock_g.reload_env = MagicMock()
            mock_g.env.cync_srv_ssl_cert = None
            mock_g.env.cync_srv_ssl_key = None
            mock_g.env.cync_cloud_relay_enabled = False
            mock_g.env.cync_cloud_forward = True
            mock_g.env.cync_cloud_server = "35.196.85.236"
            mock_g.env.cync_cloud_port = 23779
            mock_g.env.cync_cloud_debug_logging = False
            mock_g.env.cync_cloud_disable_ssl_verify = False
            mock_loop.return_value = AsyncMock()

            devices = {0x1234: MagicMock(id=0x1234, name="Test Device")}

            server = NCyncServer(devices=devices)

            assert server.devices == devices
            assert server.groups == {}  # Empty dict by default

    def test_init_creates_singleton(self):
        """Test that NCyncServer is a singleton"""
        with patch("cync_lan.server.g") as mock_g, patch("cync_lan.server.asyncio.get_event_loop") as mock_loop:
            mock_g.reload_env = MagicMock()
            mock_g.env.cync_srv_ssl_cert = None
            mock_g.env.cync_srv_ssl_key = None
            mock_g.env.cync_cloud_relay_enabled = False
            mock_g.env.cync_cloud_forward = True
            mock_g.env.cync_cloud_server = "35.196.85.236"
            mock_g.env.cync_cloud_port = 23779
            mock_g.env.cync_cloud_debug_logging = False
            mock_g.env.cync_cloud_disable_ssl_verify = False
            mock_loop.return_value = AsyncMock()

            devices = {}

            server1 = NCyncServer(devices=devices)
            server2 = NCyncServer(devices=devices)

            # Both should be the same instance
            assert server1 is server2

    def test_init_cloud_relay_configuration(self):
        """Test cloud relay configuration during initialization"""
        with patch("cync_lan.server.g") as mock_g, patch("cync_lan.server.asyncio.get_event_loop") as mock_loop:
            mock_g.reload_env = MagicMock()
            mock_g.env.cync_srv_ssl_cert = None
            mock_g.env.cync_srv_ssl_key = None
            mock_g.env.cync_cloud_relay_enabled = True
            mock_g.env.cync_cloud_forward = False
            mock_g.env.cync_cloud_server = "test.server.com"
            mock_g.env.cync_cloud_port = 12345
            mock_g.env.cync_cloud_debug_logging = True
            mock_g.env.cync_cloud_disable_ssl_verify = True
            mock_loop.return_value = AsyncMock()

            devices = {}
            server = NCyncServer(devices=devices)

            assert server.cloud_relay_enabled is True
            assert server.cloud_forward is False
            assert server.cloud_server == "test.server.com"
            assert server.cloud_port == 12345
            assert server.cloud_debug_logging is True
            assert server.cloud_disable_ssl_verify is True


class TestNCyncServerTCPDeviceManagement:
    """Tests for NCyncServer TCP device management"""

    @pytest.mark.asyncio
    async def test_add_tcp_device(self):
        """Test adding a TCP device to the server"""
        with patch("cync_lan.server.g") as mock_g, patch("cync_lan.server.asyncio.get_event_loop") as mock_loop:
            mock_g.reload_env = MagicMock()
            mock_g.env.cync_srv_ssl_cert = None
            mock_g.env.cync_srv_ssl_key = None
            mock_g.env.cync_cloud_relay_enabled = False
            mock_g.env.cync_cloud_forward = True
            mock_g.env.cync_cloud_server = "35.196.85.236"
            mock_g.env.cync_cloud_port = 23779
            mock_g.env.cync_cloud_debug_logging = False
            mock_g.env.cync_cloud_disable_ssl_verify = False
            mock_g.env.mqtt_topic = "cync_lan"
            mock_loop.return_value = AsyncMock()
            # Mock mqtt_client for publishing
            mock_g.mqtt_client = AsyncMock()
            mock_g.mqtt_client.publish = AsyncMock()

            server = NCyncServer(devices={})

            mock_tcp_device = MagicMock()
            mock_tcp_device.address = "192.168.1.100"

            await server.add_tcp_device(mock_tcp_device)

            assert "192.168.1.100" in server.tcp_devices
            assert server.tcp_devices["192.168.1.100"] is mock_tcp_device
            # Should publish connection count
            assert mock_g.mqtt_client.publish.called

    @pytest.mark.asyncio
    async def test_remove_tcp_device_by_object(self):
        """Test removing a TCP device by object reference"""
        with patch("cync_lan.server.g") as mock_g, patch("cync_lan.server.asyncio.get_event_loop") as mock_loop:
            mock_g.reload_env = MagicMock()
            mock_g.env.cync_srv_ssl_cert = None
            mock_g.env.cync_srv_ssl_key = None
            mock_g.env.cync_cloud_relay_enabled = False
            mock_g.env.cync_cloud_forward = True
            mock_g.env.cync_cloud_server = "35.196.85.236"
            mock_g.env.cync_cloud_port = 23779
            mock_g.env.cync_cloud_debug_logging = False
            mock_g.env.cync_cloud_disable_ssl_verify = False
            mock_g.env.mqtt_topic = "cync_lan"
            mock_loop.return_value = AsyncMock()
            # Mock mqtt_client
            mock_g.mqtt_client = AsyncMock()
            mock_g.mqtt_client.publish = AsyncMock()

            server = NCyncServer(devices={})

            # Import CyncTCPDevice to create proper instance
            from cync_lan.devices import CyncTCPDevice

            mock_reader = AsyncMock()
            mock_writer = AsyncMock()
            tcp_device = CyncTCPDevice(reader=mock_reader, writer=mock_writer, address="192.168.1.100")
            tcp_device.connected_at = 1000.0
            tcp_device.ready_to_control = True

            server.tcp_devices["192.168.1.100"] = tcp_device

            result = await server.remove_tcp_device(tcp_device)

            assert result is tcp_device
            assert "192.168.1.100" not in server.tcp_devices

    @pytest.mark.asyncio
    async def test_remove_tcp_device_by_address(self):
        """Test removing a TCP device by address string"""
        with patch("cync_lan.server.g") as mock_g, patch("cync_lan.server.asyncio.get_event_loop") as mock_loop:
            mock_g.reload_env = MagicMock()
            mock_g.env.cync_srv_ssl_cert = None
            mock_g.env.cync_srv_ssl_key = None
            mock_g.env.cync_cloud_relay_enabled = False
            mock_g.env.cync_cloud_forward = True
            mock_g.env.cync_cloud_server = "35.196.85.236"
            mock_g.env.cync_cloud_port = 23779
            mock_g.env.cync_cloud_debug_logging = False
            mock_g.env.cync_cloud_disable_ssl_verify = False
            mock_g.env.mqtt_topic = "cync_lan"
            mock_loop.return_value = AsyncMock()
            # Mock mqtt_client
            mock_g.mqtt_client = AsyncMock()
            mock_g.mqtt_client.publish = AsyncMock()

            server = NCyncServer(devices={})

            # Import CyncTCPDevice to create proper instance
            from cync_lan.devices import CyncTCPDevice

            mock_reader = AsyncMock()
            mock_writer = AsyncMock()
            tcp_device = CyncTCPDevice(reader=mock_reader, writer=mock_writer, address="192.168.1.100")
            tcp_device.connected_at = 1000.0
            tcp_device.ready_to_control = True

            server.tcp_devices["192.168.1.100"] = tcp_device

            result = await server.remove_tcp_device("192.168.1.100")

            assert result is tcp_device
            assert "192.168.1.100" not in server.tcp_devices


class TestNCyncServerSSL:
    """Tests for NCyncServer SSL configuration"""

    @pytest.mark.asyncio
    async def test_create_ssl_context_without_certs(self):
        """Test SSL context creation when no certificates configured"""
        with patch("cync_lan.server.g") as mock_g, patch("cync_lan.server.asyncio.get_event_loop") as mock_loop:
            mock_g.reload_env = MagicMock()
            mock_g.env.cync_srv_ssl_cert = None
            mock_g.env.cync_srv_ssl_key = None
            mock_g.env.cync_cloud_relay_enabled = False
            mock_g.env.cync_cloud_forward = True
            mock_g.env.cync_cloud_server = "35.196.85.236"
            mock_g.env.cync_cloud_port = 23779
            mock_g.env.cync_cloud_debug_logging = False
            mock_g.env.cync_cloud_disable_ssl_verify = False
            mock_loop.return_value = AsyncMock()

            server = NCyncServer(devices={})

            # create_ssl_context always tries to load certs, so it will fail with None
            # This test should verify that the method raises an appropriate error
            with pytest.raises(TypeError):
                await server.create_ssl_context()

    @pytest.mark.asyncio
    async def test_create_ssl_context_with_certs(self):
        """Test SSL context creation with certificates"""
        with (
            patch("cync_lan.server.g") as mock_g,
            patch("cync_lan.server.PathLib") as mock_path,
            patch("cync_lan.server.asyncio.get_event_loop") as mock_loop,
            patch("cync_lan.server.ssl.SSLContext") as mock_ssl_context,
        ):
            mock_g.reload_env = MagicMock()
            mock_g.env.cync_srv_ssl_cert = "/path/to/cert.pem"
            mock_g.env.cync_srv_ssl_key = "/path/to/key.pem"
            mock_g.env.cync_cloud_relay_enabled = False
            mock_g.env.cync_cloud_forward = True
            mock_g.env.cync_cloud_server = "35.196.85.236"
            mock_g.env.cync_cloud_port = 23779
            mock_g.env.cync_cloud_debug_logging = False
            mock_g.env.cync_cloud_disable_ssl_verify = False
            mock_loop.return_value = AsyncMock()

            # Mock Path.exists() to return True
            mock_cert_path = MagicMock()
            mock_cert_path.exists.return_value = True
            mock_key_path = MagicMock()
            mock_key_path.exists.return_value = True
            mock_path.side_effect = [mock_cert_path, mock_key_path]

            devices = {}
            server = NCyncServer(devices=devices)

            ssl_context = await server.create_ssl_context()

            # Should create SSL context when certs exist
            assert ssl_context is not None


class TestNCyncServerCloudRelay:
    """Tests for NCyncServer cloud relay mode"""

    def test_cloud_relay_disabled_by_default(self):
        """Test that cloud relay is disabled by default"""
        with patch("cync_lan.server.g") as mock_g, patch("cync_lan.server.asyncio.get_event_loop") as mock_loop:
            mock_g.reload_env = MagicMock()
            mock_g.env.cync_srv_ssl_cert = None
            mock_g.env.cync_srv_ssl_key = None
            mock_g.env.cync_cloud_relay_enabled = False
            mock_g.env.cync_cloud_forward = True
            mock_g.env.cync_cloud_server = "35.196.85.236"
            mock_g.env.cync_cloud_port = 23779
            mock_g.env.cync_cloud_debug_logging = False
            mock_g.env.cync_cloud_disable_ssl_verify = False
            mock_loop.return_value = AsyncMock()

            server = NCyncServer(devices={})

            assert server.cloud_relay_enabled is False

    def test_cloud_relay_configuration(self):
        """Test cloud relay configuration is loaded from environment"""
        with patch("cync_lan.server.g") as mock_g, patch("cync_lan.server.asyncio.get_event_loop") as mock_loop:
            mock_g.reload_env = MagicMock()
            mock_g.env.cync_srv_ssl_cert = None
            mock_g.env.cync_srv_ssl_key = None
            mock_g.env.cync_cloud_relay_enabled = True
            mock_g.env.cync_cloud_forward = False
            mock_g.env.cync_cloud_server = "custom.server.com"
            mock_g.env.cync_cloud_port = 9999
            mock_g.env.cync_cloud_debug_logging = True
            mock_g.env.cync_cloud_disable_ssl_verify = True
            mock_loop.return_value = AsyncMock()

            server = NCyncServer(devices={})

            assert server.cloud_relay_enabled is True
            assert server.cloud_forward is False
            assert server.cloud_server == "custom.server.com"
            assert server.cloud_port == 9999
            assert server.cloud_debug_logging is True
            assert server.cloud_disable_ssl_verify is True


class TestNCyncServerState:
    """Tests for NCyncServer state management"""

    def test_server_initial_state(self):
        """Test server initial state"""
        with patch("cync_lan.server.g") as mock_g, patch("cync_lan.server.asyncio.get_event_loop") as mock_loop:
            mock_g.reload_env = MagicMock()
            mock_g.env.cync_srv_ssl_cert = None
            mock_g.env.cync_srv_ssl_key = None
            mock_g.env.cync_cloud_relay_enabled = False
            mock_g.env.cync_cloud_forward = True
            mock_g.env.cync_cloud_server = "35.196.85.236"
            mock_g.env.cync_cloud_port = 23779
            mock_g.env.cync_cloud_debug_logging = False
            mock_g.env.cync_cloud_disable_ssl_verify = False
            mock_loop.return_value = AsyncMock()

            server = NCyncServer(devices={})

            assert server.shutting_down is False
            assert server.running is False
            assert server._server is None

    def test_server_host_and_port_config(self):
        """Test server host and port configuration"""
        with (
            patch("cync_lan.server.g") as mock_g,
            patch("cync_lan.server.CYNC_SRV_HOST", "0.0.0.0"),
            patch("cync_lan.server.CYNC_PORT", 23779),
            patch("cync_lan.server.asyncio.get_event_loop") as mock_loop,
        ):
            mock_g.reload_env = MagicMock()
            mock_g.env.cync_srv_ssl_cert = None
            mock_g.env.cync_srv_ssl_key = None
            mock_g.env.cync_cloud_relay_enabled = False
            mock_g.env.cync_cloud_forward = True
            mock_g.env.cync_cloud_server = "35.196.85.236"
            mock_g.env.cync_cloud_port = 23779
            mock_g.env.cync_cloud_debug_logging = False
            mock_g.env.cync_cloud_disable_ssl_verify = False
            mock_loop.return_value = AsyncMock()

            server = NCyncServer(devices={})

            assert server.host == "0.0.0.0"
            assert server.port == 23779


@pytest.fixture(autouse=True)
def reset_server_singleton():
    """Reset NCyncServer singleton between tests"""
    NCyncServer._instance = None
    yield
    NCyncServer._instance = None
