#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$PWD"
PROJECT_NAME="$(basename "$WORKSPACE_DIR")"

relpath() {
    local from="$1"
    local to="$2"
    if command -v grealpath >/dev/null 2>&1; then
        grealpath --relative-to="$from" "$to"
    elif realpath --relative-to="$from" "$to" >/dev/null 2>&1; then
        realpath --relative-to="$from" "$to"
    else
        python3 -c 'import os, sys; print(os.path.relpath(os.path.realpath(sys.argv[2]), os.path.realpath(sys.argv[1])))' "$from" "$to"
    fi
}

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
    IMAGE_REL="$(relpath "${WORKSPACE_DIR}/.devcontainer" "${SCRIPT_DIR}/devcontainer/image")"
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

# Create glo wrappers in bin/. Symlinks to the host checkout are dangling inside
# the devcontainer, where the image-provided tools live under /opt/glo/bin.
mkdir -p "${WORKSPACE_DIR}/bin"
for script in "${SCRIPT_DIR}/devcontainer/image/files/glo/bin"/*; do
    name="$(basename "$script")"
    dest="${WORKSPACE_DIR}/bin/${name}"
    if [[ ! -e "$dest" || -L "$dest" ]] || grep -q "exec /opt/glo/bin/${name}" "$dest" 2>/dev/null; then
        rel="$(relpath "${WORKSPACE_DIR}/bin" "$script")"
        [[ -L "$dest" ]] && rm -f "$dest"
        cat > "$dest" <<EOF
#!/usr/bin/env bash
set -euo pipefail

if [[ -x /opt/glo/bin/${name} ]]; then
    exec /opt/glo/bin/${name} "\$@"
fi

exec "\$(realpath "\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)/${rel}")" "\$@"
EOF
        chmod +x "$dest"
        echo "[I] Created bin/${name} wrapper"
    else
        echo "[I] bin/${name} already exists, skipping"
    fi
done

# Scaffold workspace directories
for _gitkeep in \
    "base/issue/.gitkeep" \
    "base/wiki/.gitkeep" \
    "lib/.gitkeep"
do
    if [[ ! -e "${WORKSPACE_DIR}/${_gitkeep}" ]]; then
        mkdir -p "${WORKSPACE_DIR}/$(dirname "$_gitkeep")"
        touch "${WORKSPACE_DIR}/${_gitkeep}"
        echo "[I] Created $(dirname "$_gitkeep")/"
    else
        echo "[I] $(dirname "$_gitkeep")/ already exists, skipping"
    fi
done

# Generate justfile from template, substituting the relative path to glo
if [[ ! -e "${WORKSPACE_DIR}/justfile" ]]; then
    GLO_REL="$(relpath "${WORKSPACE_DIR}" "${SCRIPT_DIR}")"
    sed "s|__GLO__|${GLO_REL}|g" \
        "${SCRIPT_DIR}/template/justfile" \
        > "${WORKSPACE_DIR}/justfile"
    echo "[I] Created justfile (glo at ${GLO_REL})"
else
    echo "[I] justfile already exists, skipping"
fi

# Initialize base/.zk from scaffold
BASE_ZK="${WORKSPACE_DIR}/base/.zk"
if [[ ! -e "${BASE_ZK}" ]]; then
    cp -r "${SCRIPT_DIR}/devcontainer/image/files/glo/base-scaffold/.zk" "${BASE_ZK}"
    echo "[I] Created base/.zk"
else
    echo "[I] base/.zk already exists, skipping"
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

add_to_gitignore "/.glo"
add_to_gitignore "/base/.zk/notebook.db"

echo "[I] Done. To build: just -f ${SCRIPT_DIR}/devcontainer/justfile build"
