# Development Scripts

Common development tasks for the TCP communication rebuild project.

## Available Scripts

### Setup

- **`setup.sh`** - Set up the development environment (install Poetry and dependencies)

### Development

- **`run.sh`** - Run the toggler with configurable options
- **`debug.sh`** - Run the toggler with debug logging enabled

### Testing

- **`test-all.sh`** - Run all tests (unit + integration)
  - `test-all.sh -v` or `--verbose` - Verbose output
  - `test-all.sh -c` or `--coverage` - Generate coverage report
  - `test-all.sh -w` or `--watch` - Watch mode (requires pytest-watch)
- **`test-unit.sh`** - Run only unit tests (fast, with mocks)
  - `test-unit.sh -v` or `--verbose` - Verbose output
  - `test-unit.sh -c` or `--coverage` - Generate coverage report
- **`test-integration.sh`** - Run only integration tests (real TCP server)
  - `test-integration.sh -v` or `--verbose` - Verbose output
  - `test-integration.sh --html` - Generate HTML report

### Code Quality

- **`lint.sh`** - Run linting (ruff) and type checking (mypy)
- **`format.sh`** - Auto-format code with ruff

### Build & Deploy

- **`build.sh`** - Build and validate the entire project
- **`clean.sh`** - Remove build artifacts and caches

### Utilities

- **`check-metrics.sh`** - Check if metrics endpoint is accessible and view current metrics

## Usage Examples

### Quick Start

```bash
# Setup environment (first time only)
./scripts/setup.sh

# Run tests
./scripts/test-all.sh

# Run linting
./scripts/lint.sh

# Run the toggler (uses defaults or environment variables)
./scripts/run.sh
```

### Running the Toggler

```bash
# With defaults (DEVICE123 @ 192.168.1.100:9000)
./scripts/run.sh

# Custom device
./scripts/run.sh --device-id DEVICE456 --host 192.168.1.200 --port 9001

# Toggle off
./scripts/run.sh --state off

# Debug logging
./scripts/run.sh --debug

# Environment variables
DEVICE_ID=MYDEVICE DEVICE_HOST=10.0.0.5 ./scripts/run.sh
```

### Testing

```bash
# Run all tests (unit + integration)
./scripts/test-all.sh

# Run only unit tests (fast, ~1-2 seconds)
./scripts/test-unit.sh

# Run only integration tests (slower, ~8-10 seconds)
./scripts/test-integration.sh

# Verbose output
./scripts/test-all.sh -v
./scripts/test-unit.sh -v
./scripts/test-integration.sh -v

# With coverage (unit tests only)
./scripts/test-unit.sh -c
open htmlcov/index.html # View coverage report

# Integration tests with HTML report
./scripts/test-integration.sh --html
open test-reports/integration-report.html
```

### Code Quality

```bash
# Check code
./scripts/lint.sh

# Format code
./scripts/format.sh
```

### Building

```bash
# Full build with validation
./scripts/build.sh

# Clean artifacts
./scripts/clean.sh
```

### Debugging

```bash
# Run with debug logging
./scripts/debug.sh

# Check metrics while running
./scripts/check-metrics.sh
```

## Environment Variables

Scripts respect the following environment variables:

- `DEVICE_ID` - Device identifier (default: DEVICE123)
- `DEVICE_HOST` - Device IP/hostname (default: 192.168.1.100)
- `DEVICE_PORT` - Device port (default: 9000)
- `LOG_LEVEL` - Logging level (default: INFO)
- `STATE` - Desired state (default: on)
- `METRICS_PORT` - Metrics server port (default: 9400)

## Making Scripts Executable

```bash
chmod +x scripts/*.sh
```

## CI/CD Integration

These scripts are designed to work in CI environments:

```yaml
- name: Setup
  run: ./scripts/setup.sh

- name: Lint
  run: ./scripts/lint.sh

- name: Test
  run: ./scripts/test-all.sh --coverage

- name: Build
  run: ./scripts/build.sh
```
