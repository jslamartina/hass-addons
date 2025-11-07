# MITM Local Intercept Mode

**Status**: ✅ Operational (2025-11-07)

## Overview

The MITM proxy can intercept traffic between Cync devices and a **live cync-controller** instance (instead of the cloud). This enables capturing bidirectional packet flows when issuing commands from the production Home Assistant UI.

## Architecture

### Network Flow

**Diagram**: /workspaces/hass-addons/python-rebuild-tcp-comm/docs/living/mitm-local-intercept-architecture.mermaid
TODO: Update with mermaid link when it's back up

**Flow Details**:

1. Devices resolve `cm.gelighting.com` → devcontainer IP (via DNS redirect)
2. Devices establish TLS connection to MITM proxy on port 23779
3. MITM establishes upstream SSL connection to cync-controller
4. Commands from HA UI flow: HA → MITM → Devices
5. Responses flow back: Devices → MITM → HA
6. All packets logged to capture files in real-time

**Architecture Components**:

- **Cync Devices** (192.168.x.x): Bulbs, switches, plugs with TLS connections
- **DNS**: Redirects `cm.gelighting.com` to devcontainer IP
- **MITM Proxy** (devcontainer:23779): TLS termination, packet capture, SSL upstream
- **cync-controller** (HA:23779): Production controller receiving commands from HA UI
- **Captures**: Real-time packet logs saved to `mitm/captures/`

### Key Differences vs Cloud Mode

| Aspect        | Cloud Mode                    | Local Intercept Mode              |
| ------------- | ----------------------------- | --------------------------------- |
| Upstream      | 35.196.85.236:23779           | HA IP:23779 (e.g., 192.168.50.32) |
| Commands      | Cloud-initiated only          | HA UI commands captured           |
| Bidirectional | Yes (device ↔ cloud)         | Yes (device ↔ HA)                |
| Use Case      | Protocol research             | Live command debugging            |
| DNS           | cm.gelighting.com → localhost | cm.gelighting.com → devcontainer  |

## Setup

### Prerequisites

1. **DNS Configuration**: `cm.gelighting.com` already redirected to devcontainer IP
2. **SSL Certificates**: Present in `python-rebuild-tcp-comm/certs/`
   - `cert.pem` - Server certificate
   - `key.pem` - Private key

3. **Network Access**: Devcontainer can reach HA IP
4. **Port Available**: 23779 not in use in devcontainer

### Start MITM

```bash
cd /workspaces/hass-addons/python-rebuild-tcp-comm

## Replace 192.168.50.32 with your Home Assistant IP
python mitm/mitm-proxy.py \
  --listen-port 23779 \
  --upstream-host 192.168.50.32 \
  --upstream-port 23779 \
  --api-port 8080
```

**Important**: Use IP address (not `homeassistant.local`) if hostname doesn't resolve in devcontainer.

### Verify Operation

```bash
## Check MITM is listening
ss -tlnp | grep 23779

## Check MITM process
ps aux | grep mitm

## Monitor capture file (tail -f newest capture)
tail -f mitm/captures/capture_*.txt
```

### Issue Commands

1. Open Home Assistant UI
2. Navigate to Cync device entity
3. Issue commands:
   - Toggle on/off
   - Change brightness
   - Change color
   - Any supported action

4. Observe capture file for bidirectional packets

## Captured Traffic

### Packet Direction Indicators

- **DEV→CLOUD**: Device sending to HA (through MITM)
- **CLOUD→DEV**: HA sending to device (through MITM)

### Example Capture

```text
2025-11-07T15:21:45.123456 CLOUD→DEV [T3] [conn:281473669198144] (48 bytes)
7e 73 00 00 00 2a ... [HA command to device]

2025-11-07T15:21:45.234567 DEV→CLOUD [T3] [conn:281473669198144] (36 bytes)
7e 7b 00 00 00 1e ... [Device ACK response]
```

### Traffic Types

**Keepalives** (5 bytes):

- `d3 00 00 00 00` - Device heartbeat
- `d8 00 00 00 00` - HA response

**Commands** (variable, typically 15-256 bytes):

- Toggle: ~48 bytes
- Brightness: ~72-144 bytes
- Color: ~112-256 bytes

**Responses** (typically 12-36 bytes):

- Pure ACK: 12 bytes (command rejected/invalid)
- Compound ACK: 36 bytes (command accepted with state)

## Use Cases

### 1. Protocol Validation

Compare captured commands from live controller with documented protocol:

- Verify command structure
- Validate checksums
- Confirm sequence numbers
- Check endpoint targeting

### 2. Command Discovery

Capture unknown or undocumented commands:

- New device types
- Firmware-specific features
- Advanced color modes
- Scene/effect commands

### 3. Debugging

Debug issues with specific commands:

- Why isn't this working?
- What's the actual packet sent?
- How does device respond?
- Timing and retry behavior

### 4. Implementation Reference

Use as ground truth for rebuilding transport:

- See exact command format
- Understand ACK patterns
- Observe retry behavior
- Study error handling

## Troubleshooting

### No Traffic Captured

**Symptom**: Capture file not growing, no packets logged

**Causes**:

1. Devices still connected directly to HA (not through MITM)
   - **Fix**: Power cycle devices to force reconnect

2. MITM pointing to wrong upstream
   - **Fix**: Verify `--upstream-host` is HA IP

3. DNS not redirecting to devcontainer
   - **Fix**: Check DNS configuration

### Commands Not Appearing

**Symptom**: Keepalives captured but no command packets

**Causes**:

1. MITM can't reach upstream (HA)
   - **Fix**: Verify HA IP reachable from devcontainer

2. Initial MITM was pointing to cloud (35.196.85.236)
   - **Fix**: Restart MITM with correct `--upstream-host`

### Connection Errors

**Symptom**: Devices disconnect, MITM shows errors

**Causes**:

1. SSL certificate issues
   - **Fix**: Verify `certs/cert.pem` and `certs/key.pem` exist

2. Upstream connection refused
   - **Fix**: Verify cync-controller running on HA

## Rollback

To restore direct device→HA connections:

```bash
## 1. Stop MITM
pkill -f mitm-proxy

## 2. Revert DNS to point directly to HA
## (Update DNS server configuration)

## 3. Power cycle devices
## Unplug → wait 10s → plug back in
```

## Performance Notes

- **Latency**: Adds ~1-5ms per hop (negligible for normal use)
- **Throughput**: No noticeable impact on command execution
- **Reliability**: Transparent proxy, devices/HA unaware of interception
- **Capture Size**: ~1MB per hour of moderate use

## Security Notes

- MITM uses self-signed cert (devices don't validate)
- Captures contain device IDs and network info (not sensitive)
- No user credentials captured
- Local network only (not exposed to internet)

## Example Session

```bash
## Start MITM
python mitm/mitm-proxy.py --listen-port 23779 --upstream-host homeassistant.local --upstream-port 23779

## In HA UI: Toggle light on
## Capture shows:
## [CLOUD→DEV] 48 bytes (toggle command)
## [DEV→CLOUD] 36 bytes (compound ACK)

## In HA UI: Set brightness 75%
## Capture shows:
## [CLOUD→DEV] 72 bytes (brightness command)
## [DEV→CLOUD] 36 bytes (compound ACK)

## Stop MITM (Ctrl+C)
## Capture saved to: mitm/captures/capture_20251107_152100.txt
```

## Related Documentation

- MITM Proxy README: `mitm/README.md`
- Phase 0.5 Protocol Validation: `docs/02a-phase-0.5-protocol-validation.md`
- DNS Requirements: `hass-addons/.cursor/rules/dns-requirements.mdc`
