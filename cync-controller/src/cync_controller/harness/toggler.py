"""Device toggle harness with structured logging and metrics."""

import argparse
import asyncio
import json
import logging
import math
import random
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypedDict, cast, override

from cync_controller.metrics import (
    record_packet_latency,
    record_packet_recv,
    record_packet_sent,
    record_retransmit,
    start_metrics_server,
)
from cync_controller.transport import TCPConnection


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    @override
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        # Add extra fields if present (dynamically added attribute)
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            log_data.update(cast("dict[str, object]", extra_fields))

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


@dataclass
class PacketLogData:
    """Data for packet logging."""

    event: str
    direction: str
    msg_id: str
    device_id: str
    raw_packet_hex: str
    elapsed_ms: float
    outcome: str


def log_packet(
    packet_data: PacketLogData,
    **kwargs: object,
) -> None:
    """Log packet event with structured data."""
    logger = logging.getLogger(__name__)
    extra_fields = {
        "event": packet_data.event,
        "direction": packet_data.direction,
        "msg_id": packet_data.msg_id,
        "device_id": packet_data.device_id,
        "raw_packet_hex": packet_data.raw_packet_hex,
        "elapsed_ms": round(packet_data.elapsed_ms, 2),
        "outcome": packet_data.outcome,
        **kwargs,
    }
    # Create LogRecord with extra fields
    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        __name__,
        0,
        f"Packet {packet_data.event} {packet_data.direction} {packet_data.outcome}",
        (),
        None,
    )
    record.extra_fields = extra_fields
    logger.handle(record)


def _compute_backoff_delay(attempt: int) -> float:
    """Compute exponential backoff with jitter for retries."""
    attempt_int: int = int(attempt)
    backoff_base: float = float(0.25 * math.pow(2.0, attempt_int - 1))
    jitter: float = random.uniform(0, 0.1)  # noqa: S311
    return backoff_base + jitter


async def send_toggle_packet(
    conn: TCPConnection,
    device_id: str,
    msg_id: str,
    state: bool,
) -> bytes | None:
    """Send a toggle packet and wait for response.

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
            PacketLogData(
                event="tcp_packet",
                direction="send",
                msg_id=msg_id,
                device_id=device_id,
                raw_packet_hex=packet_hex,
                elapsed_ms=elapsed_ms,
                outcome="error",
            ),
        )
        record_packet_sent(device_id, "error")
        return None

    send_elapsed_ms = (time.perf_counter() - start_time) * 1000
    log_packet(
        PacketLogData(
            event="tcp_packet",
            direction="send",
            msg_id=msg_id,
            device_id=device_id,
            raw_packet_hex=packet_hex,
            elapsed_ms=send_elapsed_ms,
            outcome="success",
        ),
    )
    record_packet_sent(device_id, "success")

    # Wait for response
    response = await conn.recv()
    total_elapsed_ms = (time.perf_counter() - start_time) * 1000

    if response is None:
        log_packet(
            PacketLogData(
                event="tcp_packet",
                direction="recv",
                msg_id=msg_id,
                device_id=device_id,
                raw_packet_hex="",
                elapsed_ms=total_elapsed_ms,
                outcome="timeout",
            ),
        )
        record_packet_recv(device_id, "timeout")
        return None

    # Type assertion: response is bytes at this point (checked above)
    response_bytes: bytes = response
    response_hex = response_bytes.hex(" ")
    log_packet(
        PacketLogData(
            event="tcp_packet",
            direction="recv",
            msg_id=msg_id,
            device_id=device_id,
            raw_packet_hex=response_hex,
            elapsed_ms=total_elapsed_ms,
            outcome="success",
        ),
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
    """Toggle device with exponential backoff retry.

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

    correlation_id = uuid.uuid4().hex[:16]
    logger.info(
        "→ Starting toggle device with retry",
        extra={
            "correlation_id": correlation_id,
            "device_id": device_id,
            "state": state,
            "max_attempts": max_attempts,
        },
    )

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
                # Exponential backoff with jitter (non-crypto use)
                delay = _compute_backoff_delay(attempt)
                logger.warning(
                    "Connection failed, retrying in %.2fs (attempt %d/%d)",
                    delay,
                    attempt,
                    max_attempts,
                )
                record_retransmit(device_id, "connection_failed")
                await asyncio.sleep(delay)
                continue
            logger.error(
                "✗ Toggle device with retry failed",
                extra={
                    "correlation_id": correlation_id,
                    "device_id": device_id,
                    "reason": "all_connection_attempts_failed",
                },
            )
            return False

        # Send toggle
        response = await send_toggle_packet(conn, device_id, msg_id, state)

        # Close connection
        await conn.close()

        if response is not None:
            logger.info(
                "✓ Toggle device with retry complete",
                extra={
                    "correlation_id": correlation_id,
                    "device_id": device_id,
                    "state": state,
                },
            )
            return True

        if attempt < max_attempts:
            # Exponential backoff with jitter
            delay = _compute_backoff_delay(attempt)
            logger.warning(
                "Toggle failed, retrying in %.2fs (attempt %d/%d)",
                delay,
                attempt,
                max_attempts,
            )
            record_retransmit(device_id, "timeout")
            await asyncio.sleep(delay)

    logger.error(
        "✗ Toggle device with retry failed",
        extra={
            "correlation_id": correlation_id,
            "device_id": device_id,
            "reason": "all_toggle_attempts_failed",
        },
    )
    return False


