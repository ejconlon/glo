#!/usr/bin/env bash
set -euo pipefail

GLO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEVCONTAINER_JUSTFILE="$GLO_DIR/devcontainer/justfile"
GLO_BUILD="$GLO_DIR/devcontainer/image/files/glo/bin/glo-build"
GLO_POSTGRES="$GLO_DIR/devcontainer/image/files/glo/bin/glo-postgres"
WORKSPACE_JUSTFILE="$GLO_DIR/template/justfile"
DOCKERFILE="$GLO_DIR/devcontainer/image/Dockerfile"
DOCKERIGNORE="$GLO_DIR/devcontainer/image/.dockerignore"
TEST_ROOT="$(mktemp -d /tmp/glo-container-tooling.XXXXXX)"
trap 'rm -rf "$TEST_ROOT"' EXIT

fail() {
    printf '[E] %s\n' "$*" >&2
    exit 1
}

require_log() {
    local pattern="$1"
    grep -Fq -- "$pattern" "$GLO_TEST_LOG" \
        || fail "Missing container command: $pattern"
}

fake_bin="$TEST_ROOT/fake-bin"
workspace="$TEST_ROOT/workspace"
mkdir -p "$fake_bin" "$workspace/.devcontainer" "$workspace/.git"
printf '{}\n' > "$workspace/.devcontainer/devcontainer.json"
export GLO_TEST_LOG="$TEST_ROOT/commands.log"

cat > "$fake_bin/container-command" <<'EOF'
#!/usr/bin/env bash
printf '%s %s\n' "$(basename "$0")" "$*" >> "$GLO_TEST_LOG"
EOF
chmod 755 "$fake_bin/container-command"
ln -s container-command "$fake_bin/devcontainer"
ln -s container-command "$fake_bin/docker"
ln -s container-command "$fake_bin/podman"

PATH="$fake_bin:$PATH" \
    just -f "$DEVCONTAINER_JUSTFILE" --set workspace "$workspace" image
require_log "devcontainer build --docker-path podman --buildkit never"

grep -Fq 'if os() == "macos" { "docker" } else { "podman" }' \
    "$DEVCONTAINER_JUSTFILE"

: > "$GLO_TEST_LOG"
PATH="$fake_bin:$PATH" GLO_CONTAINER_ENGINE=docker \
    just -f "$DEVCONTAINER_JUSTFILE" --set workspace "$workspace" image
require_log "devcontainer build --docker-path docker --buildkit auto"

: > "$GLO_TEST_LOG"
PATH="$fake_bin:$PATH" \
    just -f "$DEVCONTAINER_JUSTFILE" --set workspace "$workspace" down test123
require_log "podman ps -aq --filter label=devcontainer.project=workspace"
require_log "podman rm -f"

if GLO_CONTAINER_ENGINE=containerd \
    just -f "$DEVCONTAINER_JUSTFILE" --set workspace "$workspace" image \
    >"$TEST_ROOT/invalid.out" 2>&1; then
    fail "Invalid container engine unexpectedly succeeded"
fi
grep -Fq "GLO_CONTAINER_ENGINE must be 'podman' or 'docker'" \
    "$TEST_ROOT/invalid.out"

if (
    cd "$workspace"
    PATH="$fake_bin:$PATH" \
        GLO_CONTAINER_ENGINE=containerd \
        GLO_POSTGRES_ROOT="$TEST_ROOT/postgres" \
        "$GLO_POSTGRES" --container status
) >"$TEST_ROOT/postgres-invalid.out" 2>&1; then
    fail "Invalid PostgreSQL container engine unexpectedly succeeded"
fi
grep -Fq "GLO_CONTAINER_ENGINE must be 'podman' or 'docker'" \
    "$TEST_ROOT/postgres-invalid.out"

grep -Fq 'FROM docker.io/rockylinux/rockylinux:10.2-minimal' \
    "$DOCKERFILE"
grep -Fxq 'COPY files/glo/ /opt/glo/' "$DOCKERFILE"
[[ "$(grep -Ec '^COPY .*files/glo' "$DOCKERFILE")" -eq 1 ]] \
    || fail "Glo image resources are split across multiple COPY layers"
if grep -Eq '^RUN (mkdir -p /opt/glo|chown -R user:user /opt/glo)' "$DOCKERFILE"; then
    fail "Glo image retains a standalone directory or ownership layer"
fi
grep -Fq '    && groupadd --gid 1000 user \' "$DOCKERFILE"
grep -Fq '    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash user' \
    "$DOCKERFILE"
if grep -Fq 'RUN groupadd --gid 1000 user' "$DOCKERFILE"; then
    fail "Image user creation remains in a standalone layer"
fi
for ignored_artifact in \
    '**/.venv' \
    '**/.pytest_cache' \
    '**/.ruff_cache' \
    '**/__pycache__' \
    '**/*.py[cod]'
do
    grep -Fxq "$ignored_artifact" "$DOCKERIGNORE" \
        || fail "Image context does not ignore: $ignored_artifact"
done
while IFS= read -r command_path; do
    [[ -x "$command_path" ]] || fail "Glo command is not executable: $command_path"
done < <(find "$GLO_DIR/devcontainer/image/files/glo/bin" -maxdepth 1 -type f -print)
# shellcheck disable=SC2016  # Assert the template retains runtime expansion.
grep -Fq 'just -f {{glo}}/devcontainer/justfile --set workspace "$PWD" image' \
    "$WORKSPACE_JUSTFILE"
grep -Fq "\"\$CONTAINER_ENGINE\" run" "$GLO_BUILD"
grep -Fq 'Darwin) DEFAULT_CONTAINER_ENGINE="docker"' "$GLO_BUILD"
grep -Fq '*) DEFAULT_CONTAINER_ENGINE="podman"' "$GLO_BUILD"
grep -Fq 'Darwin) default_container_engine="docker"' "$GLO_POSTGRES"
grep -Fq '*) default_container_engine="podman"' "$GLO_POSTGRES"
grep -Fq -- '--container)' "$GLO_BUILD"
grep -Fq 'CONTAINER_USER="${GLO_CONTAINER_USER:-user}"' "$GLO_BUILD"
grep -Fq '"${VENV_VOLUME}:${CONTAINER_WORKDIR}/.glo/venv"' "$GLO_BUILD"
grep -Fq -- '--plan-container)' "$GLO_BUILD"
grep -Fq -- '--exec-container)' "$GLO_BUILD"
if grep -Eq -- '--(plan-|exec-)?docker|docker_(args|mode|start|stop|status)' \
    "$GLO_BUILD" "$GLO_POSTGRES"; then
    fail "Found deprecated Docker-named Glo interfaces or internals"
fi
if grep -Eq '^[[:space:]]*docker (build|run|rm|ps|exec)' \
    "$DEVCONTAINER_JUSTFILE" "$GLO_BUILD" "$GLO_POSTGRES"; then
    fail "Found a direct Docker lifecycle command outside the engine selector"
fi

printf '[OK] Container tooling checks passed\n'
