#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 https://github.com/YOUR_USERNAME/DriveFort-AI.git" >&2
  exit 2
fi

if ! command -v git >/dev/null 2>&1; then
  echo "Git is not installed or is not available in PATH." >&2
  exit 1
fi

REPOSITORY_URL="$1"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -d .git ]]; then
  git init -b main
fi

git add .
if ! git diff --cached --quiet; then
  git commit -m "Initial release: DriveFort AI V3"
fi

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REPOSITORY_URL"
else
  git remote add origin "$REPOSITORY_URL"
fi

git push -u origin main
