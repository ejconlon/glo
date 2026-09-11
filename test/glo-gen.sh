#!/usr/bin/env bash
# Verify that glo-gen keeps Cookiecutter cache data out of the user's home.
set -euo pipefail

GLO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/glo-gen-test.XXXXXXXX")"
cleanup() {
    rm -rf -- "$TEST_ROOT"
}
trap cleanup EXIT

WORKSPACE="${TEST_ROOT}/workspace"
TEST_TMP="${TEST_ROOT}/tmp"
OBSERVED_ARGS="${TEST_ROOT}/cookiecutter-args"
OBSERVED_CONFIG="${TEST_ROOT}/cookiecutter-config"
mkdir -p \
    "${WORKSPACE}/.git" \
    "${WORKSPACE}/.glo/build/bin" \
    "${WORKSPACE}/lib" \
    "${TEST_ROOT}/home" \
    "$TEST_TMP"

FAKE_COOKIECUTTER="${WORKSPACE}/.glo/build/bin/cookiecutter"
cat > "$FAKE_COOKIECUTTER" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" > "$OBSERVED_ARGS"
while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--config-file" ]]; then
        cp "$2" "$OBSERVED_CONFIG"
        exit 0
    fi
    shift
done
echo "missing --config-file" >&2
exit 1
EOF
chmod +x "$FAKE_COOKIECUTTER"

export OBSERVED_ARGS OBSERVED_CONFIG
(
    cd "$WORKSPACE"
    HOME="${TEST_ROOT}/home" TMPDIR="$TEST_TMP" \
        "${GLO_DIR}/devcontainer/image/files/glo/bin/glo-gen" meta generated
)

grep -Fqx -- '--config-file' "$OBSERVED_ARGS"
grep -Fq "cookiecutters_dir: ${TEST_TMP}/glo-gen-cookiecutter." "$OBSERVED_CONFIG"
grep -Fq "replay_dir: ${TEST_TMP}/glo-gen-cookiecutter." "$OBSERVED_CONFIG"
if grep -Fq "${TEST_ROOT}/home" "$OBSERVED_CONFIG"; then
    echo "glo-gen configuration unexpectedly used HOME" >&2
    exit 1
fi
if find "$TEST_TMP" -mindepth 1 -maxdepth 1 -name 'glo-gen-cookiecutter.*' | grep -q .; then
    echo "glo-gen left its temporary Cookiecutter cache behind" >&2
    exit 1
fi

echo "[OK] glo-gen temporary Cookiecutter cache"
