# glo Agent Guide

Use glo to manage work in this repository: issues, agent focus, builds, generated libraries, and notes.

## Core Rules

- Run commands from inside the workspace git repository.
- The workspace root is the nearest parent directory containing `.git`.
- Inside the devcontainer, prefer `glo`, `glo-agent`, `glo-build`, `glo-issue`, `glo-gen`, `glo-local`, and `glo-notes` directly; `/opt/glo/bin` is on `PATH`.
- `bin/glo*` wrappers also work in bootstrapped workspaces and are used by generated `justfile` recipes.
- Do not edit `.glo/` directly unless debugging glo itself; it is generated state.
- Use issues for durable task state. Use notes for longer-lived project knowledge.

## Workspace Layout

Bootstrapped workspaces normally contain:

- `base/issue/`: Markdown issues managed by `glo-issue` and `glo-agent`.
- `base/wiki/`: project notes managed through `glo-notes`/`zk`.
- `base/.zk/`: zk notebook config and templates.
- `lib/`: buildable project components.
- `.glo/build`: host-side venv for glo tooling.
- `.glo/venv/<project>`: per-project build/dependency state.
- `.glo/agent/<agent>/focus`: per-agent focus stack.
- `bin/glo*`: wrappers that use `/opt/glo/bin` in the container and checkout scripts on the host.

`glo-build` uses the glo installation path for its own implementation (`/opt/glo/lib/build` in the container, or the checkout-relative path on the host). Workspaces do not need a `lib/build` symlink.

## Starting Work

If you have an assigned task, create or choose an issue first.

```sh
glo-agent issue ready
glo-agent issue create "Short task title"
glo-agent focus push <issue-id>
```

If `AGENT_NAME` is set, `glo-agent` tracks ownership and focus under `.glo/agent/$AGENT_NAME/`. Devcontainer lifecycle commands set `AGENT_NAME` automatically for agent sessions.

Use `--force` only when intentionally overriding another agent's ownership.

## Issues

Issues are Markdown files in `base/issue/` with YAML frontmatter. IDs are generated from title plus a short hash. Most commands accept partial IDs when unambiguous.

Common commands:

```sh
glo-issue create "Title"                  # create issue, print ID
glo-issue ls                              # list issues
glo-issue ready                           # list open/in-progress issues with closed deps
glo-issue blocked                         # list issues blocked by open deps
glo-issue show <id>                       # show issue plus related context
glo-issue start <id>                      # status: in_progress
glo-issue close <id>                      # status: closed
glo-issue status <id> open                # set explicit status
glo-issue dep <id> <blocker-id>           # make id depend on blocker-id
glo-issue undep <id> <blocker-id>         # remove dependency
glo-issue dep tree <id>                   # show dependency tree
glo-issue dep cycle                       # detect dependency cycles
glo-issue link <id> <other-id>            # symmetric relation, not blocking
glo-issue unlink <id> <other-id>          # remove relation
glo-issue add-note <id> "Update"          # append timestamped note
glo-issue set-assignee <id> <name>        # assign
glo-issue set-assignee <id>               # clear assignee
glo-issue query                           # emit JSON lines
```

Use dependencies for blocking relationships. Use links for related work that does not block progress.

## Agent Focus

Use `glo-agent` when acting as an agent. It wraps issue operations with ownership checks and a focus stack.

```sh
glo-agent focus push <id>                 # start issue, assign to self, push focus
glo-agent focus pop                       # pop current issue, mark it open
glo-agent focus list                      # show focus stack
glo-agent focus get                       # print current issue ID
glo-agent focus show                      # show current issue
glo-agent focus close                     # close current issue and remove from stack
glo-agent focus add-note "Update"         # note current issue
glo-agent focus create "Title"            # create issue and focus it
glo-agent focus ready                     # focus next ready issue
```

Issue commands through `glo-agent`:

```sh
glo-agent issue list
glo-agent issue create "Title"            # assigns to AGENT_NAME by default
glo-agent issue create --unassigned "Title"
glo-agent issue ready                     # assigned-to-self or unassigned
glo-agent issue ready --all               # no ownership filter
glo-agent issue blocked
glo-agent issue blocked --all
glo-agent issue start <id>
glo-agent issue pause <id>
glo-agent issue close <id>
glo-agent issue show <id>
glo-agent issue add-note <id> "Update"
glo-agent issue block <id> <blocker-id>
glo-agent issue link <id> <other-id>
glo-agent issue assign <id> <name>
glo-agent issue unassign <id>
```

Typical agent loop:

```sh
glo-agent issue ready
glo-agent focus push <id>
# do the work
glo-agent focus add-note "Implemented X; validating Y"
glo-agent precommit
glo-agent focus close
```

## Builds

