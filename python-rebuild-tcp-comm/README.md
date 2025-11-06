# TCP Communication Rebuild

Lean harness and reliable TCP transport layer for Cync device communication.

## Phase 0: Toggle + Log Harness

This phase implements a minimal toggler with:

- JSON structured logging
- Prometheus metrics
- Single-device toggle with retry
- Per-packet correlation via msg_id

## Quick Start

```bash
# Install dependencies
poetry install

# Run toggler against a device
python -m rebuild_tcp_comm.harness.toggler \
  --device-id=DEVICE123 \
  --device-host=192.0.2.10 \
  --device-port=9000 \
  --log-level=DEBUG

# Or use helper script
./scripts/run.sh --device-id DEVICE123 --host 192.0.2.10 --port 9000 --debug

# View metrics
curl http://localhost:9400/metrics
# Or use helper
./scripts/check-metrics.sh
```

## VS Code Setup

If you see import errors in VS Code (like "Import 'prometheus_client' could not be resolved"):

1. **Select Python Interpreter**:
   - Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
   - Type "Python: Select Interpreter"
   - Choose: `./.venv/bin/python` (local virtualenv)

2. **Reload Window**:
   - Press `Ctrl+Shift+P`
   - Type "Developer: Reload Window"

See `VSCODE_SETUP.md` for detailed troubleshooting.

## Testing

```bash
# Run tests
pytest -q tests/test_toggler.py -k "toggle" --maxfail=1

# Lint
ruff check .
mypy src tests
```

## Documentation

See `docs/rebuild-tcp-comm/` for detailed design, migration plan, and runbooks.
