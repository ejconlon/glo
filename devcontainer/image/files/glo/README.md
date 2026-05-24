# /opt/glo

Developer tools installed in this container.

## Setup

Run `bootstrap.sh` from the root of a git workspace. It creates:

- `.devcontainer/devcontainer.json`
- `.devcontainer/image`, a relative symlink to the glo devcontainer image directory
- `.glo/build`, the host-side `glo_build` venv
- `bin/glo*`, wrapper scripts that use `/opt/glo/bin` in the container and the checkout copy on the host
- `base/issue/`, `base/wiki/`, and `base/.zk/`
- `lib/build`, a relative symlink to the `glo_build` source package
- `justfile`, with `shell` and `precommit` recipes

After bootstrapping, run `just shell` from the workspace root to start an interactive devcontainer shell. The generated workspace `justfile` passes the workspace path to `devcontainer/justfile`; nested `just` calls preserve that path through `GLO_WORKSPACE`.

The whole `/opt/glo/lib` directory is not symlinked into workspaces. Only `lib/build` is linked, because `glo-build` needs the `glo_build` Python package source.

Most scripts resolve the workspace root by walking up from `$PWD` to find the nearest `.git` directory.

## Scripts (`/opt/glo/bin/`)

All scripts are on `PATH`. Use `glo <command>` as a dispatcher or invoke scripts directly.

### glo

Dispatcher for all glo tools.

```
glo issue [args]       # run glo-issue
glo agent [args]       # run glo-agent
glo build [args]       # run glo-build
glo gen [args]         # run glo-gen
glo notes [args]       # run glo-notes
glo readme             # print this file
glo help               # list commands
```

### glo-issue

Minimal ticket system with dependency tracking. Tickets are stored as Markdown files in `base/issue/`. Each ticket has a YAML frontmatter block with `id`, `status`, `priority`, `assignee`, `deps`, and `links` fields, followed by a Markdown body.

```
glo-issue create [title] [options]   # create a ticket, prints ID
glo-issue ls [--status=X] [-a X]    # list tickets
glo-issue ready                      # list tickets with all deps closed
glo-issue blocked                    # list tickets with unresolved deps
glo-issue show <id>                  # display ticket with context
glo-issue start <id>                 # set status to in_progress
glo-issue close <id>                 # set status to closed
glo-issue dep <id> <dep-id>          # declare that id depends on dep-id
glo-issue dep tree <id>              # show dependency tree
glo-issue link <id> <id>             # link two tickets (symmetric)
glo-issue add-note <id> [text]       # append timestamped note
glo-issue query [jq-filter]          # output tickets as JSON
```

Supports partial ID matching — `glo-issue show abc` matches any ticket whose ID contains `abc`. Override the ticket directory with `TICKETS_DIR`.

### glo-agent

Agent-aware wrapper around `glo-issue` with a focus stack. Set `AGENT_NAME` to scope focus state and issue ownership to a named agent. Without `AGENT_NAME` it behaves as a thin passthrough with focus commands disabled.

Focus state is stored in `.glo/agent/$AGENT_NAME/focus` — a plain text stack of ticket IDs, newest at the bottom.

```
glo-agent focus push <id>     # push ticket onto stack (marks in_progress, assigns to self)
glo-agent focus pop           # pop top ticket and marks it open
glo-agent focus list          # show focus stack
glo-agent focus get           # print current focus ID
glo-agent focus show          # display current focus ticket
glo-agent focus create [title]  # create ticket and push it
glo-agent focus ready           # push next ready ticket

glo-agent issue list          # table view of all issues with age and assignee
glo-agent issue create [title] [--unassigned]  # create (auto-assigns to AGENT_NAME)
glo-agent issue start <id>    # start issue (in_progress + assign to self)
glo-agent issue close <id>    # close issue (must be assigned to self)
glo-agent issue pause <id>    # return to open, remove from stack
glo-agent issue ready [--all] # list ready issues (default: assigned to self or unassigned)
glo-agent issue blocked [--all]
glo-agent issue show <id>
glo-agent issue add-note <id> [text]
glo-agent issue block <id> <blocker-id>
glo-agent issue link <id> <id>
glo-agent issue assign <id> <name>
glo-agent issue unassign <id>

glo-agent precommit           # run glo-build --filter=work precommit
```

Most mutating commands accept `--force` to override ownership checks.

### glo-gen

