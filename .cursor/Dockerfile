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

# Use Python 3.13 as base (required by project)
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

# Create non-root user 'ubuntu' with sudo access
RUN useradd -m -s /bin/bash ubuntu \
  && echo "ubuntu ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Switch to non-root user
USER ubuntu

# Set working directory to user's home
WORKDIR /home/ubuntu

# Note: Python tools (pip, ruff, poetry) and Playwright installation
# are now consolidated in .cursor/setup-worktree.sh, which should be called
# after the repository is cloned by the background agent:
#   cd /path/to/cloned/repo && .cursor/setup-worktree.sh

# Set default shell to bash
SHELL ["/bin/bash", "-c"]

# Default command
CMD ["bash"]

# Labels
LABEL maintainer="Cursor Background Agent"
LABEL description="Background agent environment for hass-addons with Python 3.13, Node.js 20, pytest, playwright, ruff"
LABEL version="2.0.0"
LABEL usage="Code is cloned by agent at runtime - do not copy into image"
