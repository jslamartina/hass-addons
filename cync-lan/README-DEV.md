# Developer Guide

> **This file is for developers working on the add-on code, not for end users.**

## Source Code Location

All Python source code for the CyncLAN add-on is located in this directory:
- `src/cync_lan/` - Python package source code
- `pyproject.toml` - Package configuration and dependencies

## Development Workflow

1. Edit code in `src/cync_lan/` or `pyproject.toml`
2. Run `./rebuild.sh` to rebuild and restart the add-on
3. Check logs: `ha addons logs local_cync-lan`
4. Test functionality in Home Assistant

## Important Notes

- **Always rebuild after Python changes**: The Docker image must be rebuilt for code changes to take effect
- **Restart is not enough**: `ha addons restart` will not pick up Python code changes
- Use `./rebuild.sh` which handles rebuild + restart automatically
