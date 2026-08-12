#!/usr/bin/env bash
set -euo pipefail

GLO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GLO_LOCAL="$GLO_DIR/devcontainer/image/files/glo/bin/glo-local"
GLO_SECRETS="$GLO_DIR/devcontainer/image/files/glo/bin/glo-secrets"
DEVCONTAINER_JUSTFILE="$GLO_DIR/devcontainer/justfile"
TEST_ROOT="$(mktemp -d /tmp/glo-secretspec-tooling.XXXXXX)"
trap 'rm -rf "$TEST_ROOT"' EXIT

fail() {
    printf '[E] %s\n' "$*" >&2
    exit 1
}

require_text() {
    local text="$1"
    local pattern="$2"
    grep -Fq -- "$pattern" <<<"$text" || fail "Missing expected text: $pattern"
}

reject_text() {
    local text="$1"
    local pattern="$2"
    if grep -Fq -- "$pattern" <<<"$text"; then
        fail "Found unexpected text: $pattern"
    fi
}

grep -Fq 'keyring://glo-secrets/' "$GLO_SECRETS"
grep -Fq 'f"password={credential_source}"' "$GLO_SECRETS"
grep -Fq 'uri = f"kdbx:{database}"' "$GLO_SECRETS"
reject_text "$(<"$DEVCONTAINER_JUSTFILE")" 'docker.sock'
reject_text "$(<"$DEVCONTAINER_JUSTFILE")" '/var/lib/glo-secrets'
reject_text "$(<"$DEVCONTAINER_JUSTFILE")" '/run/user/'
reject_text "$(<"$DEVCONTAINER_JUSTFILE")" 'GLO_SECRETS'
reject_text "$(<"$DEVCONTAINER_JUSTFILE")" 'glo-secrets'
reject_text "$(<"$DEVCONTAINER_JUSTFILE")" 'LoadCredentialEncrypted='
reject_text "$(<"$DEVCONTAINER_JUSTFILE")" 'systemd-run'
reject_text "$(<"$DEVCONTAINER_JUSTFILE")" 'systemctl'
reject_text "$(<"$GLO_SECRETS")" 'systemd-run'
reject_text "$(<"$GLO_SECRETS")" 'systemctl'
reject_text "$(<"$GLO_LOCAL")" 'secrets-service'
reject_text "$(<"$GLO_LOCAL")" 'glo-secrets-broker'
application_name='var''pane'
if find "$GLO_DIR" \
    -type d \( -name .git -o -name .venv -o -name __pycache__ \) -prune -o \
    -type f -print0 | xargs -0 grep -Il -- "$application_name" >/dev/null; then
    fail 'Glo contains an application-specific repository name'
fi

if missing_provider_output="$("$GLO_SECRETS" build -- /lib/example unit 2>&1)"; then
    fail "Build without a runtime provider unexpectedly succeeded"
fi
require_text "$missing_provider_output" 'a user-level provider alias is required'

python3 -B "$GLO_DIR/test/secrets-cli.py"

if [[ "$(uname -s)" == "Linux" && -r /etc/arch-release ]]; then
    direct_output="$($GLO_LOCAL --dry-run secretspec 2>&1)"
    require_text "$direct_output" 'Installing SecretSpec'
    case "$(uname -m)" in
        x86_64)
            require_text "$direct_output" 'secretspec-x86_64-unknown-linux-gnu.tar.xz'
            ;;
        aarch64)
            require_text "$direct_output" 'secretspec-aarch64-unknown-linux-gnu.tar.xz'
            ;;
        *) fail "Unsupported test architecture: $(uname -m)" ;;
    esac
    require_text "$direct_output" 'gnome-keyring'
    reject_text "$direct_output" 'rustup'
    reject_text "$direct_output" 'cargo '

    workspace="$TEST_ROOT/workspace"
    mkdir -p "$workspace/.devcontainer"
    printf '%s\n' \
        '{' \
        '  "build": {' \
        '    "args": {' \
        '      "RUST_ENABLED": "0",' \
        '      "HASKELL_ENABLED": "0",' \
        '      "WASM_GHC_ENABLED": "0",' \
        '      "PURESCRIPT_ENABLED": "0",' \
        '      "SECRETSPEC_ENABLED": "1"' \
        '    }' \
        '  }' \
        '}' > "$workspace/.devcontainer/devcontainer.json"
    need_output="$(cd "$workspace" && "$GLO_LOCAL" --dry-run need 2>&1)"
    require_text "$need_output" 'Installing SecretSpec'

    sed -i 's/"SECRETSPEC_ENABLED": "1"/"SECRETSPEC_ENABLED": "0"/' \
        "$workspace/.devcontainer/devcontainer.json"
    disabled_output="$(cd "$workspace" && "$GLO_LOCAL" --dry-run need 2>&1)"
    require_text "$disabled_output" 'Skipping SecretSpec; SECRETSPEC_ENABLED is disabled'
    reject_text "$disabled_output" 'secretspec-x86_64-unknown-linux-gnu.tar.xz'

fi

fake_bin="$TEST_ROOT/fake-bin"
mkdir -p "$fake_bin"
# shellcheck disable=SC2016  # Generated helper must expand these at runtime.
printf '%s\n' \
    '#!/usr/bin/env bash' \
    'case "${1:-}" in' \
    '    -s) printf "%s\\n" "$GLO_TEST_UNAME_SYSTEM" ;;' \
    '    -m) printf "%s\\n" "$GLO_TEST_UNAME_MACHINE" ;;' \
    '    *) exec /usr/bin/uname "$@" ;;' \
    'esac' > "$fake_bin/uname"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$fake_bin/brew"
chmod 755 "$fake_bin/uname" "$fake_bin/brew"

macos_x64_output="$(env \
    PATH="$fake_bin:$PATH" \
    GLO_TEST_UNAME_SYSTEM=Darwin \
    GLO_TEST_UNAME_MACHINE=x86_64 \
    "$GLO_LOCAL" --dry-run secretspec 2>&1)"
require_text "$macos_x64_output" 'secretspec-x86_64-apple-darwin.tar.xz'

macos_arm64_output="$(env \
    PATH="$fake_bin:$PATH" \
    GLO_TEST_UNAME_SYSTEM=Darwin \
    GLO_TEST_UNAME_MACHINE=arm64 \
    "$GLO_LOCAL" --dry-run secretspec 2>&1)"
require_text "$macos_arm64_output" 'secretspec-aarch64-apple-darwin.tar.xz'

help_output="$($GLO_LOCAL --help 2>&1)"
require_text "$help_output" 'Install checksummed SecretSpec'

printf '[OK] SecretSpec tooling checks passed\n'