class ParsedArgs(TypedDict):
    """CLI arguments accepted by the toggle harness."""

    device_id: str
    device_host: str
    device_port: int
    state: str
    max_attempts: int
    log_level: str
    metrics_port: int


async def main_async(args: ParsedArgs) -> int:
    """Async main entry point."""
    logger = logging.getLogger(__name__)

    metrics_port: int = args["metrics_port"]
    device_id: str = args["device_id"]
    device_host: str = args["device_host"]
    device_port: int = args["device_port"]
    max_attempts: int = args["max_attempts"]

    # Start metrics server
    try:
        start_metrics_server(metrics_port)
        logger.info(
            "Metrics server started",
            extra={"port": metrics_port},
        )
    except (OSError, ValueError) as e:
        logger.exception(
            "Failed to start metrics server",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        return 1
    except Exception as e:
        logger.critical(
            "Unexpected error starting metrics server",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        raise  # Re-raise unexpected errors

    # Toggle device
    desired_state_raw = args["state"]
    state = desired_state_raw.lower() in ("on", "true", "1")
    success = await toggle_device_with_retry(
        device_id=device_id,
        device_host=device_host,
        device_port=device_port,
        state=state,
        max_attempts=max_attempts,
    )

    if success:
        logger.info("Device toggle completed successfully")
        return 0
    logger.error("Device toggle failed")
    return 1


def main() -> int:
    """Run toggle harness CLI."""
    parser = argparse.ArgumentParser(
        description="Toggle a Cync device with structured logging and metrics",
    )
    _ = parser.add_argument(
        "--device-id",
        required=True,
        help="Device identifier",
    )
    _ = parser.add_argument(
        "--device-host",
        required=True,
        help="Device IP address or hostname",
    )
    _ = parser.add_argument(
        "--device-port",
        type=int,
        default=9000,
        help="Device port (default: 9000)",
    )
    _ = parser.add_argument(
        "--state",
        default="on",
        help="Desired state: on/off (default: on)",
    )
    _ = parser.add_argument(
        "--max-attempts",
        type=int,
        default=2,
        help="Maximum retry attempts (default: 2)",
    )
    _ = parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )
    _ = parser.add_argument(
        "--metrics-port",
        type=int,
        default=9400,
        help="Prometheus metrics port (default: 9400)",
    )

    ns = parser.parse_args()
    parsed_args: ParsedArgs = {
        "device_id": str(cast(str, ns.device_id)),
        "device_host": str(cast(str, ns.device_host)),
        "device_port": int(cast(int, ns.device_port)),
        "state": str(cast(str, ns.state)),
        "max_attempts": int(cast(int, ns.max_attempts)),
        "log_level": str(cast(str, ns.log_level)),
        "metrics_port": int(cast(int, ns.metrics_port)),
    }

    # Setup logging
    setup_logging(parsed_args["log_level"])

    # Run async main
    return asyncio.run(main_async(parsed_args))


if __name__ == "__main__":
    sys.exit(main())
