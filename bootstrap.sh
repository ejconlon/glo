#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$PWD"
PROJECT_NAME="$(basename "$WORKSPACE_DIR")"

echo "[I] Bootstrapping devcontainer for project: $PROJECT_NAME"
echo "[I] Workspace: $WORKSPACE_DIR"

mkdir -p "${WORKSPACE_DIR}/.devcontainer"

# Generate devcontainer.json from template, substituting the project name
sed "s/\"datatone\"/\"${PROJECT_NAME}\"/" \
    "${SCRIPT_DIR}/template/devcontainer.json" \
    > "${WORKSPACE_DIR}/.devcontainer/devcontainer.json"
echo "[I] Generated .devcontainer/devcontainer.json"

# Symlink image directory using a relative path for portability
if [[ ! -e "${WORKSPACE_DIR}/.devcontainer/image" ]]; then
    IMAGE_REL="$(realpath --relative-to="${WORKSPACE_DIR}/.devcontainer" "${SCRIPT_DIR}/devcontainer/image")"
    ln -sf "$IMAGE_REL" "${WORKSPACE_DIR}/.devcontainer/image"
    echo "[I] Created .devcontainer/image -> $IMAGE_REL"
else
    echo "[I] .devcontainer/image already exists, skipping"
fi

# Create the local glo build venv at .glo/build
GLO_BUILD_VENV="${WORKSPACE_DIR}/.glo/build"
if [[ ! -x "${GLO_BUILD_VENV}/bin/python3" ]]; then
    echo "[I] Creating .glo/build venv"
    mkdir -p "${WORKSPACE_DIR}/.glo"
    UV_PROJECT_ENVIRONMENT="$GLO_BUILD_VENV" \
        uv sync --project "${SCRIPT_DIR}/devcontainer/image/files/glo/lib/build" \
        --package glo_build --frozen
    echo "[I] Created .glo/build venv"
else
    echo "[I] .glo/build venv already exists, skipping"
fi

# Symlink glo scripts into bin/
mkdir -p "${WORKSPACE_DIR}/bin"
for script in "${SCRIPT_DIR}/devcontainer/image/files/glo/bin"/*; do
    name="$(basename "$script")"
    dest="${WORKSPACE_DIR}/bin/${name}"
    if [[ ! -e "$dest" ]]; then
        rel="$(realpath --relative-to="${WORKSPACE_DIR}/bin" "$script")"
        ln -sf "$rel" "$dest"
        echo "[I] Created bin/${name} -> $rel"
    else
        echo "[I] bin/${name} already exists, skipping"
    fi
done

# Scaffold base/ workspace directories
if [[ ! -d "${WORKSPACE_DIR}/base/issue" ]]; then
    mkdir -p "${WORKSPACE_DIR}/base/issue"
    echo "[I] Created base/issue/"
else
    echo "[I] base/issue/ already exists, skipping"
fi

# Add generated paths to .gitignore
add_to_gitignore() {
    local entry="$1"
    local file="${WORKSPACE_DIR}/.gitignore"
    if ! grep -qxF "$entry" "$file" 2>/dev/null; then
        echo "$entry" >> "$file"
        echo "[I] Added $entry to .gitignore"
    fi
}

add_to_gitignore ".glo/"
add_to_gitignore "bin/"

echo "[I] Done. To build: just -f ${SCRIPT_DIR}/devcontainer/justfile build"
