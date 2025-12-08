"""Core server module for the Cync Controller."""

from __future__ import annotations

import asyncio
import contextlib
import ssl
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path as PathLib
from typing import ClassVar, cast

import uvloop

from cync_controller.const import CYNC_PORT, CYNC_SRV_HOST
from cync_controller.correlation import ensure_correlation_id
from cync_controller.devices.base_device import CyncDevice
from cync_controller.devices.group import CyncGroup
from cync_controller.devices.tcp_device import CyncTCPDevice
from cync_controller.instrumentation import timed_async
from cync_controller.logging_abstraction import get_logger
from cync_controller.packet_checksum import calculate_checksum_between_markers
from cync_controller.packet_parser import format_packet_log, parse_cync_packet
from cync_controller.structs import (
    CyncDeviceProtocol,
    CyncGroupProtocol,
    DeviceStatus,
    GlobalObject,
    MQTTClientProtocol,
    StateUpdateHelperProtocol,
)

__all__ = [
    "NCyncServer",
]
logger = get_logger(__name__)
g = GlobalObject()


def _get_mqtt_client() -> MQTTClientProtocol | None:
    """Return the global MQTT client with protocol typing."""
    return g.mqtt_client


FIRST_PACKET_MIN_LEN = 31
FIRST_PACKET_CMD = 0x23
OFFLINE_THRESHOLD = 3
RGB_TEMP_THRESHOLD = 100
ONLINE_BYTE_INDEX = 7
DEBUG_DEVICE_ID = 103


