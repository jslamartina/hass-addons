"""Device toggle harness with structured logging and metrics."""

import argparse
import asyncio
import json
import logging
import random
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Optional

from metrics import (
    record_packet_latency,
    record_packet_recv,
    record_packet_sent,
    record_retransmit,
    start_metrics_server,
)
from transport import TCPConnection


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


def setup_logging(log_level: str) -> None:
    """Configure JSON logging."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # JSON handler to stdout
    json_handler = logging.StreamHandler(sys.stdout)
    json_handler.setFormatter(JSONFormatter())
    json_handler.setLevel(level)
    root_logger.addHandler(json_handler)


def log_packet(
    event: str,
    direction: str,
    msg_id: str,
    device_id: str,
    raw_packet_hex: str,
    elapsed_ms: float,
    outcome: str,
    **kwargs: object,
) -> None:
    """Log packet event with structured data."""
    logger = logging.getLogger(__name__)
    extra_fields = {
        "event": event,
        "direction": direction,
        "msg_id": msg_id,
        "device_id": device_id,
        "raw_packet_hex": raw_packet_hex,
        "elapsed_ms": round(elapsed_ms, 2),
        "outcome": outcome,
        **kwargs,
    }
    # Create LogRecord with extra fields
    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        __name__,
        0,
        f"Packet {event} {direction} {outcome}",
        (),
        None,
    )
    setattr(record, "extra_fields", extra_fields)
    logger.handle(record)


async def send_toggle_packet(
    conn: TCPConnection,
    device_id: str,
    msg_id: str,
    state: bool,
) -> Optional[bytes]:
    """
    Send a toggle packet and wait for response.

    Args:
        conn: TCP connection
        device_id: Device identifier
        msg_id: Message identifier
        state: Desired state (True=on, False=off)

    Returns:
        Response bytes or None on failure
    """
    # For Phase 0, we create a minimal packet:
    # Magic: 0xF0 0x0D
    # Version: 0x01
    # Length: 4 bytes (big-endian)
    # Payload: JSON with opcode, device_id, msg_id, state
    payload_dict = {
        "opcode": "toggle",
        "device_id": device_id,
        "msg_id": msg_id,
        "state": state,
    }
    payload_json = json.dumps(payload_dict).encode("utf-8")
    payload_len = len(payload_json)

    # Build packet: magic (2) + version (1) + length (4) + payload
    packet = bytearray()
    packet.extend([0xF0, 0x0D])  # Magic
    packet.append(0x01)  # Version
    packet.extend(payload_len.to_bytes(4, "big"))  # Length
    packet.extend(payload_json)  # Payload

    packet_bytes = bytes(packet)
    packet_hex = packet_bytes.hex(" ")

    start_time = time.perf_counter()

    # Send packet
    send_success = await conn.send(packet_bytes)
    if not send_success:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        log_packet(
            event="tcp_packet",
            direction="send",
            msg_id=msg_id,
            device_id=device_id,
            raw_packet_hex=packet_hex,
            elapsed_ms=elapsed_ms,
            outcome="error",
        )
        record_packet_sent(device_id, "error")
        return None

    send_elapsed_ms = (time.perf_counter() - start_time) * 1000
    log_packet(
        event="tcp_packet",
        direction="send",
        msg_id=msg_id,
        device_id=device_id,
        raw_packet_hex=packet_hex,
        elapsed_ms=send_elapsed_ms,
        outcome="success",
    )
    record_packet_sent(device_id, "success")

    # Wait for response
    response = await conn.recv()
    total_elapsed_ms = (time.perf_counter() - start_time) * 1000

    if response is None:
        log_packet(
            event="tcp_packet",
            direction="recv",
            msg_id=msg_id,
            device_id=device_id,
            raw_packet_hex="",
            elapsed_ms=total_elapsed_ms,
            outcome="timeout",
        )
        record_packet_recv(device_id, "timeout")
        return None

    # Type assertion: response is bytes at this point (checked above)
    response_bytes: bytes = response
    response_hex = response_bytes.hex(" ")
    log_packet(
        event="tcp_packet",
        direction="recv",
        msg_id=msg_id,
        device_id=device_id,
        raw_packet_hex=response_hex,
        elapsed_ms=total_elapsed_ms,
        outcome="success",
    )
    record_packet_recv(device_id, "success")
    record_packet_latency(device_id, total_elapsed_ms / 1000.0)

    return response_bytes


async def toggle_device_with_retry(
    device_id: str,
    device_host: str,
    device_port: int,
    state: bool,
    max_attempts: int = 2,
) -> bool:
    """
    Toggle device with exponential backoff retry.

    Args:
        device_id: Device identifier
        device_host: Device host
        device_port: Device port
        state: Desired state
        max_attempts: Maximum retry attempts (including first attempt)

    Returns:
        True if successful, False otherwise
    """
    logger = logging.getLogger(__name__)

    for attempt in range(1, max_attempts + 1):
        msg_id = uuid.uuid4().hex[:16]  # 16 char hex ID

        logger.info(
            "Toggle attempt %d/%d for device %s (msg_id: %s)",
            attempt,
            max_attempts,
            device_id,
            msg_id,
        )

        # Create connection
        conn = TCPConnection(device_host, device_port)

        # Connect
        if not await conn.connect():
            await conn.close()
            if attempt < max_attempts:
                # Exponential backoff with jitter
                backoff_base = 0.25 * (2 ** (attempt - 1))
                jitter = random.uniform(0, 0.1)
                delay = backoff_base + jitter
                logger.warning(
                    "Connection failed, retrying in %.2fs (attempt %d/%d)",
                    delay,
                    attempt,
                    max_attempts,
                )
                record_retransmit(device_id, "connection_failed")
                await asyncio.sleep(delay)
                continue
            else:
                logger.error("All connection attempts failed")
                return False

        # Send toggle
        response = await send_toggle_packet(conn, device_id, msg_id, state)

        # Close connection
        await conn.close()

        if response is not None:
            logger.info(
                "Toggle successful for device %s (msg_id: %s)",
                device_id,
                msg_id,
            )
            return True

        if attempt < max_attempts:
            # Exponential backoff with jitter
            backoff_base = 0.25 * (2 ** (attempt - 1))
            jitter = random.uniform(0, 0.1)
            delay = backoff_base + jitter
            logger.warning(
                "Toggle failed, retrying in %.2fs (attempt %d/%d)",
                delay,
                attempt,
                max_attempts,
            )
            record_retransmit(device_id, "timeout")
            await asyncio.sleep(delay)

    logger.error("All toggle attempts failed for device %s", device_id)
    return False


async def main_async(args: argparse.Namespace) -> int:
    """Async main entry point."""
    logger = logging.getLogger(__name__)

    # Start metrics server
    try:
        start_metrics_server(args.metrics_port)
        logger.info("Metrics server started on port %d", args.metrics_port)
    except Exception as e:
        logger.error("Failed to start metrics server: %s", e)
        return 1

    # Toggle device
    state = args.state.lower() in ("on", "true", "1")
    success = await toggle_device_with_retry(
        device_id=args.device_id,
        device_host=args.device_host,
        device_port=args.device_port,
        state=state,
        max_attempts=args.max_attempts,
    )

    if success:
        logger.info("Device toggle completed successfully")
        return 0
    else:
        logger.error("Device toggle failed")
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Toggle a Cync device with structured logging and metrics"
    )
    parser.add_argument(
        "--device-id",
        required=True,
        help="Device identifier",
    )
    parser.add_argument(
        "--device-host",
        required=True,
        help="Device IP address or hostname",
    )
    parser.add_argument(
        "--device-port",
        type=int,
        default=9000,
        help="Device port (default: 9000)",
    )
    parser.add_argument(
        "--state",
        default="on",
        help="Desired state: on/off (default: on)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=2,
        help="Maximum retry attempts (default: 2)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )
    parser.add_argument(
        "--metrics-port",
        type=int,
        default=9400,
        help="Prometheus metrics port (default: 9400)",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)

    # Run async main
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