`glo-build` discovers projects by scanning `lib/**/build.json`. Each project declares a `language`; optional fields include `py_package`, `extra_deps`, `targets`, and `enabled`.

Common commands:

```sh
glo-build                         # list commands/projects
glo-build venv                    # sync/fetch dependencies
glo-build format                  # format all projects
glo-build lint                    # lint all projects
glo-build typecheck               # static checks
glo-build unit                    # unit tests
glo-build test                    # typecheck + unit
glo-build precommit               # gen + format + lint + test
glo-build clean                   # remove build artifacts and project venvs
```

Select projects and languages:

```sh
glo-build /                       # all projects
glo-build /lib/foo format         # one project by path
glo-build /py test                # all Python projects
glo-build /rs lint                # all Rust projects
glo-build /ts typecheck           # all TypeScript projects
glo-build /hs unit                # all Haskell projects
glo-build /ps format              # all PureScript projects
glo-build /py ^/lib/core test     # exclude a project
glo-build precommit ^test         # precommit without test subtargets
```

Mode flags:

```sh
glo-build --local precommit       # plan and execute locally
glo-build --docker precommit      # plan and execute in Docker
glo-build --plan-local --exec-docker precommit
glo-build --plan-docker --exec-local precommit
```

Inside a container, docker mode is forced back to local mode.

Build state locations:

- `.glo/build`: glo tooling venv in the workspace.
- `/opt/glo/.venv`: image-provided glo tooling venv.
- `.glo/venv/<project>`: project-specific dependency/build state.

Language isolation:

| language | tools | state |
|----------|-------|-------|
| `py` | uv, ruff, mypy, pytest | `.glo/venv/<name>/` |
| `ps` | spago, purs, purs-tidy | `.glo/venv/<name>/node_modules`, outputs |
| `hs` | cabal, fourmolu, hlint | `.glo/venv/<name>/cabal`, `dist-newstyle` |
| `rs` | cargo, rustfmt, clippy | `.glo/venv/<name>/target` |
| `ts` | npm, tsc, eslint, prettier, jest | `.glo/venv/<name>/node_modules` |
| `meta` | custom targets | custom |

## Generating Components

Use `glo-gen` to create a new `lib/` component from templates.

```sh
glo-gen TEMPLATE_NAME SUBPROJECT_NAME
glo-gen py my_package
glo-gen rs my_crate
```

Template types:

- `meta`: build/config component.
- `py`: Python package.
- `ps`: PureScript package.
- `hs`: Haskell package.
- `rs`: Rust crate.
- `ts`: TypeScript package.

Generated projects include `build.json` so `glo-build` can discover them.

## Notes

`glo-notes` wraps `zk` for the `base/` notebook.

```sh
glo-notes index                  # update zk index and generated indexes
glo-notes precommit              # archive closed issues, unarchive open ones, index
glo-notes <zk-cmd>               # pass through to zk with ZK_NOTEBOOK_DIR=base/
```

Notes layout:

- `base/issue/`: issue notes; closed issues are archived by `glo-notes precommit`.
- `base/wiki/`: project wiki notes.
- `base/**/TITLES.md`: generated title index.
- `base/**/TAGS.md`: generated tag index.

The SQLite index at `base/.zk/notebook.db` is generated and gitignored.

## Workspace `justfile`

Bootstrapped workspaces get a small `justfile`:

```sh
just shell                       # start an interactive devcontainer shell
just precommit                   # run build precommit and notes precommit
```

`just shell` delegates to glo's `devcontainer/justfile` and passes the workspace path explicitly. Nested `just` calls preserve it through `GLO_WORKSPACE`.

## Local Host Tooling

Use `glo-local` outside the devcontainer when you want the host OS to have the same toolchain families as the image. It detects Arch Linux or macOS and installs packages with `pacman` or `brew`. Haskell and Rust versions are pinned to the image versions.

```sh
glo-local doctor                  # show detected OS/arch and installed tools
glo-local --dry-run all           # print install commands without running them
glo-local base                    # common CLI tools
glo-local py                      # Python and uv
glo-local rs                      # Rust 1.95.0 + rustfmt/clippy/rust-analyzer/rust-src
glo-local hs                      # GHC 9.12.4, cabal 3.16.1.0, stack 3.9.3, HLS 2.14.0.0, ormolu, hlint via ghcup
glo-local ts                      # Node/npm
glo-local ps                      # PureScript tooling via npm
glo-local notes                   # zk/sqlite
```

`glo local ...` is equivalent to `glo-local ...`.

## When Finishing Work

Before handing off:

```sh
glo-agent focus add-note "Summary of changes and validation"
glo-agent precommit
glo-agent focus close
```

If work is incomplete, leave the issue open and add a note with the blocker or next step.
