#!/usr/bin/env bash

set -euo pipefail

cleanup() {
  docker compose --profile test rm -sf postgres-test
}

trap cleanup EXIT INT TERM

docker compose --profile test up -d --wait --force-recreate postgres-test
AAM_DATABASE_URL="${AAM_TEST_DATABASE_URL}" .venv/bin/alembic upgrade head
.venv/bin/pytest
