# Phase 2 Specification: Canary Deployment + SLO Monitoring

**Status**: Planning
**Effort**: Large (~34 SP, 3-4 weeks)
**Dependencies**: Phase 1 complete
**Team**: 2 Engineers + 1 SRE

---

## Executive Summary

Phase 2 deploys the new reliable transport to a subset of production traffic (canary cohort) with comprehensive SLO monitoring, dashboards, and alerting. This validates the system under real-world conditions before full migration.

---

## Goals

1. **Canary Deployment**: Route 10-50% of traffic to new transport
2. **SLO Monitoring**: Define and track Service Level Objectives
3. **Observability**: Production dashboards and alerting
4. **Rollback**: One-click rollback to legacy path
5. **Validation**: 2-week burn-in with error budget tracking

---

## Architecture

### 1. Traffic Routing

**File**: `src/rebuild_tcp_comm/routing/canary_router.py`

```python
class CanaryRouter:
    """
    Routes traffic between legacy and new transport layers.

    Features:
    - Percentage-based routing (0-100%)
    - Device-level sticky routing
    - Feature flag integration
    - Dark launch mode (mirror traffic)
    """

    def __init__(
        self,
        legacy_transport: LegacyTransport,
        new_transport: ReliableTransport,
        canary_percentage: float = 0.0,
        sticky_routing: bool = True,
    ):
        self.legacy = legacy_transport
        self.new = new_transport
        self.canary_pct = canary_percentage
        self.sticky = sticky_routing
        self.device_assignments: Dict[str, str] = {}  # device_id -> transport

    def should_use_new_transport(self, device_id: str) -> bool:
        """Determine which transport to use for device."""
        if self.sticky and device_id in self.device_assignments:
            return self.device_assignments[device_id] == "new"

        # Hash-based consistent routing
        if self.sticky:
            use_new = self._hash_device(device_id) < self.canary_pct
            self.device_assignments[device_id] = "new" if use_new else "legacy"
            return use_new

        # Random routing (non-sticky)
        return random.random() < (self.canary_pct / 100.0)

    async def send(self, device_id: str, message: bytes) -> bool:
        """Route message to appropriate transport."""
        if self.should_use_new_transport(device_id):
            record_metric("routing_decision", {"transport": "new", "device_id": device_id})
            return await self.new.send_reliable(message)
        else:
            record_metric("routing_decision", {"transport": "legacy", "device_id": device_id})
            return await self.legacy.send(message)
```

**Feature Flag Integration**:

```python
class FeatureFlags:
    """Configuration-driven feature flags."""

    @staticmethod
    def get_canary_percentage() -> float:
        """Get canary percentage from config/env."""
        return float(os.getenv("CANARY_PERCENTAGE", "0.0"))

    @staticmethod
    def is_dark_launch_enabled() -> bool:
        """Check if dark launch (mirror) mode is enabled."""
        return os.getenv("DARK_LAUNCH", "false").lower() == "true"

    @staticmethod
    def get_cohort_list() -> List[str]:
        """Get explicit device cohort (overrides percentage)."""
        cohort = os.getenv("CANARY_COHORT", "")
        return [d.strip() for d in cohort.split(",") if d.strip()]
```

### 2. Dark Launch Mode

**Mirror traffic** without affecting production:

```python
class DarkLaunchRouter(CanaryRouter):
    """
    Mirrors traffic to new transport without using responses.

    Use case: Validate new transport behavior before cutover.
    """

    async def send(self, device_id: str, message: bytes) -> bool:
        # Always use legacy for actual response
        legacy_task = asyncio.create_task(self.legacy.send(message))

        # Mirror to new transport (fire and forget)
        if self.should_use_new_transport(device_id):
            asyncio.create_task(self._mirror_to_new(device_id, message))

        return await legacy_task

    async def _mirror_to_new(self, device_id: str, message: bytes):
        """Mirror message to new transport, ignore result."""
        try:
            await self.new.send_reliable(message)
            record_metric("dark_launch_success", {"device_id": device_id})
        except Exception as e:
            record_metric("dark_launch_error", {"device_id": device_id, "error": str(e)})
```

---

## Service Level Objectives (SLOs)

### Definition

```yaml
slos:
  toggle_success_rate:
    description: "Percentage of successful toggle operations"
    target: 99.9%
    window: 30d
    error_budget: 0.1%

  toggle_latency_p99:
    description: "99th percentile toggle latency"
    target: 1500ms # Field (production)
    target_lab: 800ms # Lab (controlled)
    window: 7d

  packet_loss_rate:
    description: "Packet loss estimate (retransmits / total)"
    target: <1%
    window: 24h

  decode_error_rate:
    description: "Malformed packet rate"
    target: <0.1%
    window: 24h

  queue_full_rate:
    description: "Queue exhaustion rate"
    target: <1%
    window: 1h
```

### Error Budget

