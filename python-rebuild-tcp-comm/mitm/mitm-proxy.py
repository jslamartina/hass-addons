#!/usr/bin/env python3
"""
Minimal MITM proxy for Cync protocol packet capture.

Usage:
    python scripts/mitm-proxy.py --listen-port 23779 --upstream-host 35.196.85.236 --upstream-port 23779

    # Or forward to localhost cloud relay for testing:
    python scripts/mitm-proxy.py --listen-port 23779 --upstream-host localhost --upstream-port 23780 --no-ssl
"""

import argparse
import asyncio
import json
import signal
import ssl
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from aiohttp import web


class MITMProxy:
    """MITM proxy for Cync protocol packet capture."""

    def __init__(
        self,
        listen_port: int,
        upstream_host: str,
        upstream_port: int,
        use_ssl: bool = True,
    ):
        self.listen_port = listen_port
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.ssl_context = self._create_ssl_context() if use_ssl else None
        self.capture_dir = Path("captures")
        self.capture_dir.mkdir(exist_ok=True)
        self.capture_file = (
            self.capture_dir / f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        self.server: Optional[asyncio.Server] = None
        self.active_connections: dict[int, tuple[asyncio.StreamWriter, asyncio.StreamWriter]] = (
            {}
        )  # connection_id -> (device_writer, cloud_writer)
        self.connection_lock = asyncio.Lock()  # Thread-safe injection

    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Create SSL context for upstream connections."""
        # Auto-detect SSL context based on upstream host
        if self.upstream_host in ("localhost", "127.0.0.1"):
            # No SSL for localhost
            return None
        else:
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
            except asyncio.TimeoutError:
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

            # Bidirectional forwarding with logging
            await asyncio.gather(
                self._forward_and_log(reader, cloud_writer, "DEV→CLOUD"),
                self._forward_and_log(cloud_reader, writer, "CLOUD→DEV"),
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

            writer.close()
            await writer.wait_closed()

            if cloud_writer:
                cloud_writer.close()
                await cloud_writer.wait_closed()

            print(f"Device disconnected: {device_addr}", file=sys.stderr)

    async def _forward_and_log(
        self,
        src: asyncio.StreamReader,
        dst: asyncio.StreamWriter,
        direction: str,
    ) -> None:
        """Forward packets and log hex dumps."""
        while True:
            try:
                data = await src.read(4096)
                if not data:
                    break

                # Log to stdout (structured JSON)
                self._log_packet(data, direction)

                # Save to capture file
                self._save_capture(data, direction)

                # Forward to destination
                dst.write(data)
                await dst.drain()

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Forward error ({direction}): {e}", file=sys.stderr)
                break

    def _log_packet(self, data: bytes, direction: str) -> None:
        """Log packet in structured JSON format to stdout."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "direction": direction,
            "length": len(data),
            "hex": data.hex(" "),
        }
        print(json.dumps(log_entry))

    def _save_capture(self, data: bytes, direction: str) -> None:
        """Save raw capture to file."""
        with open(self.capture_file, "a") as f:
            f.write(f"{datetime.now().isoformat()} {direction} ({len(data)} bytes)\n")
            f.write(data.hex(" ") + "\n\n")

    async def inject_packet(self, hex_string: str, direction: str) -> dict[str, Any]:
        """Inject arbitrary packet into active connections.

        Args:
            hex_string: Hex-encoded packet (e.g., "73 00 00 00 1e ...")
            direction: "CLOUD→DEV" or "DEV→CLOUD"

        Returns:
            dict with status, timestamp, direction, length, connections
        """
        async with self.connection_lock:
            if not self.active_connections:
                raise ValueError("No active connections for injection")

            # Parse hex string to bytes
            packet = bytes.fromhex(hex_string.replace(" ", ""))

            # Inject into all active connections
            for device_writer, cloud_writer in self.active_connections.values():
                if direction == "CLOUD→DEV":
                    device_writer.write(packet)
                    await device_writer.drain()
                elif direction == "DEV→CLOUD":
                    cloud_writer.write(packet)
                    await cloud_writer.drain()
                else:
                    raise ValueError(f"Invalid direction: {direction}")

                # Log injection
                self._log_packet(packet, f"{direction} [INJECTED]")
                self._save_capture(packet, f"{direction} [INJECTED]")

            return {
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "direction": direction,
                "length": len(packet),
                "connections": len(self.active_connections),
            }

    async def _handle_inject(self, request: web.Request) -> web.Response:
        """Handle POST /inject - inject arbitrary packet."""
        try:
            data = await request.json()
            hex_string = data.get("hex")
            direction = data.get("direction")

            if not hex_string or not direction:
                return web.json_response(
                    {"error": "Missing 'hex' or 'direction' field"}, status=400
                )

            result = await self.inject_packet(hex_string, direction)
            return web.json_response(result)

        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        except Exception as e:
            return web.json_response({"error": f"Injection failed: {e}"}, status=500)

    async def _handle_status(self, request: web.Request) -> web.Response:
        """Handle GET /status - check connection status."""
        async with self.connection_lock:
            return web.json_response(
                {
                    "status": "running",
                    "active_connections": len(self.active_connections),
                    "capture_file": str(self.capture_file),
                    "timestamp": datetime.now().isoformat(),
                }
            )

    async def start_api_server(self, api_port: int) -> None:
        """Start REST API server for packet injection."""
        app = web.Application()
        app.router.add_post("/inject", self._handle_inject)
        app.router.add_get("/status", self._handle_status)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", api_port)
        await site.start()

        print(f"REST API server listening on port {api_port}", file=sys.stderr)
        print("  POST /inject - Inject packet", file=sys.stderr)
        print("  GET /status - Check status", file=sys.stderr)

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

    args = parser.parse_args()

    proxy = MITMProxy(
        listen_port=args.listen_port,
        upstream_host=args.upstream_host,
        upstream_port=args.upstream_port,
        use_ssl=not args.no_ssl,
    )

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def signal_handler() -> None:
        print("\nReceived shutdown signal", file=sys.stderr)
        asyncio.create_task(proxy.shutdown())
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


if __name__ == "__main__":
    asyncio.run(main())
