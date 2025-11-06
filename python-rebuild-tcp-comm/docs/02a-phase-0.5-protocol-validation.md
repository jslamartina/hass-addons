# Phase 0.5: Real Protocol Validation & Capture

**Status**: Planning
**Dependencies**: Phase 0 complete ✓
**Execution**: Sequential solo implementation

---

## Architecture Context

**CRITICAL**: This is a **from-scratch rebuild** of the Cync controller in `python-rebuild-tcp-comm/`.

- The existing `cync-controller/` codebase is used **only as protocol reference**
- This is **NOT an integration project** - we're building it right from the ground up
- The cloud relay infrastructure is referenced for **understanding packet capture approach only**
- All work stays in `python-rebuild-tcp-comm/` - no integration with legacy code

---

## Guidance for Technical Reviewers

**CRITICAL PRINCIPLE**: Phase 0.5 involves empirical discovery of protocol details that **cannot be known in advance**. Some aspects will be uncertain until actual packet captures are analyzed.

**Protocol Unknowns** (resolved during Phase 0.5):
1. **ACK packet structure** - msg_id presence/position unknown until captured
2. **Queue ID/Endpoint byte overlap** - Relationship unknown until captured
3. **Checksum algorithm validation** - May require adjustment based on real packets

**What Technical Reviewers Should NOT Flag (These Are EXPECTED, Not Risks)**:

❌ **DNS Redirection as "Single Point of Failure"**
- Phase 0.5 REQUIRES DNS redirection (`cm.gelighting.com` → `127.0.0.1`) - this is the ONLY capture method
- DNS prerequisite validation happens BEFORE Phase 0.5 begins (see § DNS Redirection Prerequisite)
- If DNS blocked (DNSSEC, DoH, VPN, etc.) → Phase 0.5 cannot proceed → this is EXPECTED
- Do NOT flag this as a "risk" requiring mitigation
- Do NOT ask for "alternative capture methods" or "fallback strategies"
- ACCEPT: DNS is a hard prerequisite. If unavailable, escalate and stop. No alternatives.

❌ **Timeline/Schedule/Duration Estimates**
- This is a one-person hobby project in sequential order
- Do NOT track time estimates, day counts, hour budgets, or duration predictions
- Do NOT create "risk scenarios" with "+X days" timeline impact
- Do NOT flag "daily breakdowns" as "too prescriptive" needing "more flexibility"
- ACCEPT: Implementation steps listed in order. No schedule tracking.

❌ **Protocol Unknowns Before Data Collection**
- ACK msg_id presence/position unknown until captured → Decisions deferred to Phase 1b Step 0 (Prerequisites Check)
- Checksum algorithm unvalidated until tested → May need adjustment, contingency documented
- Do NOT demand elaborate decision trees for every possible ambiguous outcome
- Do NOT require pre-commitment to implementation paths before empirical data available
- Do NOT try to pre-plan for every edge case when dealing with genuine unknowns
- ACCEPT: Uncertainty documented. Decisions made when data available.

**What Technical Reviewers Should NOT Do**:
- ❌ Demand elaborate decision trees for every possible ambiguous outcome
- ❌ Require pre-commitment to implementation paths before empirical data available
- ❌ Try to pre-plan for every edge case when dealing with genuine unknowns
- ❌ Re-review architectural decisions already made in prior planning sessions

**What Technical Reviewers SHOULD Flag (Actual Problems)**:
- ✅ **Actual Bugs**: Missing validation steps, incorrect capture procedures, gaps in packet analysis
- ✅ **Missing Guidance**: Unclear deliverable requirements that would block Phase 1a
- ✅ **Spec Inconsistencies**: Contradictions within this spec or with Phase 1a/1b specs
- ✅ Document uncertainty clearly and objectively
- ✅ Note which implementation paths remain possible after validation
- ✅ Accept that Phase 0.5 findings will drive Phase 1a-1d implementation decisions
- ✅ Trust that implementation teams will make decisions when data is available

**Example of Proper Uncertainty Handling**:

If Phase 0.5 finds ACK msg_id position is ambiguous (inconsistent across samples):
- **Document**: "ACK msg_id position varies: bytes 5-7 (80% of samples), bytes 6-8 (20% of samples)"
- **Note**: "Two implementation paths possible: (1) Parallel ACK matching with position table, (2) FIFO queue approach"
- **Defer**: "Implementation decision made in Phase 1b Step 0 (Prerequisites Check) based on these findings"
- **No elaborate decision trees needed** - implementer will choose based on actual data

**Why This Matters**: Pre-planning for unknowns is **wasteful** (time/effort spent creating plans that get invalidated by empirical findings). Better to accept uncertainty, document it clearly, and make informed decisions when data is available.

---

## Executive Summary

Phase 0.5 validates and documents the real Cync device protocol through packet capture and analysis. This phase bridges Phase 0 (which used a custom test protocol with 0xF00D magic bytes) and Phase 1a (which will implement the real Cync protocol encoder/decoder).

**Why Phase 0.5?**
- Phase 0 used custom test framing (0xF00D + JSON) that won't work with real devices
- Phase 1 spec assumes protocol knowledge, but we need real-world validation
- Building from scratch means we can't rely on legacy code assumptions
- Capture first, implement second = lower risk

---

## Goals

1. **Capture real device traffic** using MITM proxy (DNS redirection required)
2. **Document actual packet flows** for key operations (handshake, toggle, status, heartbeat)
3. **Validate protocol structure** documented in legacy codebase
4. **Create test fixtures** with real packet bytes for Phase 1a testing
5. **Identify protocol edge cases** not documented in legacy code

---

## Scope

**In Scope:**
- Packet capture of real Cync devices via cloud relay
- Documentation of packet flows and structure
- Hex dumps and annotated examples
- Test fixture generation
- Protocol validation against legacy documentation

**Out of Scope:**
- Protocol implementation (Phase 1a)
- Device simulator (Phase 1d)
- Encoder/decoder code (Phase 1a)
- Integration with Phase 0 toggler (Phase 1a)
- TLS/encryption analysis (future)

---

## Protocol Background

### Known Packet Types (from legacy `cync-controller`)

| Type   | Name             | Direction | Description                              |
|--------|------------------|-----------|------------------------------------------|
| `0x23` | HANDSHAKE        | DEV→CLOUD | Initial connection, device endpoint      |
| `0x28` | HELLO_ACK        | CLOUD→DEV | Handshake acknowledgment                 |
| `0x43` | DEVICE_INFO      | DEV→CLOUD | Bulk device status (19 bytes per device) |
| `0x48` | INFO_ACK         | CLOUD→DEV | Device info acknowledgment               |
| `0x73` | DATA_CHANNEL     | Both      | Command/response channel (main control)  |
| `0x78` | KEEPALIVE        | Both      | Connection keepalive                     |
| `0x7B` | DATA_ACK         | CLOUD→DEV | Data channel acknowledgment              |
| `0x83` | STATUS_BROADCAST | DEV→CLOUD | Device status update                     |
| `0x88` | STATUS_ACK       | CLOUD→DEV | Status acknowledgment                    |
| `0xA3` | APP_ANNOUNCE     | APP→CLOUD | Phone app announcement                   |
| `0xAB` | APP_ACK          | CLOUD→APP | App acknowledgment                       |
| `0xC3` | DEVICE_CONNECT   | DEV→CLOUD | Device connection packet                 |
| `0xC8` | CONNECT_ACK      | CLOUD→DEV | Connection acknowledgment                |
| `0xD3` | HEARTBEAT_DEV    | DEV→CLOUD | Device heartbeat/ping                    |
| `0xD8` | HEARTBEAT_CLOUD  | CLOUD→DEV | Cloud heartbeat response                 |

### Documented Packet Structure

**Header (5 bytes)**:
```
[packet_type][0x00][0x00][length_multiplier][base_length]
```

- Byte 0: Packet type (e.g., 0x73)
- Bytes 1-2: Unknown/padding (usually 0x00)
- Byte 3: Length multiplier (multiply by 256)
- Byte 4: Base length
- **Total data length** = (byte[3] * 256) + byte[4]
- Header length (5 bytes) NOT included in data length

**Endpoint/Queue ID + Message ID**:
- Varies by packet type
- 0x23: Endpoint (4 bytes) at positions 5-8
- 0x73: Queue ID (5 bytes) + msg_id (3 bytes) starting at position 5
- 0x83: Similar structure to 0x73

**Payload Framing**:
- Often wrapped in `0x7e` start/end markers
- Checksum: Sum of bytes between 0x7e markers modulo 256

---

## DNS Redirection Prerequisite (Day -1)

**Mandatory Requirement (Technical Review Finding 2.2 - Resolved)**: MITM proxy and cloud relay both require DNS redirection to intercept device traffic. This must be verified before Phase 0.5 begins.

**Approved as hard requirement**: No alternative capture methods. If DNS blocked, Phase 0.5 cannot proceed (documented escalation paths below).

### Verification Steps (Day -1)

**Test DNS Override Capability**:

