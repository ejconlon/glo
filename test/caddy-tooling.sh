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
grep -Fq 'CADDY_GO_SHA256_X64=' "$DOCKERFILE"
grep -Fq 'CADDY_GO_SHA256_ARM64=' "$DOCKERFILE"
grep -Fq 'https://go.dev/dl/' "$DOCKERFILE"
grep -Fq 'https://codeload.github.com/${source_repository}/tar.gz/${source_commit}' "$DOCKERFILE"
grep -Fq 'sha256sum -c -' "$DOCKERFILE"
grep -Fq 'go install ./cmd/xcaddy' "$DOCKERFILE"
grep -Fq 'xcaddy build "${CADDY_COMMIT}"' "$DOCKERFILE"
grep -Fq 'github.com/caddyserver/caddy/v2=/tmp/caddy-build/source/caddy' "$DOCKERFILE"
grep -Fq 'github.com/mholt/caddy-l4@${CADDY_L4_COMMIT}' "$DOCKERFILE"
grep -Fq 'github.com/mholt/caddy-l4=/tmp/caddy-build/source/caddy-l4' "$DOCKERFILE"
! grep -Eq 'go install .*github\.com/' "$DOCKERFILE"
grep -Fq 'caddy list-modules | grep -Fx layer4.handlers.tls' "$DOCKERFILE"
grep -Fxq 'COPY files/glo/ /opt/glo/' "$DOCKERFILE"
[[ -x "$GLO_CADDY" ]]
grep -Fq '"CADDY_ENABLED": "0"' "$TEMPLATE"
# shellcheck disable=SC2016  # Assert the dispatcher retains runtime expansion.
grep -Fq 'caddy)     shift; exec "${_GLO_BIN_DIR}/glo-caddy"' "$GLO"
# shellcheck disable=SC2016  # Assert the helper retains runtime expansion.
grep -Fq 'exec caddy run --config "$CADDY_CONFIG_FILE" --adapter caddyfile' "$GLO_CADDY"
shellcheck "$GLO_CADDY"

help_output="$($GLO_CADDY --help)"
grep -Fq 'CADDY_ENABLED=1' <<<"$help_output"

printf '[OK] Caddy tooling checks passed\n'
