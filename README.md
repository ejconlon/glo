# glo

A small build, issue, notes, and agent workspace toolkit.

## Install In A Workspace

From the root of your git workspace:

1. `git submodule add https://github.com/ejconlon/glo.git submodules/glo`
2. `./submodules/glo/bootstrap.sh`
3. `just shell`

`bootstrap.sh` creates the devcontainer config, `bin/glo*` wrappers, `base/`, `.glo/build`, and a workspace `justfile`.

## Existing Workspace

If the workspace already has glo as a submodule:

1. `git submodule update --init --recursive`
2. `./submodules/glo/bootstrap.sh`

Run `glo readme` inside the devcontainer for the full tool reference.

For host-local dependencies, run `bin/glo-local --dry-run all` to inspect the installer, then run the specific subcommands you need. `glo-local` supports Arch Linux via `pacman` and macOS via `brew`.
