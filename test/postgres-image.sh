#!/usr/bin/env bash
set -euo pipefail

GLO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_CONTEXT="$GLO_DIR/devcontainer/image"
DISABLED_IMAGE=glo-postgres-disabled-test
ENABLED_IMAGE=glo-postgres-enabled-test

cleanup() {
    docker image rm --force "$DISABLED_IMAGE" "$ENABLED_IMAGE" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker build \
    --target postgres-feature \
    --build-arg POSTGRES_ENABLED=0 \
    --tag "$DISABLED_IMAGE" \
    "$IMAGE_CONTEXT"

docker run --rm "$DISABLED_IMAGE" bash -ceu '
for command in psql postgres initdb pg_ctl pg_config; do
    if command -v "$command" >/dev/null 2>&1; then
        echo "PostgreSQL command unexpectedly installed: $command" >&2
        exit 1
    fi
done
if rpm -q libpq5-devel postgresql18 postgresql18-server >/dev/null 2>&1; then
    echo "PostgreSQL package unexpectedly installed" >&2
    exit 1
fi
if disabled_output="$(glo-postgres status 2>&1)"; then
    echo "Disabled helper unexpectedly succeeded" >&2
    exit 1
fi
grep -Fq "POSTGRES_ENABLED=1" <<<"$disabled_output"
'

docker build \
    --target postgres-feature \
    --build-arg POSTGRES_ENABLED=1 \
    --tag "$ENABLED_IMAGE" \
    "$IMAGE_CONTEXT"

docker run --rm --user user --env HOME=/home/user "$ENABLED_IMAGE" bash -ceu '
pg_config --version | grep -E "^PostgreSQL 18\."
glo-postgres start
eval "$(glo-postgres env)"
version="$(psql "$GLO_POSTGRES_URL" --tuples-only --no-align \
    --command="SHOW server_version_num")"
[[ "$version" =~ ^18[0-9]{4}$ ]]
psql "$GLO_POSTGRES_URL" --set=ON_ERROR_STOP=1 --quiet <<"SQL"
CREATE SCHEMA glo_smoke;
CREATE TABLE glo_smoke.values (value integer NOT NULL);
INSERT INTO glo_smoke.values (value) VALUES (18);
DO $$
BEGIN
    IF (SELECT value FROM glo_smoke.values) <> 18 THEN
        RAISE EXCEPTION '\''PostgreSQL smoke query failed'\'';
    END IF;
END
$$;
DROP SCHEMA glo_smoke CASCADE;
SQL
glo-postgres status
glo-postgres stop
'

printf '[OK] PostgreSQL image feature checks passed\n'
