#!/usr/bin/env python3
"""
Minimal MITM proxy for Cync protocol packet capture.

Usage:
    python mitm/mitm-proxy.py --listen-port 23779 --upstream-host homeassistant.local --upstream-port 23779

    # Or forward to real cloud for protocol research:
    python mitm/mitm-proxy.py --listen-port 23779 --upstream-host 35.196.85.236 --upstream-port 23779

    # Or forward to localhost cloud relay for testing:
    python mitm/mitm-proxy.py --listen-port 23779 --upstream-host localhost --upstream-port 23780 --no-ssl
"""

import argparse
import asyncio
import json
import random
import signal
import ssl
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aiohttp import web

try:
    from mitm.interfaces.packet_observer import PacketDirection, PacketObserver
    from mitm.validation.codec_validator import CodecValidatorPlugin
except ModuleNotFoundError:
    # For direct execution as script
    from interfaces.packet_observer import PacketDirection, PacketObserver  # type: ignore

    CodecValidatorPlugin = None  # type: ignore[assignment, misc]


@dataclass
class BackpressureConfig:
    """Configuration for backpressure simulation modes."""

    mode: str = "normal"
    slow_consumer_delay: float = 0.0
    buffer_fill_packet_limit: int = 10
    ack_delay: float = 0.0