Generates a new `lib/` component from a cookiecutter template in `/opt/glo/templates/`. Output is written into `lib/` at the workspace root.

```
glo-gen <type> [cookiecutter-args]
```

Available types (all generate `build.json` for glo-build discovery):

- `meta` — build/config component; `language: meta`
- `py` — Python package (`pyproject.toml`, hatchling); `language: py`
- `ps` — PureScript library (`spago.yaml`, `package.json`); `language: ps`
- `hs` — Haskell library (`*.cabal`, `src/Lib.hs`, GHC2021); `language: hs`
- `rs` — Rust crate (`Cargo.toml`, `src/lib.rs`); `language: rs`
- `ts` — TypeScript package (`package.json`, `tsconfig.json`); `language: ts`

Cookiecutter is provided by the `glo_build` venv — the same venv priority as `glo-build` (`.glo/build/` first, then `/opt/glo/.venv`).

### glo-notes

zk notebook wrapper for `base/`. Manages the zk index and generates Markdown index files; also archives closed issues on precommit. Requires `zk` and `sqlite3` on `PATH`.

```
glo-notes index          # run zk index + regenerate TITLES.md and TAGS.md
glo-notes precommit      # archive closed issues, unarchive open ones, then index
glo-notes <zk-cmd>       # passed through to zk with ZK_NOTEBOOK_DIR=base/
```

The `base/` directory is a zk notebook with two groups:

- `issue/` — zk-tracked issue notes (status-based archiving on precommit)
- `wiki/` — zk-tracked wiki notes

`bootstrap.sh` creates `base/.zk/config.toml` and `base/.zk/templates/` from the glo scaffold. The `notebook.db` sqlite index is gitignored.

Index files (`TITLES.md`, `TAGS.md`) are generated per-group and at the `base/` root.

### glo-build

Lightweight build system backed by the `glo_build` Python package in `lib/build/`. Separates planning (Python) from execution (shell script) so build plans can be inspected before running.

```
glo-build [mode] <target> [args]
```

Execution mode flags (can be combined for split plan/exec):

```
--local           plan and execute locally (default outside container)
--docker          plan and execute in Docker
--plan-local / --plan-docker    control where planning runs
--exec-local / --exec-docker    control where execution runs
```

The build venv is resolved in priority order: `.glo/build/` in the workspace (local override), then `/opt/glo/.venv` (image default), creating one if neither exists.

Projects are discovered by finding `build.json` files under `lib/`. Each `build.json` must have a `language` field; optional fields are `py_package`, `extra_deps`, `targets`, and `enabled`.

**Supported languages:**

| language | tools | venv isolation |
|----------|-------|----------------|
| `py` | uv, ruff, mypy, pytest | `.glo/venv/<name>/` via `UV_PROJECT_ENVIRONMENT` |
| `ps` | spago, purs, purs-tidy | `.glo/venv/<name>/node_modules` via `PS_NODE_MODULES` |
| `hs` | cabal, fourmolu, hlint | `.glo/venv/<name>/cabal`, `.glo/venv/<name>/dist-newstyle` |
| `rs` | cargo, rustfmt, clippy | `.glo/venv/<name>/target` via `CARGO_TARGET_DIR` |
| `ts` | npm, tsc, eslint, prettier, jest | `.glo/venv/<name>/node_modules` via `TS_NODE_MODULES` |
| `meta` | custom targets only | — |

**Common commands** (run on all projects or a selection):

```
glo-build venv                   # sync/fetch dependencies
glo-build format                 # format code
glo-build lint                   # lint code
glo-build typecheck              # type/static check
glo-build unit                   # run unit tests
glo-build test                   # typecheck + unit
glo-build precommit              # gen + format + lint + test
glo-build clean                  # remove build artifacts and venv
```

**Project selection:**

```
glo-build /lib/foo format        # single project by path
glo-build /py format             # all Python projects
glo-build /rs lint               # all Rust projects
glo-build /ts typecheck          # all TypeScript projects
glo-build /hs unit               # all Haskell projects
glo-build /ps format             # all PureScript projects
glo-build /                      # all projects
glo-build /py ^/py/core format   # all Python except /lib/core
glo-build precommit ^test        # precommit without test subtargets
```

## Library Source

The image contains the packaged glo tooling under `/opt/glo/`. In a bootstrapped workspace, `lib/build` is a relative symlink to the `glo_build` source package from the glo checkout. The rest of `/opt/glo/lib` is not linked into the workspace.
