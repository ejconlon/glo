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

## Optional PostgreSQL 18

The generated devcontainer sets `POSTGRES_ENABLED` to `0`, so the base image
contains no PostgreSQL client, server, development packages, initialized data,
or background service. Set the build argument to `1` when a workspace needs
local PostgreSQL integration tests:

```json
"build": {
  "args": {
    "POSTGRES_ENABLED": "1"
  }
}
```

Inside an enabled container, `glo postgres start` lazily initializes and starts
a disposable PostgreSQL 18 cluster listening only on `127.0.0.1:55432`.
`eval "$(glo postgres env)"` exports `GLO_POSTGRES_URL`; map that value to the
project's own test configuration rather than making application code depend on
Glo. Use `glo postgres status`, `url`, and `stop` for the remaining lifecycle.
The fixed `glo:glo` credential and `glo_test` database are strictly for local,
loopback-only testing.

For host-local dependencies, run `bin/glo-local --dry-run all` to inspect the installer, then run the specific subcommands you need. `glo-local` supports Arch Linux via `pacman` and macOS via `brew`.
