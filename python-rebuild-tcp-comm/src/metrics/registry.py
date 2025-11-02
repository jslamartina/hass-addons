"""Prometheus metrics registry for TCP communication."""

import threading
from typing import Final

from prometheus_client import Counter, Histogram, start_http_server

# Metric definitions
tcp_comm_packet_sent_total: Final = Counter(
    "tcp_comm_packet_sent_total",
    "Total packets sent",
    ["device_id", "outcome"],
)

tcp_comm_packet_recv_total: Final = Counter(
    "tcp_comm_packet_recv_total",
    "Total packets received",
    ["device_id", "outcome"],
)

tcp_comm_packet_latency_seconds: Final = Histogram(
    "tcp_comm_packet_latency_seconds",
    "Packet round-trip latency in seconds",
    ["device_id"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

tcp_comm_packet_retransmit_total: Final = Counter(
    "tcp_comm_packet_retransmit_total",
    "Total packet retransmissions",
    ["device_id", "reason"],
)

tcp_comm_decode_errors_total: Final = Counter(
    "tcp_comm_decode_errors_total",
    "Total decode errors",
    ["device_id", "reason"],
)

_server_started = False
_server_lock = threading.Lock()


def start_metrics_server(port: int = 9400) -> None:
    """Start Prometheus HTTP metrics server (idempotent)."""
    global _server_started
    with _server_lock:
        if not _server_started:
            start_http_server(port)
            _server_started = True


def record_packet_sent(device_id: str, outcome: str) -> None:
    """Record a sent packet."""
    tcp_comm_packet_sent_total.labels(device_id=device_id, outcome=outcome).inc()


def record_packet_recv(device_id: str, outcome: str) -> None:
    """Record a received packet."""
    tcp_comm_packet_recv_total.labels(device_id=device_id, outcome=outcome).inc()


def record_packet_latency(device_id: str, latency_seconds: float) -> None:
    """Record packet latency."""
    tcp_comm_packet_latency_seconds.labels(device_id=device_id).observe(latency_seconds)


def record_retransmit(device_id: str, reason: str) -> None:
    """Record a retransmission."""
    tcp_comm_packet_retransmit_total.labels(device_id=device_id, reason=reason).inc()


def record_decode_error(device_id: str, reason: str) -> None:
    """Record a decode error."""
    tcp_comm_decode_errors_total.labels(device_id=device_id, reason=reason).inc()
