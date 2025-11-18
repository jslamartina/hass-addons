#!/usr/bin/env bash
set -euo pipefail

PYENV_ROOT="${PYENV_ROOT:-/root/.pyenv}"
PYENV_VERSION="${PYENV_VERSION:-3.14.0}"
BUILD_DEPS_MARKER="/usr/local/share/pyenv-build-deps.installed"

install_build_dependencies() {
  if [ -f "$BUILD_DEPS_MARKER" ]; then
    return
  fi

  echo "Installing build dependencies for CPython ${PYENV_VERSION}..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libbz2-dev \
    libffi-dev \
    liblzma-dev \
    libncursesw5-dev \
    libreadline-dev \
    libsqlite3-dev \
    libssl-dev \
    llvm \
    tk-dev \
    wget \
    xz-utils \
    zlib1g-dev > /dev/null
  mkdir -p "$(dirname "$BUILD_DEPS_MARKER")"
  touch "$BUILD_DEPS_MARKER"
  echo "  ✓ Build dependencies installed"
}

ensure_pyenv() {
  if [ ! -d "$PYENV_ROOT" ]; then
    echo "Installing pyenv to $PYENV_ROOT..."
    git clone https://github.com/pyenv/pyenv.git "$PYENV_ROOT" > /dev/null
  else
    echo "Updating existing pyenv installation..."
    git -C "$PYENV_ROOT" pull --ff-only > /dev/null
  fi

  # Ensure shells initialize pyenv automatically
  for shell_rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ ! -f "$shell_rc" ]; then
      touch "$shell_rc"
    fi
    if grep -q "pyenv initialization (managed by .devcontainer/01-05-python-venv-setup.sh)" "$shell_rc"; then
      continue
    fi
    cat >> "$shell_rc" << 'EOF'

# pyenv initialization (managed by .devcontainer/01-05-python-venv-setup.sh)
export PYENV_ROOT="/root/.pyenv"
export PATH="$PYENV_ROOT/bin:$PYENV_ROOT/shims:$PATH"
if command -v pyenv > /dev/null 2>&1; then
  eval "$(pyenv init -)"
fi
EOF
  done

  export PYENV_ROOT
  export PATH="$PYENV_ROOT/bin:$PATH"
  # shellcheck disable=SC1090
  eval "$(pyenv init -)"
}

ensure_python_version() {
  if pyenv versions --bare | grep -qx "$PYENV_VERSION"; then
    echo "pyenv already has Python $PYENV_VERSION installed"
  else
    echo "Installing Python $PYENV_VERSION via pyenv (this may take a few minutes)..."
    # Align with CPython recommendations for optimized builds
    CFLAGS="-O3" PYTHON_CONFIGURE_OPTS="--enable-optimizations --with-lto" pyenv install "$PYENV_VERSION"
  fi

  pyenv global "$PYENV_VERSION"
  pyenv rehash
  echo "  ✓ pyenv global Python set to $PYENV_VERSION"
}

setup_venv() {
  local workspace_path="$1"
  local workspace_name
  workspace_name=$(basename "$workspace_path")

  echo "Setting up Python venv for $workspace_name..."
  cd "$workspace_path"

  if [ ! -d ".venv" ]; then
    python -m venv .venv
    echo "  ✓ Created .venv"
  else
    echo "  ✓ .venv already exists"
  fi

  # shellcheck disable=SC1091
  source .venv/bin/activate

  python -m pip install --upgrade pip setuptools wheel > /dev/null
  echo "  ✓ Upgraded pip, setuptools, wheel"

  if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt > /dev/null
    echo "  ✓ Installed requirements.txt"
  fi

  if [ -f "requirements-dev.txt" ]; then
    pip install -r requirements-dev.txt > /dev/null
    echo "  ✓ Installed requirements-dev.txt"
  fi

  pip install black ruff mypy pytest > /dev/null
  echo "  ✓ Installed dev tools (black, ruff, mypy, pytest)"

  deactivate
  echo "  ✓ Python venv ready for $workspace_name"
}

install_build_dependencies
ensure_pyenv
ensure_python_version
setup_venv "$1"

echo ""
echo "✅ Python virtual environment configured!"
