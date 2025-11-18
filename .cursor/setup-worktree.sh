#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'  # No Color

# Logging functions
log_info() {
  echo -e "${GREEN}[setup-worktree]${NC} $1"
}

log_warn() {
  echo -e "${YELLOW}[setup-worktree]${NC} $1"
}

log_error() {
  echo -e "${RED}[setup-worktree]${NC} $1" >&2
}

log_success() {
  echo -e "${GREEN}[setup-worktree] ✅${NC} $1"
}

log_section() {
  echo ""
  echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
  echo -e "${BLUE}  $1${NC}"
  echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
  echo ""
}

trap 'cleanup' EXIT
trap 'on_error $LINENO' ERR

cleanup() {
  trap - EXIT ERR
}

on_error() {
  log_error "Error on line $1"
  exit 1
}

VENV_DIR="$REPO_ROOT/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

ensure_python_binary() {
  if ! command -v "$PYTHON_BIN" > /dev/null 2>&1; then
    log_error "Python executable '$PYTHON_BIN' not found. Set PYTHON_BIN or install python3."
    exit 1
  fi
}

setup_python_environment() {
  log_section "Python Environment"
  ensure_python_binary

  if [ ! -d "$VENV_DIR" ]; then
    log_info "Creating virtual environment at $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  else
    log_info "Using existing virtual environment at $VENV_DIR"
  fi

  # shellcheck disable=SC1090,SC1091
  source "$VENV_DIR/bin/activate"

  log_info "Upgrading pip, setuptools, and wheel"
  python -m pip install --upgrade pip setuptools wheel > /dev/null

  log_info "Installing Python tooling packages"
  python -m pip install \
    pytest-asyncio \
    pytest-xdist \
    pre-commit \
    uv \
    > /dev/null

  if [ -d "$REPO_ROOT/cync-controller" ] && [ -f "$REPO_ROOT/cync-controller/pyproject.toml" ]; then
    log_info "Installing cync-controller in editable mode with dev/test extras"
    python -m pip install -e "$REPO_ROOT/cync-controller[dev,test]" > /dev/null
  else
    log_warn "cync-controller project not found; skipping editable install"
  fi

  if [ -d "$REPO_ROOT/scripts" ] && [ -f "$REPO_ROOT/scripts/pyproject.toml" ]; then
    log_info "Installing scripts package dependencies"
    python -m pip install -e "$REPO_ROOT/scripts" > /dev/null
  fi

  deactivate
  log_success "Python environment ready"
}

install_npm_dependencies() {
  log_section "Node Dependencies"

  if [ ! -f "$REPO_ROOT/package.json" ]; then
    log_warn "package.json not found; skipping npm install"
    return
  fi

  pushd "$REPO_ROOT" > /dev/null
  if npm install; then
    log_success "npm dependencies installed"
  else
    log_error "npm install failed"
    popd > /dev/null
    exit 1
  fi
  popd > /dev/null
}

install_playwright_assets() {
  log_section "Playwright Browsers"

  if ! command -v npx > /dev/null 2>&1; then
    log_warn "npx not available; skipping Playwright browser installation"
    return
  fi

  if ! npx --yes playwright --version > /dev/null 2>&1; then
    log_warn "Playwright package not installed. Run npm install to add playwright."
    return
  fi

  log_info "Installing Playwright Chromium browser (with dependencies)"
  npx --yes playwright install chromium --with-deps

  log_info "Installing Playwright system dependencies"
  npx --yes playwright install-deps chromium

  log_success "Playwright tooling ready"
}

setup_python_environment
install_npm_dependencies
install_playwright_assets

log_section "Worktree Setup Complete"
log_success "Environment ready for development"
