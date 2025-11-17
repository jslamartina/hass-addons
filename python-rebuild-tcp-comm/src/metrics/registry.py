"""Prometheus metrics registry for TCP communication."""

import threading
from typing import Final

from prometheus_client import (  # type: ignore[import-untyped]
    Counter,
    Gauge,
    Histogram,
    start_http_server,
)

# Metric definitions
tcp_comm_packet_sent_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_packet_sent_total",
    "Total packets sent",
    ["device_id", "outcome"],
)

tcp_comm_packet_recv_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_packet_recv_total",
    "Total packets received",
    ["device_id", "outcome"],
)

tcp_comm_packet_latency_seconds: Final = Histogram(  # type: ignore[assignment]
    "tcp_comm_packet_latency_seconds",
    "Packet round-trip latency in seconds",
    ["device_id"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

tcp_comm_packet_retransmit_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_packet_retransmit_total",
    "Total packet retransmissions",
    ["device_id", "reason"],
)

tcp_comm_decode_errors_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_decode_errors_total",
    "Total decode errors",
    ["device_id", "reason"],
)

# Phase 1b: ACK/Response metrics
tcp_comm_ack_received_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_ack_received_total",
    "Total ACK packets received",
    ["device_id", "ack_type", "outcome"],
)

tcp_comm_ack_timeout_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_ack_timeout_total",
    "Total ACK timeouts",
    ["device_id"],
)

tcp_comm_idempotent_drop_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_idempotent_drop_total",
    "Total duplicate packets dropped (idempotent)",
    ["device_id"],
)

tcp_comm_retry_attempts_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_retry_attempts_total",
    "Total retry attempts",
    ["device_id", "attempt_number"],
)

tcp_comm_message_abandoned_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_message_abandoned_total",
    "Total messages abandoned after max retries",
    ["device_id", "reason"],
)

# Phase 1b: Connection metrics
tcp_comm_connection_state: Final = Gauge(  # type: ignore[assignment]
    "tcp_comm_connection_state",
    "Current connection state",
    ["device_id", "state"],
)

tcp_comm_handshake_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_handshake_total",
    "Total handshake attempts",
    ["device_id", "outcome"],
)

tcp_comm_reconnection_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_reconnection_total",
    "Total reconnection attempts",
    ["device_id", "reason"],
)

tcp_comm_heartbeat_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_heartbeat_total",
    "Total heartbeat exchanges",
    ["device_id", "outcome"],
)

# Phase 1b: Dedup cache metrics
tcp_comm_dedup_cache_size: Final = Gauge(  # type: ignore[assignment]
    "tcp_comm_dedup_cache_size",
    "Current deduplication cache size",
)

tcp_comm_dedup_cache_hits_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_dedup_cache_hits_total",
    "Total deduplication cache hits",
)

tcp_comm_dedup_cache_evictions_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_dedup_cache_evictions_total",
    "Total deduplication cache evictions",
)

# Phase 1b: Performance metrics
tcp_comm_state_lock_hold_seconds: Final = Histogram(  # type: ignore[assignment]
    "tcp_comm_state_lock_hold_seconds",
    "State lock hold duration in seconds",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

# Phase 1b: Device operation metrics
tcp_comm_mesh_info_request_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_mesh_info_request_total",
    "Total mesh info requests",
    ["device_id", "outcome"],
)

tcp_comm_device_info_request_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_device_info_request_total",
    "Total device info requests",
    ["device_id", "outcome"],
)

tcp_comm_device_struct_parsed_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_device_struct_parsed_total",
    "Total device structs parsed",
    ["device_id"],
)

tcp_comm_primary_device_violations_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_primary_device_violations_total",
    "Total primary device violations (non-primary mesh info attempts)",
)

_server_state = {"started": False}
_server_lock = threading.Lock()


def start_metrics_server(port: int = 9400) -> None:
    """Start Prometheus HTTP metrics server (idempotent)."""
    with _server_lock:
        if not _server_state["started"]:
            start_http_server(port)  # type: ignore[no-untyped-call]
            _server_state["started"] = True


def record_packet_sent(device_id: str, outcome: str) -> None:
    """Record a sent packet."""
    tcp_comm_packet_sent_total.labels(device_id=device_id, outcome=outcome).inc()  # type: ignore[no-untyped-call]


def record_packet_recv(device_id: str, outcome: str) -> None:
    """Record a received packet."""
    tcp_comm_packet_recv_total.labels(device_id=device_id, outcome=outcome).inc()  # type: ignore[no-untyped-call]


def record_packet_latency(device_id: str, latency_seconds: float) -> None:
    """Record packet latency."""
    tcp_comm_packet_latency_seconds.labels(device_id=device_id).observe(latency_seconds)  # type: ignore[no-untyped-call]


def record_retransmit(device_id: str, reason: str) -> None:
    """Record a retransmission."""
    tcp_comm_packet_retransmit_total.labels(device_id=device_id, reason=reason).inc()  # type: ignore[no-untyped-call]


def record_decode_error(device_id: str, reason: str) -> None:
    """Record a decode error."""
    tcp_comm_decode_errors_total.labels(device_id=device_id, reason=reason).inc()  # type: ignore[no-untyped-call]


# Phase 1b: ACK/Response metric helpers
def record_ack_received(device_id: str, ack_type: str, outcome: str) -> None:
    """Record an ACK packet received."""
    tcp_comm_ack_received_total.labels(
        device_id=device_id, ack_type=ack_type, outcome=outcome,
    ).inc()  # type: ignore[no-untyped-call]


def record_ack_timeout(device_id: str) -> None:
    """Record an ACK timeout."""
    tcp_comm_ack_timeout_total.labels(device_id=device_id).inc()  # type: ignore[no-untyped-call]


