#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p .data

echo "=== Python compilation ==="
python -m compileall -q backend evaluation validation submission scripts tests migrations

echo "=== Migration round-trip ==="
DB="$ROOT/.data/verification.db"
rm -f "$DB"
export DATABASE_URL="sqlite:///$DB"
alembic upgrade head
alembic downgrade base
alembic upgrade head
python scripts/doctor.py
unset DATABASE_URL

echo "=== Test suite (isolated files) ==="
TEST_FILES=0
for test_file in tests/test_*.py; do
  rm -f "$ROOT/.data/casegraph.db"
  echo "--- $test_file"
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p pytest_asyncio.plugin "$test_file"
  TEST_FILES=$((TEST_FILES + 1))
done

if command -v tsc >/dev/null 2>&1; then
  echo "=== Frontend offline TypeScript smoke ==="
  tsc -p frontend/tsconfig.offline.json --pretty false
else
  echo "SKIP: global tsc not installed. Run 'cd frontend && npm install && npm run typecheck && npm run build'."
fi

echo "=== Release scan ==="
python scripts/release_scan.py

echo "=== Verification complete ==="
echo "PASS: ${TEST_FILES} isolated test files"
echo "External production gates: docs/RELEASE_CHECKLIST.md"
