# MITM Tools

The MITM proxy is available as a CLI command. Other tools are run as Python scripts.

## CLI Command

### `cync-mitm`

Start the MITM proxy server for packet capture and injection (registered as CLI command).

```bash
## Local intercept mode (capture HA commands)
cync-mitm \
  --listen-port 23779 \
  --upstream-host homeassistant.local \
  --upstream-port 23779 \
  --api-port 8080

## Cloud intercept mode (protocol research)
cync-mitm \
  --listen-port 23779 \
  --upstream-host 35.196.85.236 \
  --upstream-port 23779 \
  --api-port 8080
```

**Options**:

- `--listen-port` - Port for device connections (default: 23779)
- `--upstream-host` - Upstream host to forward to
- `--upstream-port` - Upstream port (default: 23779)
- `--api-port` - REST API port for packet injection (default: 8765)
- `--no-ssl` - Disable SSL for upstream (for localhost testing)
- `--backpressure-mode` - Test mode: normal, slow_consumer, buffer_fill, ack_delay

## Python Scripts

The following tools are run as Python scripts directly:

### `parse_capture.py`

Parse and analyze MITM capture files.

```bash
## Show all packet types
python mitm/parse_capture.py mitm/captures/capture_*.txt

## Filter by packet type
python mitm/parse_capture.py --filter 0x73 mitm/captures/capture_*.txt

## Show statistics
python mitm/parse_capture.py --stats mitm/captures/capture_*.txt

## Extract ACK pairs
python mitm/parse_capture.py --ack-pairs mitm/captures/capture_*.txt
```

### `test_toggle_injection.py`

Test packet injection via MITM REST API.

```bash
## Toggle test
python mitm/test_toggle_injection.py \
  --endpoint "45 88 0f 3a" \
  --device-id 80 \
  --iterations 10 \
  --api-url http://localhost:8080/inject

## Mesh info test
python mitm/test_toggle_injection.py \
  --test mesh-info \
  --endpoint "45 88 0f 3a" \
  --api-url http://localhost:8080/inject
```

### `analyze_captures.py`

Generate statistics from captured packets.

```bash
python mitm/analyze_captures.py mitm/captures/capture_*.txt
```

## Installation

The `cync-mitm` CLI command is automatically registered when you install the package:

```bash
poetry install
```

This creates an executable wrapper in `.venv/bin/cync-mitm` that is available when the virtualenv is activated.

Other tools are run as Python scripts directly (e.g., `python mitm/parse_capture.py`).

## Development

To modify the tools, edit the Python modules in `mitm/`:

- `mitm_proxy.py` - MITM proxy server (CLI: `cync-mitm`)
- `parse_capture.py` - Capture parser (script)
- `test_toggle_injection.py` - Injection tester (script)
- `analyze_captures.py` - Statistics generator (script)

After making changes, the code is immediately available (editable install).