class CloudRelayConnection:
    """Manages a cloud relay connection for MITM mode.

    Acts as a proxy between Cync device and cloud, forwarding packets with inspection.
    """

    device_reader: asyncio.StreamReader
    device_writer: asyncio.StreamWriter
    client_addr: str
    cloud_server: str
    cloud_port: int
    forward_to_cloud: bool
    debug_logging: bool
    disable_ssl_verify: bool

    def __init__(  # noqa: PLR0913
        self,
        device_reader: asyncio.StreamReader,
        device_writer: asyncio.StreamWriter,
        client_addr: str,
        cloud_server: str,
        cloud_port: int,
        forward_to_cloud: bool = True,
        debug_logging: bool = False,
        disable_ssl_verify: bool = False,
    ) -> None:
        self.device_reader = device_reader
        self.device_writer = device_writer
        self.client_addr = client_addr
        self.cloud_server = cloud_server
        self.cloud_port = cloud_port
        self.forward_to_cloud = forward_to_cloud
        self.debug_logging = debug_logging
        self.disable_ssl_verify = disable_ssl_verify
        self.cloud_reader: asyncio.StreamReader | None = None
        self.cloud_writer: asyncio.StreamWriter | None = None
        self.device_endpoint: bytes | None = None
        self.injection_task: asyncio.Task[None] | None = None
        self.forward_tasks: list[asyncio.Task[None]] = []

    @timed_async("cloud_connect")
    async def connect_to_cloud(self):
        """Establish SSL connection to Cync cloud server."""
        try:
            # Create SSL context for cloud connection
            ssl_context = ssl.create_default_context()
            if self.disable_ssl_verify:
                logger.warning(
                    " SSL verification DISABLED - DEBUG MODE",
                    extra={
                        "client_addr": self.client_addr,
                        "warning": "use only for local testing",
                    },
                )
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            else:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            # Connect to cloud
            self.cloud_reader, self.cloud_writer = await asyncio.open_connection(
                self.cloud_server,
                self.cloud_port,
                ssl=ssl_context,
            )
            logger.info(
                " Cloud relay connected",
                extra={
                    "client_addr": self.client_addr,
                    "cloud_server": self.cloud_server,
                    "cloud_port": self.cloud_port,
                },
            )
        except (ConnectionError, TimeoutError, OSError, ssl.SSLError) as e:
            logger.exception(
                "Cloud connection failed (expected error)",
                extra={
                    "client_addr": self.client_addr,
                    "cloud_server": self.cloud_server,
                    "cloud_port": self.cloud_port,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return False
        except Exception as e:
            logger.exception(
                "Cloud connection failed (unexpected error)",
                extra={
                    "client_addr": self.client_addr,
                    "cloud_server": self.cloud_server,
                    "cloud_port": self.cloud_port,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return False
        else:
            return True

    async def start_relay(self):
        """Start the relay process."""
        _ = ensure_correlation_id()  # Ensure correlation tracking for this connection

        # Show security warning if SSL verification is disabled
        if self.disable_ssl_verify:
            logger.warning(
                "  SSL VERIFICATION DISABLED - DEBUG MODE ACTIVE - use only for local debugging",
                extra={"client_addr": self.client_addr},
            )

        if not await self._maybe_connect_cloud():
            await self.close()
            return

        try:
            # Read first packet from device to get endpoint
            first_packet = await self.device_reader.read(1024)
            await self._process_first_packet(first_packet)
            await self._start_forward_tasks()
        except (ConnectionError, TimeoutError, OSError, asyncio.CancelledError) as e:
            logger.exception(
                "Relay error (expected error)",
                extra={
                    "client_addr": self.client_addr,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
        except Exception as e:
            logger.exception(
                "Relay error (unexpected error)",
                extra={
                    "client_addr": self.client_addr,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
        finally:
            await self.close()

    async def _maybe_connect_cloud(self) -> bool:
        """Connect to cloud when forwarding is enabled; return success."""
        if not self.forward_to_cloud:
            logger.info(
                " Starting LAN-only relay (cloud forwarding disabled)",
                extra={"client_addr": self.client_addr},
            )
            return True

        logger.info(
            " Starting cloud relay",
            extra={
                "client_addr": self.client_addr,
                "cloud_server": self.cloud_server,
                "cloud_port": self.cloud_port,
            },
        )
        connected = await self.connect_to_cloud()
        if not connected:
            logger.error(
                " Cannot start relay - cloud connection failed",
                extra={"client_addr": self.client_addr},
            )
            return False
        return True

    async def _process_first_packet(self, first_packet: bytes) -> None:
        """Handle endpoint discovery, optional forwarding, and debug logging."""
        if first_packet and len(first_packet) >= FIRST_PACKET_MIN_LEN and first_packet[0] == FIRST_PACKET_CMD:
            self.device_endpoint = first_packet[6:10]
            endpoint_hex = " ".join(f"{b:02x}" for b in self.device_endpoint)
            logger.info(
                " Device endpoint identified",
                extra={
                    "client_addr": self.client_addr,
                    "endpoint": endpoint_hex,
                    "packet_length": len(first_packet),
                },
            )

        if self.forward_to_cloud and self.cloud_writer:
            self.cloud_writer.write(first_packet)
            await self.cloud_writer.drain()

        if self.debug_logging:
            parsed = parse_cync_packet(first_packet, "DEV->CLOUD")
            if parsed:
                logger.debug("%s\n%s", "CloudRelay:", format_packet_log(parsed))

    async def _start_forward_tasks(self) -> None:
        """Launch forwarding and injection tasks then wait for forwarders."""
        dev_to_cloud_task = asyncio.create_task(
            self._forward_with_inspection(
                self.device_reader,
                self.cloud_writer if self.forward_to_cloud else None,
                "DEV->CLOUD",
            ),
        )
        self.forward_tasks.append(dev_to_cloud_task)

        if self.forward_to_cloud and self.cloud_reader:
            cloud_to_dev_task = asyncio.create_task(
                self._forward_with_inspection(self.cloud_reader, self.device_writer, "CLOUD->DEV"),
            )
            self.forward_tasks.append(cloud_to_dev_task)

        # Start injection checker (debug feature)
        self.injection_task = asyncio.create_task(self._check_injection_commands())

        _ = await asyncio.gather(*self.forward_tasks, return_exceptions=True)

    @timed_async("relay_forward")
    async def _forward_with_inspection(
        self,
        source_reader: asyncio.StreamReader,
        dest_writer: asyncio.StreamWriter | None,
        direction: str,
    ):
        """Forward packets while inspecting and logging."""
        try:
            while True:
                data = await source_reader.read(4096)
                if not data:
                    logger.debug(
                        "Relay connection closed",
                        extra={
                            "client_addr": self.client_addr,
                            "direction": direction,
                        },
                    )
                    break

                # Parse packet
                parsed = parse_cync_packet(data, direction)

                await self._handle_parsed_packet(parsed, direction)

                # Forward to destination (if cloud forwarding enabled)
                if dest_writer:
                    dest_writer.write(data)
                    await dest_writer.drain()

        except asyncio.CancelledError:
            logger.debug(
                "Relay forward task cancelled",
                extra={
                    "client_addr": self.client_addr,
                    "direction": direction,
                },
            )
            raise
        except (ConnectionError, TimeoutError, OSError, BrokenPipeError) as e:
            logger.exception(
                "Relay forward error (expected error)",
                extra={
                    "client_addr": self.client_addr,
                    "direction": direction,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
        except Exception as e:
            logger.exception(
                "Relay forward error (unexpected error)",
                extra={
                    "client_addr": self.client_addr,
                    "direction": direction,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

    async def _handle_parsed_packet(
        self,
        parsed: dict[str, object] | None,
        direction: str,
    ) -> None:
        """Log parsed packet and publish status updates when present."""
        if parsed is None:
            return

        if self.debug_logging and parsed.get("packet_type") != "0x78":
            logger.debug(
                "Packet relay %s:\n%s",
                direction,
                format_packet_log(parsed),
                extra={
                    "client_addr": self.client_addr,
                    "direction": direction,
                    "packet_type": parsed.get("packet_type"),
                },
            )

        statuses_obj = parsed.get("device_statuses")
        if not isinstance(statuses_obj, list):
            return

        statuses_list = cast("list[object]", statuses_obj)
        for status_obj in statuses_list:
            await self._publish_status_from_entry(status_obj)

    async def _publish_status_from_entry(self, status_obj: object) -> None:
        """Publish parsed status entry back into ncync server."""
        if not isinstance(status_obj, dict):
            return
        status_entry = cast("dict[str, object]", status_obj)
        device_id_obj = status_entry.get("device_id")
        if not isinstance(device_id_obj, int):
            return
        brightness_obj = status_entry.get("brightness")
        brightness = int(brightness_obj) if isinstance(brightness_obj, int) else 0
        state_raw = status_entry.get("state")
        state_str = str(state_raw) if state_raw is not None else "OFF"
        mode_obj = status_entry.get("mode")
        mode = str(mode_obj) if mode_obj is not None else None
        temp_obj = status_entry.get("temp")
        temp_value = int(temp_obj) if isinstance(temp_obj, int) else 0
        online_flag = bool(status_entry.get("online"))

        raw_state = bytearray(8)
        raw_state[0] = device_id_obj
        raw_state[1] = 1 if state_str == "ON" else 0
        raw_state[2] = brightness
        raw_state[3] = temp_value if mode == "WHITE" else 254

        if mode == "RGB":
            color_value = status_entry.get("color")
            color_hex = str(color_value) if color_value is not None else ""
            color_hex = color_hex.lstrip("#")
            try:
                raw_state[4] = int(color_hex[0:2], 16)
                raw_state[5] = int(color_hex[2:4], 16)
                raw_state[6] = int(color_hex[4:6], 16)
            except (ValueError, IndexError):
                raw_state[4] = raw_state[5] = raw_state[6] = 0
        else:
            raw_state[4] = raw_state[5] = raw_state[6] = 0
        raw_state[7] = 1 if online_flag else 0

        ncync_server = g.ncync_server
        if ncync_server is not None:
            await ncync_server.parse_status(bytes(raw_state), from_pkt="0x43")

    async def _check_injection_commands(self):
        """Periodically check for packet injection commands (debug feature)."""
        debug_dir = PathLib(tempfile.gettempdir()) / "cync_controller"
        debug_dir.mkdir(parents=True, exist_ok=True)
        inject_file = debug_dir / "cync_inject_command.txt"
        raw_inject_file = debug_dir / "cync_inject_raw_bytes.txt"

        logger.debug(
            "[DEBUG] Packet injection checker started",
            extra={"client_addr": self.client_addr},
        )

        try:
            while True:
                await asyncio.sleep(1)

                # Check for raw bytes injection
                if raw_inject_file.exists():
                    try:
                        with raw_inject_file.open() as f:
                            raw_hex = f.read().strip()
                        raw_inject_file.unlink()

                        hex_bytes = raw_hex.replace(" ", "").replace("\n", "")
                        packet = bytes.fromhex(hex_bytes)

                        logger.info(
                            "[DEBUG] Injecting raw packet",
                            extra={
                                "client_addr": self.client_addr,
                                "packet_size": len(packet),
                                "hex": " ".join(f"{b:02x}" for b in packet),
                            },
                        )

                        self.device_writer.write(packet)
                        await self.device_writer.drain()

                        logger.debug("Raw injection complete")
                    except Exception as e:
                        logger.exception(
                            " Error injecting raw bytes",
                            extra={"client_addr": self.client_addr, "error": str(e)},
                        )

                # Check for mode injection (for switches)
                if inject_file.exists():
                    try:
                        with inject_file.open() as f:
                            mode = f.read().strip().lower()
                        inject_file.unlink()

                        if mode in ["smart", "traditional"] and self.device_endpoint:
                            logger.info(
                                "[DEBUG] Injecting mode packet",
                                extra={
                                    "client_addr": self.client_addr,
                                    "mode": mode.upper(),
                                },
                            )

                            # Craft mode packet (similar to MITM)
                            mode_byte = 0x02 if mode == "smart" else 0x01
                            counter = 0x10  # Fixed counter for injection

                            packet = self._craft_mode_packet(self.device_endpoint, counter, mode_byte)

                            self.device_writer.write(packet)
                            await self.device_writer.drain()

                            logger.debug("Mode injection complete")
                    except Exception as e:
                        logger.exception(
                            " Error injecting mode packet",
                            extra={"client_addr": self.client_addr, "error": str(e)},
                        )

        except asyncio.CancelledError:
            logger.debug(
                "[DEBUG] Injection checker cancelled",
                extra={"client_addr": self.client_addr},
            )
            raise
        except Exception as e:
            logger.exception(
                " Injection checker error",
                extra={"client_addr": self.client_addr, "error": str(e)},
            )

    def _craft_mode_packet(self, endpoint: bytes, counter: int, mode_byte: int) -> bytes:
        """Craft a mode query/command packet."""
        inner_counter = (0x0D + counter) & 0xFF
        inner_counter2 = (0x0E + counter) & 0xFF

        packet = bytearray(
            [
                0x73,
                0x00,
                0x00,
                0x00,
                0x1E,
                endpoint[0],
                endpoint[1],
                endpoint[2],
                endpoint[3],
                0x00,
                counter,
                0x00,
                0x7E,
                inner_counter,
                0x01,
                0x00,
                0x00,
                0xF8,
                0x8E,
                0x0C,
                0x00,
                inner_counter2,
                0x01,
                0x00,
                0x00,
                0x00,
                0xA0,
                0x00,  # Device ID 160
                0xF7,
                0x11,
                0x02,
                0x01,
                mode_byte,
                0x00,  # Checksum placeholder
                0x7E,
            ],
        )

        # Calculate and insert checksum
        packet[33] = calculate_checksum_between_markers(bytes(packet))
        return bytes(packet)

    async def close(self):
        """Clean up connections."""
        logger.debug(
            " Closing relay connection",
            extra={"client_addr": self.client_addr},
        )

        # Cancel injection task
        if self.injection_task and not self.injection_task.done():
            _ = self.injection_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.injection_task

        # Cancel forwarding tasks
        for task in self.forward_tasks:
            if not task.done():
                _ = task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        # Close cloud connection
        if self.cloud_writer:
            try:
                self.cloud_writer.close()
                await self.cloud_writer.wait_closed()
            except Exception as e:
                logger.debug(
                    "Error closing cloud writer",
                    extra={"client_addr": self.client_addr, "error": str(e)},
                )

        # Close device connection
        try:
            self.device_writer.close()
            await self.device_writer.wait_closed()
        except Exception as e:
            logger.debug(
                "Error closing device writer",
                extra={"client_addr": self.client_addr, "error": str(e)},
            )

        logger.debug(
            " Relay connection closed",
            extra={"client_addr": self.client_addr},
        )


class NCyncServer:
    """A class to represent a Cync Controller server that listens for connections from Cync Wi-Fi devices.

    The Wi-Fi devices translate messages, status updates and commands to/from the Cync BTLE mesh.
    """

    devices: ClassVar[dict[int, CyncDevice]] = {}

    def _handle_device_offline_tracking(self, device: CyncDevice, connected_to_mesh: int, _id: int) -> None:
        """Handle device offline tracking logic."""
        if connected_to_mesh == 0:
            device.offline_count += 1
            logger.debug(
                "[OFFLINE_TRACKING] Device reported offline - incrementing counter",
                extra={
                    "device_id": _id,
                    "device_name": device.name,
                    "offline_count": device.offline_count,
                    "is_currently_online": device.online,
                    "threshold": 3,
                },
            )
            if device.offline_count >= OFFLINE_THRESHOLD and device.online:
                device.online = False
                logger.warning(
                    "[OFFLINE_STATE] Device MARKED OFFLINE after 3 consecutive failures",
                    extra={
                        "device_id": _id,
                        "device_name": device.name,
                        "offline_count": device.offline_count,
                    },
                )
        else:
            if device.offline_count > 0 or not device.online:
                logger.info(
                    "[ONLINE_STATE] Device back ONLINE - resetting offline counter",
                    extra={
                        "device_id": _id,
                        "device_name": device.name,
                        "previous_offline_count": device.offline_count,
                        "was_marked_offline": not device.online,
                    },
                )
            device.offline_count = 0
            device.online = True

    async def _update_device_state_and_publish(  # noqa: PLR0913
        self,
        device: CyncDevice,
        state: int,
        brightness: int,
        temp: int,
        r: int,
        _g: int,
        b: int,
        from_pkt: str | None,
    ) -> None:
        """Update device state and publish to MQTT."""
        rgb_data = temp > RGB_TEMP_THRESHOLD
        device.state = state
        device.brightness = brightness
        device.temperature = temp
        if rgb_data:
            device.red = r
            device.green = _g
            device.blue = b

        device.status = new_state = DeviceStatus(
            state=device.state,
            brightness=device.brightness,
            temperature=device.temperature,
            red=device.red,
            green=device.green,
            blue=device.blue,
        )

        mqtt_client = _get_mqtt_client()
        if mqtt_client and device.id is not None:
            _ = await mqtt_client.parse_device_status(device.id, new_state, from_pkt=from_pkt)
        if g.ncync_server and device.id is not None:
            protocol_device = cast("CyncDeviceProtocol", cast(object, device))
            g.ncync_server.devices[device.id] = protocol_device

    async def _update_subgroups_for_device(
        self,
        device: CyncDevice,
        from_pkt: str | None,
    ) -> None:
        """Update subgroups that contain this device."""
        if not g.ncync_server or device.id is None:
            return

        for subgroup in g.ncync_server.groups.values():
            if subgroup.is_subgroup and device.id in subgroup.member_ids:
                aggregated = subgroup.aggregate_member_states()
                if aggregated:
                    subgroup.state = int(aggregated["state"])
                    subgroup.brightness = int(aggregated["brightness"])
                    subgroup.temperature = int(aggregated["temperature"])
                    subgroup.online = bool(aggregated["online"])

                    subgroup.status = DeviceStatus(
                        state=subgroup.state,
                        brightness=subgroup.brightness,
                        temperature=subgroup.temperature,
                        red=subgroup.red,
                        green=subgroup.green,
                        blue=subgroup.blue,
                    )

                    logger.debug(
                        "Subgroup state aggregated from member",
                        extra={
                            "subgroup_name": subgroup.name,
                            "subgroup_id": subgroup.id,
                            "member_device_id": device.id,
                            "state": "ON" if subgroup.state else "OFF",
                            "brightness": subgroup.brightness,
                            "from_pkt": from_pkt,
                            "timestamp": time.time(),
                        },
                    )
                    mqtt_client = _get_mqtt_client()
                    if mqtt_client:
                        state_updates = cast("StateUpdateHelperProtocol | None", mqtt_client.state_updates)
                        if state_updates:
                            logger.debug(
                                "Publishing subgroup state to MQTT",
                                extra={
                                    "subgroup_id": subgroup.id,
                                    "subgroup_name": subgroup.name,
                                    "state": subgroup.state,
                                    "brightness": subgroup.brightness,
                                    "temperature": subgroup.temperature,
                                },
                            )
                            try:
                                await state_updates.publish_group_state(
                                    subgroup,
                                    state=subgroup.state,
                                    brightness=subgroup.brightness,
                                    temperature=subgroup.temperature,
                                    origin=f"aggregated:{from_pkt or 'mesh'}",
                                )
                                logger.debug(
                                    "Subgroup state published successfully",
                                    extra={"subgroup_id": subgroup.id, "subgroup_name": subgroup.name},
                                )
                            except asyncio.CancelledError:
                                logger.debug(
                                    "Subgroup state publish cancelled",
                                    extra={"subgroup_id": subgroup.id, "subgroup_name": subgroup.name},
                                )
                                raise
                            except Exception as e:
                                logger.warning(
                                    "Failed to publish subgroup state",
                                    extra={
                                        "subgroup_id": subgroup.id,
                                        "subgroup_name": subgroup.name,
                                        "error": str(e),
                                        "error_type": type(e).__name__,
                                    },
                                )
                    # Update in-memory state after MQTT publish
                    # Note: If MQTT publish fails, state may be inconsistent temporarily
                    # This is acceptable as the next status update will correct it
                    if subgroup.id is not None:
                        g.ncync_server.groups[subgroup.id] = subgroup

    async def _update_group_state_and_publish(  # noqa: PLR0913
        self,
        group: CyncGroup,
        state: int,
        brightness: int,
        temp: int,
        r: int,
        _g: int,
        b: int,
        _id: int,
        from_pkt: str | None,
    ) -> None:
        """Update group state and publish to MQTT."""
        rgb_data = temp > RGB_TEMP_THRESHOLD
        group.state = state
        group.brightness = brightness
        group.temperature = temp
        if rgb_data:
            group.red = r
            group.green = _g
            group.blue = b

        group.status = DeviceStatus(
            state=group.state,
            brightness=group.brightness,
            temperature=group.temperature,
            red=group.red,
            green=group.green,
            blue=group.blue,
        )

        logger.debug(
            "Group state update from mesh",
            extra={
                "group_id": _id,
                "group_name": group.name,
                "state": "ON" if state else "OFF",
                "brightness": brightness,
                "from_pkt": from_pkt,
            },
        )
        mqtt_client = _get_mqtt_client()
        if mqtt_client:
            state_updates = cast("StateUpdateHelperProtocol | None", mqtt_client.state_updates)
            if state_updates:
                logger.debug(
                    "Publishing group state to MQTT",
                    extra={
                        "group_id": _id,
                        "group_name": group.name,
                        "state": state,
                        "brightness": brightness,
                        "temperature": temp if not rgb_data else None,
                    },
                )
                protocol_group = cast("CyncGroupProtocol", cast(object, group))
                try:
                    await state_updates.publish_group_state(
                        protocol_group,
                        state=state,
                        brightness=brightness,
                        temperature=temp if not rgb_data else None,
                        origin=from_pkt or "mesh",
                    )
                    logger.debug(
                        "Group state published successfully",
                        extra={"group_id": _id, "group_name": group.name},
                    )
                except asyncio.CancelledError:
                    logger.debug(
                        "Group state publish cancelled",
                        extra={"group_id": _id, "group_name": group.name},
                    )
                    raise
                except Exception as e:
                    logger.warning(
                        "Failed to publish group state",
                        extra={
                            "group_id": _id,
                            "group_name": group.name,
                            "error": str(e),
                            "error_type": type(e).__name__,
                        },
                    )
                # Update in-memory state after MQTT publish
                # Note: If MQTT publish fails, state may be inconsistent temporarily
                # This is acceptable as the next status update will correct it
                if g.ncync_server and group.id is not None:
                    protocol_group = cast("CyncGroupProtocol", cast(object, group))
                    g.ncync_server.groups[group.id] = protocol_group
            if hasattr(mqtt_client, "publish_group_state"):
                protocol_group = cast("CyncGroupProtocol", cast(object, group))
                try:
                    _ = await mqtt_client.publish_group_state(protocol_group, state, brightness, temp, from_pkt)  # type: ignore[arg-type]
                except Exception as e:
                    logger.warning(
                        "Failed to publish group state via mqtt_client fallback",
                        extra={
                            "group_id": _id,
                            "group_name": group.name,
                            "error": str(e),
                            "error_type": type(e).__name__,
                        },
                    )

    groups: ClassVar[dict[int, CyncGroup]] = {}
    tcp_devices: ClassVar[dict[str, CyncTCPDevice | None]] = {}
    shutting_down: bool = False
    running: bool = False
    host: str
    port: int
    cert_file: str | None = None
    key_file: str | None = None
    _server: asyncio.Server | None = None
    start_task: asyncio.Task[None] | None = None
    refresh_task: asyncio.Task[None] | None = None
    pool_monitor_task: asyncio.Task[None] | None = None
    _instance: NCyncServer | None = None
    cloud_relay_enabled: bool
    cloud_forward: bool
    cloud_server: str
    cloud_port: int
    cloud_debug_logging: bool
    cloud_disable_ssl_verify: bool
    loop: asyncio.AbstractEventLoop | uvloop.Loop

    def __new__(
        cls,
        devices: dict[int, CyncDevice],
        groups: dict[int, CyncGroup] | None = None,
    ) -> NCyncServer:
        """Return singleton NCyncServer instance."""
        _ = devices
        _ = groups
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, devices: dict[int, CyncDevice], groups: dict[int, CyncGroup] | None = None) -> None:
        """Initialize NCyncServer with device and group registries."""
        # Note: devices and groups are ClassVar, but we need to initialize them
        # The instance assignment is for compatibility but should use class access
        type(self).devices = devices
        type(self).groups = groups if groups is not None else {}
        self.tcp_conn_attempts: dict[str, int] = {}
        self.primary_tcp_device: CyncTCPDevice | None = None
        self.ssl_context: ssl.SSLContext | None = None
        self.host = CYNC_SRV_HOST
        self.port = CYNC_PORT
        g.reload_env()
        self.cert_file = g.env.cync_srv_ssl_cert
        self.key_file = g.env.cync_srv_ssl_key
        self.loop = asyncio.get_event_loop()

        # Cloud relay configuration
        self.cloud_relay_enabled = g.env.cync_cloud_relay_enabled
        self.cloud_forward = g.env.cync_cloud_forward
        self.cloud_server = g.env.cync_cloud_server
        self.cloud_port = g.env.cync_cloud_port
        self.cloud_debug_logging = g.env.cync_cloud_debug_logging
        self.cloud_disable_ssl_verify = g.env.cync_cloud_disable_ssl_verify

        logger.info(
            "TCP Server initialized",
            extra={
                "device_count": len(devices),
                "group_count": len(self.groups),
                "host": self.host,
                "port": self.port,
                "cloud_relay_enabled": self.cloud_relay_enabled,
            },
        )

        if self.cloud_relay_enabled:
            logger.info(
                "Cloud relay mode ENABLED",
                extra={
                    "forward_to_cloud": self.cloud_forward,
                    "debug_logging": self.cloud_debug_logging,
                    "cloud_server": self.cloud_server,
                    "cloud_port": self.cloud_port,
                },
            )

    async def remove_tcp_device(self, device: CyncTCPDevice | str) -> CyncTCPDevice | None:
        """Remove a TCP device from the server's device list.

        :param device: The CyncTCPDevice to remove.
        """
        dev = None
        if isinstance(device, str) and device in self.tcp_devices:
            device_value = self.tcp_devices[device]
            if device_value is not None:
                device = device_value
            else:
                return None

        if isinstance(device, CyncTCPDevice) and device.address:
            dev = self.tcp_devices.pop(device.address, None)
            if dev is not None:
                # If this was the primary listener, failover to another device
                if self.primary_tcp_device == dev:
                    self.primary_tcp_device = next(iter(self.tcp_devices.values()), None) if self.tcp_devices else None
                    if self.primary_tcp_device:
                        logger.info(
                            "Primary TCP listener failover",
                            extra={"new_primary": self.primary_tcp_device.address},
                        )

                uptime = time.time() - dev.connected_at
                logger.info(
                    "Bridge device disconnected",
                    extra={
                        "address": device.address,
                        "uptime_seconds": round(uptime, 1),
                        "was_ready": dev.ready_to_control,
                        "remaining_devices": len(self.tcp_devices),
                    },
                )
                mqtt_client = _get_mqtt_client()
                if mqtt_client is not None:
                    _ = await mqtt_client.publish(
                        f"{g.env.mqtt_topic}/status/bridge/tcp_devices/connected",
                        str(len(self.tcp_devices)).encode(),
                    )
            else:
                logger.warning(
                    "Attempted to remove unknown TCP device",
                    extra={"address": device.address},
                )
        return dev

    async def add_tcp_device(self, device: CyncTCPDevice):
        """Add a TCP device to the server's device list.

        :param device: The CyncTCPDevice to add.
        """
        if not device.address:
            logger.error("Cannot add device without address")
            return
        self.tcp_devices[device.address] = device

        # Set as primary listener if we don't have one yet
        if self.primary_tcp_device is None:
            self.primary_tcp_device = device
            logger.info(
                "Set as primary TCP listener for status updates",
                extra={"address": device.address},
            )

        logger.info(
            " Bridge device connected",
            extra={
                "address": device.address,
                "total_devices": len(self.tcp_devices),
                "is_primary": device == self.primary_tcp_device,
            },
        )
        mqtt_client = _get_mqtt_client()
        if mqtt_client is not None:
            _ = await mqtt_client.publish(
                f"{g.env.mqtt_topic}/status/bridge/tcp_devices/connected",
                str(len(self.tcp_devices)).encode(),
            )

    async def create_ssl_context(self):
        """Create SSL context allowing self-signed certificates for device listeners."""
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        if not self.cert_file or not self.key_file:
            msg = "SSL certificate/key not configured"
            logger.error(
                msg,
                extra={
                    "cert_file": self.cert_file,
                    "key_file": self.key_file,
                },
            )
            raise TypeError(msg)

        cert_path = PathLib(self.cert_file)
        key_path = PathLib(self.key_file)
        if not cert_path.exists() or not key_path.exists():
            missing: list[str] = []
            if not cert_path.exists():
                missing.append(self.cert_file)
            if not key_path.exists():
                missing.append(self.key_file)
            msg = f"SSL files missing: {', '.join(missing)}"
            logger.error(msg)
            raise FileNotFoundError(msg)

        ssl_context.load_cert_chain(certfile=self.cert_file, keyfile=self.key_file)
        # turn off all the SSL verification
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        # figured out from debugging using socat
        ciphers = [
            "ECDHE-RSA-AES256-GCM-SHA384",
            "ECDHE-RSA-AES128-GCM-SHA256",
            "ECDHE-RSA-AES256-SHA384",
            "ECDHE-RSA-AES128-SHA256",
            "ECDHE-RSA-AES256-SHA",
            "ECDHE-RSA-AES128-SHA",
            "ECDHE-RSA-DES-CBC3-SHA",
            "AES256-GCM-SHA384",
            "AES128-GCM-SHA256",
            "AES256-SHA256",
            "AES128-SHA256",
            "AES256-SHA",
            "AES128-SHA",
            "DES-CBC3-SHA",
        ]
        ssl_context.set_ciphers(":".join(ciphers))
        return ssl_context

    @dataclass(slots=True)
    class StatusFields:
        """Parsed status packet fields."""

        state: int
        brightness: int
        temp: int
        r: int
        g_val: int
        b: int
        connected_to_mesh: int
        raw_state_hex: str

    def _log_status_entry(self, device_id: int, raw_state: bytes, from_pkt: str | None) -> None:
        """Log the incoming status packet with timestamp."""
        ts_ms = int(time.time() * 1000)
        state_val = raw_state[1] if len(raw_state) > 1 else 0
        logger.debug(
            "[PARSE_STATUS_ENTRY] ts=%dms id=%s state=%s from_pkt=%s",
            ts_ms,
            device_id,
            "ON" if state_val else "OFF",
            from_pkt,
        )

    def _log_debug_device_call(self, device_id: int, raw_state: bytes, from_pkt: str | None) -> None:
        """Log full state for debug device."""
        if device_id != DEBUG_DEVICE_ID:
            return
        logger.debug(
            "parse_status called for device 103",
            extra={
                "device_id": device_id,
                "from_pkt": from_pkt,
                "raw_state_hex": raw_state.hex(),
            },
        )

    def _resolve_status_target(self, device_id: int) -> tuple[CyncDevice | None, CyncGroup | None]:
        """Return device or group matching status ID."""
        if not g.ncync_server:
            logger.error("ncync_server is None, cannot process device status")
            return None, None

        device_proto = g.ncync_server.devices.get(device_id)
        device = cast("CyncDevice | None", device_proto)
        group_proto = g.ncync_server.groups.get(device_id) if device is None else None
        group = cast("CyncGroup | None", group_proto)

        if device is None and group is None:
            logger.warning(
                "Unknown device/group ID - may be disabled or needs re-export",
                extra={
                    "id": device_id,
                    "note": "Check config file or re-export Cync account devices",
                },
            )
        return device, group

    def _extract_status_fields(self, raw_state: bytes) -> NCyncServer.StatusFields:
        """Parse shared status fields from raw packet."""
        state = raw_state[1]
        brightness = raw_state[2]
        temp = raw_state[3]
        r = raw_state[4]
        g_val = raw_state[5]
        b = raw_state[6]
        connected_to_mesh = raw_state[ONLINE_BYTE_INDEX] if len(raw_state) > ONLINE_BYTE_INDEX else 1
        return self.StatusFields(
            state=state,
            brightness=brightness,
            temp=temp,
            r=r,
            g_val=g_val,
            b=b,
            connected_to_mesh=connected_to_mesh,
            raw_state_hex=raw_state.hex(),
        )

    def _log_device_debug_details(
        self,
        device_id: int,
        device: CyncDevice,
        fields: NCyncServer.StatusFields,
        from_pkt: str | None,
    ) -> None:
        """Log detailed state for debug device or fan controllers."""
        if device_id == DEBUG_DEVICE_ID:
            logger.debug(
                "Device 103 details",
                extra={
                    "device_id": device_id,
                    "device_name": device.name,
                    "is_fan_controller": device.is_fan_controller,
                    "metadata_type": device.metadata.type if device.metadata else None,
                    "capabilities": device.metadata.capabilities if device.metadata else None,
                    "brightness": fields.brightness,
                },
            )
        if device.is_fan_controller:
            logger.debug(
                "Fan controller raw brightness",
                extra={
                    "device_id": device_id,
                    "device_name": device.name,
                    "brightness": fields.brightness,
                    "raw_state_2": fields.brightness,
                    "from_pkt": from_pkt,
                },
            )

    async def _handle_device_status(
        self,
        device: CyncDevice,
        device_id: int,
        fields: NCyncServer.StatusFields,
        from_pkt: str | None,
    ) -> None:
        """Handle status updates for a device."""
        self._log_device_debug_details(device_id, device, fields, from_pkt)
        self._handle_device_offline_tracking(device, fields.connected_to_mesh, device_id)

        if fields.connected_to_mesh != 0:
            await self._update_device_state_and_publish(
                device,
                fields.state,
                fields.brightness,
                fields.temp,
                fields.r,
                fields.g_val,
                fields.b,
                from_pkt,
            )
            await self._update_subgroups_for_device(device, from_pkt)

    async def _handle_group_status(
        self,
        group: CyncGroup,
        group_id: int,
        fields: NCyncServer.StatusFields,
        from_pkt: str | None,
    ) -> None:
        """Handle status updates for a group."""
        group.online = fields.connected_to_mesh != 0
        if fields.connected_to_mesh != 0:
            await self._update_group_state_and_publish(
                group,
                fields.state,
                fields.brightness,
                fields.temp,
                fields.r,
                fields.g_val,
                fields.b,
                group_id,
                from_pkt,
            )

    async def parse_status(self, raw_state: bytes, from_pkt: str | None = None):
        """Parse status packet and publish device/group state updates."""
        device_id = raw_state[0]
        self._log_status_entry(device_id, raw_state, from_pkt)
        self._log_debug_device_call(device_id, raw_state, from_pkt)

        device, group = self._resolve_status_target(device_id)
        if device is None and group is None:
            return

        fields = self._extract_status_fields(raw_state)

        if device is not None:
            await self._handle_device_status(device, device_id, fields, from_pkt)
        elif group is not None:
            await self._handle_group_status(group, device_id, fields, from_pkt)

    async def periodic_status_refresh(self):
        """Periodic sanity check to refresh device status and ensure sync with actual device state."""
        logger.info(" Starting periodic status refresh task (every 5 minutes)")

        while self.running:
            try:
                await asyncio.sleep(300)  # Refresh every 5 minutes

                if not self.running:
                    break

                # Get active TCP bridge devices
                bridge_devices = [dev for dev in self.tcp_devices.values() if dev and dev.ready_to_control]

                if not bridge_devices:
                    logger.debug(
                        "Skipping status refresh - no ready bridges",
                        extra={"total_connections": len(self.tcp_devices)},
                    )
                    continue

                # REMOVED: Periodic mesh info polling - rely on 0x83 status packets instead
                # logger.debug(
                #     " Performing periodic status refresh",
                #     extra={"ready_bridges": len(bridge_devices)},
                # )
                # for bridge_device in bridge_devices:
                #     try:
                #         await bridge_device.ask_for_mesh_info(False)
                #         await asyncio.sleep(1)
                #     except Exception as e:
                #         logger.warning(" Bridge refresh failed", extra={...})
                # logger.debug(" Status refresh completed")

            except asyncio.CancelledError:
                logger.info("Periodic status refresh task cancelled")
                break
            except Exception as e:
                logger.exception(
                    " Error in periodic status refresh",
                    extra={"error": str(e)},
                )
                await asyncio.sleep(60)  # Wait a minute before retrying on error

    async def periodic_pool_status_logger(self):
        """Log TCP connection pool status every 30 seconds for debugging."""
        logger.info(" Starting connection pool monitoring (every 30 seconds)")

        while self.running:
            try:
                await asyncio.sleep(30)  # Log every 30 seconds

                if not self.running:
                    break

                total_connections = len(self.tcp_devices)
                ready_connections = [dev for dev in self.tcp_devices.values() if dev and dev.ready_to_control]

                logger.info(
                    "TCP Pool Status",
                    extra={
                        "total_connections": total_connections,
                        "ready_to_control": len(ready_connections),
                    },
                )

            except asyncio.CancelledError:
                logger.info("Pool monitoring task cancelled")
                break
            except Exception as e:
                logger.exception(
                    " Error in pool monitoring",
                    extra={"error": str(e)},
                )
                await asyncio.sleep(30)  # Wait before retrying on error

    async def start(self):
        """Start TCP server, MQTT listener, and optional cloud relay."""
        logger.debug(
            "Creating SSL context",
            extra={"key_file": self.key_file, "cert_file": self.cert_file},
        )
        try:
            self.ssl_context = await self.create_ssl_context()
            self._server = await asyncio.start_server(
                self._register_new_connection,
                host=self.host,
                port=self.port,
                ssl=self.ssl_context,  # Pass the SSL context to enable SSL/TLS
            )
        except asyncio.CancelledError as ce:
            logger.debug("Server start cancelled", extra={"reason": str(ce)})
            # propagate the cancellation
            raise
        except Exception as e:
            logger.exception(
                " Failed to start TCP server",
                extra={"host": self.host, "port": self.port, "error": str(e)},
            )
        else:
            logger.info(
                " TCP Server started - waiting for Cync device connections",
                extra={
                    "host": self.host,
                    "port": self.port,
                    "cloud_relay_enabled": self.cloud_relay_enabled,
                    "note": "Check DNS redirection, VLAN and firewall if no connections appear",
                },
            )
            self.running = True
            try:
                # Publish server running status
                mqtt_client = _get_mqtt_client()
                if mqtt_client:
                    _ = await mqtt_client.publish(
                        f"{g.env.mqtt_topic}/status/bridge/tcp_server/running",
                        b"ON",
                    )

                # Start the periodic status refresh task
                self.refresh_task = asyncio.create_task(self.periodic_status_refresh())

                # Start the connection pool monitoring task
                self.pool_monitor_task = asyncio.create_task(self.periodic_pool_status_logger())

                logger.info("Background tasks started (status refresh, pool monitor)")

                async with self._server:
                    await self._server.serve_forever()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception(" Server exception", extra={"error": str(e)})

    async def _close_all_devices(self) -> None:
        """Close all TCP device connections."""
        device: CyncTCPDevice
        devices = [d for d in self.tcp_devices.values() if d is not None]

        if devices:
            logger.info(
                " Shutting down server, closing device connections",
                extra={"device_count": len(devices)},
            )
            for device in devices:
                try:
                    await device.close()
                    logger.debug(
                        " Device connection closed",
                        extra={"address": device.address if device.address else "unknown"},
                    )
                except asyncio.CancelledError as ce:
                    logger.debug("Device close cancelled", extra={"reason": str(ce)})
                    raise
                except Exception as e:
                    logger.exception(
                        " Error closing device connection",
                        extra={"address": device.address, "error": str(e)},
                    )
        else:
            logger.info("No devices connected during shutdown")

    async def _close_tcp_server(self) -> None:
        """Close TCP server and publish status."""
        if not self._server or not self._server.is_serving():
            logger.debug("Server not running")
            return

        logger.debug("Closing TCP server...")
        self._server.close()
        await self._server.wait_closed()

        mqtt_client = _get_mqtt_client()
        if mqtt_client:
            _ = await mqtt_client.publish(
                f"{g.env.mqtt_topic}/status/bridge/tcp_server/running",
                b"OFF",
            )
        logger.debug(" TCP server closed")

    async def stop(self):
        """Stop TCP server and cancel background tasks."""
        try:
            self.shutting_down = True
            await self._close_all_devices()
            await self._close_tcp_server()

        except asyncio.CancelledError as ce:
            logger.debug("Server stop cancelled", extra={"reason": str(ce)})
            raise
        except Exception as e:
            logger.exception(" Error during server shutdown", extra={"error": str(e)})
        else:
            logger.info(" Server stopped successfully")
        finally:
            if self.start_task and not self.start_task.done():
                logger.debug("Cancelling start task")
                _ = self.start_task.cancel()
            if self.refresh_task and not self.refresh_task.done():
                logger.debug("Cancelling refresh task")
                _ = self.refresh_task.cancel()
            if self.pool_monitor_task and not self.pool_monitor_task.done():
                logger.debug("Cancelling pool monitor task")
                _ = self.pool_monitor_task.cancel()

    async def _register_new_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        _ = ensure_correlation_id()
        peername = cast("tuple[str, int] | None", writer.get_extra_info("peername"))
        if peername is None:
            logger.warning("Could not get peername from writer")
            return
        client_ip: str = peername[0]
        client_port: int = peername[1]
        client_addr: str = f"{client_ip}:{client_port}"  # Use IP:port to allow multiple connections from same IP

        if client_addr in self.tcp_conn_attempts:
            self.tcp_conn_attempts[client_addr] += 1
        else:
            self.tcp_conn_attempts[client_addr] = 1

        connection_attempt: int = self.tcp_conn_attempts[client_addr]

        # Branch based on relay mode
        if self.cloud_relay_enabled:
            # Cloud relay mode - use CloudRelayConnection
            # TODO: Add support for local commands in relay mode by tracking bridge devices
            #       even when in relay mode. This would allow bidirectional control:
            #       - Commands from HA -> intercepted and sent via relay
            #       - Cloud commands -> forwarded to devices
            #       - Status updates -> sent to both HA and cloud
            #       Current limitation: tcp_devices only populated in LAN-only mode
            logger.info(
                " New connection (RELAY mode)",
                extra={
                    "client_addr": client_addr,
                    "connection_attempt": connection_attempt,
                    "mode": "cloud_relay",
                },
            )
            try:
                relay = CloudRelayConnection(
                    device_reader=reader,
                    device_writer=writer,
                    client_addr=client_addr,
                    cloud_server=self.cloud_server,
                    cloud_port=self.cloud_port,
                    forward_to_cloud=self.cloud_forward,
                    debug_logging=self.cloud_debug_logging,
                    disable_ssl_verify=self.cloud_disable_ssl_verify,
                )
                await relay.start_relay()
            except asyncio.CancelledError as ce:
                logger.debug(
                    "Relay connection cancelled",
                    extra={"client_addr": client_addr, "reason": str(ce)},
                )
                raise
            except Exception as e:
                logger.exception(
                    " Error in relay connection",
                    extra={"client_addr": client_addr, "error": str(e)},
                )
        else:
            # Normal LAN-only mode - use CyncTCPDevice
            logger.info(
                " New connection (LAN mode)",
                extra={
                    "client_addr": client_addr,
                    "connection_attempt": connection_attempt,
                    "mode": "lan_only",
                },
            )

            existing_device = await self.remove_tcp_device(client_addr)
            if existing_device is not None:
                logger.debug(
                    "Replacing existing device connection",
                    extra={
                        "client_addr": client_addr,
                        "old_device_id": id(existing_device),
                    },
                )
                del existing_device

            try:
                new_device = CyncTCPDevice(reader, writer, client_addr)
                # will sleep devices that cant connect to prevent connection flooding
                can_connect = await new_device.can_connect()
                if can_connect:
                    await self.add_tcp_device(new_device)
                else:
                    logger.debug(
                        "Device connection rejected by rate limiting",
                        extra={"client_addr": client_addr},
                    )
                    del new_device
            except asyncio.CancelledError as ce:
                logger.debug(
                    "Connection cancelled",
                    extra={"client_addr": client_addr, "reason": str(ce)},
                )
                # propagate the cancellation
                raise
            except Exception as e:
                logger.exception(
                    " Error creating device connection",
                    extra={"client_addr": client_addr, "error": str(e)},
                )