def record_idempotent_drop(device_id: str) -> None:
    """Record a duplicate packet dropped (idempotent)."""
    tcp_comm_idempotent_drop_total.labels(device_id=device_id).inc()  # type: ignore[no-untyped-call]


def record_retry_attempt(device_id: str, attempt_number: int) -> None:
    """Record a retry attempt."""
    tcp_comm_retry_attempts_total.labels(
        device_id=device_id, attempt_number=str(attempt_number),
    ).inc()  # type: ignore[no-untyped-call]


def record_message_abandoned(device_id: str, reason: str) -> None:
    """Record a message abandoned after max retries."""
    tcp_comm_message_abandoned_total.labels(device_id=device_id, reason=reason).inc()  # type: ignore[no-untyped-call]


# Phase 1b: Connection metric helpers
def record_connection_state(device_id: str, state: str) -> None:
    """Record connection state change."""
    # Set gauge to 1 for current state, 0 for all others
    for s in ["disconnected", "connecting", "connected", "reconnecting"]:
        value = 1 if s == state else 0
        tcp_comm_connection_state.labels(device_id=device_id, state=s).set(value)  # type: ignore[no-untyped-call]


def record_handshake(device_id: str, outcome: str) -> None:
    """Record a handshake attempt."""
    tcp_comm_handshake_total.labels(device_id=device_id, outcome=outcome).inc()  # type: ignore[no-untyped-call]


def record_reconnection(device_id: str, reason: str) -> None:
    """Record a reconnection attempt."""
    tcp_comm_reconnection_total.labels(device_id=device_id, reason=reason).inc()  # type: ignore[no-untyped-call]


def record_heartbeat(device_id: str, outcome: str) -> None:
    """Record a heartbeat exchange."""
    tcp_comm_heartbeat_total.labels(device_id=device_id, outcome=outcome).inc()  # type: ignore[no-untyped-call]


# Phase 1b: Dedup cache metric helpers
def record_dedup_cache_size(size: int) -> None:
    """Record deduplication cache size."""
    tcp_comm_dedup_cache_size.set(size)  # type: ignore[no-untyped-call]


def record_dedup_cache_hit() -> None:
    """Record a deduplication cache hit."""
    tcp_comm_dedup_cache_hits_total.inc()  # type: ignore[no-untyped-call]


def record_dedup_cache_eviction() -> None:
    """Record a deduplication cache eviction."""
    tcp_comm_dedup_cache_evictions_total.inc()  # type: ignore[no-untyped-call]


# Phase 1b: Performance metric helpers
def record_state_lock_hold(hold_seconds: float) -> None:
    """Record state lock hold duration."""
    tcp_comm_state_lock_hold_seconds.observe(hold_seconds)  # type: ignore[no-untyped-call]


# Phase 1b: Device operation metric helpers
def record_mesh_info_request(device_id: str, outcome: str) -> None:
    """Record a mesh info request."""
    tcp_comm_mesh_info_request_total.labels(device_id=device_id, outcome=outcome).inc()  # type: ignore[no-untyped-call]


def record_device_info_request(device_id: str, outcome: str) -> None:
    """Record a device info request."""
    tcp_comm_device_info_request_total.labels(device_id=device_id, outcome=outcome).inc()  # type: ignore[no-untyped-call]


def record_device_struct_parsed(device_id: str) -> None:
    """Record a device struct parsed."""
    tcp_comm_device_struct_parsed_total.labels(device_id=device_id).inc()  # type: ignore[no-untyped-call]


def record_primary_device_violation() -> None:
    """Record a primary device violation (non-primary mesh info attempt)."""
    tcp_comm_primary_device_violations_total.inc()  # type: ignore[no-untyped-call]


# Phase 1b: Device operation performance metrics
tcp_comm_device_info_request_latency_seconds: Final = Histogram(  # type: ignore[assignment]
    "tcp_comm_device_info_request_latency_seconds",
    "Device info request latency in seconds",
    ["device_id"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

tcp_comm_mesh_info_collection_duration_seconds: Final = Histogram(  # type: ignore[assignment]
    "tcp_comm_mesh_info_collection_duration_seconds",
    "Mesh info collection duration in seconds",
    buckets=(1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0),
)

tcp_comm_device_cache_hits_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_device_cache_hits_total",
    "Total device cache hits",
)

tcp_comm_device_cache_misses_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_device_cache_misses_total",
    "Total device cache misses",
)

tcp_comm_device_cache_evictions_total: Final = Counter(  # type: ignore[assignment]
    "tcp_comm_device_cache_evictions_total",
    "Total device cache evictions",
)


def record_device_info_request_latency(device_id: str, latency_seconds: float) -> None:
    """Record device info request latency."""
    tcp_comm_device_info_request_latency_seconds.labels(device_id=device_id).observe(
        latency_seconds,
    )  # type: ignore[no-untyped-call]


def record_mesh_info_collection_duration(duration_seconds: float) -> None:
    """Record mesh info collection duration."""
    tcp_comm_mesh_info_collection_duration_seconds.observe(duration_seconds)  # type: ignore[no-untyped-call]


def record_device_cache_hit() -> None:
    """Record a device cache hit."""
    tcp_comm_device_cache_hits_total.inc()  # type: ignore[no-untyped-call]


def record_device_cache_miss() -> None:
    """Record a device cache miss."""
    tcp_comm_device_cache_misses_total.inc()  # type: ignore[no-untyped-call]


def record_device_cache_eviction() -> None:
    """Record a device cache eviction."""
    tcp_comm_device_cache_evictions_total.inc()  # type: ignore[no-untyped-call]