class MITMProxy:
    """MITM proxy for Cync protocol packet capture."""

    def __init__(
        self,
        listen_port: int,
        upstream_host: str,
        upstream_port: int,
        use_ssl: bool = True,
        backpressure: BackpressureConfig | None = None,
    ):
        self.listen_port = listen_port
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.ssl_context = self._create_ssl_context() if use_ssl else None
        self.backpressure_config = backpressure or BackpressureConfig()
        # Always use mitm/captures/ regardless of where proxy is started
        self.capture_dir = Path(__file__).parent / "captures"
        self.capture_dir.mkdir(exist_ok=True)
        self.capture_file = (
            self.capture_dir / f"capture_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.txt"
        )
        self.server: asyncio.Server | None = None
        self.active_connections: dict[
            int, tuple[asyncio.StreamWriter, asyncio.StreamWriter]
        ] = {}  # connection_id -> (device_writer, cloud_writer)
        self.connection_lock = asyncio.Lock()  # Thread-safe injection
        self.current_annotation: str | None = None  # For annotating capture sessions
        self.observers: list[PacketObserver] = []  # Observer plugins

        # Backpressure testing configuration

        # Metrics tracking
        self.metrics = {
            "dev_to_cloud_packets": 0,
            "cloud_to_dev_packets": 0,
            "dev_to_cloud_bytes": 0,
            "cloud_to_dev_bytes": 0,
            "buffer_fill_reached": False,
            "disconnects": 0,
            "ack_delays_applied": 0,
        }

    def _create_ssl_context(self) -> ssl.SSLContext | None:
        """Create SSL context for upstream connections."""
        # Auto-detect SSL context based on upstream host
        if self.upstream_host in ("localhost", "127.0.0.1"):
            # No SSL for localhost
            return None
        # Production cloud - disable certificate verification for MITM purposes
        # This is acceptable for local debugging/packet capture
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    def _create_ssl_context_for_devices(self) -> ssl.SSLContext:
        """Create SSL context for accepting device TLS connections.

        Uses same configuration as cloud relay to ensure device compatibility.
        """
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile="certs/cert.pem", keyfile="certs/key.pem")
        # Turn off SSL verification (devices don't validate)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # Cipher list from cloud relay - required for Cync device compatibility
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

    def register_observer(self, observer: PacketObserver) -> None:
        """Register plugin to receive packet notifications.

        Args:
            observer: Plugin implementing PacketObserver Protocol
        """
        self.observers.append(observer)
        print(f"Registered observer: {observer.__class__.__name__}", file=sys.stderr)

    def _notify_observers_packet(
        self, direction: PacketDirection, data: bytes, connection_id: int
    ) -> None:
        """Notify all observers of packet event.

        Observer failures don't break proxy - errors are logged but ignored.
        """
        for observer in self.observers:
            try:
                observer.on_packet_received(direction, data, connection_id)
            except Exception as e:
                print(f"Observer error ({observer.__class__.__name__}): {e}", file=sys.stderr)

    def _notify_observers_connection_established(self, connection_id: int) -> None:
        """Notify all observers of connection established event."""
        for observer in self.observers:
            try:
                observer.on_connection_established(connection_id)
            except Exception as e:
                print(f"Observer error ({observer.__class__.__name__}): {e}", file=sys.stderr)

    def _notify_observers_connection_closed(self, connection_id: int) -> None:
        """Notify all observers of connection closed event."""
        for observer in self.observers:
            try:
                observer.on_connection_closed(connection_id)
            except Exception as e:
                print(f"Observer error ({observer.__class__.__name__}): {e}", file=sys.stderr)

    def _is_ack_packet(self, data: bytes) -> bool:
        """Detect if packet is an ACK (0x28, 0x7B, 0x88, 0xD8)."""
        if len(data) < 1:
            return False
        packet_type = data[0]
        return packet_type in (0x28, 0x7B, 0x88, 0xD8)

    async def start(self) -> None:
        """Start the proxy server."""
        # Create SSL context for accepting device TLS connections
        device_ssl_context = self._create_ssl_context_for_devices()

        self.server = await asyncio.start_server(
            self.handle_device,
            "0.0.0.0",
            self.listen_port,
            ssl=device_ssl_context,  # Enable TLS termination
        )

        print(f"MITM Proxy listening on port {self.listen_port} (TLS)", file=sys.stderr)
        print(
            f"Forwarding to {self.upstream_host}:{self.upstream_port}",
            file=sys.stderr,
        )
        print(f"Upstream SSL: {'enabled' if self.ssl_context else 'disabled'}", file=sys.stderr)
        print(f"Captures will be saved to {self.capture_file}", file=sys.stderr)
        print(f"Backpressure mode: {self.backpressure_config.mode}", file=sys.stderr)
        if self.backpressure_config.mode == "slow_consumer":
            print(
                f"  Slow consumer delay: {self.backpressure_config.slow_consumer_delay}s",
                file=sys.stderr,
            )
        elif self.backpressure_config.mode == "buffer_fill":
            print(
                f"  Buffer fill packet limit: {self.backpressure_config.buffer_fill_packet_limit}",
                file=sys.stderr,
            )
        elif self.backpressure_config.mode == "ack_delay":
            print(f"  ACK delay: {self.backpressure_config.ack_delay}s", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

        async with self.server:
            await self.server.serve_forever()

    async def handle_device(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle device connection and forward to upstream."""
        device_addr = writer.get_extra_info("peername")
        print(f"Device connected: {device_addr}", file=sys.stderr)

        cloud_writer = None
        connection_id = None
        try:
            # Connect to upstream (cloud or cloud relay)
            try:
                cloud_reader, cloud_writer = await asyncio.open_connection(
                    self.upstream_host, self.upstream_port, ssl=self.ssl_context
                )
            except ssl.SSLError as e:
                print(f"SSL connection failed: {e}", file=sys.stderr)
                raise
            except ConnectionRefusedError:
                print(
                    f"Cloud connection refused (check host/port: {self.upstream_host}:{self.upstream_port})",
                    file=sys.stderr,
                )
                raise
            except TimeoutError:
                print("Cloud connection timeout (check network)", file=sys.stderr)
                raise

            print(
                f"Connected to upstream: {self.upstream_host}:{self.upstream_port}",
                file=sys.stderr,
            )

            # Track active connection with writers for injection
            connection_id = id(reader)
            async with self.connection_lock:
                self.active_connections[connection_id] = (writer, cloud_writer)

            # Notify observers of connection establishment
            self._notify_observers_connection_established(connection_id)

            # Bidirectional forwarding with logging (include connection ID)
            await asyncio.gather(
                self._forward_and_log(reader, cloud_writer, "DEV→CLOUD", connection_id),
                self._forward_and_log(cloud_reader, writer, "CLOUD→DEV", connection_id),
                return_exceptions=True,
            )

        except Exception as e:
            print(f"Connection error: {e}", file=sys.stderr)
        finally:
            # Clean up connection tracking
            if connection_id is not None:
                async with self.connection_lock:
                    if connection_id in self.active_connections:
                        del self.active_connections[connection_id]
                    self.metrics["disconnects"] += 1

                # Notify observers of connection closure (outside lock for symmetry with establishment)
                self._notify_observers_connection_closed(connection_id)

            writer.close()
            await writer.wait_closed()

            if cloud_writer:
                cloud_writer.close()
                await cloud_writer.wait_closed()

            print(f"Device disconnected: {device_addr}", file=sys.stderr)
            print(f"Metrics: {json.dumps(self.metrics)}", file=sys.stderr)

    def _update_packet_metrics(self, data: bytes, direction: str) -> None:
        """Update metrics for a forwarded packet."""
        if direction == "DEV→CLOUD":
            self.metrics["dev_to_cloud_packets"] += 1
            self.metrics["dev_to_cloud_bytes"] += len(data)
        else:
            self.metrics["cloud_to_dev_packets"] += 1
            self.metrics["cloud_to_dev_bytes"] += len(data)

    async def _handle_buffer_fill_backpressure(self, packet_count: int, direction: str) -> bool:
        """Handle buffer fill backpressure scenario. Returns True if should stop reading."""
        if (
            self.backpressure_config.mode == "buffer_fill"
            and direction == "DEV→CLOUD"
            and packet_count >= self.backpressure_config.buffer_fill_packet_limit
        ):
            if not self.metrics["buffer_fill_reached"]:
                self.metrics["buffer_fill_reached"] = True
                print(
                    f"[BACKPRESSURE] Buffer fill limit reached ({self.backpressure_config.buffer_fill_packet_limit} packets). "
                    f"Stopping reads from device. TCP buffer will fill.",
                    file=sys.stderr,
                )
            # Stop reading - this will cause TCP buffer to fill
            await asyncio.sleep(3600)  # Sleep for 1 hour (effectively forever)
            return True
        return False

    async def _handle_ack_delay_backpressure(self, data: bytes, direction: str) -> None:
        """Handle ACK delay backpressure scenario."""
        if (
            self.backpressure_config.mode == "ack_delay"
            and direction == "CLOUD→DEV"
            and self._is_ack_packet(data)
        ):
            self.metrics["ack_delays_applied"] += 1
            print(
                f"[BACKPRESSURE] Delaying ACK packet (type 0x{data[0]:02x}) by {self.backpressure_config.ack_delay}s",
                file=sys.stderr,
            )
            await asyncio.sleep(self.backpressure_config.ack_delay)

    async def _handle_slow_consumer_backpressure(self, direction: str) -> None:
        """Handle slow consumer backpressure scenario."""
        if (
            self.backpressure_config.mode == "slow_consumer"
            and direction == "DEV→CLOUD"
            and self.backpressure_config.slow_consumer_delay > 0
        ):
            await asyncio.sleep(self.backpressure_config.slow_consumer_delay)

    async def _forward_and_log(
        self,
        src: asyncio.StreamReader,
        dst: asyncio.StreamWriter,
        direction: str,
        connection_id: int | None = None,
    ) -> None:
        """Forward packets and log hex dumps with optional backpressure simulation."""
        packet_count = 0

        while True:
            try:
                # Scenario 2: Buffer Fill - Stop reading after limit
                if await self._handle_buffer_fill_backpressure(packet_count, direction):
                    break

                data = await src.read(4096)
                if not data:
                    break

                packet_count += 1

                # Update metrics
                self._update_packet_metrics(data, direction)

                # Log to stdout (structured JSON)
                self._log_packet(data, direction)

                # Save to capture file with connection tracking
                self._save_capture(data, direction, connection_id)

                # Notify observers of packet (if connection_id available)
                if connection_id is not None:
                    packet_direction = (
                        PacketDirection.DEVICE_TO_CLOUD
                        if direction == "DEV→CLOUD"
                        else PacketDirection.CLOUD_TO_DEVICE
                    )
                    self._notify_observers_packet(packet_direction, data, connection_id)

                # Scenario 3: ACK Delay - Delay forwarding of ACK packets
                await self._handle_ack_delay_backpressure(data, direction)

                # Forward to destination
                dst.write(data)
                await dst.drain()

                # Scenario 1: Slow Consumer - Delay after forwarding DEV→CLOUD packets
                await self._handle_slow_consumer_backpressure(direction)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Forward error ({direction}): {e}", file=sys.stderr)
                break

    def _log_packet(self, data: bytes, direction: str) -> None:
        """Log packet in structured JSON format to stdout."""
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "direction": direction,
            "length": len(data),
            "hex": data.hex(" "),
            "annotation": self.current_annotation,
        }
        print(json.dumps(log_entry))

    def _save_capture(self, data: bytes, direction: str, connection_id: int | None = None) -> None:
        """Save raw capture to file with connection tracking."""
        with self.capture_file.open("a") as f:
            annotation_str = f" [{self.current_annotation}]" if self.current_annotation else ""
            conn_str = f" [conn:{connection_id}]" if connection_id else ""
            f.write(
                f"{datetime.now(UTC).isoformat()} {direction}{annotation_str}{conn_str} ({len(data)} bytes)\n"
            )
            f.write(data.hex(" ") + "\n\n")

    async def inject_packet(
        self, hex_string: str, direction: str, broadcast: bool = False
    ) -> dict[str, Any]:
        """Inject arbitrary packet into active connections.

        Args:
            hex_string: Hex-encoded packet (e.g., "73 00 00 00 1e ...")
            direction: "CLOUD→DEV" or "DEV→CLOUD"
            broadcast: If True, inject to all connections; if False (default), inject to one random connection

        Returns:
            dict with status, timestamp, direction, length, connections, target_connections
        """
        async with self.connection_lock:
            if not self.active_connections:
                error_msg = "No active connections for injection"
                raise ValueError(error_msg)

            # Parse hex string to bytes
            packet = bytes.fromhex(hex_string.replace(" ", ""))

            # Select target connections
            if broadcast:
                target_connections = list(self.active_connections.items())
            else:
                # Pick ONE random connection
                conn_id = random.choice(list(self.active_connections.keys()))
                target_connections = [(conn_id, self.active_connections[conn_id])]

            # Inject into target connections
            injected_count = 0
            for conn_id, (device_writer, cloud_writer) in target_connections:
                if direction == "CLOUD→DEV":
                    device_writer.write(packet)
                    await device_writer.drain()
                elif direction == "DEV→CLOUD":
                    cloud_writer.write(packet)
                    await cloud_writer.drain()
                else:
                    error_msg = f"Invalid direction: {direction}"
                    raise ValueError(error_msg)

                # Log injection with connection ID
                self._log_packet(packet, f"{direction} [INJECTED to conn:{conn_id}]")
                self._save_capture(packet, f"{direction} [INJECTED to conn:{conn_id}]", conn_id)
                injected_count += 1

            return {
                "status": "success",
                "timestamp": datetime.now(UTC).isoformat(),
                "direction": direction,
                "length": len(packet),
                "total_connections": len(self.active_connections),
                "target_connections": injected_count,
                "broadcast": broadcast,
            }

    async def _handle_inject(self, request: web.Request) -> web.Response:
        """Handle POST /inject - inject arbitrary packet.

        Request body:
            {
                "hex": "73 00 00 ...",
                "direction": "CLOUD→DEV" or "DEV→CLOUD",
                "broadcast": true/false (optional, default: false - sends to one random connection)
            }
        """
        try:
            data = await request.json()
            hex_string = data.get("hex")
            direction = data.get("direction")
            broadcast = data.get("broadcast", False)  # Default: single random connection

            if not hex_string or not direction:
                return web.json_response(
                    {"error": "Missing 'hex' or 'direction' field"}, status=400
                )

            result = await self.inject_packet(hex_string, direction, broadcast)
            return web.json_response(result)

        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        except Exception as e:
            return web.json_response({"error": f"Injection failed: {e}"}, status=500)

    async def _handle_status(self, _request: web.Request) -> web.Response:
        """Handle GET /status - check connection status."""
        async with self.connection_lock:
            return web.json_response(
                {
                    "status": "running",
                    "active_connections": len(self.active_connections),
                    "capture_file": str(self.capture_file),
                    "current_annotation": self.current_annotation,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

    async def _handle_metrics(self, _request: web.Request) -> web.Response:
        """Handle GET /metrics - retrieve backpressure test metrics."""
        return web.json_response(
            {
                "metrics": self.metrics,
                "backpressure_mode": self.backpressure_config.mode,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    async def _handle_annotate(self, request: web.Request) -> web.Response:
        """Handle POST /annotate - set annotation label for subsequent packets."""
        try:
            data = await request.json()
            label = data.get("label")

            if label is None:
                return web.json_response({"error": "Missing 'label' field"}, status=400)

            self.current_annotation = label if label else None

            # Log annotation change to capture file
            with self.capture_file.open("a") as f:
                f.write(f"\n{'=' * 60}\n")
                f.write(f"ANNOTATION SET: {label}\n")
                f.write(f"Timestamp: {datetime.now(UTC).isoformat()}\n")
                f.write(f"{'=' * 60}\n\n")

            return web.json_response(
                {
                    "status": "ok",
                    "label": self.current_annotation,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

        except Exception as e:
            return web.json_response({"error": f"Annotation failed: {e}"}, status=500)

    async def start_api_server(self, api_port: int) -> None:
        """Start REST API server for packet injection."""
        app = web.Application()
        app.router.add_post("/inject", self._handle_inject)
        app.router.add_post("/annotate", self._handle_annotate)
        app.router.add_get("/status", self._handle_status)
        app.router.add_get("/metrics", self._handle_metrics)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", api_port)
        _site_task = await site.start()
        _ = _site_task  # Store reference for RUF006

        print(f"REST API server listening on port {api_port}", file=sys.stderr)
        print("  POST /inject - Inject packet", file=sys.stderr)
        print("  POST /annotate - Set annotation label", file=sys.stderr)
        print("  GET /status - Check status", file=sys.stderr)
        print("  GET /metrics - Retrieve backpressure metrics", file=sys.stderr)

    async def shutdown(self) -> None:
        """Gracefully shutdown the proxy."""
        print("\nShutting down proxy...", file=sys.stderr)

        if self.server:
            self.server.close()
            await self.server.wait_closed()

        print(f"Capture saved to: {self.capture_file}", file=sys.stderr)
        print("Proxy stopped.", file=sys.stderr)


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="MITM proxy for Cync protocol packet capture")
    parser.add_argument(
        "--listen-port",
        type=int,
        default=23779,
        help="Port to listen on for device connections (default: 23779)",
    )
    parser.add_argument(
        "--upstream-host",
        type=str,
        default="35.196.85.236",
        help="Upstream host to forward to (default: 35.196.85.236)",
    )
    parser.add_argument(
        "--upstream-port",
        type=int,
        default=23779,
        help="Upstream port to forward to (default: 23779)",
    )
    parser.add_argument(
        "--no-ssl",
        action="store_true",
        help="Disable SSL for upstream connection (for localhost testing)",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=8080,
        help="REST API port for packet injection (default: 8080)",
    )
    parser.add_argument(
        "--enable-codec-validation",
        action="store_true",
        help="Enable Phase 1a codec validation plugin",
    )

    # Backpressure testing arguments
    parser.add_argument(
        "--backpressure-mode",
        type=str,
        choices=["normal", "slow_consumer", "buffer_fill", "ack_delay"],
        default="normal",
        help="Backpressure testing mode (default: normal)",
    )
    parser.add_argument(
        "--slow-consumer-delay",
        type=float,
        default=1.0,
        help="Delay in seconds between reads for slow_consumer mode (default: 1.0)",
    )
    parser.add_argument(
        "--buffer-fill-packet-limit",
        type=int,
        default=10,
        help="Number of packets to read before stopping for buffer_fill mode (default: 10)",
    )
    parser.add_argument(
        "--ack-delay",
        type=float,
        default=2.0,
        help="Delay in seconds for ACK forwarding in ack_delay mode (default: 2.0)",
    )

    args = parser.parse_args()

    backpressure_config = BackpressureConfig(
        mode=args.backpressure_mode,
        slow_consumer_delay=args.slow_consumer_delay,
        buffer_fill_packet_limit=args.buffer_fill_packet_limit,
        ack_delay=args.ack_delay,
    )

    proxy = MITMProxy(
        listen_port=args.listen_port,
        upstream_host=args.upstream_host,
        upstream_port=args.upstream_port,
        use_ssl=not args.no_ssl,
        backpressure=backpressure_config,
    )

    # Register codec validation plugin if enabled
    if args.enable_codec_validation:
        if CodecValidatorPlugin is None:
            print("Warning: CodecValidatorPlugin not available", file=sys.stderr)
        else:
            proxy.register_observer(CodecValidatorPlugin())

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def signal_handler() -> None:
        print("\nReceived shutdown signal", file=sys.stderr)
        _shutdown_task = asyncio.create_task(proxy.shutdown())
        _ = _shutdown_task  # Store reference for RUF006
        loop.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        # Start REST API server
        await proxy.start_api_server(args.api_port)

        # Start proxy server
        await proxy.start()
    except KeyboardInterrupt:
        pass
    finally:
        await proxy.shutdown()


def cli_main() -> None:
    """CLI entry point for poetry scripts."""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