```bash
# Linux/Mac: Add to /etc/hosts
sudo sh -c 'echo "127.0.0.1  cm.gelighting.com" >> /etc/hosts'

# Windows: Add to C:\Windows\System32\drivers\etc\hosts
# (Open notepad as Administrator, add line: 127.0.0.1  cm.gelighting.com)

# Verify DNS resolution
nslookup cm.gelighting.com
# Expected output: Should resolve to 127.0.0.1

# Alternative verification
ping cm.gelighting.com
# Should ping 127.0.0.1
```

**Common DNS Override Issues & Solutions (Technical Review Finding 2.2 - Enhanced)**:

| Issue | Symptom | Solution |
|-------|---------|----------|
| **DNSSEC** | `nslookup` still resolves to real cloud IP | Disable DNSSEC in router settings OR use different network |
| **DNS-over-HTTPS (DoH)** | Browser bypasses /etc/hosts | Disable DoH in browser settings (Firefox: about:config → network.trr.mode=5) |
| **Router DNS** | Device ignores /etc/hosts | Configure DNS override in router OR use Pi-hole for network-wide DNS |
| **Corporate VPN** | VPN enforces specific DNS | Disconnect VPN OR use personal network OR request VPN DNS exception |
| **Systemd-resolved** | Linux DNS caching | `sudo systemctl restart systemd-resolved` after editing /etc/hosts |

**Verification Command**:
```bash
# MUST return 127.0.0.1 (not real cloud IP)
nslookup cm.gelighting.com

# Expected output:
# Server:         127.0.0.1
# Address:        127.0.0.1#53
#
# Name:   cm.gelighting.com
# Address: 127.0.0.1
```

**Escalation Paths (if DNS validation fails)**:

1. **Option A: Fix DNS Issue** (recommended)
   - Follow troubleshooting table above
   - Retry validation after fix
   - Proceed with Phase 0.5

2. **Option B: Use Different Network** (alternative)
   - Switch to personal network (if on corporate)
   - Use mobile hotspot
   - Retry validation on new network

3. **Option C: Pause Phase 0.5** (last resort)
   - Document DNS blocker (cannot be worked around)
   - Escalate to user for decision
   - Consider alternative: Use existing cloud relay logs (if available) for reference

**If DNS works**: Proceed with Phase 0.5
**If DNS blocked after all options**: Phase 0.5 cannot proceed (no workarounds - this is accepted limitation)

---

## Methodology

### 1. Packet Capture Approach

**Method: MITM Proxy (ONLY METHOD)**

We will implement a minimal MITM (Man-in-the-Middle) proxy in `python-rebuild-tcp-comm/` as the packet capture tool. This approach provides complete control over packet logging and capture format while maintaining independence from the existing cloud relay implementation.

**Note**: Both MITM proxy and cloud relay modes require DNS redirection - there is no alternative capture method that avoids this requirement.

**MITM Proxy Requirements**:

The proxy implementation (`scripts/mitm-proxy.py`) must provide:

