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
grep -Fq '# Caddy v2.11.4.' "$DOCKERFILE"
grep -Fq 'ARG CADDY_COMMIT=e2eee6a7fce366321294c9c2a79f3146891dcbdf' "$DOCKERFILE"
grep -Fq 'ARG CADDY_SOURCE_SHA256=a593bd7077c76102ca76d19287a5e247d4e359dd67eddbc933f865afd3c131eb' "$DOCKERFILE"
grep -Fq '# caddy-l4 v0.1.2.' "$DOCKERFILE"
grep -Fq 'ARG CADDY_L4_COMMIT=42db5690dea199f930a6f08005fe2e4aab10dcc9' "$DOCKERFILE"
grep -Fq 'ARG CADDY_L4_SOURCE_SHA256=a2def12c2a1c45b859c1412fa520f4fa1b630cc2ba69a6a254f58051080942a1' "$DOCKERFILE"
grep -Fq '# xcaddy v0.4.5.' "$DOCKERFILE"
grep -Fq 'ARG XCADDY_COMMIT=328cac711a1fe80041c3b79db2dfbb4e10330a05' "$DOCKERFILE"
grep -Fq 'ARG XCADDY_SOURCE_SHA256=23dbf0f640a1eb6ae560d014f2c8f57cbe0ae740cdf874f3e712fe0286c8a6ab' "$DOCKERFILE"
grep -Fq 'ARG CADDY_GO_VERSION=1.25.14' "$DOCKERFILE"
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
