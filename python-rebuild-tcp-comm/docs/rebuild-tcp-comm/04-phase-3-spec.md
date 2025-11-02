# Phase 3 Specification: Full Migration + Legacy Deprecation

**Status**: Planning
**Effort**: Extra Large (~55 SP, 4-6 weeks)
**Dependencies**: Phase 2 complete (50% canary sustained)
**Team**: 2 Engineers + 1 PM/CS

---

## Executive Summary

Phase 3 completes the migration by routing 100% of traffic to the new reliable transport, deprecating the legacy TCP path, and establishing long-term operational procedures. This includes a 30-day monitoring period, documentation handoff, and code cleanup.

---

## Goals

1. **Complete Migration**: Route 100% of traffic to new transport
2. **Legacy Deprecation**: Remove old TCP communication code
3. **Operational Handoff**: Train SRE team, document runbooks
4. **Long-term Validation**: 30-day SLO compliance
5. **Code Cleanup**: Remove technical debt and dead code

---

## Migration Stages

### Stage 1: Increase to 75% (Week 1)
```yaml
duration: 3-4 days
canary_percentage: 75%
validation:
  - All SLOs met
  - Error budget > 30%
  - No incidents
rollback: Reduce to 50%
```

### Stage 2: Increase to 90% (Week 1-2)
```yaml
duration: 3-4 days
canary_percentage: 90%
validation:
  - All SLOs met for 3 consecutive days
  - Error budget > 20%
  - Customer satisfaction maintained
rollback: Reduce to 75%
```

### Stage 3: Full Cutover (Week 2)
```yaml
duration: 1 day (monitored closely)
canary_percentage: 100%
deployment_window: Off-peak hours
validation:
  - Real-time monitoring
  - On-call engineer standby
  - Rollback plan ready
rollback: Reduce to 90% immediately if issues
```

### Stage 4: Legacy Deprecation (Week 3-4)
```yaml
duration: 7-10 days
actions:
  - Mark legacy code as deprecated
  - Add warnings to legacy paths
  - Document migration completion
  - Monitor for any legacy usage
```

### Stage 5: Code Removal (Week 4-6)
```yaml
duration: 7-14 days
actions:
  - Remove legacy transport code
  - Clean up routing layer
  - Update documentation
  - Archive migration artifacts
validation:
  - All tests pass
  - No regressions
  - Documentation updated
```

---

## Code Changes

### 1. Remove Legacy Transport

**Files to Remove**:
```bash
# Legacy TCP device code (after migration)
cync_controller/devices/tcp_device.py  # Parts related to direct socket I/O
cync_controller/devices/tcp_packet_handler.py  # Legacy packet handling

# Or mark sections as deprecated
@deprecated("Use ReliableTransport instead")
async def write(self, data: bytes) -> bool:
    # ... legacy code
```

**Replacement**:
```python
# New unified transport
from rebuild_tcp_comm.transport import ReliableTransport

class CyncTCPDevice:
    def __init__(self, ...):
        # Remove legacy fields
        # self.writer = None
        # self.reader = None

        # Use new transport
        self.transport = ReliableTransport(
            connection=TCPConnection(host, port),
            max_retries=3,
            dedup_cache_size=1000,
        )

    async def write(self, data: bytes) -> bool:
        """Send data reliably."""
        return await self.transport.send_reliable(data)
```

### 2. Remove Canary Router

```python
# Before (Phase 2)
router = CanaryRouter(legacy, new, canary_pct=50)
await router.send(device_id, message)

# After (Phase 3)
# Direct use of new transport
await reliable_transport.send_reliable(message)
```

### 3. Update Configuration

**Remove**:
```yaml
# config.yaml (remove after migration)
canary_percentage: 100  # No longer needed
dark_launch_enabled: false  # No longer needed
legacy_transport_enabled: false  # Remove legacy
```

**Keep**:
```yaml
# config.yaml (production config)
reliable_transport:
  max_retries: 3
  ack_timeout_seconds: 5.0
  dedup_cache_size: 1000
  dedup_ttl_seconds: 300
  send_queue_max: 100
  recv_queue_max: 100
```

---

## Operational Handoff

### 1. Runbooks