- **TCP Server**: Accept device connections on configurable port (default: 23779)
  - **REQUIRES DNS REDIRECTION**: Device must resolve `cm.gelighting.com` → `127.0.0.1` (see DNS setup below)
  - Device connects via plaintext TCP (thinks it's connecting to cloud)
- **Bidirectional Forwarding**: Forward packets between device and upstream server
  - Upstream can be real Cync cloud (35.196.85.236:23779) OR localhost cloud relay for testing
  - **Device → Proxy**: Plaintext TCP (no SSL from device perspective)
  - **Proxy → Cloud**: SSL/TLS connection when forwarding to real cloud
  - Uses `ssl.create_default_context()` for upstream SSL validation
- **Structured Logging**: Log all packets to stdout in structured JSON format
  - Timestamp (ISO 8601 with milliseconds)
  - Direction ("DEV→CLOUD" or "CLOUD→DEV")
  - Hex dump of full packet
  - Packet length
- **Raw Capture Storage**: Save raw packet captures to `python-rebuild-tcp-comm/captures/` directory
  - Filename format: `capture_YYYYMMDD_HHMMSS.txt` with timestamped hex dumps
  - Optional `.pcap` format support for Wireshark analysis
- **Clean Shutdown**: Graceful connection handling and task cleanup on SIGINT/SIGTERM
- **Implementation Size**: ~200-250 lines using asyncio, based on `CloudRelayConnection` architecture pattern from `cync-controller/src/cync_controller/server.py` (reference only, not integrated)
  - Core proxy logic: ~120 lines
  - SSL handling + error cases: ~40 lines
  - Logging + capture: ~40 lines
  - Annotation support (optional): ~30 lines
  - CLI argument parsing: ~20 lines

---

### SSL/TLS Handling for MITM

**Device → Proxy Connection** (Port 23779):
- Device connects via DNS redirection (thinks proxy is cloud)
- Connection is **plaintext TCP** (no SSL from device perspective)
- Requires DNS redirection: `cm.gelighting.com → 127.0.0.1`
- Device sends unencrypted Cync protocol packets

**Proxy → Cloud Connection** (35.196.85.236:23779):
- Proxy forwards to real cloud via SSL/TLS
- Uses system CA certificates for validation
- Python: `ssl.create_default_context()` (line 279 in implementation)
- Proxy acts as SSL client to cloud

**SSL/TLS Certificate Validation Scenarios**:

**SSL Context Selection (Decision Tree)**:

Choose SSL context based on upstream host:
1. **Upstream = localhost?** → Scenario 2 (No SSL)
2. **Upstream = real cloud (35.196.85.236)?** → Scenario 1 (Production with cert validation)
3. **Upstream = custom host?** → Check certificate:
   - Valid cert from trusted CA → Scenario 1 (Production)
   - Self-signed cert → Scenario 3 (Dev only, log warning)
   - Custom CA cert → Scenario 4 (Enterprise, provide CA bundle path)

**Implementation**: Auto-detect based on `--upstream-host` CLI argument

---

**Scenario 1: Production Cloud (Recommended)**
```python
# Forward to real Cync cloud with certificate validation
ssl_context = ssl.create_default_context()
# Validates against system CA certificates
# Will fail if cert invalid/expired
```

**Scenario 2: Localhost Cloud Relay (Testing)**
```python
# Forward to localhost cloud relay (no SSL needed)
ssl_context = None  # No SSL for localhost
upstream_host = "localhost"
upstream_port = 23780  # Cloud relay port
```

**Scenario 3: Self-Signed Certificate (Development Only)**

⚠️ **WARNING**: Only use for development/testing. NEVER in production.

```python
# Disable certificate validation (INSECURE)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False  # Skip hostname verification
ssl_context.verify_mode = ssl.CERT_NONE  # Skip certificate validation

# Log warning
logger.warning("SSL certificate validation DISABLED - development only!")
```

**Scenario 4: Custom CA Certificate**
```python
# Use custom CA certificate (enterprise environments)
ssl_context = ssl.create_default_context(cafile="/path/to/custom_ca.pem")
# Validates against custom CA only
```

**Error Handling**:

```python
# In MITM proxy connect method
try:
    cloud_reader, cloud_writer = await asyncio.open_connection(
        self.upstream_host,
        self.upstream_port,
        ssl=self.ssl_context
    )
except ssl.SSLError as e:
    logger.error("SSL connection failed: %s", e)
    # Common causes:
    # - Certificate expired
    # - Hostname mismatch
    # - Untrusted CA
    # - Network issue during SSL handshake
    raise

except ConnectionRefusedError:
    logger.error("Cloud connection refused (check host/port)")
    raise

except asyncio.TimeoutError:
    logger.error("Cloud connection timeout (check network)")
    raise
```

**Implementation Checklist**:
- [ ] Use `ssl.create_default_context()` for production cloud
- [ ] Use `ssl_context=None` for localhost testing
- [ ] Never disable cert validation in production
- [ ] Log SSL errors with actionable messages
- [ ] Test both scenarios: real cloud + localhost relay

**DNS Redirection Requirement**:

The MITM proxy **requires** DNS redirection to be in place. The device must resolve the cloud hostname to the proxy's IP address.

```bash
# Example: DNS redirection via /etc/hosts
cm.gelighting.com → 127.0.0.1
```

**Prerequisite Validation (Day -1)**:
- DNS redirection must be validated BEFORE Phase 0.5 begins
- If DNS unavailable → Phase 0.5 cannot proceed
- No alternative capture methods supported in this spec

**Architecture Pattern** (from cloud relay reference):
```python
class MITMProxy:
    """Minimal MITM proxy for Cync protocol packet capture."""

    async def handle_device(self, reader, writer):
        """Handle device connection and forward to upstream."""
        # 1. Connect to upstream (cloud or cloud relay)
        cloud_reader, cloud_writer = await asyncio.open_connection(
            self.upstream_host, self.upstream_port, ssl=self.ssl_context
        )

        # 2. Bidirectional forwarding with logging
        await asyncio.gather(
            self._forward_and_log(reader, cloud_writer, "DEV→CLOUD"),
            self._forward_and_log(cloud_reader, writer, "CLOUD→DEV"),
        )

    async def _forward_and_log(self, src, dst, direction):
        """Forward packets and log hex dumps."""
        while True:
            data = await src.read(4096)
            if not data:
                break
            # Log with timestamp, direction, hex dump (structured JSON to stdout)
            self._log_packet(data, direction)
            # Save to capture file
            self._save_capture(data, direction)
            # Forward to destination
            dst.write(data)
            await dst.drain()
```

**Reference Materials** (for cross-validation only, NOT alternatives):

- **Legacy Cloud Relay Logs**: Review existing cloud relay logs from `cync-controller` for pattern validation
  - Useful for cross-referencing MITM proxy captures
  - Look for logs with "CLOUD→DEV" and "DEV→CLOUD" prefixes
  - File: `cync-controller/src/cync_controller/packet_parser.py` for structure understanding
  - **Not a capture method**: Reference only

- **tcpdump/Wireshark**: Supplementary low-level troubleshooting
  ```bash
  # Capture packets for troubleshooting only
  tcpdump -i any -w cync_packets.pcap tcp port 23779
  ```
  - Useful for debugging MITM proxy issues
  - **Not a capture method**: Troubleshooting tool only

**Note**: These are reference/troubleshooting tools, NOT alternative capture methods. Phase 0.5 requires MITM proxy with DNS redirection.

### 2. Key Flows to Capture

#### Flow 1: Device Handshake
**Trigger**: Device boots or reconnects
**Expected Sequence**:
1. `0x23` DEV→CLOUD (handshake with endpoint)
2. `0x28` CLOUD→DEV (hello ACK)

**Capture Goal**: Full hex dump of both packets, endpoint extraction

#### Flow 2: Device Toggle (Primary Use Case)
**Trigger**: Turn light on/off via Home Assistant
**Expected Sequence**:
1. `0x73` CLOUD→DEV (control command)
2. `0x7B` DEV→CLOUD (data ACK)
3. `0x83` DEV→CLOUD (status broadcast - state change)
4. `0x88` CLOUD→DEV (status ACK)

**Capture Goal**: Full hex dump of entire sequence, timing between packets

#### Flow 3: Status Broadcast (Passive)
**Trigger**: Device reports state change (button press, etc.)
**Expected Sequence**:
1. `0x83` DEV→CLOUD (status broadcast)
2. `0x88` CLOUD→DEV (status ACK)

**Capture Goal**: Validate 19-byte device payload structure

#### Flow 4: Heartbeat/Keepalive
**Trigger**: Periodic (every ~60 seconds)
**Expected Sequence**:
1. `0xD3` DEV→CLOUD (heartbeat)
2. `0xD8` CLOUD→DEV (heartbeat ACK)

**Capture Goal**: Verify timing and minimal payload

#### Flow 5: Device Info Broadcast
**Trigger**: Device boots or on request
**Expected Sequence**:
1. `0x43` DEV→CLOUD (device info - all devices on endpoint)
2. `0x48` CLOUD→DEV (info ACK)

**Capture Goal**: Bulk device data format (19 bytes × N devices)

### 3. Packet Analysis Checklist

For each captured packet:
- [ ] Hex dump (full packet bytes)
- [ ] Header breakdown (type, length calculation)
- [ ] Endpoint/queue_id/msg_id positions
- [ ] Payload extraction (between 0x7e markers if present)
- [ ] Checksum validation
- [ ] Timestamp and RTT (if ACK pair)
- [ ] Direction (DEV→CLOUD or CLOUD→DEV)
- [ ] Context (what triggered this packet)

### 4. ACK msg_id Position Validation (REQUIRED for Phase 1b)

**Goal**: Determine if ACK packets contain msg_id and document exact byte positions for reliable ACK matching.

**ACK Confidence Thresholds**

Confidence criteria determine which Phase 1b implementation approach to use:
- **High Confidence** → Parallel ACK matching (if msg_id consistently found)
- **Medium Confidence** → Additional validation samples needed
- **Low Confidence** → FIFO queue approach (if msg_id absent or inconsistent)

**Validation Criteria**:

For each ACK type (0x28, 0x7B, 0x88, 0xD8), the validation must meet these standards:

1. **Sample Size**: Capture **10+ request→ACK pairs** (not just 5)
   - Rationale: Higher sample size reduces false positive risk
   - Detects firmware version variance (if present)

2. **Unique msg_id Values**: Use distinctive msg_ids to avoid false matches
   - Good examples: `0xAA 0xBB 0xCC`, `0x11 0x22 0x33`, `0xFF 0x00 0xFF`
   - Avoid: Common values like `0x00 0x00 0x00` or `0xFF 0xFF 0xFF`
   - Rationale: Reduces chance of accidental match in other fields

3. **Multiple Match Detection**: Record ALL positions where msg_id found
   - If msg_id appears at 2+ positions: Document ambiguity
   - Example: "Found at bytes[5:8] AND bytes[10:13] (ambiguous)"
   - Requires additional analysis to determine correct position

4. **Consistency Check**: Position must be identical across all 10+ captures
   - If variance detected: Document as "FIRMWARE-DEPENDENT" risk
   - Example: "Position bytes 5-7 in 8 packets, bytes 6-8 in 2 packets"
   - Escalate variance to architecture review

5. **Structural Validation**: Verify position makes structural sense
   - NOT in header length field (bytes 3-4)
   - NOT in checksum position (last byte before 0x7E)
   - NOT in packet type field (byte 0)
   - Position should align with protocol structure

**Detailed Method** (for each ACK type):

**Step 1: Capture Request→ACK Pairs**
```bash
# Example for 0x73 → 0x7B validation
for i in {1..10}; do
    # Send command with unique msg_id
    msg_id=$(printf "%02x%02x%02x" $((i*10)) $((i*20)) $((i*30)))
    echo "Sending command with msg_id: $msg_id"
    # Trigger via Home Assistant
    # Capture both 0x73 and 0x7B packets
    sleep 2
done
```

**Step 2: Extract Known msg_id from Request**
```python
# For 0x73 data packet
request_packet = captured_0x73
msg_id = request_packet[10:13]  # Bytes 10-12 (known position)
print(f"Request msg_id: {msg_id.hex()}")  # e.g., "0a 14 1e"
```

**Step 3: Search ACK Packet for msg_id**
```python
ack_packet = captured_0x7B
matches = []

# Search all possible 3-byte positions
for pos in range(len(ack_packet) - 2):
    if ack_packet[pos:pos+3] == msg_id:
        matches.append(pos)
        print(f"Match found at bytes {pos}-{pos+2}")

if len(matches) == 0:
    print("msg_id NOT PRESENT in ACK")
elif len(matches) == 1:
    print(f"msg_id found at single position: bytes {matches[0]}-{matches[0]+2}")
else:
    print(f"WARNING: Multiple matches at positions: {matches}")
    # Requires disambiguation via structural analysis
```

**Step 4: Consistency Validation**
```python
# Across all 10+ captures
position_counts = {}
for capture in all_captures:
    position = find_msg_id_position(capture.ack_packet, capture.msg_id)
    position_counts[position] = position_counts.get(position, 0) + 1

# Check for 100% consistency
if len(position_counts) == 1:
    position, count = list(position_counts.items())[0]
    print(f"✅ Consistent position: bytes {position}-{position+2} (10/10 captures)")
else:
    print(f"⚠️ VARIANCE DETECTED: {position_counts}")
    # Example: {5: 8, 6: 2} means bytes 5-7 in 8 captures, bytes 6-8 in 2 captures
```

**Step 5: False Positive Mitigation**
```python
# If multiple positions found, use structural analysis to disambiguate
def validate_position_structure(ack_packet, position):
    """Check if position makes structural sense."""
    # Check 1: Not in fixed header (bytes 0-4)
    if position < 5:
        return False, "Position in fixed header (invalid)"

    # Check 2: Not in length field
    if position in [3, 4]:
        return False, "Position overlaps length field (invalid)"

    # Check 3: Not in checksum position (if packet has 0x7e framing)
    if b'\x7e' in ack_packet:
        end_marker_pos = ack_packet.rfind(0x7E)
        if position == end_marker_pos - 1:
            return False, "Position is checksum byte (invalid)"

    return True, "Position structurally valid"
```

**Step 6: Documentation**
```markdown
| ACK Type | Request Type | msg_id Present? | Position | Confidence | Sample Size | Notes |
|----------|--------------|-----------------|----------|------------|-------------|-------|
| 0x7B | 0x73 | YES | bytes 5-7 | High | 10/10 consistent | Immediately after queue_id |
| 0x88 | 0x83 | YES | bytes 5-7 | High | 10/10 consistent | Same position as 0x7B |
| 0x28 | 0x23 | NO | N/A | High | 10/10 no match | Handshake ACK has no msg_id |
| 0xD8 | 0xD3 | UNKNOWN | TBD | Low | Pending capture | Need validation |
```

**Deliverable**: Update Phase 1b ACK table (02c-phase-1b-reliable-transport.md lines 596-601) with validated positions and confidence levels before Phase 1b implementation starts.

**Confidence Level Determination** (guides Phase 1b path selection):

**High Confidence** (enables parallel matching):
- Sample size: ≥10 captures per ACK type (40+ total across all 4 types)
- Consistency: 100% of captures show msg_id at same byte position
- Structural validation: Position makes structural sense (not in header, checksum, or length fields)
- No firmware variance: Same position observed across different device firmware versions
- Result: Phase 1b implements parallel ACK matching

**Medium Confidence** (needs more samples):
- Sample size: 5-9 captures per ACK type (20-35 total)
- Consistency: ≥80% of captures show msg_id at same position
- Action: Capture 5+ additional samples to reach High confidence

**Low Confidence** (use FIFO approach):
- Consistency: <80% position match OR multiple ambiguous positions found
- Firmware variance: Different positions across firmware versions
- Result: Phase 1b implements FIFO queue (serialized requests)

**⚠️ CRITICAL EXIT CRITERIA (Technical Review Finding 1.1 - Resolved)**

Phase 0.5 MUST produce definitive ACK structure findings before Phase 1b starts. Ambiguous results are NOT acceptable exit criteria.

**If findings are ambiguous after initial 10+ samples per ACK type:**
1. **DO NOT proceed to Phase 1b**
2. **Capture 10+ ADDITIONAL samples** per ambiguous ACK type
3. **Analyze firmware variance** (test with different device firmware versions if available)
4. **If still ambiguous after 20+ samples total**: Escalate to architectural review
   - Document all observed patterns with confidence levels
   - Recommend FIFO approach (safest fallback)
   - Add technical debt item for parallel matching optimization

**Phase 1b gate:** ACK structure validation MUST achieve either:
- **High Confidence** for ALL 4 ACK types (parallel matching ready), OR
- **Definitive determination** that msg_id absent (FIFO approach documented)

**Ambiguous findings block Phase 1b start** - no exceptions.

This resolves circular dependency: Phase 0.5 delivers definitive findings → Phase 1b implements based on facts (no deferred decisions).

---

## Deliverables

### Deliverables Overview

Phase 0.5 includes 11 deliverables covering packet capture, protocol validation, and test fixture generation. All deliverables contribute to understanding the real Cync protocol behavior.

**Note**: Deliverable #11 (Group Operation Performance) is validated in Phase 1d instead of Phase 0.5 (full stack validation preferred).

---

### 1. MITM Proxy Tool

**File**: `scripts/mitm-proxy.py`

**Purpose**: Minimal TCP proxy for capturing Cync protocol packets with bidirectional forwarding and comprehensive logging.

**Architecture** (based on `CloudRelayConnection` from `cync-controller/src/cync_controller/server.py`):

```python
#!/usr/bin/env python3
"""
Minimal MITM proxy for Cync protocol packet capture.

Usage:
    python scripts/mitm-proxy.py --listen-port 23779 --upstream-host 35.196.85.236 --upstream-port 23779

    # Or forward to localhost cloud relay for testing:
    python scripts/mitm-proxy.py --listen-port 23779 --upstream-host localhost --upstream-port 23780 --no-ssl
"""

import asyncio
import json
import ssl
from datetime import datetime
from pathlib import Path

class MITMProxy:
    """MITM proxy for packet capture."""

    def __init__(self, listen_port: int, upstream_host: str, upstream_port: int, use_ssl: bool = True):
        self.listen_port = listen_port
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.ssl_context = ssl.create_default_context() if use_ssl else None
        self.capture_dir = Path("captures")
        self.capture_dir.mkdir(exist_ok=True)
        self.capture_file = self.capture_dir / f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    async def start(self):
        """Start the proxy server."""
        server = await asyncio.start_server(
            self.handle_device,
            "0.0.0.0",
            self.listen_port
        )
        print(f"MITM Proxy listening on port {self.listen_port}")
        print(f"Forwarding to {self.upstream_host}:{self.upstream_port}")
        print(f"Captures will be saved to {self.capture_file}")

        async with server:
            await server.serve_forever()

    async def handle_device(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle device connection and forward to upstream."""
        try:
            # Connect to upstream (cloud or cloud relay)
            cloud_reader, cloud_writer = await asyncio.open_connection(
                self.upstream_host,
                self.upstream_port,
                ssl=self.ssl_context
            )

            # Bidirectional forwarding with logging
            await asyncio.gather(
                self._forward_and_log(reader, cloud_writer, "DEV→CLOUD"),
                self._forward_and_log(cloud_reader, writer, "CLOUD→DEV"),
                return_exceptions=True
            )
        finally:
            writer.close()
            await writer.wait_closed()

    async def _forward_and_log(self, src: asyncio.StreamReader, dst: asyncio.StreamWriter, direction: str):
        """Forward packets and log hex dumps."""
        while True:
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

    def _log_packet(self, data: bytes, direction: str):
        """Log packet in structured JSON format to stdout."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "direction": direction,
            "length": len(data),
            "hex": data.hex(' ')
        }
        print(json.dumps(log_entry))

    def _save_capture(self, data: bytes, direction: str):
        """Save raw capture to file."""
        with open(self.capture_file, "a") as f:
            f.write(f"{datetime.now().isoformat()} {direction} ({len(data)} bytes)\n")
            f.write(data.hex(' ') + "\n\n")
```

**Features**:
- Accepts device connections on configurable port (default: 23779)
- Forwards to real Cync cloud OR localhost cloud relay (configurable)
- SSL support for real cloud connections
- Structured JSON logging to stdout
- Raw capture files saved to `captures/` directory
- Clean shutdown on SIGINT/SIGTERM
- ~150-200 lines using asyncio

**Reference**: Architecture based on `CloudRelayConnection._forward_with_inspection()` from existing cloud relay (reference only, not integrated)

### 2. Protocol Capture Document

**File**: `docs/protocol/02-phase-0.5-captures.md`

**Contents**:
- Annotated hex dumps for all 5 flows
- Packet structure validation (confirm or correct legacy docs)
- **ACK Packet Structure Validation** (Required for Phase 1b):
  - Capture 10+ request→ACK pairs per ACK type (0x28, 0x7B, 0x88, 0xD8)
  - Validate msg_id presence/absence with high confidence
  - Document exact byte positions if msg_id present
  - Provide architectural recommendation for Phase 1b (parallel vs FIFO)
  - Use validation method from lines 429-560 (ACK msg_id Position Validation section)
-   **Queue ID ↔ Endpoint Derivation Validation** (Required for Phase 1a):
  - Capture 5+ handshake→data sequences (0x23 followed by 0x73/0x83)
  - Extract endpoint from bytes[6:10] in 0x23 packet (NOTE: Byte 5 is unknown/padding, not part of endpoint)
  - Extract queue_id from bytes[5:10] in 0x73/0x83 packet
  - Extract msg_id and determine exact byte positions (e.g., bytes[9:12] or bytes[10:13])
  - **CRITICAL**: Check for byte overlap between queue_id and msg_id (e.g., Option D where byte 9 is shared)
  - Compare bytes to identify pattern (Option A: suffix, B: independent, C: embedded, D: overlapping)
  - Document transformation algorithm with annotated examples
  - Provide clear guidance on byte extraction for Phase 1a implementation

  **⚠️ USER DECISION REQUIRED (ONLY IF OVERLAP DETECTED)**: Byte Overlap Handling Strategy

  **Technical Review Finding 1.3 - Resolved**: This decision is conditional on overlap detection.

  **If Phase 0.5 finds NO overlap (Options A, B, or C)**: Document extraction algorithm, proceed to Phase 1a (no user decision needed).

  **If validation reveals byte overlap (Option D)**, user must approve handling approach:

  **Option A** (Recommended if overlap confirmed): Accept overlapping byte ranges
  - Acknowledge byte 9 serves dual purpose in both queue_id and msg_id
  - Document extraction algorithm showing overlap:
    ```
    Packet bytes: [... 05 06 07 08 09 10 11 ...]
    queue_id: packet[5:10] = [05 06 07 08 09]  # bytes 5-9 inclusive
    msg_id: packet[9:12] = [09 10 11]          # bytes 9-11 inclusive
    Overlap: byte 9 appears in BOTH identifiers
    ```
  - Phase 1a implementation: Extract both with overlapping ranges (simple, follows protocol)
  - Complexity: Low (straightforward array slicing)
  - Risk: None (protocol defines it this way)

  **Option B**: Require separate byte ranges (reject overlap)
  - If validation shows overlap, request protocol clarification or firmware update
  - Treat overlap as protocol ambiguity requiring resolution
  - Delay Phase 1a until non-overlapping structure validated
  - Complexity: High (requires protocol investigation/change)
  - Risk: Timeline delay if protocol cannot be changed

  **Recommendation**: Select Option A if overlap is confirmed in validation. Protocol designers may have intentionally shared byte 9 for space efficiency. Phase 1a can handle overlapping extractions without issues.
- Timing analysis (RTT, inter-packet delays)
- Edge cases discovered (malformed packets, retries, etc.)
- Device firmware version correlation
- **Packet Size Validation** (for Phase 1a PacketFramer MAX_PACKET_SIZE):
  - Record packet sizes for all captured packets (header + data length)
  - Calculate: max observed packet size across all captures
  - Validate: max packet size < 4096 bytes (MAX_PACKET_SIZE assumption)
  - If any packet > 4KB: Document in validation report and update Phase 1a PacketFramer.MAX_PACKET_SIZE
  - Provide size distribution table:
    ```
    | Packet Type | Min Size | Max Size | Median | p99 |
    |-------------|----------|----------|--------|-----|
    | 0x23        | 31 bytes | 31 bytes | 31     | 31  |
    | 0x73        | 20 bytes | 150 bytes| 45     | 120 |
    | 0x83        | 25 bytes | 44 bytes | 29     | 40  |
    ```

**Format Example**:
```markdown
### Flow 1: Device Handshake

**Context**: Cync bulb (firmware 1.2.3) boots and connects

**Packet 1: 0x23 Handshake (DEV→CLOUD)**
```
Timestamp: 2025-11-02T10:23:45.123Z
Direction: DEV→CLOUD
Raw Hex: 23 00 00 00 1a 03 39 87 c8 57 00 10 31 65 30 37 ...

Breakdown:
- Byte 0: 0x23 (HANDSHAKE)
- Byte 1-2: 0x00 0x00
- Byte 3: 0x00 (multiplier = 0)
- Byte 4: 0x1a (length = 26 bytes)
- Byte 5: 0x03 (unknown/padding)
- Bytes[6:10]: 0x39 0x87 0xc8 0x57 (endpoint = 0x57c88739 / 1472825145)
- Bytes[10:26]: 0x00 10 31 65 30 37 ... (auth code - partially redacted)
```

**Packet 2: 0x28 Hello ACK (CLOUD→DEV)**
...
```

**Endpoint Extraction Validation**:
```python
# Extract endpoint from 0x23 handshake packet
handshake_packet = captured_0x23
endpoint = handshake_packet[6:10]  # Bytes 6-9 (4 bytes)
print(f"Endpoint (hex): {endpoint.hex(' ')}")  # e.g., "39 87 c8 57"
print(f"Endpoint (decimal): {int.from_bytes(endpoint, 'big')}")  # e.g., 967239767
print(f"Endpoint (little-endian): {int.from_bytes(endpoint, 'little')}")  # For comparison

# Verify byte 5 is NOT part of endpoint
byte_5 = handshake_packet[5]
print(f"Byte 5 (padding/unknown): 0x{byte_5:02x}")  # e.g., 0x03 (varies, not endpoint)
```

### 3. Test Fixtures

**File**: `tests/fixtures/real_packets.py`

```python
"""Real packet captures for protocol validation testing.

All packets captured during Phase 0.5 protocol validation.
Each packet includes metadata for traceability and test parameterization.
"""

from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class PacketMetadata:
    """Metadata for captured packet."""
    device_type: str         # e.g., "bulb", "switch", "plug"
    firmware_version: str    # e.g., "1.2.3"
    captured_at: str         # ISO 8601 timestamp
    device_id: str           # Hex endpoint or identifier
    operation: str           # e.g., "handshake", "toggle_on", "status"
    notes: str = ""          # Additional context

# Phase 0.5 - Captured 2025-11-02 from Cync bulb (firmware 1.2.3)

HANDSHAKE_0x23_DEV_TO_CLOUD = bytes.fromhex(
    "23 00 00 00 1a 03 39 87 c8 57 00 10 31 65 30 37 "
    "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 3c"
)
HANDSHAKE_0x23_METADATA = PacketMetadata(
    device_type="bulb",
    firmware_version="1.2.3",
    captured_at="2025-11-02T10:23:45.123Z",
    device_id="39:87:c8:57",
    operation="handshake",
    notes="Initial device connection"
)

HELLO_ACK_0x28_CLOUD_TO_DEV = bytes.fromhex(
    "28 00 00 00 02 00 00"
)
HELLO_ACK_0x28_METADATA = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-02T10:23:45.145Z",
    device_id="N/A",
    operation="handshake_ack",
    notes="Cloud acknowledges handshake"
)

TOGGLE_ON_0x73_CLOUD_TO_DEV = bytes.fromhex(
    "73 00 00 00 1e 1b dc da 3e 00 13 00 7e 0d 01 00 "
    "00 f8 8e 0c 00 0e 01 00 00 00 a0 00 f7 11 02 01 "
    "01 55 7e"
)
TOGGLE_ON_0x73_METADATA = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-02T10:24:12.456Z",
    device_id="N/A",
    operation="toggle_on",
    notes="Command to turn light on"
)

DATA_ACK_0x7B_DEV_TO_CLOUD = bytes.fromhex(
    "7b 00 00 00 07 1b dc da 3e 00 13 00"
)
DATA_ACK_0x7B_METADATA = PacketMetadata(
    device_type="bulb",
    firmware_version="1.2.3",
    captured_at="2025-11-02T10:24:12.478Z",
    device_id="39:87:c8:57",
    operation="data_ack",
    notes="Device acknowledges toggle command"
)

STATUS_BROADCAST_0x83_DEV_TO_CLOUD = bytes.fromhex(
    "83 00 00 00 18 39 87 c8 57 01 7e 01 64 01 ff ff "
    "ff ff c8 32 00 01 00 00 00 00 01 55 7e"
)
STATUS_BROADCAST_0x83_METADATA = PacketMetadata(
    device_type="bulb",
    firmware_version="1.2.3",
    captured_at="2025-11-02T10:24:12.502Z",
    device_id="39:87:c8:57",
    operation="status_broadcast",
    notes="Device reports state change (now on)"
)

STATUS_ACK_0x88_CLOUD_TO_DEV = bytes.fromhex(
    "88 00 00 00 03 00 00 00"
)
STATUS_ACK_0x88_METADATA = PacketMetadata(
    device_type="cloud",
    firmware_version="N/A",
    captured_at="2025-11-02T10:24:12.515Z",
    device_id="N/A",
    operation="status_ack",
    notes="Cloud acknowledges status broadcast"
)

# Metadata registry for parameterized tests
PACKET_METADATA: Dict[str, PacketMetadata] = {
    "HANDSHAKE_0x23": HANDSHAKE_0x23_METADATA,
    "HELLO_ACK_0x28": HELLO_ACK_0x28_METADATA,
    "TOGGLE_ON_0x73": TOGGLE_ON_0x73_METADATA,
    "DATA_ACK_0x7B": DATA_ACK_0x7B_METADATA,
    "STATUS_BROADCAST_0x83": STATUS_BROADCAST_0x83_METADATA,
    "STATUS_ACK_0x88": STATUS_ACK_0x88_METADATA,
}

# Additional fixtures for edge cases...
```

### 4. Checksum Validation Results

**File**: `docs/protocol/checksum-validation.md`

**Contents**:
- **Checksum Algorithm Specification** (from `cync_controller/packet_checksum.py`):

  **Structure**: `[...][0x7E][skip 6 bytes][data to sum...][checksum byte][0x7E]`

  **Algorithm Steps**:
  1. Locate first 0x7E marker (start position)
  2. Locate last 0x7E marker (end position)
  3. Sum bytes from `packet[start+6 : end-1]`
     - Starts 6 bytes after first 0x7E
     - Ends before checksum byte (which is at position end-1)
     - Excludes both the checksum itself and trailing 0x7E
  4. Result = sum % 256

  **Visual Example**:
  ```
  Position:  0  1  2  3  4  5  6  7  8  9  10 11 12 13 14
  Bytes:    [header....][0x7E][6 skip bytes][AA][BB][CC][55][0x7E]
                         ^                   ^sum these^ ^cs ^end
                       start
  Checksum = (AA + BB + CC) % 256 = 0x55
  ```

- Validation against 10+ real captured packets
- Results table with columns:
  - Packet type (0x73, 0x83, etc.)
  - Expected checksum (extracted from packet)
  - Calculated checksum (using `calculate_checksum_between_markers()`)
  - Match? (Yes/No)
- Confirmation or correction of algorithm based on validation results
- Edge cases (if any discovered)

**If Validation Fails** (mismatches found):
- Document all mismatches with packet examples showing expected vs calculated
- Trigger Phase 1a contingency plan (see `02b-phase-1a-protocol-codec.md` Step 2)
- Reserve 2-3 days for reverse-engineering correct algorithm from captured packets
- Do NOT proceed to Phase 1a implementation until algorithm validated 100%

### 5. Protocol Validation Report

**File**: `docs/protocol/validation-report.md`

**Sections**:
1. **Validation Summary**: What matched legacy docs, what didn't
2. **Discovered Differences**: New findings vs. assumptions
3. **Edge Cases**: Malformed packets, retries, firmware variations
4. **Timing Analysis**: RTT distribution, latency percentiles
5. **Checksum Validation**: Reference to checksum-validation.md
6. **Recommendations**: Updates needed for Phase 1a implementation

### 6. Updated Protocol Documentation

**File**: `docs/protocol/packet-structure-validated.md`

- Corrected packet structure based on real captures
- Confirmed positions for endpoint, queue_id, msg_id
- Validated checksum algorithm
- Edge case handling notes

### 7. Checksum Validation Script

**File**: `scripts/validate-checksum-REFERENCE-ONLY.py`

**⚠️ CRITICAL ARCHITECTURE EXCEPTION**: This validation script is the **ONLY** exception to the "No Legacy Imports" principle (see Phase 1 spec lines 21-27). This script imports legacy code **for validation purposes only** to confirm the algorithm is correct. Phase 1a implementation MUST copy the validated algorithm, NOT import it. See Phase 1a Step 2 for correct implementation pattern.

**Purpose**: Validate the checksum algorithm using legacy code reference against real captured packets.

**Prerequisites**:
- Phase 0.5 captured packets available as test fixtures
- Access to legacy codebase (`cync-controller/`)

**Implementation Pattern**:

```python
"""Validate Cync checksum algorithm against captured packets.

This script tests the checksum algorithm from the legacy codebase
against real packet fixtures captured during Phase 0.5.

Uses legacy code as reference - Phase 1a will copy the validated algorithm.

**⚠️ CRITICAL ARCHITECTURE EXCEPTION**: This validation script is the ONLY exception to
the "No Legacy Imports" principle (Phase 1 spec lines 21-27). This script imports legacy
code for verification purposes ONLY to validate the algorithm is correct.

**FOR PHASE 1a IMPLEMENTERS**: DO NOT import legacy code in production implementation!
Phase 1a MUST copy the validated algorithm into new codebase (see Phase 1a Step 2).
Importing legacy code in Phase 1a violates architecture principles and will be rejected.
"""

# Import from legacy codebase (reference only - for validation)
from cync_controller.packet_checksum import calculate_checksum_between_markers

# Test fixtures from Phase 0.5 captures
FIXTURES = {
    "CONTROL_COMMAND_0x73": bytes.fromhex(
        "73 00 00 00 0a 01 20 03 15 29 7e 64 ff 01 55 7e"
    ),
    "STATUS_BROADCAST_0x83": bytes.fromhex(
        "83 00 00 00 18 39 87 c8 57 01 7e 01 64 01 ff ff "
        "ff ff c8 32 00 01 00 00 00 00 01 55 7e"
    ),
    # ... add 10+ real captured packets
}

def extract_checksum_from_packet(packet: bytes) -> int:
    """Extract the checksum byte from packet (second-to-last byte before 0x7E)."""
    end_marker_pos = packet.rfind(0x7E)
    if end_marker_pos < 2:
        raise ValueError("No trailing 0x7E marker found")
    return packet[end_marker_pos - 1]

def validate_fixtures():
    """Validate checksum algorithm matches legacy code against all fixtures."""
    results = []
    for packet_name, packet_bytes in FIXTURES.items():
        expected = extract_checksum_from_packet(packet_bytes)
        calculated = calculate_checksum_between_markers(packet_bytes)
        match = expected == calculated

        results.append({
            "packet": packet_name,
            "expected": expected,
            "calculated": calculated,
            "match": match
        })

        if not match:
            print(f"❌ MISMATCH: {packet_name}")
            print(f"   Expected: 0x{expected:02x}, Calculated: 0x{calculated:02x}")
        else:
            print(f"✅ MATCH: {packet_name} (0x{expected:02x})")

    # Assert all match (fail fast if algorithm is wrong)
    mismatches = [r for r in results if not r["match"]]
    assert not mismatches, f"{len(mismatches)} checksum mismatches found!"

    print(f"\n✅ All {len(results)} packets validated successfully")
    return results

if __name__ == "__main__":
    validate_fixtures()
```

**Key Requirements**:
- Test legacy `calculate_checksum_between_markers()` implementation directly
- Imports from legacy codebase for validation purposes
- Test against 10+ real captured packets from Phase 0.5
- Assert failures on mismatch (algorithm must be correct before Phase 1a copies it)
- Output results to `docs/protocol/checksum-validation.md`
- Phase 1a will copy and adapt this validated algorithm

### 8. Full Fingerprint Field Verification (Prerequisite for Phase 1b)

**File**: `docs/protocol/deduplication-strategy.md`

**Purpose**: Verify that Full Fingerprint required fields (packet_type, endpoint, msg_id, payload) are present and extractable in retry packets.

**Scope**:
- ✅ **What Phase 0.5 Verifies**: Fields EXIST and are EXTRACTABLE from packets
- ✅ **What Phase 0.5 Verifies**: Fields STABLE across retries (same values in original vs retry)
- ❌ **What Phase 0.5 Does NOT Test**: Whether strategy correctly identifies duplicates (that's Phase 1b Step 4)

**Strategy Pre-Selected**: Full Fingerprint (Option C) - already decided
**Actual Strategy Validation**: Phase 1b Step 4 (with automatic retries to test dedup effectiveness)

**Capture Methodology for Retry Analysis**:

**IMPORTANT**: Phase 0.5 runs BEFORE Phase 1b implements automatic retry logic. Therefore, retry packet capture requires **manual simulation** of retries.

**Method: Manual Retry Simulation**

1. **Setup MITM Proxy** (standard capture, no packet drop needed):
   ```bash
   # Start MITM proxy with standard logging
   python scripts/mitm-proxy.py \
       --listen-port 23779 \
       --upstream-host 35.196.85.236 \
       --upstream-port 23779 \
       --capture-file captures/retry-analysis.txt
   ```

2. **Manual Retry Trigger Process**:

   For each retry capture iteration (repeat 20 times):

   a. **Send Command #1** via Home Assistant:
      - Action: Turn on specific light (e.g., "Living Room Lamp")
      - Log: "ITERATION_01_ATTEMPT_1" in capture notes
      - Wait: 2 seconds for completion

   b. **Send Identical Command #2** (simulated retry):
      - Action: Turn on SAME light with SAME parameters
      - Log: "ITERATION_01_ATTEMPT_2" in capture notes
      - Wait: 2 seconds

   c. **Send Identical Command #3** (second simulated retry):
      - Action: Turn on SAME light with SAME parameters
      - Log: "ITERATION_01_ATTEMPT_3" in capture notes
      - Wait: 2 seconds

   d. **Toggle Off** (reset for next iteration):
      - Action: Turn off light
      - Wait: 2 seconds

   e. **Repeat** for iterations 02-20 with different light/device

3. **Packet Labeling in MITM Proxy**:

   Update `scripts/mitm-proxy.py` to support manual annotations:

   ```python
   # Add to MITM proxy
   def _log_packet(self, data: bytes, direction: str):
       log_entry = {
           "timestamp": datetime.now().isoformat(),
           "direction": direction,
           "length": len(data),
           "hex": data.hex(' '),
           "sequence": self.packet_counter,  # Auto-increment counter
           "annotation": self.current_annotation  # Set via signal/file
       }
       print(json.dumps(log_entry))
       self.packet_counter += 1
   ```

   **Annotation Methods**:
   - Option A: Signal file (`/tmp/mitm-annotation.txt`) - proxy reads on each packet
   - Option B: Keyboard input - press key to advance iteration
   - Option C: REST API - call endpoint to set annotation

4. **Correlation Method**:

   After capture, correlate packets by analyzing capture log:

   ```python
   # Example correlation logic
   for iteration in range(1, 21):
       attempt_1_packets = find_packets_with_annotation(f"ITERATION_{iteration:02d}_ATTEMPT_1")
       attempt_2_packets = find_packets_with_annotation(f"ITERATION_{iteration:02d}_ATTEMPT_2")
       attempt_3_packets = find_packets_with_annotation(f"ITERATION_{iteration:02d}_ATTEMPT_3")

       # Match by packet type and direction
       original_cmd = filter_by_type(attempt_1_packets, packet_type=0x73, direction="CLOUD→DEV")
       retry_1_cmd = filter_by_type(attempt_2_packets, packet_type=0x73, direction="CLOUD→DEV")
       retry_2_cmd = filter_by_type(attempt_3_packets, packet_type=0x73, direction="CLOUD→DEV")

       # Compare bytes
       compare_packets(original_cmd, retry_1_cmd, retry_2_cmd)
   ```

5. **Byte-by-Byte Comparison**:
   ```bash
   # Analyze captured retry packets
   python scripts/analyze-retry-packets.py captures/retry-analysis.txt \
       --output docs/protocol/deduplication-strategy.md
   ```

   Analysis script should:
   - Group packets by logical operation (original vs retry)
   - Perform byte-by-byte diff of retry vs original
   - Identify any dynamic fields (timestamps, counters, random values)
   - Document variance positions and value ranges
   - Calculate hash stability (SHA256 of full packet)

**Analysis Requirements**:

1. **Dynamic Field Detection**:
   - Examine 20+ packet captures for same logical operation
   - Compare original vs retry packets byte-by-byte
   - Document any changing fields:
     - Field position (byte offset)
     - Field purpose (timestamp, counter, random, etc.)
     - Value range observed
     - Whether field is in header or payload

2. **Full Fingerprint Validation**:
   Validate that Full Fingerprint (Option C) strategy produces correct dedup keys:

   **Selected Strategy: Full Fingerprint (Option C)**
   - Key: `f"{packet_type:02x}:{endpoint.hex()}:{msg_id.hex()}:{sha256(data).hexdigest()[:16]}"`
   - Pre-selected for maximum robustness
   - Combines multiple protocol fields for uniqueness
   - Most robust approach, handles all variance patterns

   **Validation Requirements**:
   - Verify packet_type is extractable and stable across retries
   - Verify endpoint is extractable and stable across retries
   - Verify msg_id is extractable (may or may not be stable - Full Fingerprint tolerates variance)
   - Verify payload is extractable and hashable
   - Confirm same logical retry produces same dedup_key
   - Confirm different commands produce different dedup_keys

   **Alternative Strategies (Reference Only)**:
   These strategies are NOT being used in Phase 1, but documented for future reference:
   - Option A (Raw Bytes): Simpler but fragile to any byte changes
   - Option B (msg_id + Payload): Middle ground, but has collision risk

3. **Test Cases for Phase 1b**:
   - Provide 5+ packet pairs (original + retry) as test fixtures
   - Include edge cases:
     - Retries after ACK timeout
     - Retries after packet loss
     - Reordered packets (if captured)
     - Legitimate duplicates vs retries

**Deliverable Format**:
```markdown
## Deduplication Strategy Field Verification Results

**Strategy Pre-Selected**: Full Fingerprint (Option C)
**Phase 0.5 Deliverable**: Field verification (NOT strategy validation)

**Test Setup**: 20 toggle commands with manual retry simulation

**Field Verification Results**:
- Full Fingerprint required fields confirmed extractable: [YES/NO for each field]
  - packet_type (byte 0): [PRESENT/ABSENT] [STABLE/VARIES across retries]
  - endpoint (bytes[6:10] or bytes[5:10] depending on packet type): [PRESENT/ABSENT] [STABLE/VARIES]
  - msg_id (bytes[10:13]): [PRESENT/ABSENT] [STABLE/VARIES]
  - payload: [PRESENT/ABSENT] [STABLE/VARIES]
- Fields provide sufficient diversity for deduplication: [YES/NO]

**Dynamic Field Analysis** (informative):
- Fields that vary on retry: [list with positions]
- Fields that remain stable: [list with positions]
- Full Fingerprint tolerance: [Does it handle the variance correctly?]

**Test Fixtures for Phase 1b**:
```python
# Packet pair 1: Toggle light on (original + retry)
TOGGLE_ON_ORIGINAL = bytes.fromhex("...")
TOGGLE_ON_RETRY = bytes.fromhex("...")

# Expected dedup key using Full Fingerprint:
# Format: "{packet_type:02x}:{endpoint.hex()}:{msg_id.hex()}:{payload_hash[:16]}"
EXPECTED_DEDUP_KEY_ORIGINAL = "73:3987c857:0a141e:a3f2b9c4d8e1f6a2"
EXPECTED_DEDUP_KEY_RETRY = "73:3987c857:0a141e:a3f2b9c4d8e1f6a2"  # Should match!
```

**Field Verification Conclusion for Phase 1b**:
- Required fields extractable: [YES/NO]
- Fields stable across retries: [YES/NO]
- Test fixtures ready for Phase 1b: [YES/NO]
```

**Phase 1b Strategy Validation Note**:

Phase 0.5 uses **manual retry simulation** to verify fields exist (field verification only). This is **NOT strategy validation** - it only confirms that required fields are present and extractable.

**Phase 1b Step 4 Strategy Validation** (actual testing of dedup effectiveness):
Phase 1b Step 4 performs the **actual strategy validation** using real automatic retries to confirm:

1. **Full Fingerprint strategy correctly identifies duplicate packets** (zero false positives/negatives)
2. **Automatic retries produce same dedup_keys** as manual retries
3. **No unexpected edge cases** with automatic retry behavior

**Phase 1b Step 4 Strategy Validation Method**:
- Implement Full Fingerprint dedup_key generation in `_make_dedup_key()`
- Run Phase 1d simulator with packet drop (20%) to trigger automatic retries
- Verify strategy correctly identifies duplicate packets with zero false positives/negatives
- Document: "Full Fingerprint strategy validated - correctly identifies all duplicates"

**Terminology Clarity**:
- **Phase 0.5 Field Verification**: Confirms required fields exist and are extractable (prerequisite)
- **Phase 1b Step 4 Strategy Validation**: Tests dedup effectiveness with real retries (actual validation)

**Acceptance Criteria for Phase 1b Step 4**:
- [ ] Full Fingerprint strategy implemented in `_make_dedup_key()`
- [ ] Strategy validated with automatic retries (zero false positives/negatives)
- [ ] Test fixtures from Phase 0.5 field verification used in unit tests
- [ ] Dedup cache correctly identifies all duplicate packets in chaos tests

### 9. Device Backpressure Behavior Testing

**File**: `docs/protocol/backpressure-behavior.md`

**Purpose**: Validate how Cync devices react when receiver applies backpressure (TCP buffer fills, slow ACKs).

**Test Scenarios**:

1. **Slow Consumer Test**
   - Setup: MITM proxy with intentional receive delay (1 msg/sec)
   - Trigger: Device sends rapid updates (button press spam, ~5-10 msgs/sec)
   - Observe: Does device buffer? Drop packets? Disconnect? Retry?
   - Record: Device behavior, timeout values, internal buffering capacity

2. **TCP Buffer Fill Test**
   - Setup: Stop reading from TCP socket (let OS buffer fill to ~64KB)
   - Trigger: Device sends normal traffic
   - Observe: Does device detect full buffer? How long until timeout/disconnect?
   - Record: Device timeout behavior, reconnection attempts

3. **Selective ACK Delay Test**
   - Setup: MITM proxy delays ACKs by 2-5 seconds (but still reads packets)
   - Trigger: Device sends commands expecting ACKs
   - Observe: Does device retry? Timeout? Continue sending?
   - Record: Retry behavior, timeout thresholds

**Documentation Requirements**:
- Observed behavior for each scenario (with packet captures if possible)
- Timeout values (if device disconnects)
- Whether device has internal buffering/retry logic
- **Recommendation for Phase 1c recv_queue size** (50? 100? 200?)
- **Recommendation for Phase 1c recv_queue policy** (BLOCK vs DROP_OLDEST)

**Success Criteria**:
- [ ] Device behavior documented for all 3 scenarios
- [ ] Specific recommendation made for recv_queue policy
- [ ] Specific recommendation made for recv_queue size
- [ ] Edge cases documented (disconnects, retries, etc.)

### 10. Helper Scripts

**File**: `scripts/parse-capture.py`

```python
"""Parse captured packet logs and generate test fixtures."""

import re
import sys

def parse_log_line(line: str) -> dict:
    """Extract packet hex from capture log."""
    # Implementation to extract hex, direction, type, timestamp
    pass

def generate_fixture(packets: list) -> str:
    """Generate Python test fixture from captured packets."""
    pass

if __name__ == "__main__":
    # Read from stdin or file
    # Parse packets
    # Generate fixtures
    pass
```

### 11. Group Operation Performance Validation

**Note**: This validation is performed in Phase 1d instead of Phase 0.5 (full stack validation preferred).

**Purpose**: Validate `asyncio.gather()` approach for bulk operations (group commands to multiple devices) and confirm Phase 1c "no send_queue" decision.

**Test Scenarios**:

1. **10-Device Parallel Toggle**:
   - Setup: 10 simulated devices (or real devices if available)
   - Action: Send toggle commands to all 10 devices simultaneously using `asyncio.gather()`
   - Measure: p50, p95, p99 latency for entire group operation
   - Expected: p99 < 2s (Phase 1c re-evaluation trigger threshold)

2. **State Lock Hold Time Measurement**:
   - Instrument Phase 0 toggler with timing around critical sections
   - Measure time spent holding any locks during send operations
   - Document: Lock hold time distribution
   - Validate: Assumption of "60ms serial lock" from Phase 1c spec

3. **Concurrent Device Stress Test**:
   - Setup: Send commands to 20+ devices rapidly (stress test)
   - Measure: Success rate, timeout rate, retry rate
   - Goal: Confirm `asyncio.gather()` scales adequately

**Deliverables**:
- Performance report: `docs/protocol/group-operation-performance.md`
- Results table with p50/p95/p99 for 10-device operations
- State lock hold time measurements
- Recommendation for Phase 1c (proceed with no send_queue vs add send_queue)

**Decision Criteria**:
- If Phase 1d group validation shows p99 < 2s: "No send_queue" decision validated
- If Phase 1d group validation shows p99 > 2s: Document findings, proceed without send_queue (optimization deferred to Phase 2)

---

## Acceptance Criteria

**Organization**: Criteria grouped into 4 tiers by importance and blocking status

**Deliverable Priority Tiers**:
- **Tier 1 (Required - BLOCKS Phase 1a)**: Core protocol validation deliverables (1, 2, 4, 5, 6, 7)
  - MITM proxy, captures, checksum validation, documentation
  - **Phase 1a cannot start without these**
  - **Completion Criterion**: All Tier 1 deliverables complete

- **Tier 2 (Important but not blocking)**: Supporting deliverables (3, 8)
  - Test fixtures (can be generated during Phase 1a if needed)
  - Dedup field verification (Phase 1b can proceed without, just needs more unit tests)
  - **If incomplete**: Document gaps and proceed to Phase 1a

- **Tier 3 (Optional enhancements)**: Enhanced validation (9)
  - Device backpressure behavior (Phase 1c can use conservative defaults)
  - **If incomplete**: Use conservative defaults, no blocker

- **Tier 4 (Deferred to later phase)**: Group operation performance (11)
  - Moved to Phase 1d (not Phase 0.5)
  - **Not part of Phase 0.5 completion**

**Phase 0.5 Completion Criterion**: Tier 1 deliverables complete. Tier 2-3 completed on best-effort basis - do not block Phase 1a start. If Tier 2-3 incomplete, document gaps and proceed with known limitations.

---

### Tier 1: Core Requirements (Blocking Phase 1a)

These criteria are essential for Phase 0.5 completion and block Phase 1a:

**Checksum Validation (Required for Phase 1a)**:
- [ ] Checksum algorithm validated against legacy test fixtures
- [ ] Checksum re-validated against 10+ real captured packets
- [ ] `docs/protocol/checksum-validation.md` created with validation results

**ACK Structure Validation (Required for Phase 1b)**:
- [ ] All 4 ACK types captured with 10+ samples each (0x28, 0x7B, 0x88, 0xD8)
- [ ] msg_id presence/absence documented with High confidence
- [ ] If ACK validation is ambiguous (multiple positions found, or inconsistent across samples), capture 10+ additional samples from different firmware versions before declaring Path C
- [ ] Phase 1b implementation path selected (parallel vs FIFO, or Path C escalation if ambiguous)

**Queue ID Derivation (Required for Phase 1a)**:
- [ ] Queue ID ↔ Endpoint derivation algorithm validated and documented
- [ ] 5+ handshake→data sequences captured for validation

**Protocol Capture Document (Required)**:
- [ ] Protocol Capture Document complete (`docs/protocol/02-phase-0.5-captures.md`)
- [ ] Updated protocol documentation complete (`docs/protocol/packet-structure-validated.md`)

---

### Tier 2: Quality Criteria

These 15 criteria are important for quality and completeness:

**Functional Captures**:
- [ ] Captured at least 3 complete toggle sequences (on/off/on)
- [ ] Captured handshake flow from 2+ different devices
- [ ] Captured status broadcast (passive state change)
- [ ] Captured heartbeat sequence
- [ ] Captured device info broadcast
- [ ] All hex dumps are complete (no truncation)
- [ ] Timing data recorded (RTT, inter-packet delays)

**ACK Latency Measurement** (for Phase 1b timeout tuning):
- [ ] Measured ACK latency for all 4 ACK types (0x28, 0x7B, 0x88, 0xD8)
- [ ] Sample size ≥100 per ACK type
- [ ] Calculated percentiles: p50, p95, p99, max
- [ ] Recommended timeout values provided (using formula: p99 × 2.5)

**Deduplication Strategy Validation** (validates Full Fingerprint for Phase 1b):
- [ ] Captured 20+ retry packet pairs (manual retry simulation)
- [ ] Full Fingerprint fields validated as extractable and stable
- [ ] Full Fingerprint produces same dedup_key for retry packets (validated)
- [ ] Test fixtures provided for Phase 1b dedup tests (5+ packet pairs)

---

### Tier 3: Additional Quality Criteria

These 10 criteria enhance quality and completeness:

**Documentation Polish**:
- [ ] Edge cases documented (if any discovered)
- [ ] Multiple device types/firmware versions captured (if available)
- [ ] Validation report includes device firmware correlation
- [ ] Protocol differences from legacy docs clearly highlighted

**Validation Depth**:
- [ ] At least 10 unique packets captured per flow type
- [ ] msg_id extraction positions confirmed for data packets (0x73, 0x83)
- [ ] Endpoint extraction confirmed
- [ ] 0x7e framing confirmed for data payloads

**Additional Deliverables**:
- [ ] Deliverable #9: Device backpressure behavior tested
- [ ] Deliverable #11: Group operation performance (Note: Validated in Phase 1d instead)

---

## Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Packet capture method not working | High | Low | Have multiple capture options ready (tcpdump, proxy, reference logs) |
| Packet structure differs from docs | Medium | Medium | Document actual structure; update Phase 1a plans |
| Limited device variety | Low | Medium | Capture what's available; note firmware versions |
| Checksum algorithm incorrect | Medium | Low | Validate against multiple real packets with checksum validation script |
| Missing edge cases | Medium | High | Extended capture period; trigger error conditions |

---

## Implementation Steps (Sequential Order)

**Step 0: DNS Prerequisite Validation**
- Test DNS override capability (`/etc/hosts` or router configuration)
- Verify `cm.gelighting.com` resolves to `127.0.0.1`
- Check for DNS blockers (DNSSEC, DoH, VPN)
- If DNS works → proceed; if blocked → Phase 0.5 cannot continue

**Step 1: MITM Proxy Implementation**
- Implement `scripts/mitm-proxy.py` (~200 lines)
- SSL/TLS connection handling
- Bidirectional forwarding with logging
- Structured JSON output to stdout
- Raw capture storage to `captures/` directory
- Test with real device

**Step 2: Checksum Validation Preparation**
- Implement `scripts/validate-checksum-REFERENCE-ONLY.py` skeleton
- Import legacy checksum algorithm: `from cync_controller.packet_checksum import calculate_checksum_between_markers`
- Create test harness structure for validation

**Step 3: Initial Packet Capture + Checksum Algorithm Validation**

**Packet Capture**:
- Capture basic flows (handshake, toggle)
- Handshake flows (0x23 → 0x28)
- Toggle flows (0x73, 0x7B, 0x83, 0x88)
- Initial hex dump review

**Checksum Algorithm Validation**:
- Run checksum validation script against legacy test fixtures
- Validate algorithm against known-good packets from legacy codebase test suite
- Create `docs/protocol/checksum-validation.md` (preliminary)
- Document algorithm specification and validation methodology
- Output: Algorithm validated and documented, ready for Phase 1a to copy

**Step 4: Additional Flow Capture + Checksum Re-validation**

**Packet Capture**:
- Capture status broadcasts, heartbeats, device info
- Edge case triggers (disconnects, errors)
- **ACK Latency Measurement**: Send 100+ commands per ACK type, record timestamps
  - **Sample size rationale**: n=100 provides stable p99 estimate (±10% margin at 95% confidence)
    - Smaller samples (n=20-50): High p99 variance (±30% margin) - insufficient for timeout tuning
    - Larger samples (n=200+): Minimal accuracy improvement (<5%) for 2× effort - diminishing returns
    - n=100 is sweet spot: Stable p99 with reasonable capture time
  - Measure time between request sent and ACK received
  - Calculate latency distribution (p50, p95, p99, max)
  - Test all 4 ACK types: 0x28 (handshake), 0x7B (data), 0x88 (status), 0xD8 (heartbeat)
- Capture 10+ complete packet sequences for validation

**Checksum Re-validation Against Real Packets**:
- Re-run checksum validation script against 10+ newly captured packets
- Update `docs/protocol/checksum-validation.md` with real-world validation results
- Table columns: packet type, expected checksum, calculated checksum, match status
- Document any algorithm discrepancies or edge cases found in real packets
- **Confirmation**: Algorithm works correctly with real device traffic

**Step 5: Documentation and Test Fixtures**
- Annotate hex dumps with checksum calculation details
- Generate test fixtures with validated checksums (`tests/fixtures/real_packets.py`)
- Write validation report (`docs/protocol/validation-report.md`)
- Update protocol documentation (`docs/protocol/packet-structure-validated.md`)
- Document chosen capture method and rationale

**Step 6: Review and Phase 1a Handoff**
- Review captures and validation results
- Final validation against legacy code
- Verify all acceptance criteria met
- Prepare materials for Phase 1a:
  - ✓ Protocol Capture Document (Deliverable #2)
  - ✓ Checksum Validation Results (Deliverable #4)
  - ✓ Updated Protocol Documentation (Deliverable #6)
  - ✓ Deduplication Field Verification (Deliverable #8)
- Phase 1a starts after this completes

---

## Success Metrics

- ✅ **Complete**: 5/5 key flows captured with annotations
- ✅ **Accurate**: Protocol structure validated or corrected
- ✅ **Usable**: Test fixtures ready for Phase 1a
- ✅ **Documented**: Clear handoff materials for implementation

---

## Next Phase

**Phase 1a**: Cync Protocol Codec (1 week)
- Implement encoder/decoder based on Phase 0.5 captures
- Use test fixtures for unit testing
- Validate against real devices

---

## Related Documentation

- **Phase 0**: `01-phase-0.md` - Test harness foundation
- **Phase 1a**: `02b-phase-1a-protocol-codec.md` - Protocol implementation
- **Discovery**: `00-discovery.md` - Original protocol notes
- **Legacy Packet Parser**: `cync-controller/src/cync_controller/packet_parser.py`
- **Legacy Protocol Docs**: `docs/protocol/packet_structure.md`

---

## Notes

**Important**: This phase is critical for de-risking Phase 1a. Don't skip the capture step - real-world validation prevents costly rework later.

**Tip**: Capture more than you think you need. Storage is cheap, re-capturing is expensive.

**Warning**: Redact any auth codes or sensitive data in public documentation.

