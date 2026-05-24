# /opt/glo

Developer tools installed in this container.

## Setup

All scripts resolve the workspace root by walking up from `$PWD` to find the nearest `.git` directory.

## Scripts (`/opt/glo/bin/`)

All scripts are on `PATH`. Use `glo <command>` as a dispatcher or invoke scripts directly.

### glo

Dispatcher for all glo tools.

```
glo issue [args]       # run glo-issue
glo agent [args]       # run glo-agent
glo build [args]       # run glo-build
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
glo-agent focus pop           # pop top ticket (marks open, removes assignment)
glo-agent focus list          # show focus stack, top first
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
| `py` | uv, ruff, mypy, pytest | `.venv/<name>/` via `UV_PROJECT_ENVIRONMENT` |
| `ps` | spago, purs, purs-tidy | `.venv/<name>/node_modules` via `PS_NODE_MODULES` |
| `hs` | cabal, fourmolu, hlint | `.venv/<name>/cabal`, `.venv/<name>/dist-newstyle` |
| `rs` | cargo, rustfmt, clippy | `.venv/<name>/target` via `CARGO_TARGET_DIR` |
| `ts` | npm, tsc, eslint, prettier, jest | `.venv/<name>/node_modules` via `TS_NODE_MODULES` |
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

## Library (`/opt/glo/lib/`)

Contains the `glo_build` Python package used by `glo-build`. Symlinked into each workspace as `lib/`.
