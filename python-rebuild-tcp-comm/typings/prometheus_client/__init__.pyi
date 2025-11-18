"""Typed stubs for the subset of prometheus_client APIs used in this repo."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol

class _CounterChild(Protocol):
    def inc(self, amount: float = ...) -> None: ...
    def labels(self, **labels: str) -> _CounterChild: ...


class Counter:
    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: Iterable[str] | None = ...,
        *,
        namespace: str | None = ...,
        subsystem: str | None = ...,
        unit: str | None = ...,
        registry: Any | None = ...,
    ) -> None: ...

    def labels(self, **labels: str) -> _CounterChild: ...
    def inc(self, amount: float = ...) -> None: ...
    def collect(self) -> list[Any]: ...


class _GaugeChild(Protocol):
    def set(self, value: float) -> None: ...
    def inc(self, amount: float = ...) -> None: ...
    def dec(self, amount: float = ...) -> None: ...
    def labels(self, **labels: str) -> _GaugeChild: ...


class Gauge:
    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: Iterable[str] | None = ...,
        *,
        namespace: str | None = ...,
        subsystem: str | None = ...,
        unit: str | None = ...,
        registry: Any | None = ...,
    ) -> None: ...

    def labels(self, **labels: str) -> _GaugeChild: ...
    def set(self, value: float) -> None: ...
    def inc(self, amount: float = ...) -> None: ...
    def dec(self, amount: float = ...) -> None: ...
    def collect(self) -> list[Any]: ...


class _HistogramChild(Protocol):
    def observe(self, amount: float) -> None: ...
    def labels(self, **labels: str) -> _HistogramChild: ...


class Histogram:
    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: Iterable[str] | None = ...,
        buckets: Iterable[float] | None = ...,
        *,
        namespace: str | None = ...,
        subsystem: str | None = ...,
        unit: str | None = ...,
        registry: Any | None = ...,
    ) -> None: ...

    def labels(self, **labels: str) -> _HistogramChild: ...
    def observe(self, amount: float) -> None: ...
    def collect(self) -> list[Any]: ...


class _SummaryChild(Protocol):
    def observe(self, amount: float) -> None: ...


class Summary:
    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: Iterable[str] | None = ...,
        *,
        namespace: str | None = ...,
        subsystem: str | None = ...,
        unit: str | None = ...,
        registry: Any | None = ...,
    ) -> None: ...

    def labels(self, **labels: str) -> _SummaryChild: ...
    def observe(self, amount: float) -> None: ...
    def collect(self) -> list[Any]: ...


def start_http_server(port: int, addr: str = ..., registry: Any | None = ...) -> None: ...


class CollectorRegistry:
    def __init__(self, auto_describe: bool = ..., target_info: Mapping[str, str] | None = ...) -> None: ...


