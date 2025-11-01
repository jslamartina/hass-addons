#!/usr/bin/env bash
set -e

# Load common output functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/shell-common/common-output.sh"

# shellcheck disable=SC2034  # LP used by common-output.sh log functions
LP="[$(basename "$0")]"

echo "================================================"
echo "Running all linters across the codebase"
echo "================================================"

# Change to repository root
cd "$(dirname "$0")/.."

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

# Shell script linting with ShellCheck
echo -e "\n${YELLOW}=== Running ShellCheck (Shell script linter) ===${NC}"
# Use git ls-files to automatically respect .gitignore
# Only check warning and error level (exclude info-level messages like SC1091)
if git ls-files '*.sh' | xargs -r shellcheck --severity=warning; then
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
