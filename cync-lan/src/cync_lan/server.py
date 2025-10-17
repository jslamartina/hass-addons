import asyncio
import logging
import os
import socket
import ssl
from typing import Optional, Union

import uvloop

from cync_lan.const import *
from cync_lan.devices import CyncDevice, CyncGroup, CyncTCPDevice
from cync_lan.packet_parser import parse_cync_packet, format_packet_log
from cync_lan.packet_checksum import calculate_checksum_between_markers
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
        self.cloud_reader: Optional[asyncio.StreamReader] = None
        self.cloud_writer: Optional[asyncio.StreamWriter] = None
        self.device_endpoint: Optional[bytes] = None
        self.injection_task: Optional[asyncio.Task] = None
        self.forward_tasks: list[asyncio.Task] = []
        self.lp = f"CloudRelay:{client_addr}:"

    async def connect_to_cloud(self):
        """Establish SSL connection to Cync cloud server"""
        lp = f"{self.lp}connect_cloud:"
        try:
            # Create SSL context for cloud connection
            ssl_context = ssl.create_default_context()
            if self.disable_ssl_verify:
                logger.warning(
                    f"{lp} SSL verification DISABLED - DEBUG MODE (use only for local testing)"
                )
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            else:
                # Secure mode - but Cync cloud uses self-signed certs, so we still need to disable verification
                logger.debug(f"{lp} Connecting to cloud with SSL")
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            # Connect to cloud
            self.cloud_reader, self.cloud_writer = await asyncio.open_connection(
                self.cloud_server, self.cloud_port, ssl=ssl_context
            )
            logger.info(
                f"{lp} Connected to cloud server {self.cloud_server}:{self.cloud_port}"
            )
            return True
        except Exception as e:
            logger.error(f"{lp} Failed to connect to cloud: {e}")
            return False

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
                logger.error(f"{lp} Cannot start relay without cloud connection")
                await self.close()
                return
        else:
            logger.info(f"{lp} LAN-only mode - cloud forwarding disabled")

        try:
            # Read first packet from device to get endpoint
            first_packet = await self.device_reader.read(1024)
            if first_packet and len(first_packet) >= 31 and first_packet[0] == 0x23:
                self.device_endpoint = first_packet[6:10]
                logger.info(
                    f"{lp} Device endpoint: {' '.join(f'{b:02x}' for b in self.device_endpoint)}"
                )

            # Forward first packet to cloud if enabled
            if self.forward_to_cloud and self.cloud_writer:
                self.cloud_writer.write(first_packet)
                await self.cloud_writer.drain()

            # Parse and log first packet
            if self.debug_logging:
                parsed = parse_cync_packet(first_packet, "DEV->CLOUD")
                if parsed:
                    logger.debug(f"{lp}\n{format_packet_log(parsed)}")

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
                    self._forward_with_inspection(
                        self.cloud_reader, self.device_writer, "CLOUD->DEV"
                    )
                )
                self.forward_tasks.append(cloud_to_dev_task)

            # Start injection checker (debug feature)
            self.injection_task = asyncio.create_task(self._check_injection_commands())

            # Wait for all tasks to complete
            await asyncio.gather(*self.forward_tasks, return_exceptions=True)

        except Exception as e:
            logger.error(f"{lp} Relay error: {e}")
        finally:
            await self.close()

    async def _forward_with_inspection(
        self,
        source_reader: asyncio.StreamReader,
        dest_writer: Optional[asyncio.StreamWriter],
        direction: str,
    ):
        """Forward packets while inspecting and logging"""
        lp = f"{self.lp}{direction}:"
        try:
            while True:
                data = await source_reader.read(4096)
                if not data:
                    logger.debug(f"{lp} Connection closed")
                    break

                # Parse packet
                parsed = parse_cync_packet(data, direction)

                # Log if debug enabled (skip keepalives to reduce clutter)
                if self.debug_logging and parsed:
                    if parsed.get("packet_type") != "0x78":  # Skip KEEPALIVE
                        logger.debug(f"{lp}\n{format_packet_log(parsed)}")

                # Extract status updates for MQTT (for 0x43 DEVICE_INFO packets)
                if parsed and "device_statuses" in parsed:
                    for status in parsed["device_statuses"]:
                        # Convert parsed status to raw_state format for existing parse_status
                        raw_state = bytearray(8)
                        raw_state[0] = status["device_id"]
                        raw_state[1] = 1 if status["state"] == "ON" else 0
                        raw_state[2] = status["brightness"]
                        raw_state[3] = (
                            status.get("temp", 0)
                            if status.get("mode") == "WHITE"
                            else 254
                        )
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
                        await g.ncync_server.parse_status(
                            bytes(raw_state), from_pkt="0x43"
                        )

                # Forward to destination (if cloud forwarding enabled)
                if dest_writer:
                    dest_writer.write(data)
                    await dest_writer.drain()

        except asyncio.CancelledError:
            logger.debug(f"{lp} Task cancelled")
            raise
        except Exception as e:
            logger.error(f"{lp} Forward error: {e}")

    async def _check_injection_commands(self):
        """Periodically check for packet injection commands (debug feature)"""
        lp = f"{self.lp}injection:"
        inject_file = "/tmp/cync_inject_command.txt"
        raw_inject_file = "/tmp/cync_inject_raw_bytes.txt"

        logger.debug(f"{lp} Injection checker started")

        try:
            while True:
                await asyncio.sleep(1)

                # Check for raw bytes injection
                if os.path.exists(raw_inject_file):
                    try:
                        with open(raw_inject_file, "r") as f:
                            raw_hex = f.read().strip()
                        os.remove(raw_inject_file)

                        hex_bytes = raw_hex.replace(" ", "").replace("\n", "")
                        packet = bytes.fromhex(hex_bytes)

                        logger.info(f"{lp} Injecting raw packet ({len(packet)} bytes)")
                        logger.debug(
                            f"{lp} Hex: {' '.join(f'{b:02x}' for b in packet)}"
                        )

                        self.device_writer.write(packet)
                        await self.device_writer.drain()

                        logger.info(f"{lp} Raw injection complete")
                    except Exception as e:
                        logger.error(f"{lp} Error injecting raw bytes: {e}")

                # Check for mode injection (for switches)
                if os.path.exists(inject_file):
                    try:
                        with open(inject_file, "r") as f:
                            mode = f.read().strip().lower()
                        os.remove(inject_file)

                        if mode in ["smart", "traditional"] and self.device_endpoint:
                            logger.info(f"{lp} Injecting {mode.upper()} mode packet")

                            # Craft mode packet (similar to MITM)
                            mode_byte = 0x02 if mode == "smart" else 0x01
                            counter = 0x10  # Fixed counter for injection

                            packet = self._craft_mode_packet(
                                self.device_endpoint, counter, mode_byte
                            )

                            self.device_writer.write(packet)
                            await self.device_writer.drain()

                            logger.info(f"{lp} Mode injection complete")
                    except Exception as e:
                        logger.error(f"{lp} Error injecting mode packet: {e}")

        except asyncio.CancelledError:
            logger.debug(f"{lp} Injection checker cancelled")
            raise
        except Exception as e:
            logger.error(f"{lp} Injection checker error: {e}")

    def _craft_mode_packet(
        self, endpoint: bytes, counter: int, mode_byte: int
    ) -> bytes:
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
        logger.debug(f"{lp} Closing relay connection")

        # Cancel injection task
        if self.injection_task and not self.injection_task.done():
            self.injection_task.cancel()
            try:
                await self.injection_task
            except asyncio.CancelledError:
                pass

        # Cancel forwarding tasks
        for task in self.forward_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close cloud connection
        if self.cloud_writer:
            try:
                self.cloud_writer.close()
                await self.cloud_writer.wait_closed()
            except Exception as e:
                logger.debug(f"{lp} Error closing cloud writer: {e}")

        # Close device connection
        try:
            self.device_writer.close()
            await self.device_writer.wait_closed()
        except Exception as e:
            logger.debug(f"{lp} Error closing device writer: {e}")

        logger.debug(f"{lp} Relay connection closed")


