import asyncio
import contextlib
import logging
import ssl
import time
from pathlib import Path as PathLib
from typing import ClassVar, Optional

import uvloop

from cync_lan.const import *
from cync_lan.devices import CyncDevice, CyncGroup, CyncTCPDevice
from cync_lan.packet_checksum import calculate_checksum_between_markers
from cync_lan.packet_parser import format_packet_log, parse_cync_packet
from cync_lan.structs import DeviceStatus, GlobalObject

__all__ = [
    "NCyncServer",
]
logger = logging.getLogger(CYNC_LOG_NAME)
g = GlobalObject()


class CloudRelayConnection:
    """
    Manages a cloud relay connection for MITM mode.
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
        self.lp = f"CloudRelay:{client_addr}:"

    async def connect_to_cloud(self):
        """Establish SSL connection to Cync cloud server"""
        lp = f"{self.lp}connect_cloud:"
        try:
            # Create SSL context for cloud connection
            ssl_context = ssl.create_default_context()
            if self.disable_ssl_verify:
                logger.warning("%s SSL verification DISABLED - DEBUG MODE (use only for local testing)", lp)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            else:
                # Secure mode - but Cync cloud uses self-signed certs, so we still need to disable verification
                logger.debug("%s Connecting to cloud with SSL", lp)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            # Connect to cloud
            self.cloud_reader, self.cloud_writer = await asyncio.open_connection(
                self.cloud_server, self.cloud_port, ssl=ssl_context
            )
            logger.info("%s Connected to cloud server %s:%s", lp, self.cloud_server, self.cloud_port)
        except Exception:
            logger.exception("%s Failed to connect to cloud", lp)
            return False
        else:
            return True

    async def start_relay(self):
        """Start the relay process"""
        lp = f"{self.lp}start_relay:"

        # Show security warning if SSL verification is disabled
        if self.disable_ssl_verify:
            logger.warning("=" * 60)
            logger.warning("⚠️  SSL VERIFICATION DISABLED - DEBUG MODE ACTIVE ⚠️")
            logger.warning("This mode should ONLY be used for local debugging!")
            logger.warning("DO NOT use on untrusted networks or production systems!")
            logger.warning("=" * 60)

        # Connect to cloud if forwarding is enabled
        if self.forward_to_cloud:
            connected = await self.connect_to_cloud()
            if not connected:
                logger.error("%s Cannot start relay without cloud connection", lp)
                await self.close()
                return
        else:
            logger.info("%s LAN-only mode - cloud forwarding disabled", lp)

        try:
            # Read first packet from device to get endpoint
            first_packet = await self.device_reader.read(1024)
            if first_packet and len(first_packet) >= 31 and first_packet[0] == 0x23:
                self.device_endpoint = first_packet[6:10]
                endpoint_hex = " ".join(f"{b:02x}" for b in self.device_endpoint)
                logger.info("%s Device endpoint: %s", lp, endpoint_hex)

            # Forward first packet to cloud if enabled
            if self.forward_to_cloud and self.cloud_writer:
                self.cloud_writer.write(first_packet)
                await self.cloud_writer.drain()

            # Parse and log first packet
            if self.debug_logging:
                parsed = parse_cync_packet(first_packet, "DEV->CLOUD")
                if parsed:
                    logger.debug("%s\n%s", lp, format_packet_log(parsed))

            # Start bidirectional forwarding
            dev_to_cloud_task = asyncio.create_task(
                self._forward_with_inspection(
                    self.device_reader,
                    self.cloud_writer if self.forward_to_cloud else None,
                    "DEV->CLOUD",
                )
            )
            self.forward_tasks.append(dev_to_cloud_task)

            if self.forward_to_cloud and self.cloud_reader:
                cloud_to_dev_task = asyncio.create_task(
                    self._forward_with_inspection(self.cloud_reader, self.device_writer, "CLOUD->DEV")
                )
                self.forward_tasks.append(cloud_to_dev_task)

            # Start injection checker (debug feature)
            self.injection_task = asyncio.create_task(self._check_injection_commands())

            # Wait for all tasks to complete
            await asyncio.gather(*self.forward_tasks, return_exceptions=True)

        except Exception:
            logger.exception("%s Relay error", lp)
        finally:
            await self.close()

    async def _forward_with_inspection(
        self,
        source_reader: asyncio.StreamReader,
        dest_writer: asyncio.StreamWriter | None,
        direction: str,
    ):
        """Forward packets while inspecting and logging"""
        lp = f"{self.lp}{direction}:"
        try:
            while True:
                data = await source_reader.read(4096)
                if not data:
                    logger.debug("%s Connection closed", lp)
                    break

                # Parse packet
                parsed = parse_cync_packet(data, direction)

                # Log if debug enabled (skip keepalives to reduce clutter)
                if self.debug_logging and parsed and parsed.get("packet_type") != "0x78":  # Skip KEEPALIVE
                    logger.debug("%s\n%s", lp, format_packet_log(parsed))

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
                        await g.ncync_server.parse_status(bytes(raw_state), from_pkt="0x43")

                # Forward to destination (if cloud forwarding enabled)
                if dest_writer:
                    dest_writer.write(data)
                    await dest_writer.drain()

        except asyncio.CancelledError:
            logger.debug("%s Task cancelled", lp)
            raise
        except Exception:
            logger.exception("%s Forward error", lp)

    async def _check_injection_commands(self):
        """Periodically check for packet injection commands (debug feature)"""
        lp = f"{self.lp}injection:"
        inject_file = "/tmp/cync_inject_command.txt"
        raw_inject_file = "/tmp/cync_inject_raw_bytes.txt"

        logger.debug("%s Injection checker started", lp)

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

                        logger.info("%s Injecting raw packet (%s bytes)", lp, len(packet))
                        packet_hex = " ".join(f"{b:02x}" for b in packet)
                        logger.debug("%s Hex: %s", lp, packet_hex)

                        self.device_writer.write(packet)
                        await self.device_writer.drain()

                        logger.info("%s Raw injection complete", lp)
                    except Exception:
                        logger.exception("%s Error injecting raw bytes", lp)

                # Check for mode injection (for switches)
                if PathLib(inject_file).exists():
                    try:
                        with PathLib(inject_file).open() as f:
                            mode = f.read().strip().lower()
                        PathLib(inject_file).unlink()

                        if mode in ["smart", "traditional"] and self.device_endpoint:
                            logger.info("%s Injecting %s mode packet", lp, mode.upper())

                            # Craft mode packet (similar to MITM)
                            mode_byte = 0x02 if mode == "smart" else 0x01
                            counter = 0x10  # Fixed counter for injection

                            packet = self._craft_mode_packet(self.device_endpoint, counter, mode_byte)

                            self.device_writer.write(packet)
                            await self.device_writer.drain()

                            logger.info("%s Mode injection complete", lp)
                    except Exception:
                        logger.exception("%s Error injecting mode packet", lp)

        except asyncio.CancelledError:
            logger.debug("%s Injection checker cancelled", lp)
            raise
        except Exception:
            logger.exception("%s Injection checker error", lp)

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
            ]
        )

        # Calculate and insert checksum
        packet[33] = calculate_checksum_between_markers(bytes(packet))
        return bytes(packet)

    async def close(self):
        """Clean up connections"""
        lp = f"{self.lp}close:"
        logger.debug("%s Closing relay connection", lp)

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
                logger.debug("%s Error closing cloud writer: %s", lp, e)

        # Close device connection
        try:
            self.device_writer.close()
            await self.device_writer.wait_closed()
        except Exception as e:
            logger.debug("%s Error closing device writer: %s", lp, e)

        logger.debug("%s Relay connection closed", lp)


class NCyncServer:
    """
    A class to represent a Cync Controller server that listens for connections from Cync Wi-Fi devices.
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
    lp: str = "nCync:"
    start_task: asyncio.Task | None = None
    refresh_task: asyncio.Task | None = None
    pool_monitor_task: asyncio.Task | None = None
    _instance: Optional["NCyncServer"] = None

    def __new__(cls, *_args, **_kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, devices: dict, groups: dict | None = None):
        self.devices = devices
        self.groups = groups if groups is not None else {}
        self.tcp_conn_attempts: dict = {}
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

        if self.cloud_relay_enabled:
            logger.info(
                "%s Cloud relay mode ENABLED (forward_to_cloud=%s, debug_logging=%s)",
                self.lp,
                self.cloud_forward,
                self.cloud_debug_logging,
            )

    async def remove_tcp_device(self, device: CyncTCPDevice | str) -> CyncTCPDevice | None:
        """
        Remove a TCP device from the server's device list.
        :param device: The CyncTCPDevice to remove.
        """
        dev = None
        lp = f"{self.lp}remove_tcp_device:"
        if isinstance(device, str) and device in self.tcp_devices:
            # if device is a string, it is the address
            device = self.tcp_devices[device]

        if isinstance(device, CyncTCPDevice):
            if device.address in self.tcp_devices:
                dev = self.tcp_devices.pop(device.address, None)
                if dev is not None:
                    uptime = time.time() - dev.connected_at
                    logger.debug(
                        "%s Removed TCP device %s from server (uptime: %.1fs, ready_to_control: %s)",
                        lp,
                        device.address,
                        uptime,
                        dev.ready_to_control,
                    )
                    # "state_topic": f"{self.topic}/status/bridge/tcp_devices/connected",
                    # TODO: publish the device removal
                    if g.mqtt_client is not None:
                        await g.mqtt_client.publish(
                            f"{g.env.mqtt_topic}/status/bridge/tcp_devices/connected",
                            str(len(self.tcp_devices)).encode(),
                        )
            else:
                logger.warning("%s Device %s not found in TCP devices.", lp, device.address)
        return dev

    async def add_tcp_device(self, device: CyncTCPDevice):
        """
        Add a TCP device to the server's device list.
        :param device: The CyncTCPDevice to add.
        """
        lp = f"{self.lp}add_tcp_device:"
        self.tcp_devices[device.address] = device
        logger.debug("%s Added TCP device %s to server.", lp, device.address)
        # TODO: publish updated TCP devices connected
        # "state_topic": f"{self.topic}/status/bridge/tcp_devices/connected",
        if g.mqtt_client is not None:
            # publish the device removal
            await g.mqtt_client.publish(
                f"{g.env.mqtt_topic}/status/bridge/tcp_devices/connected",
                str(len(self.tcp_devices)).encode(),
            )

    async def create_ssl_context(self):
        # Allow the server to use a self-signed certificate
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
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

    async def parse_status(self, raw_state: bytes, from_pkt: str | None = None):  # noqa: PLR0915
        """Extracted status packet parsing, handles mqtt publishing and device/group state changes."""
        _id = raw_state[0]

        # Debug: log every parse_status call
        if _id == 103:
            logger.warning(
                "%s >>> PARSE_STATUS CALLED for device 103, from_pkt=%s, raw_state=%s",
                self.lp,
                from_pkt,
                raw_state.hex(),
            )

        # Check if this is a device or a group
        device = g.ncync_server.devices.get(_id)
        group = g.ncync_server.groups.get(_id) if device is None else None

        if device is None and group is None:
            logger.warning(
                "ID: %s not found in devices or groups! May be disabled in config file or you need to "
                "re-export your Cync account devices!",
                _id,
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
                logger.warning(
                    "%s >>> DEVICE 103 DEBUG: name='%s' is_fan_controller=%s metadata=%s type=%s capabilities=%s brightness=%s",
                    self.lp,
                    device.name,
                    device.is_fan_controller,
                    device.metadata,
                    device.metadata.type if device.metadata else None,
                    device.metadata.capabilities if device.metadata else None,
                    brightness,
                )
            # Log brightness for fan devices to debug preset mode mapping
            if device.is_fan_controller:
                logger.warning(
                    "%s >>> RAW BRIGHTNESS from device: ID=%s name='%s' brightness=%s (raw_state[2]=%s) from_pkt=%s",
                    self.lp,
                    _id,
                    device.name,
                    brightness,
                    raw_state[2],
                    from_pkt,
                )
            if connected_to_mesh == 0:
                # This usually happens when a device loses power/connection.
                # Increment counter and only mark offline after 3 consecutive offline reports
                # to avoid false positives from unreliable mesh info packets
                device.offline_count += 1
                if device.offline_count >= 3 and device.online:
                    device.online = False
                    logger.warning(
                        '%s Device ID: %s ("%s") has been offline for %s consecutive checks, marking as unavailable...',
                        self.lp,
                        _id,
                        device.name,
                        device.offline_count,
                    )
            else:
                # Device is online, reset the offline counter
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
                await g.mqtt_client.parse_device_status(device.id, new_state, from_pkt=from_pkt)
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
                                '%s Subgroup "%s" (ID: %s) aggregated from member device %s: state=%s, brightness=%s',
                                self.lp,
                                subgroup.name,
                                subgroup.id,
                                device.id,
                                "ON" if subgroup.state else "OFF",
                                subgroup.brightness,
                            )
                            await g.mqtt_client.publish_group_state(
                                subgroup,
                                state=subgroup.state,
                                brightness=subgroup.brightness,
                                temperature=subgroup.temperature,
                                origin=f"aggregated:{from_pkt or 'mesh'}",
                            )
                            g.ncync_server.groups[subgroup.id] = subgroup

                            # Sync individual switch states to match subgroup state
                            # (only switches, individual commands take precedence)
                            for member_id in subgroup.member_ids:
                                if member_id in g.ncync_server.devices:
                                    member_device = g.ncync_server.devices[member_id]
                                    await g.mqtt_client.update_switch_from_subgroup(
                                        member_device,
                                        subgroup.state,
                                        subgroup.name,
                                    )

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
                    '%s Group ID: %s ("%s") state update from mesh: state=%s, brightness=%s%s',
                    self.lp,
                    _id,
                    group.name,
                    "ON" if state else "OFF",
                    brightness,
                    f" [from {from_pkt}]" if from_pkt else "",
                )
                await g.mqtt_client.publish_group_state(
                    group,
                    state=state,
                    brightness=brightness,
                    temperature=temp if not rgb_data else None,
                    origin=from_pkt or "mesh",
                )
                g.ncync_server.groups[group.id] = group

    async def periodic_status_refresh(self):
        """Periodic sanity check to refresh device status and ensure sync with actual device state."""
        lp = f"{self.lp}status_refresh:"
        logger.info("%s Starting periodic status refresh task...", lp)

        while self.running:
            try:
                await asyncio.sleep(300)  # Refresh every 5 minutes

                if not self.running:
                    break

                logger.debug("%s Performing periodic status refresh...", lp)

                # Get active TCP bridge devices
                bridge_devices = [dev for dev in self.tcp_devices.values() if dev and dev.ready_to_control]

                if not bridge_devices:
                    logger.debug("%s No active bridge devices available for status refresh", lp)
                    continue

                # Request mesh info from each bridge to refresh all device statuses
                for bridge_device in bridge_devices:
                    try:
                        logger.debug("%s Requesting mesh info from bridge %s", lp, bridge_device.address)
                        await bridge_device.ask_for_mesh_info(False)  # False = don't log verbose
                        await asyncio.sleep(1)  # Small delay between bridge requests
                    except Exception as e:
                        logger.warning("%s Failed to refresh status from bridge %s: %s", lp, bridge_device.address, e)

                logger.debug("%s Periodic status refresh completed", lp)

            except asyncio.CancelledError:
                logger.info("%s Periodic status refresh task cancelled", lp)
                break
            except Exception:
                logger.exception("%s Error in periodic status refresh", lp)
                await asyncio.sleep(60)  # Wait a minute before retrying on error

    async def periodic_pool_status_logger(self):
        """Log TCP connection pool status every 30 seconds for debugging."""
        lp = f"{self.lp}pool_monitor:"
        logger.info("%s Starting connection pool monitoring task...", lp)

        while self.running:
            try:
                await asyncio.sleep(30)  # Log every 30 seconds

                if not self.running:
                    break

                total_connections = len(self.tcp_devices)
                ready_connections = [dev for dev in self.tcp_devices.values() if dev and dev.ready_to_control]

                logger.info(
                    "%s TCP Pool Status: %d total connections, %d ready_to_control",
                    lp,
                    total_connections,
                    len(ready_connections),
                )

                # Log details for each connection
                for addr, dev in self.tcp_devices.items():
                    if dev:
                        uptime = time.time() - dev.connected_at
                        logger.info(
                            "%s   - %s: uptime=%.1fs, ready=%s, id=%s",
                            lp,
                            addr,
                            uptime,
                            dev.ready_to_control,
                            dev.id,
                        )

            except asyncio.CancelledError:
                logger.info("%s Pool monitoring task cancelled", lp)
                break
            except Exception:
                logger.exception("%s Error in pool monitoring", lp)
                await asyncio.sleep(30)  # Wait before retrying on error

    async def start(self):
        lp = f"{self.lp}start:"
        logger.debug("%s Creating SSL context - key: %s, cert: %s", lp, self.key_file, self.cert_file)
        try:
            self.ssl_context = await self.create_ssl_context()
            self._server = await asyncio.start_server(
                self._register_new_connection,
                host=self.host,
                port=self.port,
                ssl=self.ssl_context,  # Pass the SSL context to enable SSL/TLS
            )
        except asyncio.CancelledError as ce:
            logger.debug("%s Server start cancelled: %s", lp, ce)
            # propagate the cancellation
            raise
        except Exception:
            logger.exception("%s Failed to start server", lp)
        else:
            logger.info(
                "%s bound to %s:%s - Waiting for connections from Cync devices, if you dont"
                " see any, check your DNS redirection, VLAN and firewall settings.",
                lp,
                self.host,
                self.port,
            )
            self.running = True
            try:
                # "state_topic": f"{self.topic}/status/bridge/tcp_server/running",
                # TODO: publish the server running status
                if g.mqtt_client:
                    await g.mqtt_client.publish(
                        f"{g.env.mqtt_topic}/status/bridge/tcp_server/running",
                        b"ON",
                    )

                # Start the periodic status refresh task
                self.refresh_task = asyncio.create_task(self.periodic_status_refresh())

                # Start the connection pool monitoring task
                self.pool_monitor_task = asyncio.create_task(self.periodic_pool_status_logger())

                async with self._server:
                    await self._server.serve_forever()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("%s Server Exception", self.lp)
            else:
                logger.debug("%s DEBUG>>> AFTER self._server.serve_forever() <<<DEBUG", lp)

    async def stop(self):
        try:
            self.shutting_down = True
            lp = f"{self.lp}stop:"
            device: CyncTCPDevice
            devices = list(self.tcp_devices.values())
            if devices:
                logger.debug("%s Shutting down, closing connections to %s devices...", lp, len(devices))
                for device in devices:
                    try:
                        await device.close()
                    except asyncio.CancelledError as ce:
                        logger.debug("%s Device close cancelled: %s", lp, ce)
                        # propagate the cancellation
                        raise
                    except Exception:
                        logger.exception("%s Error closing Cync Wi-Fi device connection", lp)
                    else:
                        logger.debug("%s Cync Wi-Fi device connection closed", lp)
            else:
                logger.debug("%s No Cync Wi-Fi devices connected!", lp)

            if self._server:
                if self._server.is_serving():
                    logger.debug("%s shutting down NOW...", lp)
                    self._server.close()
                    await self._server.wait_closed()
                    # TODO: publish the server running status
                    if g.mqtt_client:
                        await g.mqtt_client.publish(
                            f"{g.env.mqtt_topic}/status/bridge/tcp_server/running",
                            b"OFF",
                        )
                    logger.debug("%s shut down!", lp)
                else:
                    logger.debug("%s not running!", lp)

        except asyncio.CancelledError as ce:
            logger.debug("%s Server stop cancelled: %s", lp, ce)
            # propagate the cancellation
            raise
        except Exception:
            logger.exception("%s Error during server shutdown", lp)
        else:
            logger.info("%s Server stopped successfully.", lp)
        finally:
            if self.start_task and not self.start_task.done():
                logger.debug("%s FINISHING: Cancelling start task", lp)
                self.start_task.cancel()
            if self.refresh_task and not self.refresh_task.done():
                logger.debug("%s FINISHING: Cancelling refresh task", lp)
                self.refresh_task.cancel()
            if self.pool_monitor_task and not self.pool_monitor_task.done():
                logger.debug("%s FINISHING: Cancelling pool monitor task", lp)
                self.pool_monitor_task.cancel()

    async def _register_new_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peername = writer.get_extra_info("peername")
        client_ip: str = peername[0]
        client_port: int = peername[1]
        client_addr: str = f"{client_ip}:{client_port}"  # Use IP:port to allow multiple connections from same IP

        if client_addr in self.tcp_conn_attempts:
            self.tcp_conn_attempts[client_addr] += 1
        else:
            self.tcp_conn_attempts[client_addr] = 1
        lp = f"{self.lp}new_conn:{client_addr}:"

        # Branch based on relay mode
        if self.cloud_relay_enabled:
            # Cloud relay mode - use CloudRelayConnection
            # TODO: Add support for local commands in relay mode by tracking bridge devices
            #       even when in relay mode. This would allow bidirectional control:
            #       - Commands from HA -> intercepted and sent via relay
            #       - Cloud commands -> forwarded to devices
            #       - Status updates -> sent to both HA and cloud
            #       Current limitation: tcp_devices only populated in LAN-only mode
            logger.info("%s New connection in RELAY mode", lp)
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
                logger.debug("%s Relay connection cancelled: %s", lp, ce)
                raise
            except Exception:
                logger.exception("%s Error in relay connection", lp)
        else:
            # Normal LAN-only mode - use CyncTCPDevice
            existing_device = await self.remove_tcp_device(client_addr)
            if existing_device is not None:
                existing_device_id = id(existing_device)
                logger.debug("%s Existing device found (%s), gracefully killing...", lp, existing_device_id)
                del existing_device
            try:
                new_device = CyncTCPDevice(reader, writer, client_addr)
                # will sleep devices that cant connect to prevent connection flooding
                can_connect = await new_device.can_connect()
                if can_connect:
                    await self.add_tcp_device(new_device)
                else:
                    del new_device
            except asyncio.CancelledError as ce:
                logger.debug("%s Connection cancelled: %s", lp, ce)
                # propagate the cancellation
                raise
            except Exception:
                logger.exception("%s Error creating new Cync Wi-Fi device", lp)