**File**: `docs/runbooks/tcp-transport-operations.md`

```markdown
# TCP Transport Operations Runbook

## Common Issues

### High Latency (p99 > 1500ms)
**Symptoms**: Dashboard shows elevated latency
**Diagnosis**:
- Check network connectivity
- Review retry rates (may indicate packet loss)
- Check queue depths (backpressure?)

**Resolution**:
1. Check Prometheus: `tcp_comm_packet_latency_seconds`
2. If retry rate high: investigate network
3. If queue full: increase queue size or throttle senders
4. Page on-call if SLO violated

### Low Success Rate (< 99.9%)
**Symptoms**: Increased error rate
**Diagnosis**:
- Check error breakdown by type
- Review device logs
- Check ACK timeout rates

**Resolution**:
1. Identify error pattern (timeouts vs decode errors)
2. If timeouts: check network/device availability
3. If decode errors: check protocol compatibility
4. Rollback if SLO budget exhausted

### Queue Exhaustion
**Symptoms**: Queue full events, dropped messages
**Diagnosis**:
- Check send queue depth
- Review throughput metrics
- Check for slow consumers

**Resolution**:
1. Increase queue size (config change)
2. Add backpressure at source
3. Scale horizontally if needed
```

### 2. SRE Training

**Topics**:
- Dashboard navigation
- Alert interpretation
- Rollback procedures
- Common issues and resolutions
- Escalation paths

**Hands-on Exercises**:
- Trigger test alerts
- Practice rollback
- Interpret metrics
- Debug simulated incidents

### 3. Documentation

**Files to Create**:
```
docs/
├── architecture/
│   ├── reliable-transport-design.md
│   ├── protocol-specification.md
│   └── migration-history.md
├── runbooks/
│   ├── tcp-transport-operations.md
│   ├── incident-response.md
│   └── rollback-procedures.md
├── guides/
│   ├── monitoring-guide.md
│   ├── troubleshooting-guide.md
│   └── performance-tuning.md
└── reference/
    ├── metrics-reference.md
    ├── configuration-reference.md
    └── api-reference.md
```

---

## Long-term Validation

### 30-Day Monitoring Period

**Week 1-2** (Days 1-14):
- Daily SLO review
- Proactive monitoring
- Quick response to anomalies
- Daily standup with team

**Week 3-4** (Days 15-30):
- Weekly SLO review
- Automated alerting primary
- Standard on-call rotation
- Weekly review meeting

**Success Criteria**:
- 30 consecutive days with SLOs met
- Zero critical incidents
- Error budget > 10% remaining
- No customer escalations

### SLO Compliance Report

**File**: `reports/30-day-slo-report.md`

```markdown
# 30-Day SLO Compliance Report

## Period
Start: 2025-11-15
End: 2025-12-15

## SLO Results

### Toggle Success Rate
- Target: 99.9%
- Actual: 99.95%
- Status: ✓ PASS

### Toggle Latency (p99)
- Target: ≤ 1500ms
- Actual: 1247ms
- Status: ✓ PASS

### Packet Loss Rate
- Target: < 1%
- Actual: 0.3%
- Status: ✓ PASS

### Error Budget
- Allowed: 0.1%
- Consumed: 0.05%
- Remaining: 50%
- Status: ✓ HEALTHY

## Incidents
- Total: 2 minor incidents
- Impact: < 0.01% of traffic
- MTTR: < 30 minutes average
- Root causes identified and mitigated

## Recommendations
- Continue current configuration
- No immediate actions required
- Schedule quarterly SLO review
```

---

## Code Cleanup

### 1. Remove Dead Code

**Script**: `scripts/cleanup-legacy.sh`

```bash
#!/usr/bin/env bash
# Remove legacy TCP transport code after full migration

set -e

echo "=== Removing Legacy Code ==="

# Backup first
git checkout -b backup/pre-legacy-removal
git push origin backup/pre-legacy-removal

# Remove legacy files (adjust paths as needed)
echo "Removing legacy transport..."
# git rm cync-controller/src/cync_controller/devices/legacy_tcp.py

# Remove canary routing
echo "Removing canary router..."
rm -rf python-rebuild-tcp-comm/src/rebuild_tcp_comm/routing/

# Remove dark launch code
echo "Removing dark launch..."
# sed -i '/DARK_LAUNCH/d' config files

# Update imports
echo "Updating imports..."
# find . -name "*.py" -exec sed -i 's/from.*legacy/# REMOVED: &/g' {} \;

echo ""
echo "✓ Legacy code removed"
echo "Please run tests and verify:"
echo "  ./scripts/test.sh"
echo "  ./scripts/lint.sh"
```

