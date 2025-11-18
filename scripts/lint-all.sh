#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

# Load common output functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091  # Source path is dynamic via $SCRIPT_DIR
source "$SCRIPT_DIR/shell-common/common-output.sh"

# shellcheck disable=SC2034  # LP used by common-output.sh log functions
LP="[$(basename "$0")]"

REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

activate_venv() {
  if [ -n "${VIRTUAL_ENV:-}" ]; then
    log_info "Using active virtualenv: $VIRTUAL_ENV"
    return
  fi

  local venv_path="$REPO_ROOT/.venv"
  if [ -f "$venv_path/bin/activate" ]; then
    log_info "Activating repository virtualenv at $venv_path"
    # shellcheck disable=SC1090
    source "$venv_path/bin/activate"
  else
    log_warn "Repository virtualenv not found at $venv_path. Run python-rebuild-tcp-comm/scripts/setup.sh to create it."
  fi
}

activate_venv

echo "================================================"
echo "Running all linters across the codebase"
echo "================================================"

# Change to repository root
cd "$REPO_ROOT"

# Track overall status
FAILED=0

# Python linting with Ruff
echo -e "\n${YELLOW}=== Running Ruff (Python linter) ===${NC}"
if ruff check .; then
  echo -e "${GREEN}✅ Ruff check passed${NC}"
else
  echo -e "${RED}❌ Ruff found issues${NC}"
  FAILED=1
fi

# Python formatting with Ruff
echo -e "\n${YELLOW}=== Running Ruff (Python formatter) ===${NC}"
if ruff format --check .; then
  echo -e "${GREEN}✅ Ruff format check passed${NC}"
else
  echo -e "${RED}❌ Ruff found formatting issues (run 'ruff format .' to fix)${NC}"
  FAILED=1
fi

run_pyright() {
  local pyright_cmd=()

  if command -v pyright > /dev/null 2>&1; then
    pyright_cmd=("pyright")
    log_info "Using pyright from PATH: $(command -v pyright)"
  elif [ -x "$REPO_ROOT/node_modules/.bin/pyright" ]; then
    pyright_cmd=("$REPO_ROOT/node_modules/.bin/pyright")
    log_info "Using pyright from node_modules"
  elif command -v npx > /dev/null 2>&1; then
    pyright_cmd=("npx" "--yes" "pyright")
    log_info "Pyright not installed globally; running via npx"
  else
    log_error "pyright command not found. Install via npm (npm install) or pip (pip install pyright)"
    return 1
  fi

  "${pyright_cmd[@]}" --project "$REPO_ROOT/python-rebuild-tcp-comm/pyrightconfig.json"
}

# Python type checking with pyright
echo -e "\n${YELLOW}=== Running pyright (Python type checker) ===${NC}"
if run_pyright; then
  echo -e "${GREEN}✅ pyright check passed${NC}"
else
  echo -e "${RED}❌ pyright found type errors or command missing${NC}"
  FAILED=1
fi

# Shell script linting with ShellCheck
echo -e "\n${YELLOW}=== Running ShellCheck (Shell script linter) ===${NC}"
# Use git ls-files to automatically respect .gitignore
# Check all severity levels (info, warning, error) for comprehensive linting
# Use -x flag to allow following sourced files (shell-common/common-output.sh)
if git ls-files '*.sh' | xargs -r shellcheck --severity=info --external-sources; then
  echo -e "${GREEN}✅ ShellCheck passed${NC}"
else
  echo -e "${RED}❌ ShellCheck found issues${NC}"
  FAILED=1
fi

# TypeScript linting with ESLint
echo -e "\n${YELLOW}=== Running ESLint (TypeScript linter) ===${NC}"
if npm run lint:typescript --silent; then
  echo -e "${GREEN}✅ ESLint check passed${NC}"
else
  echo -e "${RED}❌ ESLint found issues (run 'npm run lint:typescript:fix' to fix)${NC}"
  FAILED=1
fi

# Markdown linting with markdownlint
echo -e "\n${YELLOW}=== Running markdownlint (Markdown linter) ===${NC}"
if npm run lint:markdown --silent; then
  echo -e "${GREEN}✅ markdownlint check passed${NC}"
else
  echo -e "${RED}❌ markdownlint found issues (run 'npm run lint:markdown:fix' to fix)${NC}"
  FAILED=1
fi

# Format checking with Prettier
echo -e "\n${YELLOW}=== Running Prettier (Format checker) ===${NC}"
if npm run format:check --silent; then
  echo -e "${GREEN}✅ Prettier check passed${NC}"
else
  echo -e "${RED}❌ Prettier found formatting issues (run 'npm run format' to fix)${NC}"
  FAILED=1
fi

# Summary
echo -e "\n================================================"
if [ $FAILED -eq 0 ]; then
  echo -e "${GREEN}✅ All linters passed!${NC}"
  exit 0
else
  echo -e "${RED}❌ Some linters found issues. See output above.${NC}"
  exit 1
fi
