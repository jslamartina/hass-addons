# MITM Proxy for Cync Protocol

This directory contains the MITM (Man-in-the-Middle) proxy tool and captured packet data for Phase 0.5 protocol validation.

## Contents

- **`mitm-proxy.py`** - MITM proxy script for intercepting and logging Cync device traffic
- **`analyze-captures.py`** - Script to analyze captured packets and generate statistics
- **`validate-checksum-REFERENCE-ONLY.py`** - Checksum validation script (imports legacy code for validation only)
- **`captures/`** - Directory containing captured packet logs
- **`results/`** - Directory containing analysis results and test output

## Usage

### Start MITM Proxy

#### Mode 1: Cloud Intercept (Protocol Research)

Forward to real Cync cloud for protocol validation:

```bash
## Forward to real Cync cloud
python mitm/mitm-proxy.py --listen-port 23779 --upstream-host 35.196.85.236 --upstream-port 23779

## With packet injection API
python mitm/mitm-proxy.py --listen-port 23779 --upstream-host 35.196.85.236 --api-port 8080
```

**Use case**: Phase 0.5 protocol validation, capturing device behavior with real cloud.

#### Mode 2: Local Intercept (Live Command Capture) 🆕

Forward to local cync-controller for capturing live HA commands:

```bash
## Forward to cync-controller running at 192.168.50.32
python mitm/mitm-proxy.py --listen-port 23779 --upstream-host homeassistant.local --upstream-port 23779 --api-port 8080
```

**Network flow**:

```text
Devices → DNS (cm.gelighting.com → devcontainer)
        → MITM (devcontainer:23779, TLS)
        → cync-controller (HA:23779, SSL)
        → Captures bidirectional traffic
```

**Use case**: Capture commands issued from live Home Assistant UI to see exact command sequences and device responses.

**Benefits**:

- See what the production controller sends for any action
- Capture bidirectional flow (HA→device AND device→HA)
- Debug command sequences in real-time
- Validate protocol implementation against live system

**Setup requirements**:

1. DNS already pointing `cm.gelighting.com` to devcontainer IP
2. Devices connected to MITM (will auto-reconnect through DNS)
3. Use actual HA IP address (not hostname if DNS unavailable in devcontainer)

#### Mode 3: Localhost Testing

Forward to localhost cloud relay simulator:

```bash
python mitm/mitm-proxy.py --listen-port 23779 --upstream-host localhost --upstream-port 23780 --no-ssl
```

**Use case**: Testing with local simulators.

### Analyze Captures

```bash
## Analyze captured JSONL packets
python mitm/analyze-captures.py
```

Generates statistics and flow status for Phase 0.5 deliverables.

### Validate Checksum Algorithm

```bash
## Validate checksum algorithm against test fixtures and real packets
python mitm/validate-checksum-REFERENCE-ONLY.py
```

**Note**: This script imports legacy code for validation purposes only. Phase 1a must copy the validated algorithm, not import it.

### Prerequisites

**General**:

- Port 23779 available in devcontainer
- TLS termination configured (devices use SSL with self-signed cert)
- SSL certificates in `certs/cert.pem` and `certs/key.pem`

**DNS Configuration**:

- **Cloud mode**: `cm.gelighting.com → 127.0.0.1` (localhost)
- **Local intercept mode**: `cm.gelighting.com → <devcontainer IP>` (already configured if using)

## Directory Structure

### `captures/`

Packet captures stored with timestamped filenames:

- Format: `capture_YYYYMMDD_HHMMSS.txt`
- Contains: Bidirectional packet flows with timestamps, direction, and hex dumps
- Structured JSON logging to stdout

### `results/`

Analysis results and test output:

- `test-3-latency.json` - ACK latency measurements for timeout tuning

## Documentation

**Quick Start Guides**:

- **Local intercept mode**: `docs/living/mitm-local-intercept.md` - Capture live HA commands 🆕
- **Phase 0.5 validation**: `docs/02a-phase-0.5-protocol-validation.md` - Cloud mode protocol research

**Detailed Documentation**:

- Full MITM proxy specification
- Packet capture methodology
- Protocol validation results
- Usage examples
