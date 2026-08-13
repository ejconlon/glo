#!/usr/bin/env bash
set -euo pipefail

GLO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="$GLO_DIR/devcontainer/image/Dockerfile"
TEMPLATE="$GLO_DIR/template/devcontainer.json"
GLO="$GLO_DIR/devcontainer/image/files/glo/bin/glo"
GLO_POSTGRES="$GLO_DIR/devcontainer/image/files/glo/bin/glo-postgres"

grep -Fq 'ARG POSTGRES_ENABLED=0' "$DOCKERFILE"
grep -Fq 'postgresql18-server' "$DOCKERFILE"
grep -Fq 'libpq5-devel' "$DOCKERFILE"
grep -Fq 'FROM base AS postgres-feature' "$DOCKERFILE"
grep -Fq '"POSTGRES_ENABLED": "0"' "$TEMPLATE"
# shellcheck disable=SC2016  # Assert the dispatcher retains runtime expansion.
grep -Fq 'postgres)  shift; exec "${_GLO_BIN_DIR}/glo-postgres"' "$GLO"
grep -Fq '127.0.0.1' "$GLO_POSTGRES"
grep -Fq 'PostgreSQL 18 is unavailable; rebuild with POSTGRES_ENABLED=1' \
    "$GLO_POSTGRES"
shellcheck "$GLO_POSTGRES" "$GLO_DIR/test/postgres-image.sh"

help_output="$($GLO_POSTGRES --help 2>&1 || true)"
grep -Fq 'POSTGRES_ENABLED=1' <<<"$help_output"

printf '[OK] PostgreSQL tooling checks passed\n'
