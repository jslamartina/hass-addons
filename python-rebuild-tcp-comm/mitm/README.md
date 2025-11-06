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

```bash
# Forward to real Cync cloud
python mitm/mitm-proxy.py --listen-port 23779 --upstream-host 35.196.85.236 --upstream-port 23779

# Forward to localhost cloud relay (testing)
python mitm/mitm-proxy.py --listen-port 23779 --upstream-host localhost --upstream-port 23780 --no-ssl

# With packet injection API
python mitm/mitm-proxy.py --listen-port 23779 --upstream-host 35.196.85.236 --api-port 8080
```

### Analyze Captures

```bash
# Analyze captured JSONL packets
python mitm/analyze-captures.py
```

Generates statistics and flow status for Phase 0.5 deliverables.

### Validate Checksum Algorithm

```bash
# Validate checksum algorithm against test fixtures and real packets
python mitm/validate-checksum-REFERENCE-ONLY.py
```

**Note**: This script imports legacy code for validation purposes only. Phase 1a must copy the validated algorithm, not import it.

### Prerequisites

- DNS redirection: `cm.gelighting.com → 127.0.0.1`
- Port 23779 available
- TLS termination configured (devices use SSL with self-signed cert)

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

See `docs/02a-phase-0.5-protocol-validation.md` for:
- Full MITM proxy specification
- Packet capture methodology
- Protocol validation results
- Usage examples

