#!/usr/bin/env bash
# Migration roundtrip + zero-drift check; output tee'd to evidence/.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://tester@127.0.0.1:55427/intel_approval_test}"
mkdir -p evidence

{
  echo "== alembic upgrade head =="
  .venv/bin/alembic upgrade head
  echo "== alembic downgrade -1 =="
  .venv/bin/alembic downgrade -1
  echo "== alembic upgrade head (again) =="
  .venv/bin/alembic upgrade head
  echo "== alembic check =="
  .venv/bin/alembic check
} 2>&1 | tee evidence/migration-check.txt