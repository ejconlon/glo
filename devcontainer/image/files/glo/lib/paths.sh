# shellcheck shell=bash
# Shared notebook path resolution for Glo commands and bootstrap.

# Print the selected base path without requiring the directory to exist.
# Relative GLO_BASE values are rooted at the supplied workspace, not the cwd.
glo_base_dir() {
    local base="${GLO_BASE:-base}"
    if [[ "$base" != /* ]]; then
        base="${1%/}/$base"
    fi
    while [[ "$base" != / && "$base" == */ ]]; do
        base="${base%/}"
    done
    printf '%s\n' "$base"
}
