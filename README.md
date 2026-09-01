# glo

A small build, issue, notes, and agent workspace toolkit.

## Install In A Workspace

From the root of your git workspace:

1. `git submodule add https://github.com/ejconlon/glo.git submodules/glo`
2. `./submodules/glo/bootstrap.sh`
3. `just image`
4. `just shell`

Host container commands default to Docker on macOS and Podman on other
supported hosts. Set `GLO_CONTAINER_ENGINE` to `docker` or `podman` to override
the platform default. The same selection is passed to the Dev Container CLI
and all direct lifecycle commands; Podman builds use its native builder instead
of Docker Buildx.

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
`glo postgres run` owns the same cluster as a foreground container process.
`eval "$(glo postgres env)"` exports `GLO_POSTGRES_URL`; map that value to the
project's own test configuration rather than making application code depend on
Glo. Use `glo postgres status`, `url`, and `stop` for the remaining lifecycle.
The fixed `glo:glo` credential and `glo_test` database are strictly for local,
loopback-only testing.

From the host, `bin/glo-postgres --container start` runs the same helper from an
enabled `devcontainer-WORKSPACE` image through the selected engine and
publishes only the loopback port.
Set `GLO_POSTGRES_ROOT` to an absolute host directory such as
`$PWD/temp/run/postgres`; the engine bind-mounts it so cluster files survive
the container's removal. Image and container names can be overridden with
`GLO_POSTGRES_CONTAINER_IMAGE` and `GLO_POSTGRES_CONTAINER_NAME`.

## Optional Caddy

The generated devcontainer sets `CADDY_ENABLED` to `0`. Set it to `1` to
build the pinned Caddy release with the pinned `caddy-l4` module. The build uses
a temporary checksummed Go toolchain. It downloads Caddy, `caddy-l4`, and
`xcaddy` as exact commit-SHA source archives, verifies each archive against its
pinned SHA-256 digest, and supplies the extracted Caddy sources to `xcaddy` as
local module replacements. No mutable tag or branch selects source at build
time, and neither the Go toolchain nor `xcaddy` is retained in the image. The
feature installs no configuration or service and starts no background process;
projects supply their own configuration and run it in the foreground with
`glo caddy run`.

## Optional Garage

The generated devcontainer also sets `GARAGE_ENABLED` to `0`. Set it to `1` to
install the pinned, SHA-256-verified Garage release binary for the image
architecture. The feature installs no configuration or service and starts no
background process. `glo garage run` requires an absolute
`GARAGE_CONFIG_FILE` and owns Garage's single-node development process in the
foreground for container use.

For host-local dependencies, run `bin/glo-local --dry-run all` to inspect the installer, then run the specific subcommands you need. `glo-local` supports Arch Linux via `pacman` and macOS via `brew`.
