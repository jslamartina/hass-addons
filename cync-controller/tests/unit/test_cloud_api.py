"""Unit tests for cloud_api module.

Tests CyncCloudAPI class for authentication, token management, and device export.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from cync_controller.cloud_api import ComputedTokenData, CyncAuthenticationError, CyncCloudAPI


@pytest.fixture(autouse=True)
def reset_cloud_api_singleton():
    """Reset CyncCloudAPI singleton between tests"""
    CyncCloudAPI._instance = None
    yield
    CyncCloudAPI._instance = None


class TestCyncCloudAPIInitialization:
    """Tests for CyncCloudAPI initialization"""

    def test_init_default_params(self):
        """Test CyncCloudAPI initialization with defaults"""
        api = CyncCloudAPI()

        assert api.api_timeout == 8
        assert api.lp == "CyncCloudAPI"
        assert api.http_session is None

    def test_init_custom_params(self):
        """Test CyncCloudAPI initialization with custom parameters"""
        api = CyncCloudAPI(api_timeout=15, lp="TestAPI")

        assert api.api_timeout == 15
        assert api.lp == "TestAPI"

    def test_init_creates_singleton(self):
        """Test that CyncCloudAPI is a singleton"""
        api1 = CyncCloudAPI()
        api2 = CyncCloudAPI()

        assert api1 is api2


class TestCyncCloudAPISession:
    """Tests for CyncCloudAPI session management"""

    @pytest.mark.asyncio
    async def test_check_session_creates_new_session(self):
        """Test that _check_session creates session if none exists"""
        with patch("cync_controller.cloud_api.aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock()
            mock_session_class.return_value = mock_session

            api = CyncCloudAPI()

            await api._check_session()

            assert api.http_session is mock_session
            assert mock_session.__aenter__.called

    @pytest.mark.asyncio
    async def test_check_session_reuses_open_session(self):
        """Test that _check_session doesn't recreate open session"""
        with patch("cync_controller.cloud_api.aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.closed = False
            mock_session_class.return_value = mock_session

            api = CyncCloudAPI()
            api.http_session = mock_session

            await api._check_session()

            # Should not create new session
            assert mock_session_class.call_count == 0

    @pytest.mark.asyncio
    async def test_close_session(self):
        """Test closing HTTP session"""
        api = CyncCloudAPI()
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        api.http_session = mock_session

        await api.close()

        # Session should be closed
        assert mock_session.close.called
        # http_session should be set to None after close
        assert api.http_session is None


class TestCyncCloudAPITokenManagement:
    """Tests for token cache management"""

    @pytest.mark.asyncio
    async def test_read_token_cache_not_found(self):
        """Test reading token cache when file doesn't exist"""
        api = CyncCloudAPI()

        with patch("cync_controller.cloud_api.Path") as mock_path:
            mock_file = MagicMock()
            mock_file.open.side_effect = FileNotFoundError()
            mock_path.return_value = mock_file

            result = await api.read_token_cache()

            assert result is None

    @pytest.mark.asyncio
    async def test_read_token_cache_success(self):
        """Test reading valid token cache"""
        api = CyncCloudAPI()

        # Create sample token data with all required fields
        sample_token = ComputedTokenData(
            user_id="test-user",
            access_token="test-token",
            authorize="test-auth",
            expire_in=3600,  # Note: expire_in not expires_in
            refresh_token="test-refresh-token",
            issued_at=datetime.datetime.now(datetime.UTC),
        )

        with (
            patch("cync_controller.cloud_api.Path") as mock_path,
            patch("cync_controller.cloud_api.pickle.load") as mock_pickle,
        ):
            _ = MagicMock()
            mock_path.return_value.open = mock_open()
            mock_pickle.return_value = sample_token

            result = await api.read_token_cache()

            assert result is sample_token

    @pytest.mark.asyncio
    async def test_write_token_cache(self):
        """Test writing token cache"""
        api = CyncCloudAPI()

        sample_token = ComputedTokenData(
            user_id="test-user",
            access_token="test-token",
            authorize="test-auth",
            expire_in=3600,
            refresh_token="test-refresh-token",
            issued_at=datetime.datetime.now(datetime.UTC),
        )

        with (
            patch("cync_controller.cloud_api.Path") as mock_path,
            patch("cync_controller.cloud_api.pickle.dump") as mock_pickle,
        ):
            mock_file = mock_open()
            mock_path.return_value.open = mock_file

            result = await api.write_token_cache(sample_token)

            assert result is True
            assert mock_pickle.called

    @pytest.mark.asyncio
    async def test_check_token_valid(self):
        """Test checking valid token"""
        api = CyncCloudAPI()

        # Create token that expires in the future (issued now, expires in 1 hour)
        sample_token = ComputedTokenData(
            user_id="test-user",
            access_token="test-token",
            authorize="test-auth",
            expire_in=3600,
            refresh_token="test-refresh-token",
            issued_at=datetime.datetime.now(datetime.UTC),
        )
        # expires_at is computed from issued_at + expire_in

        api.read_token_cache = AsyncMock(return_value=sample_token)

        result = await api.check_token()

        assert result is True
        assert api.token_cache is sample_token

    @pytest.mark.asyncio
    async def test_check_token_expired(self):
        """Test checking expired token"""
        api = CyncCloudAPI()

        # Create token that expired in the past (issued 2 hours ago, expires in 1 hour = expired 1 hour ago)
        sample_token = ComputedTokenData(
            user_id="test-user",
            access_token="test-token",
            authorize="test-auth",
            expire_in=3600,  # 1 hour
            refresh_token="test-refresh-token",
            issued_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=2),
        )
        # expires_at is computed: issued_at + 1 hour = 1 hour ago (expired)

        api.read_token_cache = AsyncMock(return_value=sample_token)

        result = await api.check_token()

        assert result is False

    @pytest.mark.asyncio
    async def test_check_token_not_found(self):
        """Test checking token when no cache exists"""
        api = CyncCloudAPI()
        api.read_token_cache = AsyncMock(return_value=None)

        result = await api.check_token()

        assert result is False


