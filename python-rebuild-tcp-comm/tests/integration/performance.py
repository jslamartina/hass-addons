"""Performance tracking and reporting for integration tests."""

import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final


@dataclass
class PerformanceThresholds:
    """Performance thresholds for validation."""

    p95_ms: float = 300.0  # Phase 0 target: p95 < 300ms
    p99_ms: float = 800.0  # Phase 1 stretch goal


@dataclass
class PerformanceMetrics:
    """Calculated performance metrics."""

    sample_count: int
    min_ms: float
    max_ms: float
    mean_ms: float
    stddev_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float


@dataclass
class PerformanceReport:
    """Complete performance report with metadata."""

    timestamp: str
    thresholds: PerformanceThresholds
    metrics: PerformanceMetrics
    samples_ms: list[float]
    warnings: list[str] = field(default_factory=lambda: [])  # noqa: PIE807

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "thresholds": asdict(self.thresholds),
            "metrics": asdict(self.metrics),
            "samples_ms": self.samples_ms,
            "warnings": self.warnings,
        }


class PerformanceTracker:
    """Tracks and analyzes performance metrics."""

    def __init__(self, thresholds: PerformanceThresholds | None = None) -> None:
        """Initialize tracker with optional custom thresholds."""
        self.thresholds: Final = thresholds or PerformanceThresholds()
        self.samples: list[float] = []

    def record_latency(self, latency_ms: float) -> None:
        """Record a latency sample in milliseconds."""
        self.samples.append(latency_ms)

    def calculate_metrics(self) -> PerformanceMetrics | None:
        """Calculate performance metrics from collected samples."""
        if not self.samples:
            return None

        sorted_samples = sorted(self.samples)

        return PerformanceMetrics(
            sample_count=len(sorted_samples),
            min_ms=min(sorted_samples),
            max_ms=max(sorted_samples),
            mean_ms=statistics.mean(sorted_samples),
            stddev_ms=statistics.stdev(sorted_samples) if len(sorted_samples) > 1 else 0.0,
            p50_ms=self._percentile(sorted_samples, 50),
            p95_ms=self._percentile(sorted_samples, 95),
            p99_ms=self._percentile(sorted_samples, 99),
        )

    def generate_report(self) -> PerformanceReport | None:
        """Generate complete performance report."""
        metrics = self.calculate_metrics()
        if metrics is None:
            return None

        warnings: list[str] = []

        # Check p95 threshold (primary target)
        if metrics.p95_ms > self.thresholds.p95_ms:
            warnings.append(
                f"p95 latency ({metrics.p95_ms:.1f}ms) exceeds "
                f"threshold ({self.thresholds.p95_ms:.1f}ms)"
            )

        # Check p99 threshold (stretch goal)
        if metrics.p99_ms > self.thresholds.p99_ms:
            warnings.append(
                f"p99 latency ({metrics.p99_ms:.1f}ms) exceeds "
                f"threshold ({self.thresholds.p99_ms:.1f}ms)"
            )

        return PerformanceReport(
            timestamp=datetime.now(UTC).isoformat(),
            thresholds=self.thresholds,
            metrics=metrics,
            samples_ms=self.samples.copy(),
            warnings=warnings,
        )

    def save_report(self, output_path: Path) -> None:
        """Save performance report to JSON file."""
        report = self.generate_report()
        if report is None:
            return

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w") as f:
            json.dump(report.to_dict(), f, indent=2)

    def format_text_report(self) -> str:
        """Format performance report as text summary."""
        report = self.generate_report()
        if report is None:
            return "No performance data collected"

        metrics = report.metrics

        lines = [
            "",
            "=" * 70,
            "PERFORMANCE REPORT - Round-Trip Command Latency",
            "=" * 70,
            "",
            f"Samples collected: {metrics.sample_count}",
            "",
            "Latency Statistics:",
            f"  Min:    {metrics.min_ms:8.2f} ms",
            f"  Max:    {metrics.max_ms:8.2f} ms",
            f"  Mean:   {metrics.mean_ms:8.2f} ms",
            f"  StdDev: {metrics.stddev_ms:8.2f} ms",
            "",
            "Percentiles:",
            f"  p50:    {metrics.p50_ms:8.2f} ms",
            f"  p95:    {metrics.p95_ms:8.2f} ms  (threshold: {self.thresholds.p95_ms:.1f} ms)",
            f"  p99:    {metrics.p99_ms:8.2f} ms  (threshold: {self.thresholds.p99_ms:.1f} ms)",
            "",
        ]

        # Add warnings if any
        if report.warnings:
            lines.extend(["⚠️  PERFORMANCE WARNINGS:", ""])
            for warning in report.warnings:
                lines.append(f"  - {warning}")
            lines.append("")
        else:
            lines.extend(["✅ All performance thresholds met", ""])

        lines.append("=" * 70)

        return "\n".join(lines)

    @staticmethod
    def _percentile(sorted_samples: list[float], percentile: int) -> float:
        """Calculate percentile from sorted samples using nearest-rank method."""
        if not sorted_samples:
            return 0.0

        if len(sorted_samples) == 1:
            return sorted_samples[0]

        # Use nearest-rank method
        rank = (percentile / 100.0) * len(sorted_samples)
        index = max(0, min(len(sorted_samples) - 1, int(rank)))

        return sorted_samples[index]
