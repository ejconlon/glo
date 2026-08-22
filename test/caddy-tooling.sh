#!/usr/bin/env bash
set -euo pipefail

GLO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="$GLO_DIR/devcontainer/image/Dockerfile"
TEMPLATE="$GLO_DIR/template/devcontainer.json"
GLO="$GLO_DIR/devcontainer/image/files/glo/bin/glo"
GLO_CADDY="$GLO_DIR/devcontainer/image/files/glo/bin/glo-caddy"

[[ "$(grep -c '^FROM ' "$DOCKERFILE")" == "1" ]]
[[ "$(head -n 1 "$DOCKERFILE")" =~ ^FROM\ [^[:space:]]+$ ]]
grep -Fq 'ARG CADDY_ENABLED=0' "$DOCKERFILE"
grep -Fq 'ARG CADDY_VERSION=2.11.4' "$DOCKERFILE"
grep -Fq 'CADDY_SHA512_X64=' "$DOCKERFILE"
grep -Fq 'CADDY_SHA512_ARM64=' "$DOCKERFILE"
grep -Fq 'github.com/caddyserver/caddy/releases/download/' "$DOCKERFILE"
grep -Fq 'sha512sum -c -' "$DOCKERFILE"
grep -Fq 'files/glo/bin/glo-caddy /opt/glo/bin/glo-caddy' "$DOCKERFILE"
grep -Fq '"CADDY_ENABLED": "0"' "$TEMPLATE"
# shellcheck disable=SC2016  # Assert the dispatcher retains runtime expansion.
grep -Fq 'caddy)     shift; exec "${_GLO_BIN_DIR}/glo-caddy"' "$GLO"
# shellcheck disable=SC2016  # Assert the helper retains runtime expansion.
grep -Fq 'exec caddy run --config "$CADDY_CONFIG_FILE" --adapter caddyfile' "$GLO_CADDY"
shellcheck "$GLO_CADDY"

help_output="$($GLO_CADDY --help)"
grep -Fq 'CADDY_ENABLED=1' <<<"$help_output"

printf '[OK] Caddy tooling checks passed\n'
