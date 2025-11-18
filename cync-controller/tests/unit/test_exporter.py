"""
Unit tests for exporter.py module.

Tests FastAPI endpoints for OTP flow, device export, and ExportServer lifecycle.
"""

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp
import pytest
from fastapi import HTTPException

# Mock StaticFiles before import to avoid directory initialization error
with patch("starlette.staticfiles.StaticFiles"):
    from cync_controller.exporter import ExportServer


@pytest.fixture(autouse=True)
def reset_export_server_singleton():
    """Reset ExportServer singleton between tests"""
    ExportServer._instance = None
    yield
    ExportServer._instance = None


@pytest.fixture
def mock_global_object():
    """Mock the global object to avoid dependencies"""
    with patch("cync_controller.exporter.g") as mock_g:
        mock_g.cloud_api = MagicMock()
        mock_g.env = MagicMock()
        mock_g.env.mqtt_topic = "cync_lan"
        mock_g.mqtt_client = None
        yield mock_g


@pytest.fixture
def mock_static_dir(tmp_path):
    """Create a temporary static directory for testing"""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    index_file = static_dir / "index.html"
    index_file.write_text("<html>Test Page</html>")
    return static_dir


class TestExportServerInitialization:
    """Tests for ExportServer initialization"""

    def test_init_is_singleton(self):
        """Test that ExportServer is a singleton"""
        server1 = ExportServer()
        server2 = ExportServer()

        assert server1 is server2

    def test_init_creates_uvicorn_server(self):
        """Test that initialization creates uvicorn server with correct config"""
        with (
            patch("cync_controller.exporter.uvicorn.Server"),
            patch("cync_controller.exporter.uvicorn.Config") as mock_config,
        ):
            server = ExportServer()

            assert mock_config.called
            mock_config.assert_called_once()
            assert server.uvi_server is not None


class TestExportServerLifecycle:
    """Tests for ExportServer start and stop"""

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self, mock_global_object):
        """Test that start sets running flag and publishes MQTT message"""
        mock_global_object.mqtt_client = MagicMock()
        mock_global_object.mqtt_client.publish = AsyncMock()

        server = ExportServer()
        server.uvi_server.serve = AsyncMock()

        start_task = asyncio.create_task(server.start())
        await asyncio.sleep(0.1)

        assert server.running is True
        assert mock_global_object.mqtt_client.publish.called

        start_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await start_task

    @pytest.mark.asyncio
    async def test_start_with_cancelled_error(self, mock_global_object):
        """Test that start handles CancelledError gracefully"""
        server = ExportServer()
        server.uvi_server.serve = AsyncMock(side_effect=asyncio.CancelledError())

        with pytest.raises(asyncio.CancelledError):
            await server.start()

        # Should log info about server stopped
        assert server.running is True  # Set before cancelled

    @pytest.mark.asyncio
    async def test_stop_shuts_down_server(self, mock_global_object):
        """Test that stop calls uvicorn shutdown"""
        mock_global_object.mqtt_client = MagicMock()
        mock_global_object.mqtt_client.publish = AsyncMock()

        server = ExportServer()
        server.running = True
        server.uvi_server.shutdown = AsyncMock()
        server.start_task = None

        await server.stop()

        assert server.uvi_server.shutdown.called
        assert server.running is False

    @pytest.mark.asyncio
    async def test_stop_publishes_mqtt_message(self, mock_global_object):
        """Test that stop publishes MQTT message indicating server stopped"""
        mock_global_object.mqtt_client = MagicMock()
        mock_global_object.mqtt_client.publish = AsyncMock()

        server = ExportServer()
        server.running = True
        server.uvi_server.shutdown = AsyncMock()
        server.start_task = None

        await server.stop()

        assert mock_global_object.mqtt_client.publish.called


