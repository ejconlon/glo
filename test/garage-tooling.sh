#!/usr/bin/env bash
set -euo pipefail

GLO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="$GLO_DIR/devcontainer/image/Dockerfile"
TEMPLATE="$GLO_DIR/template/devcontainer.json"
GLO="$GLO_DIR/devcontainer/image/files/glo/bin/glo"
GLO_GARAGE="$GLO_DIR/devcontainer/image/files/glo/bin/glo-garage"

[[ "$(grep -c '^FROM ' "$DOCKERFILE")" == "1" ]]
[[ "$(head -n 1 "$DOCKERFILE")" =~ ^FROM\ [^[:space:]]+$ ]]
grep -Fq 'ARG GARAGE_ENABLED=0' "$DOCKERFILE"
grep -Fq 'ARG GARAGE_VERSION=2.3.0' "$DOCKERFILE"
grep -Fq 'GARAGE_SHA256_X64=' "$DOCKERFILE"
grep -Fq 'GARAGE_SHA256_ARM64=' "$DOCKERFILE"
grep -Fq 'garagehq.deuxfleurs.fr/_releases/' "$DOCKERFILE"
grep -Fxq 'COPY files/glo/ /opt/glo/' "$DOCKERFILE"
[[ -x "$GLO_GARAGE" ]]
grep -Fq '"GARAGE_ENABLED": "0"' "$TEMPLATE"
# shellcheck disable=SC2016  # Assert the dispatcher retains runtime expansion.
grep -Fq 'garage)    shift; exec "${_GLO_BIN_DIR}/glo-garage"' "$GLO"
grep -Fq 'exec garage server --single-node --default-bucket' "$GLO_GARAGE"
shellcheck "$GLO_GARAGE"

help_output="$($GLO_GARAGE --help)"
grep -Fq 'GARAGE_ENABLED=1' <<<"$help_output"

printf '[OK] Garage tooling checks passed\n'
