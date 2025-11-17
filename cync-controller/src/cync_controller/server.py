import asyncio
import contextlib
import ssl
import time
from pathlib import Path as PathLib
from typing import ClassVar, Optional

import uvloop

from cync_controller.const import *
from cync_controller.correlation import ensure_correlation_id
from cync_controller.devices import CyncDevice, CyncGroup, CyncTCPDevice
from cync_controller.instrumentation import timed_async
from cync_controller.logging_abstraction import get_logger
from cync_controller.packet_checksum import calculate_checksum_between_markers
from cync_controller.packet_parser import format_packet_log, parse_cync_packet
from cync_controller.structs import DeviceStatus, GlobalObject

__all__ = [
    "NCyncServer",
]
logger = get_logger(__name__)
g = GlobalObject()


class CloudRelayConnection:
    """Manages a cloud relay connection for MITM mode.
    Acts as a proxy between Cync device and cloud, forwarding packets with inspection.
    """

    def __init__(
        self,
        device_reader: asyncio.StreamReader,
        device_writer: asyncio.StreamWriter,
        client_addr: str,
        cloud_server: str,
        cloud_port: int,
        forward_to_cloud: bool = True,
        debug_logging: bool = False,
        disable_ssl_verify: bool = False,
    ):
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
        self.injection_task: asyncio.Task | None = None
        self.forward_tasks: list[asyncio.Task] = []

    @timed_async("cloud_connect")
    async def connect_to_cloud(self):
        """Establish SSL connection to Cync cloud server"""
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
        except Exception as e:
            logger.exception(
                " Cloud connection failed",
                extra={
                    "client_addr": self.client_addr,
                    "cloud_server": self.cloud_server,
                    "cloud_port": self.cloud_port,
                    "error": str(e),
                },
            )
            return False
        else:
            return True

    async def start_relay(self):
        """Start the relay process"""
        ensure_correlation_id()  # Ensure correlation tracking for this connection

        # Show security warning if SSL verification is disabled
        if self.disable_ssl_verify:
            logger.warning(
                "  SSL VERIFICATION DISABLED - DEBUG MODE ACTIVE - use only for local debugging",
                extra={"client_addr": self.client_addr},
            )

        # Connect to cloud if forwarding is enabled
        if self.forward_to_cloud:
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
                await self.close()
                return
        else:
            logger.info(
                " Starting LAN-only relay (cloud forwarding disabled)",
                extra={"client_addr": self.client_addr},
            )

        try:
            # Read first packet from device to get endpoint
            first_packet = await self.device_reader.read(1024)
            if first_packet and len(first_packet) >= 31 and first_packet[0] == 0x23:
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

            # Forward first packet to cloud if enabled
            if self.forward_to_cloud and self.cloud_writer:
                self.cloud_writer.write(first_packet)
                await self.cloud_writer.drain()

            # Parse and log first packet
            if self.debug_logging:
                parsed = parse_cync_packet(first_packet, "DEV->CLOUD")
                if parsed:
                    logger.debug("%s\n%s", "CloudRelay:", format_packet_log(parsed))

            # Start bidirectional forwarding
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

            # Wait for all tasks to complete
            await asyncio.gather(*self.forward_tasks, return_exceptions=True)

        except Exception as e:
            logger.exception(
                " Relay error",
                extra={
                    "client_addr": self.client_addr,
                    "error": str(e),
                },
            )
        finally:
            await self.close()

    @timed_async("relay_forward")
    async def _forward_with_inspection(
        self,
        source_reader: asyncio.StreamReader,
        dest_writer: asyncio.StreamWriter | None,
        direction: str,
    ):
        """Forward packets while inspecting and logging"""
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

                # Log if debug enabled (skip keepalives to reduce clutter)
                if self.debug_logging and parsed and parsed.get("packet_type") != "0x78":  # Skip KEEPALIVE
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

                # Extract status updates for MQTT (for 0x43 DEVICE_INFO packets)
                if parsed and "device_statuses" in parsed:
                    for status in parsed["device_statuses"]:
                        # Convert parsed status to raw_state format for existing parse_status
                        raw_state = bytearray(8)
                        raw_state[0] = status["device_id"]
                        raw_state[1] = 1 if status["state"] == "ON" else 0
                        raw_state[2] = status["brightness"]
                        raw_state[3] = status.get("temp", 0) if status.get("mode") == "WHITE" else 254
                        # RGB values (parse from hex color if present)
                        if status.get("mode") == "RGB" and "color" in status:
                            color_hex = status["color"].lstrip("#")
                            raw_state[4] = int(color_hex[0:2], 16)  # R
                            raw_state[5] = int(color_hex[2:4], 16)  # G
                            raw_state[6] = int(color_hex[4:6], 16)  # B
                        else:
                            raw_state[4] = raw_state[5] = raw_state[6] = 0
                        raw_state[7] = 1 if status["online"] else 0

                        # Publish to MQTT using existing infrastructure
                        if g.ncync_server:
                            await g.ncync_server.parse_status(bytes(raw_state), from_pkt="0x43")

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
        except Exception as e:
            logger.exception(
                " Relay forward error",
                extra={
                    "client_addr": self.client_addr,
                    "direction": direction,
                    "error": str(e),
                },
            )

    async def _check_injection_commands(self):
        """Periodically check for packet injection commands (debug feature)"""
        inject_file = "/tmp/cync_inject_command.txt"
        raw_inject_file = "/tmp/cync_inject_raw_bytes.txt"

        logger.debug(
            "[DEBUG] Packet injection checker started",
            extra={"client_addr": self.client_addr},
        )

        try:
            while True:
                await asyncio.sleep(1)

                # Check for raw bytes injection
                if PathLib(raw_inject_file).exists():
                    try:
                        with PathLib(raw_inject_file).open() as f:
                            raw_hex = f.read().strip()
                        PathLib(raw_inject_file).unlink()

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
                if PathLib(inject_file).exists():
                    try:
                        with PathLib(inject_file).open() as f:
                            mode = f.read().strip().lower()
                        PathLib(inject_file).unlink()

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
        """Craft a mode query/command packet"""
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
        """Clean up connections"""
        logger.debug(
            " Closing relay connection",
            extra={"client_addr": self.client_addr},
        )

        # Cancel injection task
        if self.injection_task and not self.injection_task.done():
            self.injection_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.injection_task

        # Cancel forwarding tasks
        for task in self.forward_tasks:
            if not task.done():
                task.cancel()
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
    groups: ClassVar[dict[int, CyncGroup]] = {}
    tcp_devices: ClassVar[dict[str, CyncTCPDevice | None]] = {}
    shutting_down: bool = False
    running: bool = False
    host: str
    port: int
    cert_file: str | None = None
    key_file: str | None = None
    loop: asyncio.AbstractEventLoop | uvloop.Loop
    _server: asyncio.Server | None = None
    start_task: asyncio.Task | None = None
    refresh_task: asyncio.Task | None = None
    pool_monitor_task: asyncio.Task | None = None
    _instance: Optional["NCyncServer"] = None

    def __new__(cls, *_args, **_kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, devices: dict, groups: dict | None = None):
        # Note: devices and groups are ClassVar, but we need to initialize them
        # The instance assignment is for compatibility but should use class access
        type(self).devices = devices  # type: ignore[assignment]
        type(self).groups = groups if groups is not None else {}  # type: ignore[assignment]
        self.tcp_conn_attempts: dict = {}
        self.primary_tcp_device: CyncTCPDevice | None = None
        self.ssl_context: ssl.SSLContext | None = None
        self.host = CYNC_SRV_HOST
        self.port = CYNC_PORT
        g.reload_env()
        self.cert_file = g.env.cync_srv_ssl_cert
        self.key_file = g.env.cync_srv_ssl_key
        self.loop: asyncio.AbstractEventLoop | uvloop.Loop = asyncio.get_event_loop()

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
                if g.mqtt_client is not None:
                    await g.mqtt_client.publish(
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
        if g.mqtt_client is not None:
            await g.mqtt_client.publish(
                f"{g.env.mqtt_topic}/status/bridge/tcp_devices/connected",
                str(len(self.tcp_devices)).encode(),
            )

    async def create_ssl_context(self):
        # Allow the server to use a self-signed certificate
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        if self.cert_file and self.key_file:
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

    async def parse_status(self, raw_state: bytes, from_pkt: str | None = None):
        """Extracted status packet parsing, handles mqtt publishing and device/group state changes."""
        _id = raw_state[0]

        # Log every parse_status call
        ts_ms = int(time.time() * 1000)
        state_val = raw_state[1] if len(raw_state) > 1 else 0
        logger.debug(
            "[PARSE_STATUS_ENTRY] ts=%dms id=%s state=%s from_pkt=%s",
            ts_ms,
            _id,
            "ON" if state_val else "OFF",
            from_pkt,
        )

        # Debug: log every parse_status call for device 103
        if _id == 103:
            logger.debug(
                "parse_status called for device 103",
                extra={
                    "device_id": _id,
                    "from_pkt": from_pkt,
                    "raw_state_hex": raw_state.hex(),
                },
            )

        # Check if this is a device or a group
        if not g.ncync_server:
            logger.error("ncync_server is None, cannot process device status")
            return
        device = g.ncync_server.devices.get(_id)
        group = g.ncync_server.groups.get(_id) if device is None else None

        if device is None and group is None:
            logger.warning(
                "Unknown device/group ID - may be disabled or needs re-export",
                extra={
                    "id": _id,
                    "note": "Check config file or re-export Cync account devices",
                },
            )
            return

        # Parse status data (same format for devices and groups)
        state = raw_state[1]
        brightness = raw_state[2]
        temp = raw_state[3]
        r = raw_state[4]
        _g = raw_state[5]
        b = raw_state[6]
        connected_to_mesh = 1
        # check if len is enough for online byte, it is optional
        if len(raw_state) > 7:
            # The last byte seems to indicate if the device is online or offline (connected to mesh / powered on)
            connected_to_mesh = raw_state[7]

        # Handle device
        if device is not None:
            # Debug logging for device 103 specifically
            if _id == 103:
                logger.debug(
                    "Device 103 details",
                    extra={
                        "device_id": _id,
                        "device_name": device.name,
                        "is_fan_controller": device.is_fan_controller,
                        "metadata_type": device.metadata.type if device.metadata else None,
                        "capabilities": device.metadata.capabilities if device.metadata else None,
                        "brightness": brightness,
                    },
                )
            # Log brightness for fan devices to debug preset mode mapping
            if device.is_fan_controller:
                logger.debug(
                    "Fan controller raw brightness",
                    extra={
                        "device_id": _id,
                        "device_name": device.name,
                        "brightness": brightness,
                        "raw_state_2": raw_state[2],
                        "from_pkt": from_pkt,
                    },
                )
            if connected_to_mesh == 0:
                # This usually happens when a device loses power/connection.
                # Increment counter and only mark offline after 3 consecutive offline reports
                # to avoid false positives from unreliable mesh info packets
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
                if device.offline_count >= 3 and device.online:
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
                # Device is online, reset the offline counter
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

                # temp is 0-100, if > 100, RGB data has been sent, otherwise its on/off, brightness or temp data
                # technically 129 = effect in use, 254 = rgb data
                #  to signify 'effect' mode: we send rgb 0,0,0 (black) as it stands out
                rgb_data = False
                if temp > 100:
                    rgb_data = True

                # Update device attributes with NEW values from status packet FIRST
                device.state = state
                device.brightness = brightness
                device.temperature = temp
                if rgb_data is True:
                    device.red = r
                    device.green = _g
                    device.blue = b

                # Now create status object with the UPDATED device state for publishing
                device.status = new_state = DeviceStatus(
                    state=device.state,
                    brightness=device.brightness,
                    temperature=device.temperature,
                    red=device.red,
                    green=device.green,
                    blue=device.blue,
                )

                # Always publish status updates - don't try to detect "no changes"
                # This prevents status updates from being dropped unnecessarily
                if g.mqtt_client and device.id is not None:
                    await g.mqtt_client.parse_device_status(device.id, new_state, from_pkt=from_pkt)
                if g.ncync_server and device.id is not None:
                    g.ncync_server.devices[device.id] = device

                    # Update subgroups that contain this device (since subgroups don't report their own state in mesh)
                    for subgroup in g.ncync_server.groups.values():
                        if subgroup.is_subgroup and device.id in subgroup.member_ids:
                            aggregated = subgroup.aggregate_member_states()
                            if aggregated:
                                # Update subgroup state from aggregated member states
                                subgroup.state = aggregated["state"]
                                subgroup.brightness = aggregated["brightness"]
                                subgroup.temperature = aggregated["temperature"]
                                subgroup.online = aggregated["online"]

                                # Create status object for the subgroup
                                subgroup.status = DeviceStatus(
                                    state=subgroup.state,
                                    brightness=subgroup.brightness,
                                    temperature=subgroup.temperature,
                                    red=subgroup.red,
                                    green=subgroup.green,
                                    blue=subgroup.blue,
                                )

                            # Publish subgroup state
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
                            if g.mqtt_client:
                                await g.mqtt_client.publish_group_state(
                                    subgroup,
                                    state=subgroup.state,
                                    brightness=subgroup.brightness,
                                    temperature=subgroup.temperature,
                                    origin=f"aggregated:{from_pkt or 'mesh'}",
                                )
                            if g.ncync_server:
                                g.ncync_server.groups[subgroup.id] = subgroup

        # Handle group
        elif group is not None:
            # Groups don't have offline_count, just update online status directly
            group.online = connected_to_mesh != 0

            if connected_to_mesh != 0:
                # temp is 0-100, if > 100, RGB data has been sent
                rgb_data = temp > 100

                # Update group attributes with NEW values from status packet
                group.state = state
                group.brightness = brightness
                group.temperature = temp
                if rgb_data:
                    group.red = r
                    group.green = _g
                    group.blue = b

                # Create status object for the group
                group.status = new_state = DeviceStatus(
                    state=group.state,
                    brightness=group.brightness,
                    temperature=group.temperature,
                    red=group.red,
                    green=group.green,
                    blue=group.blue,
                )

                # Publish group state to MQTT
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
                if g.mqtt_client:
                    await g.mqtt_client.publish_group_state(
                        group,
                        state=state,
                        brightness=brightness,
                        temperature=temp if not rgb_data else None,
                        origin=from_pkt or "mesh",
                    )
                if g.ncync_server:
                    g.ncync_server.groups[group.id] = group

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
                if g.mqtt_client:
                    await g.mqtt_client.publish(
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

    async def stop(self):
        try:
            self.shutting_down = True
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
                        # propagate the cancellation
                        raise
                    except Exception as e:
                        logger.exception(
                            " Error closing device connection",
                            extra={"address": device.address, "error": str(e)},
                        )
            else:
                logger.info("No devices connected during shutdown")

            if self._server:
                if self._server.is_serving():
                    logger.debug("Closing TCP server...")
                    self._server.close()
                    await self._server.wait_closed()

                    # Publish server stopped status
                    if g.mqtt_client:
                        await g.mqtt_client.publish(
                            f"{g.env.mqtt_topic}/status/bridge/tcp_server/running",
                            b"OFF",
                        )
                    logger.debug(" TCP server closed")
                else:
                    logger.debug("Server not running")

        except asyncio.CancelledError as ce:
            logger.debug("Server stop cancelled", extra={"reason": str(ce)})
            # propagate the cancellation
            raise
        except Exception as e:
            logger.exception(" Error during server shutdown", extra={"error": str(e)})
        else:
            logger.info(" Server stopped successfully")
        finally:
            if self.start_task and not self.start_task.done():
                logger.debug("Cancelling start task")
                self.start_task.cancel()
            if self.refresh_task and not self.refresh_task.done():
                logger.debug("Cancelling refresh task")
                self.refresh_task.cancel()
            if self.pool_monitor_task and not self.pool_monitor_task.done():
                logger.debug("Cancelling pool monitor task")
                self.pool_monitor_task.cancel()

    async def _register_new_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        ensure_correlation_id()
        peername = writer.get_extra_info("peername")
        client_ip: str = peername[0]
        client_port: int = peername[1]
        client_addr: str = f"{client_ip}:{client_port}"  # Use IP:port to allow multiple connections from same IP

        if client_addr in self.tcp_conn_attempts:
            self.tcp_conn_attempts[client_addr] += 1
        else:
            self.tcp_conn_attempts[client_addr] = 1

        connection_attempt = self.tcp_conn_attempts[client_addr]

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