class TestFastAPIEndpoints:
    """Tests for FastAPI endpoint functions"""

    @pytest.mark.asyncio
    async def test_get_index(self, mock_static_dir):
        """Test index page serves HTML content"""
        with (
            patch("cync_controller.exporter.CYNC_STATIC_DIR", str(mock_static_dir)),
            patch("pathlib.Path.open") as mock_open,
        ):
            mock_file = MagicMock()
            mock_file.read.return_value = "<html>Test Content</html>"
            mock_file.__enter__ = Mock(return_value=mock_file)
            mock_file.__exit__ = Mock(return_value=None)
            mock_open.return_value = mock_file

            with patch("builtins.open", mock_open, create=True):
                from cync_controller.exporter import get_index

                result = await get_index()
                assert result == "<html>Test Content</html>"

    @pytest.mark.asyncio
    async def test_start_export_success(self, mock_global_object):
        """Test start_export with valid token"""
        mock_global_object.cloud_api.check_token = AsyncMock(return_value=True)
        mock_global_object.cloud_api.export_config_file = AsyncMock(return_value=True)

        from cync_controller.exporter import start_export

        result = await start_export()

        assert result["success"] is True
        assert "message" in result

    @pytest.mark.asyncio
    async def test_start_export_requires_otp(self, mock_global_object):
        """Test start_export requests OTP when token invalid"""
        mock_global_object.cloud_api.check_token = AsyncMock(return_value=False)
        mock_global_object.cloud_api.request_otp = AsyncMock(return_value=True)

        from cync_controller.exporter import start_export

        result = await start_export()

        assert result["success"] is False
        assert "OTP requested" in result["message"]

    @pytest.mark.asyncio
    async def test_start_export_failure(self, mock_global_object):
        """Test start_export raises HTTPException on failure"""
        mock_global_object.cloud_api.check_token = AsyncMock(side_effect=Exception("API Error"))

        from cync_controller.exporter import start_export

        with pytest.raises(HTTPException) as exc_info:
            await start_export()

        detail = exc_info.value.detail
        assert "error_id" in detail
        assert "Failed to start export" in detail["message"]

    @pytest.mark.asyncio
    async def test_request_otp_success(self, mock_global_object):
        """Test request_otp succeeds"""
        mock_global_object.cloud_api.request_otp = AsyncMock(return_value=True)

        from cync_controller.exporter import request_otp

        result = await request_otp()

        assert result["success"] is True
        assert "OTP requested successfully" in result["message"]

    @pytest.mark.asyncio
    async def test_request_otp_failure(self, mock_global_object):
        """Test request_otp returns failure message"""
        mock_global_object.cloud_api.request_otp = AsyncMock(return_value=False)

        from cync_controller.exporter import request_otp

        result = await request_otp()

        assert result["success"] is False
        assert "Failed to request OTP" in result["message"]

    @pytest.mark.asyncio
    async def test_submit_otp_success(self, mock_global_object):
        """Test submit_otp with valid OTP"""
        mock_global_object.cloud_api.send_otp = AsyncMock(return_value=True)
        mock_global_object.cloud_api.export_config_file = AsyncMock(return_value=True)

        from cync_controller.exporter import OTPRequest, submit_otp

        otp_request = OTPRequest(otp=123456)

        result = await submit_otp(otp_request)

        assert result["success"] is True
        assert "Export completed successfully" in result["message"]

    @pytest.mark.asyncio
    async def test_submit_otp_invalid_code(self, mock_global_object):
        """Test submit_otp with invalid OTP"""
        mock_global_object.cloud_api.send_otp = AsyncMock(return_value=False)

        from cync_controller.exporter import OTPRequest, submit_otp

        otp_request = OTPRequest(otp=999999)

        result = await submit_otp(otp_request)

        assert result["success"] is False
        assert "Invalid OTP" in result["message"]

    @pytest.mark.asyncio
    async def test_submit_otp_export_failure(self, mock_global_object):
        """Test submit_otp when export fails after valid OTP"""
        mock_global_object.cloud_api.send_otp = AsyncMock(return_value=True)
        mock_global_object.cloud_api.export_config_file = AsyncMock(return_value=False)

        from cync_controller.exporter import OTPRequest, submit_otp

        otp_request = OTPRequest(otp=123456)

        result = await submit_otp(otp_request)

        assert result["success"] is False
        assert "Failed to complete export" in result["message"]

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health_check endpoint"""
        from cync_controller.exporter import health_check

        result = await health_check()

        assert result["status"] == "ok"
        assert "Cync Export Server is running" in result["message"]

    @pytest.mark.asyncio
    async def test_download_config_file_exists(self, tmp_path):
        """Test download_config returns file when config exists"""
        config_file = tmp_path / "cync_mesh.yaml"
        config_file.write_text("test config")

        with patch("cync_controller.exporter.CYNC_CONFIG_FILE_PATH", str(config_file)):
            from cync_controller.exporter import download_config

            result = await download_config()

            # result should be a FileResponse instance
            from starlette.responses import FileResponse

            assert isinstance(result, FileResponse)
            assert hasattr(result, "path")
            assert result.path == str(config_file)

    @pytest.mark.asyncio
    async def test_download_config_file_missing(self, tmp_path):
        """Test download_config raises HTTPException when file missing"""
        missing_config = tmp_path / "missing.yaml"

        with patch("cync_controller.exporter.CYNC_CONFIG_FILE_PATH", str(missing_config)):
            from cync_controller.exporter import download_config

            with pytest.raises(Exception, match=r".*"):
                await download_config()

    @pytest.mark.asyncio
    async def test_restart_success(self, mock_global_object):
        """Test restart endpoint with valid supervisor token"""
        with (
            patch("cync_controller.exporter.os.environ") as mock_env,
            patch("cync_controller.exporter.aiohttp.ClientSession") as mock_session_class,
        ):
            mock_env.get.return_value = "test-token"

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value="OK")

            # session.post() returns a response object that itself acts as an async context manager
            mock_post_context = MagicMock()
            mock_post_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_context.__aexit__ = AsyncMock(return_value=None)

            mock_session = MagicMock()  # Use MagicMock not AsyncMock for session
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.post = MagicMock(return_value=mock_post_context)  # Use MagicMock here too
            mock_session_class.return_value = mock_session

            from cync_controller.exporter import restart

            result = await restart()

            assert result["success"] is True
            assert "restarting" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_restart_no_token(self):
        """Test restart fails without supervisor token"""
        with patch("cync_controller.exporter.os.environ") as mock_env:
            mock_env.get.return_value = None

            from cync_controller.exporter import restart

            result = await restart()

            assert result["success"] is False
            assert "Supervisor token" in result["message"]

    @pytest.mark.asyncio
    async def test_restart_supervisor_non_200_masked_error(self):
        """Test restart masks supervisor API failures"""
        with (
            patch("cync_controller.exporter.os.environ") as mock_env,
            patch("cync_controller.exporter.aiohttp.ClientSession") as mock_session_class,
        ):
            mock_env.get.return_value = "test-token"

            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value="Traceback: super secret stack trace")

            mock_post_context = MagicMock()
            mock_post_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_context.__aexit__ = AsyncMock(return_value=None)

            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.post = MagicMock(return_value=mock_post_context)
            mock_session_class.return_value = mock_session

            from cync_controller.exporter import restart

            with pytest.raises(HTTPException) as exc_info:
                await restart()

            detail = exc_info.value.detail
            assert "error_id" in detail
            assert "Failed to restart add-on" in detail["message"]
            assert "Traceback" not in detail["message"]

    @pytest.mark.asyncio
    async def test_restart_aiohttp_client_error_masked(self):
        """Test restart masks aiohttp client errors"""
        with (
            patch("cync_controller.exporter.os.environ") as mock_env,
            patch("cync_controller.exporter.aiohttp.ClientSession") as mock_session_class,
        ):
            mock_env.get.return_value = "test-token"

            mock_post_context = MagicMock()
            mock_post_context.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("boom"))
            mock_post_context.__aexit__ = AsyncMock(return_value=None)

            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.post = MagicMock(return_value=mock_post_context)
            mock_session_class.return_value = mock_session

            from cync_controller.exporter import restart

            with pytest.raises(HTTPException) as exc_info:
                await restart()

            detail = exc_info.value.detail
            assert "error_id" in detail
            assert "reach Supervisor API" in detail["message"]
            assert "boom" not in detail["message"]
