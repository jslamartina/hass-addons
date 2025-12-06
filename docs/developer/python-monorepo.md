# Python Monorepo Workflow

- Install deps: `poetry install` (uses root `.venv`, Python >=3.14.1).
- Lint: `ruff check .` ; format: `ruff format .`.
- Type check: `basedpyright --project pyrightconfig.json`.
- Tests: `pytest tests` (or narrower paths like `tests/unit`).
- Console scripts: `cync-controller` and `rebuild-tcp-comm` from the unified wheel.
- Packaging: root `pyproject.toml` (name/version `cync_controller` 0.0.4.13) with sources in `src/cync_controller`.
- Add-on build: Dockerfile in `cync-controller/` consumes `cync-controller/src`; keep it in sync with root via `rsync -a --delete ../src/cync_controller/ cync-controller/src/cync_controller/`.