```python
@dataclass
class ErrorBudget:
    """Track error budget consumption."""

    slo_target: float  # e.g., 99.9%
    window_days: int
    current_success_rate: float

    @property
    def budget_remaining(self) -> float:
        """Percentage of error budget remaining."""
        allowed_error = 1.0 - self.slo_target
        actual_error = 1.0 - self.current_success_rate
        if allowed_error == 0:
            return 0.0
        return max(0.0, 1.0 - (actual_error / allowed_error))

    @property
    def is_exhausted(self) -> bool:
        """Check if error budget is exhausted."""
        return self.budget_remaining <= 0.0
```

---

## Monitoring & Dashboards

### 1. Prometheus Queries

**Success Rate (SLO)**:

```promql
## 30-day success rate
sum(rate(tcp_comm_packet_sent_total{outcome="success"}[30d]))
/
sum(rate(tcp_comm_packet_sent_total[30d]))

## Per-transport comparison
sum(rate(tcp_comm_packet_sent_total{transport="new",outcome="success"}[5m]))
/
sum(rate(tcp_comm_packet_sent_total{transport="new"}[5m]))
```

**Latency (SLO)**:

```promql
## p99 latency by transport
histogram_quantile(0.99,
  sum(rate(tcp_comm_packet_latency_seconds_bucket{transport="new"}[5m])) by (le)
)

## p99 latency comparison (new vs legacy)
histogram_quantile(0.99,
  sum(rate(tcp_comm_packet_latency_seconds_bucket[5m])) by (transport, le)
)
```

**Error Budget**:

```promql
## Error budget consumption (30d)
1 - (
  (1 - sum(rate(tcp_comm_packet_sent_total{outcome="success"}[30d])) / sum(rate(tcp_comm_packet_sent_total[30d])))
  /
  (1 - 0.999)  # Target: 99.9%
)
```

**Queue Health**:

```promql
## Queue depth by transport
tcp_comm_send_queue_size{transport="new"}

## Queue full events
rate(tcp_comm_queue_full_total{transport="new"}[5m])
```

### 2. Grafana Dashboard

**Panels**:

1. **Overview**
   - Canary percentage gauge
   - Total requests (new vs legacy)
   - Success rate (new vs legacy)
   - Error rate (new vs legacy)

2. **SLO Tracking**
   - Success rate vs target (99.9%)
   - Latency p99 vs target (1500ms)
   - Error budget remaining (gauge)
   - SLO compliance history (7d, 30d)

3. **Latency**
   - p50, p95, p99, p999 (new vs legacy)
   - Latency heatmap
   - Per-device latency

4. **Reliability**
   - Retry rate
   - ACK timeout rate
   - Idempotent drops
   - Packet loss estimate

5. **Queues**
   - Send queue depth
   - Receive queue depth
   - Queue full events
   - Throughput (msg/sec)

6. **Errors**
   - Error breakdown by type
   - Decode errors
   - Connection failures
   - Timeout distribution

### 3. Dashboard JSON

**File**: `monitoring/grafana-dashboard.json`

```json
{
  "dashboard": {
    "title": "Cync TCP Rebuild - Phase 2 Canary",
    "panels": [
      {
        "title": "Success Rate vs SLO",
        "targets": [
          {
            "expr": "sum(rate(tcp_comm_packet_sent_total{outcome=\"success\"}[5m])) / sum(rate(tcp_comm_packet_sent_total[5m]))"
          }
        ],
        "thresholds": [
          { "value": 0.999, "color": "green" },
          { "value": 0.995, "color": "yellow" },
          { "value": 0, "color": "red" }
        ]
      }
    ]
  }
}
```

---

## Alerting

### Alert Rules

**File**: `monitoring/prometheus-alerts.yml`

```yaml
groups:
  - name: tcp_rebuild_slo
    interval: 1m
    rules:
      - alert: ToggleSuccessRateLow
        expr: |
          sum(rate(tcp_comm_packet_sent_total{transport="new",outcome="success"}[10m]))
          /
          sum(rate(tcp_comm_packet_sent_total{transport="new"}[10m]))
          < 0.995
        for: 10m
        severity: page
        annotations:
          summary: "Toggle success rate below SLO (< 99.5%)"
          description: "Success rate: {{ $value | humanizePercentage }}"

      - alert: ToggleLatencyHigh
        expr: |
          histogram_quantile(0.99,
            sum(rate(tcp_comm_packet_latency_seconds_bucket{transport="new"}[10m])) by (le)
          ) > 1.5
        for: 10m
        severity: page
        annotations:
          summary: "p99 latency above SLO (> 1500ms)"
          description: "p99 latency: {{ $value | humanizeDuration }}"

      - alert: ErrorBudgetExhausted
        expr: |
          (1 - sum(rate(tcp_comm_packet_sent_total{transport="new",outcome="success"}[30d]))
           / sum(rate(tcp_comm_packet_sent_total{transport="new"}[30d])))
          /
          (1 - 0.999)
          > 1.0
        for: 1h
        severity: ticket
        annotations:
          summary: "30-day error budget exhausted"
          description: "Pause rollout and investigate"

      - alert: QueueFullFrequent
        expr: |
          rate(tcp_comm_queue_full_total{transport="new"}[5m]) > 0.01
        for: 5m
        severity: warning
        annotations:
          summary: "Queue full events > 1%"
          description: "Backpressure detected"
```