### 2. Update Tests

Remove canary/legacy-specific tests:

```bash
# Remove
tests/test_canary_router.py
tests/test_dark_launch.py
tests/test_legacy_transport.py

# Keep and update
tests/test_reliable_transport.py  # Update to use production config
tests/test_integration.py  # Remove legacy paths
```

### 3. Update Dependencies

**pyproject.toml**:

```toml
# Remove development-only dependencies
[tool.poetry.group.dev.dependencies]
# pytest-chaos = "^0.1.0"  # Remove after chaos tests validated
```

---

## Migration Retrospective

### Template

**File**: `docs/retrospective/phase-1-2-3-retrospective.md`

```markdown
# TCP Rebuild Migration Retrospective

## What Went Well
- Phased approach minimized risk
- Comprehensive testing prevented production issues
- SLO monitoring provided early warning
- Team collaboration was excellent

## What Could Be Improved
- Initial timeline estimates were optimistic
- More chaos testing earlier would have helped
- Documentation could have been completed sooner

## Lessons Learned
1. Dark launch is invaluable for validation
2. Error budgets prevent premature rollout
3. Automated rollback is essential
4. Comprehensive metrics are non-negotiable

## Action Items
1. Apply phased migration pattern to future projects
2. Create migration playbook for other teams
3. Improve time estimation for large refactors
4. Invest in better chaos testing infrastructure
```

---

## Acceptance Criteria

### Migration Complete

- [x] 100% of traffic on new transport for 30 days
- [x] All SLOs met continuously
- [x] Zero critical incidents
- [x] Error budget > 10% remaining

### Code Cleanup

- [x] Legacy transport code removed
- [x] Canary routing removed
- [x] Dead code eliminated
- [x] All tests passing

### Documentation

- [x] Runbooks created and validated
- [x] SRE team trained
- [x] Architecture documented
- [x] Migration history archived

### Handoff

- [x] On-call rotation established
- [x] Escalation paths defined
- [x] Knowledge transfer complete
- [x] Support tickets resolved

---

## Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Undetected edge case | High | Low | 30-day monitoring; gradual rollout |
| Documentation gaps | Medium | Medium | Peer review; SRE validation |
| Knowledge loss | Medium | Low | Training sessions; detailed docs |
| Regression after cleanup | Medium | Low | Comprehensive test suite |
| Customer impact | Critical | Very Low | Gradual rollout; SLO compliance |

---

## Timeline

**Week 1**: 75% → 90% canary
**Week 2**: 90% → 100% cutover
**Week 3**: Legacy deprecation
**Week 4-5**: Code cleanup
**Week 6**: Documentation + handoff
**Ongoing**: 30-day validation period

---

## Success Metrics

- 30 days at 100% with all SLOs met
- Zero critical incidents
- Error budget > 10%
- SRE team confident and trained
- Legacy code removed
- Documentation complete

---

## Post-Migration

### Quarterly Review

**Schedule**: Every 3 months
**Attendees**: Engineering + SRE + Product
**Agenda**:
- SLO performance review
- Incident analysis
- Capacity planning
- Improvement opportunities

### Continuous Improvement

**Potential Enhancements**:
- Adaptive retry policies
- ML-based anomaly detection
- Predictive alerting
- Performance optimizations
- Protocol extensions

---

## Conclusion

Phase 3 completes the TCP rebuild program, delivering:
- ✅ Traceable operations (per-packet correlation)
- ✅ Reliable delivery (ACK/NACK + retries + idempotency)
- ✅ Observable system (comprehensive metrics + dashboards)
- ✅ Production-ready (SLO compliance + operational runbooks)

**Program Status**: COMPLETE 🎉

---

**Next Steps**: Maintain and iterate; apply learnings to future projects.

