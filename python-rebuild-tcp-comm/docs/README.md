# TCP Communication Rebuild - Documentation Index

**Program Status**: Phase 0 Complete ✓ | Phase 1-3 Planned
**Last Updated**: 2025-11-01

---

## Overview

This directory contains comprehensive documentation for the TCP communication layer rebuild program. The program follows a bottom-up, phased approach to replace the legacy TCP communication layer with a traceable, reliable, testable system.

---

## Documentation Structure

### Discovery & Planning

**[00-discovery.md](00-discovery.md)** - Current System Analysis
- File map and code survey
- Current TCP flow diagram
- Identified failure modes
- Protocol notes (Cync packet format)
- Evidence and recommendations

### Implementation Phases

**[01-phase-0.md](01-phase-0.md)** - Phase 0: Toggle + Log Harness ✓ **COMPLETE**
- Minimal toggler with JSON logging
- Prometheus metrics endpoint
- TCP transport abstraction
- Acceptance criteria (all met)
- **Status**: Delivered and validated

**[02-phase-1-spec.md](02-phase-1-spec.md)** - Phase 1: Reliable Frame Layer
- ACK/NACK with retries
- Idempotency via LRU deduplication
- Bounded queues for backpressure
- Cync protocol integration
- Device simulator for chaos testing
- **Status**: Specification complete, ready for implementation
- **Effort**: ~3-4 weeks, 2-3 engineers

**[03-phase-2-spec.md](03-phase-2-spec.md)** - Phase 2: Canary Deployment
- Traffic routing (10-50% canary)
- SLO monitoring and dashboards
- Error budget tracking
- Automated rollback
- Dark launch validation
- **Status**: Specification complete
- **Effort**: ~3-4 weeks, 2 engineers + 1 SRE

**[04-phase-3-spec.md](04-phase-3-spec.md)** - Phase 3: Full Migration
- 100% traffic cutover
- Legacy code deprecation
- Operational handoff
- 30-day validation period
- Code cleanup
- **Status**: Specification complete
- **Effort**: ~4-6 weeks, 2 engineers + 1 PM

---

## Quick Reference

### Phase Summary

| Phase | Status | Effort | Deliverables |
|-------|--------|--------|--------------|
| Phase 0 | ✓ Complete | 1-2 weeks | Toggler, metrics, tests, docs |
| Phase 1 | Planned | 3-4 weeks | Reliability layer, simulator |
| Phase 2 | Planned | 3-4 weeks | Canary deployment, monitoring |
| Phase 3 | Planned | 4-6 weeks | Full migration, deprecation |

**Total Program**: ~12-16 weeks (3-4 months)

### Key Decisions

**Phase 0 Decisions** (Implemented):
- Python 3.13 (latest GA)
- Minimal dependencies (prometheus-client only)
- JSON structured logging (stdlib)
- Simple framing (0xF00D magic + length + JSON)
- Asyncio TCP transport with timeouts

**Phase 1 Decisions** (Specified):
- ACK/NACK explicit frames
- UUIDv7 for msg_id (sortable)
- LRU deduplication (1000 entry cache, 5min TTL)
- Exponential backoff (250ms → 5s, max 3 retries)
- Real Cync protocol (0x73, 0x83, 0x43 support)

**Phase 2 Decisions** (Specified):
- Hash-based canary routing (sticky per device)
- Dark launch before cutover
- SLO targets: 99.9% success, p99 < 1.5s
- Auto-rollback on SLO violation
- Error budget tracking (30-day window)

**Phase 3 Decisions** (Specified):
- Gradual increase: 75% → 90% → 100%
- 30-day validation at 100%
- Deprecate then remove legacy code
- Operational handoff with runbooks

---

## Architecture Evolution

### Phase 0 (Current)
```
[Toggler CLI] → [TCPConnection] → [Device]
                      ↓
                [Prometheus Metrics]
                [JSON Logs]
```

### Phase 1 (Target)
```
[Application] → [ReliableTransport] → [TCPConnection] → [Device]
                     ↓                      ↑
                [ACK/NACK Handler]          |
                [Dedup Cache (LRU)]         |
                [Retry Logic]               |
                     └──────────────────────┘
                     ↓
                [Metrics + Logs]
```

### Phase 2 (Canary)
```
[Application] → [CanaryRouter] ─→ [ReliableTransport (new)] → [Device]
                     ├──────────→ [LegacyTransport] → [Device]
                     ↓
                [Traffic Split: 10-50%]
                [SLO Monitoring]
                [Auto Rollback]
```

### Phase 3 (Final)
```
[Application] → [ReliableTransport] → [Device]
                     ↓
                [Full Production]
                [Legacy Removed]
                [SLO Validated]
```

---

## Metrics Reference

### Phase 0 Metrics (Implemented)

```
tcp_comm_packet_sent_total{device_id, outcome}
tcp_comm_packet_recv_total{device_id, outcome}
tcp_comm_packet_latency_seconds_bucket{device_id}
tcp_comm_packet_retransmit_total{device_id, reason}
tcp_comm_decode_errors_total{device_id, reason}
```

### Phase 1 Additional Metrics (Planned)