class NCyncServer:
    """
    A class to represent a Cync LAN server that listens for connections from Cync Wi-Fi devices.
    The Wi-Fi devices translate messages, status updates and commands to/from the Cync BTLE mesh.
    """

    devices: dict[int, CyncDevice] = {}
    groups: dict[int, CyncGroup] = {}
    tcp_devices: dict[str, Optional[CyncTCPDevice]] = {}
    shutting_down: bool = False
    running: bool = False
    host: str
    port: int
    cert_file: Optional[str] = None
    key_file: Optional[str] = None
    loop: Union[asyncio.AbstractEventLoop, uvloop.Loop]
    _server: Optional[asyncio.Server] = None
    lp: str = "nCync:"
    start_task: Optional[asyncio.Task] = None
    refresh_task: Optional[asyncio.Task] = None
    _instance: Optional["NCyncServer"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, devices: dict, groups: dict = None):
        self.devices = devices
        self.groups = groups if groups is not None else {}
        self.tcp_conn_attempts: dict = {}
        self.ssl_context: Optional[ssl.SSLContext] = None
        self.host = CYNC_SRV_HOST
        self.port = CYNC_PORT
        g.reload_env()
        self.cert_file = g.env.cync_srv_ssl_cert
        self.key_file = g.env.cync_srv_ssl_key
        self.loop: Union[asyncio.AbstractEventLoop, uvloop.Loop] = (
            asyncio.get_event_loop()
        )

        # Cloud relay configuration
        self.cloud_relay_enabled = g.env.cync_cloud_relay_enabled
        self.cloud_forward = g.env.cync_cloud_forward
        self.cloud_server = g.env.cync_cloud_server
        self.cloud_port = g.env.cync_cloud_port
        self.cloud_debug_logging = g.env.cync_cloud_debug_logging
        self.cloud_disable_ssl_verify = g.env.cync_cloud_disable_ssl_verify

        if self.cloud_relay_enabled:
            logger.info(
                f"{self.lp} Cloud relay mode ENABLED "
                f"(forward_to_cloud={self.cloud_forward}, "
                f"debug_logging={self.cloud_debug_logging})"
            )

    async def remove_tcp_device(
        self, device: Union[CyncTCPDevice, str]
    ) -> Optional[CyncTCPDevice]:
        """
        Remove a TCP device from the server's device list.
        :param device: The CyncTCPDevice to remove.
        """
        dev = None
        lp = f"{self.lp}remove_tcp_device:"
        if isinstance(device, str):
            # if device is a string, it is the address
            if device in self.tcp_devices:
                device = self.tcp_devices[device]

        if isinstance(device, CyncTCPDevice):
            if device.address in self.tcp_devices:
                dev = self.tcp_devices.pop(device.address, None)
                if dev is not None:
                    logger.debug(
                        f"{lp} Removed TCP device {device.address} from server."
                    )
                    # "state_topic": f"{self.topic}/status/bridge/tcp_devices/connected",
                    # TODO: publish the device removal
                    if g.mqtt_client is not None:
                        await g.mqtt_client.publish(
                            f"{g.env.mqtt_topic}/status/bridge/tcp_devices/connected",
                            str(len(self.tcp_devices)).encode(),
                        )
            else:
                logger.warning(
                    f"{lp} Device {device.address} not found in TCP devices."
                )
        return dev

    async def add_tcp_device(self, device: CyncTCPDevice):
        """
        Add a TCP device to the server's device list.
        :param device: The CyncTCPDevice to add.
        """
        lp = f"{self.lp}add_tcp_device:"
        self.tcp_devices[device.address] = device
        logger.debug(f"{lp} Added TCP device {device.address} to server.")
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

    async def parse_status(self, raw_state: bytes, from_pkt: Optional[str] = None):
        """Extracted status packet parsing, handles mqtt publishing and device state changes."""
        _id = raw_state[0]
        device = g.ncync_server.devices.get(_id)
        if device is None:
            logger.warning(
                f"Device ID: {_id} not found in devices! device may be disabled in config file or you need to "
                f"re-export your Cync account devices!"
            )
            return
        state = raw_state[1]
        brightness = raw_state[2]
        temp = raw_state[3]
        r = raw_state[4]
        _g = raw_state[5]
        b = raw_state[6]
        connected_to_mesh = 1
        # check if len is enough for good byte, it is optional
        if len(raw_state) > 7:
            # The last byte seems to indicate if the device is online or offline (connected to mesh / powered on)
            connected_to_mesh = raw_state[7]

        if connected_to_mesh == 0:
            # This usually happens when a device loses power/connection.
            # Increment counter and only mark offline after 3 consecutive offline reports
            # to avoid false positives from unreliable mesh info packets
            device.offline_count += 1
            if device.offline_count >= 3 and device.online:
                device.online = False
                logger.warning(
                    f'{self.lp} Device ID: {_id} ("{device.name}") has been offline for {device.offline_count} '
                    f"consecutive checks, marking as unavailable..."
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
            await g.mqtt_client.parse_device_status(
                device.id, new_state, from_pkt=from_pkt
            )
            g.ncync_server.devices[device.id] = device

    async def periodic_status_refresh(self):
        """Periodic sanity check to refresh device status and ensure sync with actual device state."""
        lp = f"{self.lp}status_refresh:"
        logger.info(f"{lp} Starting periodic status refresh task...")

        while self.running:
            try:
                await asyncio.sleep(300)  # Refresh every 5 minutes

                if not self.running:
                    break

                logger.debug(f"{lp} Performing periodic status refresh...")

                # Get active TCP bridge devices
                bridge_devices = [
                    dev
                    for dev in self.tcp_devices.values()
                    if dev and dev.ready_to_control
                ]

                if not bridge_devices:
                    logger.debug(
                        f"{lp} No active bridge devices available for status refresh"
                    )
                    continue

                # Request mesh info from each bridge to refresh all device statuses
                for bridge_device in bridge_devices:
                    try:
                        logger.debug(
                            f"{lp} Requesting mesh info from bridge {bridge_device.address}"
                        )
                        await bridge_device.ask_for_mesh_info(
                            False
                        )  # False = don't log verbose
                        await asyncio.sleep(1)  # Small delay between bridge requests
                    except Exception as e:
                        logger.warning(
                            f"{lp} Failed to refresh status from bridge {bridge_device.address}: {e}"
                        )

                logger.debug(f"{lp} Periodic status refresh completed")

            except asyncio.CancelledError:
                logger.info(f"{lp} Periodic status refresh task cancelled")
                break
            except Exception as e:
                logger.error(f"{lp} Error in periodic status refresh: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying on error

    async def start(self):
        lp = f"{self.lp}start:"
        logger.debug(
            f"{lp} Creating SSL context - key: {self.key_file}, cert: {self.cert_file}"
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
            logger.debug(f"{lp} Server start cancelled: {ce}")
            # propagate the cancellation
            raise ce
        except Exception as e:
            logger.exception(f"{lp} Failed to start server: {e}")
        else:
            logger.info(
                f"{lp} bound to {self.host}:{self.port} - Waiting for connections from Cync devices, if you dont"
                f" see any, check your DNS redirection, VLAN and firewall settings."
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

                async with self._server:
                    await self._server.serve_forever()
            except asyncio.CancelledError as ce:
                raise ce
            except Exception as e:
                logger.exception(f"{self.lp} Server Exception: {e}")
            else:
                logger.debug(
                    f"{lp} DEBUG>>> AFTER self._server.serve_forever() <<<DEBUG"
                )

    async def stop(self):
        try:
            self.shutting_down = True
            lp = f"{self.lp}stop:"
            device: CyncTCPDevice
            devices = list(self.tcp_devices.values())
            if devices:
                logger.debug(
                    f"{lp} Shutting down, closing connections to {len(devices)} devices..."
                )
                for device in devices:
                    try:
                        await device.close()
                    except asyncio.CancelledError as ce:
                        logger.debug(f"{lp} Device close cancelled: {ce}")
                        # propagate the cancellation
                        raise ce
                    except Exception as e:
                        logger.exception(
                            f"{lp} Error closing Cync Wi-Fi device connection: {e}"
                        )
                    else:
                        logger.debug(f"{lp} Cync Wi-Fi device connection closed")
            else:
                logger.debug(f"{lp} No Cync Wi-Fi devices connected!")

            if self._server:
                if self._server.is_serving():
                    logger.debug(f"{lp} shutting down NOW...")
                    self._server.close()
                    await self._server.wait_closed()
                    # TODO: publish the server running status
                    if g.mqtt_client:
                        await g.mqtt_client.publish(
                            f"{g.env.mqtt_topic}/status/bridge/tcp_server/running",
                            b"OFF",
                        )
                    logger.debug(f"{lp} shut down!")
                else:
                    logger.debug(f"{lp} not running!")

        except asyncio.CancelledError as ce:
            logger.debug(f"{lp} Server stop cancelled: {ce}")
            # propagate the cancellation
            raise ce
        except Exception as e:
            logger.exception(f"{lp} Error during server shutdown: {e}")
        else:
            logger.info(f"{lp} Server stopped successfully.")
        finally:
            if self.start_task and not self.start_task.done():
                logger.debug(f"{lp} FINISHING: Cancelling start task")
                self.start_task.cancel()
            if self.refresh_task and not self.refresh_task.done():
                logger.debug(f"{lp} FINISHING: Cancelling refresh task")
                self.refresh_task.cancel()

    async def _register_new_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        client_addr: str = writer.get_extra_info("peername")[0]
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
            logger.info(f"{lp} New connection in RELAY mode")
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
                logger.debug(f"{lp} Relay connection cancelled: {ce}")
                raise ce
            except Exception as e:
                logger.exception(f"{lp} Error in relay connection: {e}")
        else:
            # Normal LAN-only mode - use CyncTCPDevice
            existing_device = await self.remove_tcp_device(client_addr)
            if existing_device is not None:
                existing_device_id = id(existing_device)
                logger.debug(
                    f"{lp} Existing device found ({existing_device_id}), gracefully killing..."
                )
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
                logger.debug(f"{lp} Connection cancelled: {ce}")
                # propagate the cancellation
                raise ce
            except Exception as e:
                logger.exception(f"{lp} Error creating new Cync Wi-Fi device: {e}")
