# Repository Guidelines
## Project Structure & Module Organization
- `cync-lan/` packages the Home Assistant add-on (Dockerfile, run.sh, static/ assets, translations/) and ships the supervisor metadata.
- `cync-lan/cync-lan-python/` contains the installable Python stack under `src/cync_lan` plus sample configs and docs for DNS, install, and troubleshooting workflows.
- `docs/` hosts add-on level references; `mitm/` holds packet-analysis utilities; top-level `package.json` manages repository-wide formatting tooling.

## Build, Test, and Development Commands
- `pip install -e cync-lan/cync-lan-python[dev]`: set up the local library with optional developer extras.
- `python -m cync_lan.main --export-server --env config/.env.local`: run the stack from source using a checked-in config export.
- `docker build -t hass-cync-lan ./cync-lan`: produce an add-on image identical to what Home Assistant Supervisor expects.
- `npm run format:check` (or `npm run format`) ensures Prettier normalizes YAML, JSON, and shell scripts before submission.

## Coding Style & Naming Conventions
- Python follows Ruff (`pyproject.toml`): 4-space indentation, 120-character soft limit, snake_case modules, PascalCase classes, and explicit type hints on async boundaries.
- Keep shell scripts Bash-compatible, favor uppercase log prefixes (`LP=`) and `bashio::config` accessors when reading add-on settings.
- Name exported assets and translation files with lowercase-kebab names to match Home Assistant conventions.

## Testing Guidelines
- Add future unit tests beside the library code (e.g., `cync-lan/cync-lan-python/tests/test_mqtt_client.py`) and execute them with `python -m pytest` after installing the dev extras.
- Use fixture YAML produced by the exporter to simulate devices and assert MQTT payload shapes; avoid hardcoding secrets in tests.
- For end-to-end smoke checks, run `python -c "from cync_lan.main import main; main()" --enable-export` against a Supervisor dev instance and confirm MQTT discovery topics.

## Commit & Pull Request Guidelines
- Mirror existing history: single-sentence, present-tense summaries that capture both change and motivation (e.g., `Refine run.sh; export MQTT credentials by default`).
- Group related edits per commit and keep diffs focused on one feature or bug fix.
- PRs should describe test evidence, affected Home Assistant versions, DNS or MQTT changes, and link related issues or forum threads.
- Don't commit the files, so that they can be reviewed by me locally first.

## Security & Configuration Tips
- Never commit credentials; rely on `.env` files referenced by `--env` or add-on secrets.
- When altering network endpoints, refresh `config.yaml`, `cync_lan/const.py`, and the DNS guidance in `cync-lan/cync-lan-python/docs/DNS.md` to keep users aligned.
