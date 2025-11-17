#!/bin/bash
NAME=$1
DIR=".worktrees/$NAME"
BRANCH="feature/$NAME"

mkdir -p .worktrees
git worktree add "$DIR" -b "$BRANCH"

echo "Created worktree at $DIR"
echo "Open that folder manually in Cursor."