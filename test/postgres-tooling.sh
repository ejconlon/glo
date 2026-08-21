#!/usr/bin/env bash
set -euo pipefail

GLO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="$GLO_DIR/devcontainer/image/Dockerfile"
TEMPLATE="$GLO_DIR/template/devcontainer.json"
GLO="$GLO_DIR/devcontainer/image/files/glo/bin/glo"
GLO_POSTGRES="$GLO_DIR/devcontainer/image/files/glo/bin/glo-postgres"
BOOTSTRAP="$GLO_DIR/bootstrap.sh"

grep -Fq 'ARG POSTGRES_ENABLED=0' "$DOCKERFILE"
grep -Fq 'postgresql18-server' "$DOCKERFILE"
grep -Fq 'libpq5-devel' "$DOCKERFILE"
grep -Fq '"POSTGRES_ENABLED": "0"' "$TEMPLATE"
# shellcheck disable=SC2016  # Assert the dispatcher retains runtime expansion.
grep -Fq 'postgres)  shift; exec "${_GLO_BIN_DIR}/glo-postgres"' "$GLO"
grep -Fq '127.0.0.1' "$GLO_POSTGRES"
grep -Fq 'PostgreSQL 18 is unavailable; rebuild with POSTGRES_ENABLED=1 or use --docker' \
    "$GLO_POSTGRES"
grep -Fq 'GLO_POSTGRES_DOCKER_IMAGE' "$GLO_POSTGRES"
grep -Fq 'run) run_cluster' "$GLO_POSTGRES"
# shellcheck disable=SC2016  # Assert the helper retains runtime expansion.
grep -Fq -- '-D "$postgres_data"' "$GLO_POSTGRES"
# shellcheck disable=SC2016  # Assert the helper retains runtime expansion.
grep -Fq 'type=bind,source=${mounted_root},target=${docker_state_root}' "$GLO_POSTGRES"
# shellcheck disable=SC2016  # Assert the helper retains runtime expansion.
grep -Fq 'type=bind,source=${helper_path},target=/usr/local/bin/glo-postgres,readonly' \
    "$GLO_POSTGRES"
# Bootstrap discovers every shipped command, including glo-postgres, when it
# creates the workspace bin/ wrappers.
# shellcheck disable=SC2016  # Assert bootstrap retains runtime expansion.
grep -Fq 'for script in "${SCRIPT_DIR}/devcontainer/image/files/glo/bin"/*' \
    "$BOOTSTRAP"
shellcheck "$GLO_POSTGRES"

help_output="$($GLO_POSTGRES --help 2>&1 || true)"
grep -Fq 'POSTGRES_ENABLED=1' <<<"$help_output"
grep -Fq -- '--docker' <<<"$help_output"
grep -Fq '{run|start|stop|status|url|env}' <<<"$help_output"

printf '[OK] PostgreSQL tooling checks passed\n'
