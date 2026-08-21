#!/usr/bin/env bash
set -euo pipefail

GLO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="$GLO_DIR/devcontainer/image/Dockerfile"
TEMPLATE="$GLO_DIR/template/devcontainer.json"

[[ "$(grep -c '^FROM ' "$DOCKERFILE")" == "1" ]]
[[ "$(head -n 1 "$DOCKERFILE")" == 'FROM rockylinux/rockylinux:10-minimal' ]]
grep -Fq 'ARG GARAGE_ENABLED=0' "$DOCKERFILE"
grep -Fq 'ARG GARAGE_VERSION=2.3.0' "$DOCKERFILE"
grep -Fq 'GARAGE_SHA256_X64=' "$DOCKERFILE"
grep -Fq 'GARAGE_SHA256_ARM64=' "$DOCKERFILE"
grep -Fq 'garagehq.deuxfleurs.fr/_releases/' "$DOCKERFILE"
grep -Fq '"GARAGE_ENABLED": "0"' "$TEMPLATE"

printf '[OK] Garage tooling checks passed\n'