```
tcp_comm_ack_received_total{device_id, outcome}
tcp_comm_ack_timeout_total{device_id}
tcp_comm_idempotent_drop_total{device_id}
tcp_comm_send_queue_size{device_id}
tcp_comm_recv_queue_size{device_id}
tcp_comm_queue_full_total{device_id, queue_type}
```

### Phase 2 Additional Metrics (Planned)

```
tcp_comm_routing_decision{transport, device_id}
tcp_comm_canary_percentage
tcp_comm_slo_compliance{slo_name}
tcp_comm_error_budget_remaining{slo_name}
```

---

## SLO Definitions

### Production SLOs (Phase 2+)

| SLO | Target | Window | Error Budget |
|-----|--------|--------|--------------|
| Toggle Success Rate | 99.9% | 30d | 0.1% |
| Toggle Latency (p99) | ≤ 1500ms | 7d | N/A |
| Packet Loss Rate | < 1% | 24h | N/A |
| Decode Error Rate | < 0.1% | 24h | N/A |
| Queue Full Rate | < 1% | 1h | N/A |

### Lab SLOs (Phase 1)

| Metric | Target |
|--------|--------|
| p95 latency | < 300ms |
| p99 latency | < 800ms |
| Retransmit rate | < 0.5% |

---

## Testing Strategy

### Phase 0 (Implemented)
- ✓ 11 unit tests (100% pass)
- ✓ Mock-based isolation
- ✓ Integration with pytest-asyncio

### Phase 1 (Planned)
- 30+ unit tests (reliability + dedup + queues)
- 10+ integration tests with device simulator
- 5+ chaos tests (latency, loss, reorder, partition)

### Phase 2 (Planned)
- Dark launch validation
- Canary testing (10%, 25%, 50%)
- SLO compliance monitoring
- Rollback testing

### Phase 3 (Planned)
- 30-day production validation
- Regression testing after cleanup
- Load testing at 100%

---

## Risks & Mitigation

### High-Risk Items

1. **Cync Protocol Incompatibility** (Phase 1)
   - Mitigation: Device simulator + real device lab testing

2. **Production Outage** (Phase 2)
   - Mitigation: Dark launch + gradual rollout + auto-rollback

3. **Performance Regression** (Phase 2)
   - Mitigation: SLO monitoring + latency tracking

4. **Knowledge Loss** (Phase 3)
   - Mitigation: Documentation + training + runbooks

---

## How to Use This Documentation

### For Engineers Implementing Phase 1
1. Read `01-phase-0.md` to understand foundation
2. Study `02-phase-1-spec.md` for detailed requirements
3. Review existing code in `cync-controller/src/cync_controller/`
4. Start with reliable transport, then simulator
5. Reference acceptance criteria for done definition

### For SRE Team (Phase 2)
1. Review `03-phase-2-spec.md` for monitoring setup
2. Set up Grafana dashboards from specs
3. Configure Prometheus alerts
4. Practice rollback procedures
5. Validate dark launch before canary

### For Product/Leadership
1. Review this README for program overview
2. Check phase summaries for timeline and effort
3. Review SLO definitions for success criteria
4. Understand risk mitigation strategies
5. Track error budget consumption during rollout

---

## Related Documentation

### External to This Directory

- **Implementation**: `/python-rebuild-tcp-comm/src/` - Phase 0 code
- **Tests**: `/python-rebuild-tcp-comm/tests/` - Phase 0 tests
- **Scripts**: `/python-rebuild-tcp-comm/scripts/` - Dev tools
- **Legacy Code**: `/cync-controller/src/cync_controller/` - Current system

### References

- [Cync Protocol Notes](00-discovery.md#protocol-notes)
- [Phase 0 Acceptance Criteria](01-phase-0.md#acceptance-criteria)
- [SLO Definitions](03-phase-2-spec.md#service-level-objectives-slos)
- [Rollback Procedures](03-phase-2-spec.md#rollback-procedure)

---

## FAQ

**Q: Why bottom-up instead of big-bang rewrite?**
A: Reduces risk, provides early value, allows validation at each step, and enables rollback.

**Q: Why so many phases?**
A: Each phase delivers value and validates assumptions before moving forward. Fail fast, learn early.

**Q: Can we skip Phase 2 canary?**
A: Not recommended. Canary deployment is critical for validating production behavior without full risk.

**Q: How long until full production deployment?**
A: 12-16 weeks total (Phase 0 done, 3-4 weeks each for Phases 1-3).

**Q: What if we find issues during canary?**
A: Auto-rollback + error budget tracking ensures we catch and fix issues before they impact SLOs.

**Q: Can we use this pattern for other systems?**
A: Yes! This phased migration approach is reusable. See retrospective (Phase 3) for lessons learned.

---

## Change Log

- **2025-11-01**: Phase 0 complete; Phase 1-3 specifications created
- **2025-11-01**: Initial program kickoff and discovery

---

## Contact

**Program Owner**: TCP Rebuild Team
**Documentation**: This directory
**Code**: `/python-rebuild-tcp-comm/`
**Issues**: [GitHub Issues] or internal tracking system

---

**Next Action**: Review Phase 1 spec and schedule kick-off meeting.

