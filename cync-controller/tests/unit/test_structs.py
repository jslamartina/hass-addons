"""Unit tests for structs module.

Tests data structures including Pydantic models, dataclasses, and global object.
"""

import time
from unittest.mock import MagicMock

from cync_controller.structs import (
    CacheData,
    ControlMessageCallback,
    DeviceStatus,
    GlobalObject,
    GlobalObjEnv,
    MeshInfo,
    Messages,
    Tasks,
)


class TestGlobalObjEnv:
    """Tests for GlobalObjEnv Pydantic model."""

    def test_global_obj_env_creates_instance(self):
        """Test that GlobalObjEnv can be instantiated."""
        env = GlobalObjEnv()

        assert env is not None
        assert isinstance(env, GlobalObjEnv)

    def test_global_obj_env_default_values(self):
        """Test that GlobalObjEnv has sensible default values."""
        env = GlobalObjEnv()

        # All fields should default to None or their configured values
        assert env.account_username is None
        assert env.account_password is None
        assert env.mqtt_host is None

    def test_global_obj_env_with_values(self):
        """Test setting GlobalObjEnv values."""
        env = GlobalObjEnv(
            account_username="testuser",
            account_password="testpass",
            mqtt_host="localhost",
            mqtt_port=1883,
        )

        assert env.account_username == "testuser"
        assert env.account_password == "testpass"
        assert env.mqtt_host == "localhost"
        assert env.mqtt_port == 1883


class TestGlobalObject:
    """Tests for GlobalObject singleton."""

    def test_global_object_creates_instance(self):
        """Test that GlobalObject can be instantiated."""
        g = GlobalObject()

        assert g is not None
        assert isinstance(g, GlobalObject)

    def test_global_object_has_env(self):
        """Test that GlobalObject has env attribute."""
        g = GlobalObject()

        assert hasattr(g, "env")
        assert isinstance(g.env, GlobalObjEnv)


class TestTasks:
    """Tests for Tasks dataclass."""

    def test_tasks_initialization(self):
        """Test Tasks dataclass creation."""
        tasks = Tasks()

        assert tasks.receive is None
        assert tasks.send is None
        assert tasks.callback_cleanup is None

    def test_tasks_iteration(self):
        """Test that Tasks is iterable."""
        tasks = Tasks()

        task_list = list(tasks)

        assert task_list == [None, None, None]


class TestControlMessageCallback:
    """Tests for ControlMessageCallback class."""

    def test_control_message_callback_creation(self):
        """Test creating ControlMessageCallback."""
        callback = MagicMock()
        cmsg = ControlMessageCallback(
            msg_id=0x01,
            message=b"\x00\x01\x02",
            sent_at=time.time(),
            callback=callback,
            device_id=0x1234,
        )

        assert cmsg.id == 0x01
        assert cmsg.message == b"\x00\x01\x02"
        assert cmsg.device_id == 0x1234
        assert cmsg.callback is callback

    def test_control_message_callback_elapsed_property(self):
        """Test elapsed time property."""
        callback = MagicMock()
        sent_time = time.time() - 1.0  # Sent 1 second ago

        cmsg = ControlMessageCallback(
            msg_id=0x01,
            message=b"",
            sent_at=sent_time,
            callback=callback,
        )

        # Should be approximately 1.0 second elapsed
        assert 0.95 < cmsg.elapsed < 1.5

    def test_control_message_callback_string_representation(self):
        """Test string representation."""
        callback = MagicMock()
        cmsg = ControlMessageCallback(
            msg_id=0x42,
            message=b"",
            sent_at=time.time(),
            callback=callback,
        )

        string_repr = str(cmsg)

        assert "0x42" in string_repr or "66" in string_repr  # 0x42 = 66
        assert "elapsed" in string_repr.lower()

    def test_control_message_callback_equality(self):
        """Test equality comparison."""
        callback = MagicMock()
        cmsg = ControlMessageCallback(
            msg_id=0x01,
            message=b"",
            sent_at=time.time(),
            callback=callback,
        )

        # Should equal its ID
        assert cmsg == 0x01
        assert cmsg != 0x02

    def test_control_message_callback_hash(self):
        """Test that ControlMessageCallback is hashable."""
        callback = MagicMock()
        cmsg = ControlMessageCallback(
            msg_id=0x01,
            message=b"",
            sent_at=time.time(),
            callback=callback,
        )

        # Should be able to use in set/dict
        callback_set = {cmsg}
        assert len(callback_set) == 1

    def test_control_message_callback_call(self):
        """Test calling the callback."""
        mock_callback = MagicMock()
        cmsg = ControlMessageCallback(
            msg_id=0x01,
            message=b"",
            sent_at=time.time(),
            callback=mock_callback,
        )

        result = cmsg()

        assert result is mock_callback

    def test_control_message_callback_call_without_callback(self):
        """Test calling when no callback set."""
        cmsg = ControlMessageCallback(
            msg_id=0x01,
            message=b"",
            sent_at=time.time(),
            callback=None,
        )

        result = cmsg()

        assert result is None

    def test_control_message_callback_retry_count(self):
        """Test retry count initialization."""
        callback = MagicMock()
        cmsg = ControlMessageCallback(
            msg_id=0x01,
            message=b"",
            sent_at=time.time(),
            callback=callback,
            max_retries=5,
        )

        assert cmsg.retry_count == 0
        assert cmsg.max_retries == 5