class TestCyncCloudAPIAuthentication:
    """Tests for authentication methods"""

    @pytest.mark.asyncio
    async def test_request_otp_success(self):
        """Test successful OTP request"""
        with (
            patch("cync_controller.cloud_api.CYNC_ACCOUNT_USERNAME", "test@example.com"),
            patch("cync_controller.cloud_api.CYNC_ACCOUNT_PASSWORD", "password123"),
        ):
            api = CyncCloudAPI()

            # Mock HTTP session
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_session.post = AsyncMock(return_value=mock_response)
            api.http_session = mock_session

            api._check_session = AsyncMock()

            result = await api.request_otp()

            assert result is True
            assert mock_session.post.called

    @pytest.mark.asyncio
    async def test_request_otp_no_credentials(self):
        """Test OTP request without credentials"""
        with (
            patch("cync_controller.cloud_api.CYNC_ACCOUNT_USERNAME", None),
            patch("cync_controller.cloud_api.CYNC_ACCOUNT_PASSWORD", None),
        ):
            api = CyncCloudAPI()
            api._check_session = AsyncMock()

            result = await api.request_otp()

            assert result is False

    @pytest.mark.asyncio
    async def test_request_otp_http_error(self):
        """Test OTP request with HTTP error"""
        with (
            patch("cync_controller.cloud_api.CYNC_ACCOUNT_USERNAME", "test@example.com"),
            patch("cync_controller.cloud_api.CYNC_ACCOUNT_PASSWORD", "password123"),
        ):
            api = CyncCloudAPI()

            # Mock HTTP session with error
            mock_session = AsyncMock()
            from aiohttp import ClientResponseError

            mock_session.post = AsyncMock(side_effect=ClientResponseError(None, None))
            api.http_session = mock_session

            api._check_session = AsyncMock()

            result = await api.request_otp()

            assert result is False

    @pytest.mark.asyncio
    async def test_send_otp_success(self):
        """Test successful OTP submission"""
        with (
            patch("cync_controller.cloud_api.CYNC_ACCOUNT_USERNAME", "test@example.com"),
            patch("cync_controller.cloud_api.CYNC_ACCOUNT_PASSWORD", "password123"),
        ):
            api = CyncCloudAPI()

            # Mock HTTP session
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json = AsyncMock(
                return_value={
                    "user_id": "test-user",
                    "access_token": "test-token",
                    "authorize": "test-auth",
                    "expire_in": 604800,
                    "refresh_token": "test-refresh-token",
                },
            )
            mock_session.post = AsyncMock(return_value=mock_response)
            api.http_session = mock_session

            api._check_session = AsyncMock()
            api.write_token_cache = AsyncMock(return_value=True)

            result = await api.send_otp(123456)

            assert result is True
            assert api.write_token_cache.called

    @pytest.mark.asyncio
    async def test_send_otp_invalid_code(self):
        """Test OTP submission with invalid code"""
        api = CyncCloudAPI()

        result = await api.send_otp(None)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_otp_string_conversion(self):
        """Test OTP submission with string code (gets converted)"""
        with (
            patch("cync_controller.cloud_api.CYNC_ACCOUNT_USERNAME", "test@example.com"),
            patch("cync_controller.cloud_api.CYNC_ACCOUNT_PASSWORD", "password123"),
        ):
            api = CyncCloudAPI()

            # Mock HTTP session
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json = AsyncMock(
                return_value={
                    "user_id": "test-user",
                    "access_token": "test-token",
                    "authorize": "test-auth",
                    "expire_in": 604800,
                    "refresh_token": "test-refresh-token",
                },
            )
            mock_session.post = AsyncMock(return_value=mock_response)
            api.http_session = mock_session

            api._check_session = AsyncMock()
            api.write_token_cache = AsyncMock(return_value=True)

            # Mock response with complete token data
            mock_response.json = AsyncMock(
                return_value={
                    "user_id": "test-user",
                    "access_token": "test-token",
                    "authorize": "test-auth",
                    "expire_in": 3600,
                    "refresh_token": "test-refresh-token",
                },
            )

            # Pass string that can be converted to int
            result = await api.send_otp("123456")

            assert result is True


