from typing import Final

class PacketMetadata:
    device_type: str
    firmware_version: str
    captured_at: str
    device_id: str
    operation: str
    notes: str
    def __init__(
        self,
        device_type: str,
        firmware_version: str,
        captured_at: str,
        device_id: str,
        operation: str,
        notes: str = ...,
    ) -> None: ...

HANDSHAKE_0x23_DEV_TO_CLOUD: Final[bytes]
HELLO_ACK_0x28_CLOUD_TO_DEV: Final[bytes]
HEARTBEAT_DEV_0xD3_DEV_TO_CLOUD: Final[bytes]
HEARTBEAT_CLOUD_0xD8_CLOUD_TO_DEV: Final[bytes]
STATUS_BROADCAST_0x83_DEV_TO_CLOUD: Final[bytes]
STATUS_ACK_0x88_CLOUD_TO_DEV: Final[bytes]
DEVICE_INFO_0x43_DEV_TO_CLOUD: Final[bytes]
INFO_ACK_0x48_CLOUD_TO_DEV: Final[bytes]
DATA_ACK_0x7B_DEV_TO_CLOUD: Final[bytes]
TOGGLE_ON_0x73_CLOUD_TO_DEV: Final[bytes]
TOGGLE_OFF_0x73_CLOUD_TO_DEV: Final[bytes]
STATUS_BROADCAST_0x83_FRAMED_4: Final[bytes]
STATUS_BROADCAST_0x83_FRAMED_5: Final[bytes]
STATUS_BROADCAST_0x83_FRAMED_6: Final[bytes]
STATUS_BROADCAST_0x83_FRAMED_7: Final[bytes]
STATUS_BROADCAST_0x83_FRAMED_8: Final[bytes]
STATUS_BROADCAST_0x83_FRAMED_9: Final[bytes]
STATUS_BROADCAST_0x83_FRAMED_10: Final[bytes]
STATUS_BROADCAST_0x83_FRAMED_11: Final[bytes]