### Alert Routing

```yaml
## alertmanager.yml
route:
  group_by: ["alertname", "transport"]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: "tcp-rebuild-team"

  routes:
    - match:
        severity: page
      receiver: "pagerduty"

    - match:
        severity: ticket
      receiver: "jira"

    - match:
        severity: warning
      receiver: "slack"

receivers:
  - name: "pagerduty"
    pagerduty_configs:
      - service_key: "<PD_SERVICE_KEY>"

  - name: "jira"
    webhook_configs:
      - url: "<JIRA_WEBHOOK>"

  - name: "slack"
    slack_configs:
      - api_url: "<SLACK_WEBHOOK>"
        channel: "#tcp-rebuild-alerts"
```

---

## Rollout Plan

### Stage 1: Dark Launch (Week 1)

- **Canary %**: 0% (dark launch only)
- **Goal**: Validate metrics collection
- **Validation**: Metrics match legacy transport
- **Rollback**: Disable dark launch flag

### Stage 2: Initial Canary (Week 1-2)

- **Canary %**: 10%
- **Duration**: 3 days
- **Goal**: Detect critical issues early
- **Validation**: Success rate ≥ 99.5%, no SLO violations
- **Rollback**: Set `CANARY_PERCENTAGE=0`

### Stage 3: Expanded Canary (Week 2)

- **Canary %**: 25%
- **Duration**: 4 days
- **Goal**: Validate under moderate load
- **Validation**: SLOs met, error budget > 50%
- **Rollback**: Reduce to 10% or 0%

### Stage 4: Majority Canary (Week 3-4)

- **Canary %**: 50%
- **Duration**: 7 days
- **Goal**: Full load validation
- **Validation**: All SLOs met for 7 consecutive days
- **Rollback**: Reduce to previous stage

### Rollback Procedure

**Automatic**:

```python
class AutoRollback:
    """Automatic rollback on SLO violation."""

    def __init__(self, slo_checker: SLOChecker):
        self.slo = slo_checker
        self.violation_count = 0
        self.max_violations = 3

    async def check_and_rollback(self):
        """Check SLOs every minute, rollback if violated."""
        if not await self.slo.check_all():
            self.violation_count += 1
            if self.violation_count >= self.max_violations:
                await self.rollback()
        else:
            self.violation_count = 0

    async def rollback(self):
        """Emergency rollback to legacy."""
        logger.critical("Auto-rollback triggered - SLO violations")
        FeatureFlags.set_canary_percentage(0.0)
        await self.notify_team("ROLLBACK: Canary disabled due to SLO violations")
```

**Manual**:

```bash
## Immediate rollback
kubectl set env deployment/cync-controller CANARY_PERCENTAGE=0

## Or via config
./scripts/set-canary.sh 0

## Verify
curl http://cync-controller:9400/metrics | grep canary_percentage
```

---

## Acceptance Criteria

### Deployment

- [x] Canary router implemented and tested
- [x] Feature flags functional
- [x] Dark launch mode validated
- [x] Rollback tested (manual + auto)

### Monitoring

- [x] Grafana dashboard deployed
- [x] All SLO queries validated
- [x] Error budget tracking functional
- [x] Alerts configured and tested

### SLOs

- [x] Success rate ≥ 99.9% (30d)
- [x] p99 latency ≤ 1500ms (7d)
- [x] Packet loss < 1% (24h)
- [x] Error budget > 0% at end of phase

### Validation

- [x] 50% canary for 7 days with no SLO violations
- [x] No critical incidents
- [x] Rollback procedures tested
- [x] Team trained on dashboards/alerts

---

## Risks & Mitigation

| Risk                   | Impact   | Probability | Mitigation                              |
| ---------------------- | -------- | ----------- | --------------------------------------- |
| Production outage      | Critical | Low         | Auto-rollback + dark launch validation  |
| SLO violations         | High     | Medium      | Gradual rollout + error budget tracking |
| Alert fatigue          | Medium   | Medium      | Tuned thresholds + escalation policies  |
| Performance regression | High     | Low         | Latency SLO + benchmarking              |
| Rollback failure       | Critical | Very Low    | Tested rollback + feature flag fallback |

---

## Timeline

**Week 1**: Dark launch + initial canary (10%)
**Week 2**: Expanded canary (25%)
**Week 3-4**: Majority canary (50%) + validation
**Week 4**: Handoff + Phase 3 planning

---

## Success Metrics

- 50% canary sustained for 7+ days
- All SLOs met continuously
- Zero critical incidents
- Error budget > 25% remaining
- Rollback tested successfully

---

## Next Phase

Phase 3: Full migration and legacy deprecation (see `04-phase-3-spec.md`)