class TestCyncCloudAPIDeviceOperations:
    """Tests for device export and configuration"""

    @pytest.mark.asyncio
    async def test_request_devices_success(self):
        """Test successful device request"""
        api = CyncCloudAPI()

        # Mock valid token
        datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)
        sample_token = ComputedTokenData(
            user_id="test-user",
            access_token="test-token",
            authorize="test-auth",
            expire_in=3600,
            refresh_token="test-refresh-token",
            issued_at=datetime.datetime.now(datetime.UTC),
        )
        # expires_at is computed from issued_at + expire_in
        api.token_cache = sample_token

        # Mock HTTP session
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(return_value={"data": []})
        mock_session.get = AsyncMock(return_value=mock_response)
        api.http_session = mock_session

        api._check_session = AsyncMock()

        result = await api.request_devices()

        assert result is not None
        assert mock_session.get.called

    @pytest.mark.asyncio
    async def test_request_devices_no_token(self):
        """Test device request without valid token"""
        api = CyncCloudAPI()
        api.token_cache = None
        api._check_session = AsyncMock()

        # request_devices requires a valid token cache and should raise
        # an explicit authentication error when it is missing
        with pytest.raises(CyncAuthenticationError):
            await api.request_devices()

    @pytest.mark.asyncio
    async def test_get_properties_success(self):
        """Test successful device property retrieval"""
        api = CyncCloudAPI()
        api.token_cache = ComputedTokenData(
            user_id="test-user",
            access_token="test-token",
            authorize="test-auth",
            expire_in=3600,
            refresh_token="test-refresh",
            issued_at=datetime.datetime.now(datetime.UTC),
        )
        api._check_session = AsyncMock()

        # Mock successful HTTP response
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={"properties": {"brightness": 100, "power": True}})

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        api.http_session = mock_session

        result = await api.get_properties(product_id=123, device_id=456)

        assert result == {"properties": {"brightness": 100, "power": True}}
        mock_session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_properties_access_token_expired(self):
        """Test get_properties with expired access token (code 4031021)"""
        from cync_controller.cloud_api import CyncAuthenticationError

        api = CyncCloudAPI()
        api.token_cache = ComputedTokenData(
            user_id="test-user",
            access_token="expired-token",
            authorize="test-auth",
            expire_in=3600,
            refresh_token="test-refresh",
            issued_at=datetime.datetime.now(datetime.UTC),
        )
        api._check_session = AsyncMock()

        # Mock expired token response
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={"error": {"msg": "Access-Token Expired", "code": 4031021}})

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        api.http_session = mock_session

        with pytest.raises(CyncAuthenticationError, match="Access-Token expired"):
            _ = await api.get_properties(product_id=123, device_id=456)

    @pytest.mark.asyncio
    async def test_get_properties_no_properties_error(self):
        """Test get_properties with 4041009 error (no properties for home ID)"""
        api = CyncCloudAPI()
        api.token_cache = ComputedTokenData(
            user_id="test-user",
            access_token="test-token",
            authorize="test-auth",
            expire_in=3600,
            refresh_token="test-refresh",
            issued_at=datetime.datetime.now(datetime.UTC),
        )
        api._check_session = AsyncMock()

        # Mock 4041009 error response (no properties)
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={"error": {"msg": "No properties found", "code": 4041009}})

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        api.http_session = mock_session

        result = await api.get_properties(product_id=123, device_id=456)

        # Should return the error dict without logging warning (code 4041009 is expected)
        assert result == {"error": {"msg": "No properties found", "code": 4041009}}

    @pytest.mark.asyncio
    async def test_get_properties_json_decode_error(self):
        """Test get_properties with JSON decode error"""
        api = CyncCloudAPI()
        api.token_cache = ComputedTokenData(
            user_id="test-user",
            access_token="test-token",
            authorize="test-auth",
            expire_in=3600,
            refresh_token="test-refresh",
            issued_at=datetime.datetime.now(datetime.UTC),
        )
        api._check_session = AsyncMock()

        # Mock JSON decode error
        import json

        mock_response = AsyncMock()
        mock_response.json = AsyncMock(side_effect=json.JSONDecodeError("test", "doc", 0))

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        api.http_session = mock_session

        with pytest.raises(json.JSONDecodeError):
            _ = await api.get_properties(product_id=123, device_id=456)

    @pytest.mark.asyncio
    async def test_export_config_full_mesh(self):
        """Test _mesh_to_config with complete mesh data (devices and groups)"""
        api = CyncCloudAPI()

        mesh_info = [
            {
                "name": "Home Mesh",
                "id": "mesh-123",
                "mac": "AA:BB:CC:DD:EE:FF",
                "access_key": "test-key",
                "properties": {
                    "bulbsArray": [
                        {
                            "deviceID": 1234567890,
                            "displayName": "Living Room Light",
                            "mac": "11:22:33:44:55:66",
                            "deviceType": 1,
                            "firmwareVersion": "1.2.3",
                        },
                    ],
                    "groupsArray": [
                        {
                            "groupID": 1,
                            "displayName": "All Lights",
                            "deviceIDArray": [1234567890],
                            "isSubgroup": False,
                        },
                    ],
                },
            },
        ]

        with patch("cync_controller.cloud_api.Path") as mock_path:
            mock_file = mock_open()
            mock_path.return_value.open = mock_file

            result = await api._mesh_to_config(mesh_info)

        assert "account data" in result
        assert "Home Mesh" in result["account data"]
        mesh = result["account data"]["Home Mesh"]
        assert mesh["id"] == "mesh-123"
        assert mesh["mac"] == "AA:BB:CC:DD:EE:FF"
        assert mesh["access_key"] == "test-key"
        assert 890 in mesh["devices"]  # Last 3 digits of deviceID
        assert mesh["devices"][890]["name"] == "Living Room Light"
        assert 1 in mesh["groups"]
        assert mesh["groups"][1]["name"] == "All Lights"
        assert mesh["groups"][1]["members"] == [890]

    @pytest.mark.asyncio
    async def test_export_config_skip_unnamed_mesh(self):
        """Test export_config skips mesh without name"""
        api = CyncCloudAPI()

        mesh_info = [
            {
                # No 'name' field
                "id": "mesh-123",
                "properties": {"bulbsArray": []},
            },
        ]

        with patch("cync_controller.cloud_api.Path") as mock_path:
            mock_file = mock_open()
            mock_path.return_value.open = mock_file

            result = await api._mesh_to_config(mesh_info)

        assert "account data" in result
        assert len(result["account data"]) == 0  # Mesh should be skipped

    @pytest.mark.asyncio
    async def test_export_config_skip_no_properties(self):
        """Test export_config skips mesh without properties"""
        api = CyncCloudAPI()

        mesh_info = [
            {
                "name": "Test Mesh",
                "id": "mesh-123",
                # No 'properties' field
            },
        ]

        with patch("cync_controller.cloud_api.Path") as mock_path:
            mock_file = mock_open()
            mock_path.return_value.open = mock_file

            result = await api._mesh_to_config(mesh_info)

        assert "account data" in result
        assert len(result["account data"]) == 0  # Mesh should be skipped

    @pytest.mark.asyncio
    async def test_export_config_skip_no_bulbs_array(self):
        """Test export_config skips mesh without bulbsArray"""
        api = CyncCloudAPI()

        mesh_info = [
            {
                "name": "Test Mesh",
                "id": "mesh-123",
                "properties": {
                    # No 'bulbsArray' field
                    "someOtherField": "value",
                },
            },
        ]

        with patch("cync_controller.cloud_api.Path") as mock_path:
            mock_file = mock_open()
            mock_path.return_value.open = mock_file

            result = await api._mesh_to_config(mesh_info)

        assert "account data" in result
        assert len(result["account data"]) == 0  # Mesh should be skipped

    @pytest.mark.asyncio
    async def test_export_config_device_with_hvac(self):
        """Test export_config properly parses HVAC device configuration"""
        api = CyncCloudAPI()

        mesh_info = [
            {
                "name": "HVAC Mesh",
                "id": "mesh-hvac",
                "properties": {
                    "bulbsArray": [
                        {
                            "deviceID": 9999999123,
                            "displayName": "Thermostat",
                            "mac": "AA:BB:CC:DD:EE:FF",
                            "deviceType": 100,
                            "firmwareVersion": "2.0.0",
                            "hvacSystem": {
                                "changeoverMode": 0,
                                "auxHeatStages": 1,
                                "type": 2,
                            },
                            "thermostatSensors": [{"pin": "025572", "name": "Living Room", "type": "savant"}],
                        },
                    ],
                },
            },
        ]

        with patch("cync_controller.cloud_api.Path") as mock_path:
            mock_file = mock_open()
            mock_path.return_value.open = mock_file

            result = await api._mesh_to_config(mesh_info)

        assert "HVAC Mesh" in result["account data"]
        mesh = result["account data"]["HVAC Mesh"]
        assert 123 in mesh["devices"]  # Last 3 digits
        device = mesh["devices"][123]
        assert device["name"] == "Thermostat"
        assert "hvac" in device
        assert device["hvac"]["type"] == 2
        assert "thermostatSensors" in device["hvac"]

    @pytest.mark.asyncio
    async def test_export_config_skip_invalid_device(self):
        """Test export_config skips devices with missing required attributes"""
        api = CyncCloudAPI()

        mesh_info = [
            {
                "name": "Test Mesh",
                "id": "mesh-123",
                "properties": {
                    "bulbsArray": [
                        {
                            "deviceID": 1234567890,
                            "displayName": "Valid Light",
                            "mac": "11:22:33:44:55:66",
                            "deviceType": 1,
                            "firmwareVersion": "1.0.0",
                        },
                        {
                            # Missing 'mac' field - should be skipped
                            "deviceID": 1234567891,
                            "displayName": "Invalid Light",
                            "deviceType": 1,
                            "firmwareVersion": "1.0.0",
                        },
                    ],
                },
            },
        ]

        with patch("cync_controller.cloud_api.Path") as mock_path:
            mock_file = mock_open()
            mock_path.return_value.open = mock_file

            result = await api._mesh_to_config(mesh_info)

        mesh = result["account data"]["Test Mesh"]
        assert 890 in mesh["devices"]  # Valid device
        assert 891 not in mesh["devices"]  # Invalid device skipped

    @pytest.mark.asyncio
    async def test_export_config_groups_parsing(self):
        """Test export_config correctly parses groups with members"""
        api = CyncCloudAPI()

        mesh_info = [
            {
                "name": "Group Test",
                "id": "mesh-groups",
                "properties": {
                    "bulbsArray": [
                        {
                            "deviceID": 1000000001,
                            "displayName": "Device 1",
                            "mac": "AA:BB:CC:DD:EE:01",
                            "deviceType": 1,
                            "firmwareVersion": "1.0",
                        },
                        {
                            "deviceID": 1000000002,
                            "displayName": "Device 2",
                            "mac": "AA:BB:CC:DD:EE:02",
                            "deviceType": 1,
                            "firmwareVersion": "1.0",
                        },
                    ],
                    "groupsArray": [
                        {
                            "groupID": 10,
                            "displayName": "Main Group",
                            "deviceIDArray": [1000000001, 1000000002],
                            "isSubgroup": False,
                        },
                        {
                            "groupID": 11,
                            "displayName": "Subgroup",
                            "deviceIDArray": [1000000001],
                            "isSubgroup": True,
                        },
                    ],
                },
            },
        ]

        with patch("cync_controller.cloud_api.Path") as mock_path:
            mock_file = mock_open()
            mock_path.return_value.open = mock_file

            result = await api._mesh_to_config(mesh_info)

        mesh = result["account data"]["Group Test"]
        assert 10 in mesh["groups"]
        assert mesh["groups"][10]["name"] == "Main Group"
        assert mesh["groups"][10]["members"] == [1, 2]  # Last 3 digits
        assert mesh["groups"][10]["is_subgroup"] is False

        assert 11 in mesh["groups"]
        assert mesh["groups"][11]["name"] == "Subgroup"
        assert mesh["groups"][11]["members"] == [1]
        assert mesh["groups"][11]["is_subgroup"] is True

    @pytest.mark.asyncio
    async def test_export_config_skip_empty_groups(self):
        """Test export_config skips groups without devices"""
        api = CyncCloudAPI()

        mesh_info = [
            {
                "name": "Empty Group Test",
                "id": "mesh-empty",
                "properties": {
                    "bulbsArray": [],
                    "groupsArray": [
                        {
                            "groupID": 99,
                            "displayName": "Empty Group",
                            "deviceIDArray": [],  # No devices
                            "isSubgroup": False,
                        },
                    ],
                },
            },
        ]

        with patch("cync_controller.cloud_api.Path") as mock_path:
            mock_file = mock_open()
            mock_path.return_value.open = mock_file

            result = await api._mesh_to_config(mesh_info)

        mesh = result["account data"]["Empty Group Test"]
        assert len(mesh["groups"]) == 0  # Empty group should be skipped
