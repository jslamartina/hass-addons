# Cursor Background Agent Dockerfile
# Provides a complete development environment for hass-addons repository
# This Dockerfile creates a base environment without copying code
# The code will be cloned by the background agent at runtime
#
# Key principles for background agents:
# - Do NOT copy code (agent clones the repo)
# - Install all development tools and dependencies
# - Run as non-root user for security
# - Use home directory as WORKDIR

# Use Python 3.14 as base (required by project)
FROM python:3.14-slim-bookworm

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive \
  PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  PIP_NO_CACHE_DIR=1 \
  PIP_DISABLE_PIP_VERSION_CHECK=1 \
  NODE_VERSION=20

# Install system dependencies
# Essential build tools, shell linting, Playwright dependencies, and utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  git \
  curl \
  wget \
  ca-certificates \
  gnupg \
  sudo \
  shellcheck \
  libnss3 \
  libnspr4 \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libcups2 \
  libdrm2 \
  libdbus-1-3 \
  libxkbcommon0 \
  libxcomposite1 \
  libxdamage1 \
  libxfixes3 \
  libxrandr2 \
  libgbm1 \
  libpango-1.0-0 \
  libcairo2 \
  libasound2 \
  libatspi2.0-0 \
  vim \
  nano \
  less \
  procps \
  && rm -rf /var/lib/apt/lists/*

# Install Node.js 20.x (for npm scripts, TypeScript, Playwright)
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
  && apt-get install -y nodejs \
  && rm -rf /var/lib/apt/lists/*

# Install global Python tooling (pytest, ruff) and Playwright browsers
RUN python3 -m pip install --upgrade pip setuptools wheel \
  && python3 -m pip install \
    ruff \
    pytest \
    pytest-asyncio \
    pytest-xdist \
    pytest-playwright \
    basedpyright \
  && npx --yes playwright install chromium

# Create non-root user 'ubuntu' with sudo access
RUN useradd -m -s /bin/bash ubuntu \
  && echo "ubuntu ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Switch to non-root user
USER ubuntu

# Set working directory to user's home
WORKDIR /home/ubuntu

# Install auto-setup hook in bashrc
# This automatically runs setup-worktree.sh when entering a hass-addons repo
RUN echo '' >> ~/.bashrc && \
    echo '# Auto-setup hass-addons worktree when entering repo directory' >> ~/.bashrc && \
    echo 'auto_setup_worktree() {' >> ~/.bashrc && \
    echo '  # Check if we are in a hass-addons repo and setup-worktree.sh exists' >> ~/.bashrc && \
    echo '  if [ -f ".cursor/setup-worktree.sh" ] && [ -f "package.json" ] && [ -d "cync-controller" ]; then' >> ~/.bashrc && \
    echo '    # Check if already set up (venv exists)' >> ~/.bashrc && \
    echo '    if [ ! -d ".venv" ]; then' >> ~/.bashrc && \
    echo '      echo "🔧 Auto-detected hass-addons repo - running setup-worktree.sh..."' >> ~/.bashrc && \
    echo '      bash .cursor/setup-worktree.sh' >> ~/.bashrc && \
    echo '    fi' >> ~/.bashrc && \
    echo '  fi' >> ~/.bashrc && \
    echo '}' >> ~/.bashrc && \
    echo '# Run auto-setup on directory change' >> ~/.bashrc && \
    echo 'cd() { command cd "$@" && auto_setup_worktree; }' >> ~/.bashrc && \
    echo '# Run on initial shell start if already in repo' >> ~/.bashrc && \
    echo 'auto_setup_worktree' >> ~/.bashrc

# Set default shell to bash
SHELL ["/bin/bash", "-c"]

# Default command
CMD ["bash"]

# Labels
LABEL maintainer="Cursor Background Agent"
LABEL description="Background agent environment for hass-addons with Python 3.14, Node.js 20, pytest, playwright, ruff"
LABEL version="2.0.0"
LABEL usage="Code is cloned by agent at runtime - do not copy into image"
