# /opt/glo

Developer tools installed in this container.

## Setup

Run once from your project root (which must contain a `.git` directory):

```
glo-bootstrap
```

This creates `notes/issue/` for issue tracking and symlinks `lib/` to `/opt/glo/lib`.

All scripts resolve the workspace root by walking up from `$PWD` to find the nearest `.git` directory.

## Scripts (`/opt/glo/`)

All scripts are on `PATH`.

### glo-bootstrap

Initializes a workspace. Creates:
- `notes/issue/` — issue tracker storage
- `lib/` → `/opt/glo/lib` — symlink to build library

### glo-issue

Minimal ticket system with dependency tracking. Tickets are stored as Markdown files in `notes/issue/`.

```
glo-issue <command> [args]
```

Key commands: `create`, `start`, `close`, `ls`, `ready`, `blocked`, `show`, `dep`, `link`

Override ticket directory with `TICKETS_DIR` env var.

### glo-agent

Agent-aware wrapper around `glo-issue` with a focus stack and build integration. Set `AGENT_NAME` to scope issues and focus to a named agent.

```
glo-agent focus push <id>    # start working on an issue
glo-agent focus pop          # pause current issue
glo-agent issue list         # list all issues
glo-agent issue create       # create an issue (auto-assigned to AGENT_NAME)
glo-agent precommit          # run build precommit checks
```

### glo-build

Lightweight build system backed by the `loupe_build` Python package in `lib/build/`.

```
glo-build [--local|--docker] <target> [args]
```

Manages a Python venv at `.venv/build/` in the workspace. Can run builds locally or inside Docker.

## Library (`/opt/glo/lib/`)

Contains the `loupe_build` Python package used by `glo-build`. Symlinked into each workspace as `lib/` by `glo-bootstrap`.