class TestMessages:
    """Tests for Messages class."""

    def test_messages_initialization(self):
        """Test Messages class creation."""
        messages = Messages()

        assert hasattr(messages, "control")
        assert isinstance(messages.control, dict)
        assert len(messages.control) == 0

    def test_messages_add_control_message(self):
        """Test adding control message to Messages."""
        messages = Messages()
        callback = MagicMock()
        cmsg = ControlMessageCallback(
            msg_id=0x01,
            message=b"",
            sent_at=time.time(),
            callback=callback,
        )

        messages.control[0x01] = cmsg

        assert 0x01 in messages.control
        assert messages.control[0x01] is cmsg


class TestCacheData:
    """Tests for CacheData dataclass."""

    def test_cache_data_initialization(self):
        """Test CacheData dataclass creation."""
        cache = CacheData()

        assert cache.all_data == b""
        assert cache.timestamp == 0
        assert cache.data == b""
        assert cache.data_len == 0
        assert cache.needed_len == 0

    def test_cache_data_with_values(self):
        """Test CacheData with values."""
        cache = CacheData(
            all_data=b"\x01\x02\x03",
            timestamp=123.456,
            data=b"\x04\x05",
            data_len=2,
            needed_len=10,
        )

        assert cache.all_data == b"\x01\x02\x03"
        assert cache.timestamp == 123.456
        assert cache.data == b"\x04\x05"
        assert cache.data_len == 2
        assert cache.needed_len == 10


class TestDeviceStatus:
    """Tests for DeviceStatus Pydantic model."""

    def test_device_status_initialization(self):
        """Test DeviceStatus creation with defaults."""
        status = DeviceStatus()

        assert status.state is None
        assert status.brightness is None
        assert status.temperature is None
        assert status.red is None
        assert status.green is None
        assert status.blue is None

    def test_device_status_with_values(self):
        """Test DeviceStatus with values."""
        status = DeviceStatus(
            state=1,
            brightness=128,
            temperature=2700,
            red=255,
            green=200,
            blue=150,
        )

        assert status.state == 1
        assert status.brightness == 128
        assert status.temperature == 2700
        assert status.red == 255
        assert status.green == 200
        assert status.blue == 150

    def test_device_status_partial_values(self):
        """Test DeviceStatus with partial values."""
        status = DeviceStatus(state=1, brightness=75)

        assert status.state == 1
        assert status.brightness == 75
        assert status.temperature is None
        assert status.red is None


class TestMeshInfo:
    """Tests for MeshInfo dataclass."""

    def test_mesh_info_initialization(self):
        """Test MeshInfo dataclass creation."""
        mesh_info = MeshInfo(status=[[1, 2, 3]], id_from=0x1234)

        assert mesh_info.status == [[1, 2, 3]]
        assert mesh_info.id_from == 0x1234

    def test_mesh_info_with_complex_status(self):
        """Test MeshInfo with complex status structure."""
        status_data = [[1, 2, None], [None, 3, 4]]
        mesh_info = MeshInfo(status=status_data, id_from=0x5678)

        assert mesh_info.status == status_data
        assert mesh_info.id_from == 0x5678

    def test_mesh_info_with_empty_status(self):
        """Test MeshInfo with empty status."""
        mesh_info = MeshInfo(status=[], id_from=0xABCD)

        assert mesh_info.status == []
        assert mesh_info.id_from == 0xABCD
