#!/usr/bin/env bash
# Run this task's tests inside the task directory with the task's own venv.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+psycopg://tester@127.0.0.1:55427/intel_approval_test}"
exec .venv/bin/python -m pytest "$@"