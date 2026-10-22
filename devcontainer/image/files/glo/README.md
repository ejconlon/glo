# glo Agent Guide

Use glo to manage work in this repository: issues, agent focus, builds, generated libraries, and notes.

## Core Rules

- Run commands from inside the workspace git repository.
- Workspace lookup uses the current directory or nearest ancestor with a `.git` directory. A `.git` file, as used by linked worktrees and submodules, does not establish a workspace root.
- Inside the devcontainer, prefer `glo`, `glo-agent`, `glo-board`, `glo-build`, `glo-caddy`, `glo-garage`, `glo-issue`, `glo-gen`, `glo-local`, `glo-notes`, `glo-postgres`, and `glo-secrets` directly; `/opt/glo/bin` is on `PATH`.
- `bin/glo*` wrappers also work in bootstrapped workspaces and are used by generated `justfile` recipes. They prefer `/opt/glo/bin` when installed and otherwise use the checkout scripts.
- `glo issue ...`, `glo build ...` and the other dispatcher commands invoke their `glo-*` counterparts. `glo readme` prints this guide from the selected glo installation.
- Do not edit `.glo/` directly unless debugging glo itself; it is generated state.
- Use issues for durable task state. Use notes for longer-lived project knowledge.

## Workspace Layout

Bootstrapped workspaces normally contain the following paths. Examples in
this guide use the default `base/`; set `GLO_BASE` as described below to choose
a different notebook directory.

- `base/issue/`: Markdown issues managed by `glo-issue` and `glo-agent`.
- `base/wiki/`: project notes managed through `glo-notes`/`zk`.
- `base/.zk/`: zk notebook config and templates.
- `lib/`: buildable project components.
- `.glo/build`: host-side venv for glo tooling.
- `.glo/venv/<project>`: per-project build/dependency state.
- `.glo/agent/<agent>/focus`: per-agent focus stack.
- `bin/glo*`: wrappers that select the installed or checkout tools as described above.

`glo-build` uses the glo installation path for its own implementation (`/opt/glo/lib/build` in the container, or the checkout-relative path on the host). Workspaces do not need a `lib/build` symlink.

### Notebook directory

`GLO_BASE` selects the notebook root for `glo-issue`, `glo-board`, `glo-agent`, `glo-notes`
and `bootstrap.sh`, including commands invoked through the `glo` dispatcher.

- **Default:** Unset or empty `GLO_BASE` uses `<workspace>/base`.
- **Relative path:** `GLO_BASE=knowledge` uses `<workspace>/knowledge`, even
  when commands run from a workspace subdirectory.
- **Absolute path:** `GLO_BASE=/path/to/notebook` uses that directory directly.
- **Contents:** Issues and archives live in `issue/` and `issue/archive/`;
  wiki notes live in `wiki/`; notebook config and the database live in `.zk/`.
  Generated title and tag indexes also use the selected notebook.
- **Bootstrap:** Reads `GLO_BASE` from its environment and scaffolds the
  selected directory. It does not save the value in generated wrappers. It
  adds the selected database path to the workspace's `.gitignore` when the
  notebook is inside the workspace.
- **Issue-only override:** Direct `glo-issue` calls still honor `TICKETS_DIR`
  ahead of `GLO_BASE/issue`. Agent and notes workflows use their selected
  notebook's `issue/` directory, regardless of an ambient `TICKETS_DIR`.

For example, from the workspace root:

```sh
export GLO_BASE="knowledge base"
./submodules/glo/bootstrap.sh
./bin/glo issue ls
./bin/glo notes zk list
```

Keep `GLO_BASE` set in the environment where later commands run, including
inside a devcontainer when using one. Selecting a different path does not
move existing notes or issues. Agent focus and build state remain under the
workspace's `.glo/` directory.

## Starting Work

If you have an assigned task, create or choose an issue first.

```sh
glo-agent issue ready
glo-agent issue create "Short task title"
glo-agent focus push <issue-id>
```

`glo-agent` tracks ownership and focus under `.glo/agent/$AGENT_NAME/`. It defaults `AGENT_NAME` to `agent`; devcontainer lifecycle commands set a more specific name automatically for agent sessions.

Use `--force` only when intentionally overriding another agent's ownership.

## Issues

Issues are Markdown files with YAML frontmatter in the selected notebook's
`issue/` directory (default `base/issue/`). IDs are generated from title plus
a short hash. Most commands accept partial IDs when unambiguous.
`TICKETS_DIR` overrides the issue directory for direct `glo-issue` calls.

`ls`, `ready`, `blocked`, `closed` and `query` select issues directly in the
active issue directory by default. Add `--with-archived` to select from both
that directory and `archive/`, or `--only-archived` to select only archived issues.
Commands that address an issue by ID, such as `show` and `set`, always find
issues in both locations. Dependencies and other relationships also resolve
across both locations, regardless of listing scope or attribute filters.

Common commands:

```sh
glo-issue create "Title"                  # create issue, print ID
glo-issue ls                              # list issues
glo-issue ready                           # open/in-progress with no unresolved deps
glo-issue blocked                         # open/in-progress with unresolved deps
glo-issue closed                          # recently modified closed issues, before archiving
glo-issue closed --with-archived           # include archived history
glo-issue show <id>                       # show issue plus related context
glo-issue start <id>                      # status: in_progress
glo-issue icebox <id>                     # status: icebox (deferred, incomplete)
glo-issue close <id>                      # status: closed
glo-issue archive <id>                    # move a closed/iceboxed issue to archive/
glo-issue unarchive <id>                  # restore the file, preserving its status
glo-issue status <id> open                # set explicit status
glo-issue dep <id> <blocker-id>           # make id depend on blocker-id
glo-issue undep <id> <blocker-id>         # remove dependency
glo-issue dep tree <id>                   # show dependency tree
glo-issue dep cycle                       # detect dependency cycles
glo-issue link <id> <other-id>            # symmetric relation, not blocking
glo-issue unlink <id> <other-id>          # remove relation
glo-issue add-note <id> "Update"          # append timestamped note
glo-issue set <id> plan=accept            # add or update an attribute
glo-issue set-assignee <id> <name>        # assign
glo-issue set-assignee <id>               # clear assignee
glo-issue query                           # emit JSON lines
```

Use dependencies for blocking relationships. Use links for related work that does not block progress.
Use `create --parent <epic-id>` or `set <child-id> parent=<epic-id>` to group
work under an epic. Parent membership is separate from blocking: do not put
the parent in a child's `deps` or list children in the epic's `deps` merely
to represent membership. Check the epic's children when assessing completion.
Parents resolve across active and archived issues; partial IDs are stored in
full. Missing parents, self-parenting and ancestry cycles are rejected before
writing. `set <id> parent=` clears membership and leaves dependencies unchanged.
Relationship commands accept unambiguous partial IDs and store full IDs.
`show` resolves parent, child, blocker and linked-issue context across both
locations. `dep tree` includes archived dependencies; `dep cycle` checks
non-closed issues in both locations, including iceboxed issues.

Run `glo-issue --help` or `glo-issue <top-level-command> --help` for argument
definitions, supported option forms and defaults. In listing commands:

- **Archive scope:** `--with-archived` includes active and archived issues;
  `--only-archived` selects only archived issues. Both work on `ls`, `ready`,
  `blocked`, `closed` and `query`. They cannot be combined. Without either,
  only active-directory issues are candidates.
- **Assignee:** `-a NAME` or `--assignee=NAME` selects issues assigned to NAME.
- **Tag:** `-T TAG` or `--tag=TAG` selects issues containing that whole tag.
  Uppercase `-T` filters tags; lowercase `-t` sets the type on `create`.
- **Status:** `--status=STATUS` restricts `ls` to `open`, `in_progress`,
  `icebox` or `closed`. Without it, `ls` includes all statuses in its issue set.
- **Limit:** `--limit=N` caps matching `closed` results, newest modification
  first. It defaults to 20; 0 returns no results.
- **Attribute:** `-f KEY=VALUE`, `--filter KEY=VALUE` or `--filter=KEY=VALUE`
  selects any frontmatter attribute, as described below.

Assignee and tag options apply to `ls`, `ready`, `blocked` and `closed`.
Use `--filter` for those fields on `query`. Long listing options for assignee,
tag, status and limit use `=`; creation options take separate values, such as
`create "Title" --assignee agent --tags peal,syntax`. Listing restrictions
combine with AND. Empty legacy assignee/tag/status values disable that
restriction; use `-f assignee=` to select a present empty assignee.

### Attribute updates

Set one or more frontmatter attributes with `glo-issue set <id> key=value ...`.
The command accepts full or unambiguous partial IDs, including archived issues.

```sh
glo-issue set <id> plan=accept
glo-issue set <id> plan=review priority=1
glo-issue set <id> 'assignee=Jane Doe' 'tags=[peal, syntax]'
glo-issue set <id> plan=
```

- **Assignments:** Existing fields are replaced; missing fields are added.
  Multiple assignments are checked before writing and applied together. If a
  key is repeated, its last value wins. The body and unrelated fields are kept.
- **Values:** Use the issue format's literal, single-line scalar or inline-list
  spelling. The first `=` separates the key and value. Quote the entire argument
  for spaces or shell metacharacters. `key=` leaves a present empty scalar; it
  does not remove the field. Updated values can be selected with `--filter`.
- **Lifecycle:** `status=` accepts the existing status values and restores an
  archived issue to the active directory when set to `open` or `in_progress`.
  Updating other attributes leaves an archived issue in place. Issue IDs cannot
  be changed; use `parent=` for membership, `dep`/`undep` for prerequisites,
  and `link`/`unlink` for related work.

Custom attributes such as `plan` are stored and filtered as data. Glo does not
enforce their meaning; follow the workspace's instructions for plan review and
implementation approval.

### Attribute filters

Use repeatable `--filter key=value` options (`-f key=value` or
`--filter=key=value` also work) with `ls`, `ready`, `blocked`, `closed` and
`query`. Any flat frontmatter attribute can be selected, including custom
fields such as `plan`.

```sh
glo-issue ls -f plan=review -f type=epic
glo-issue ready --filter=priority=1 -a agent
glo-issue blocked -f parent=some-epic-id
glo-issue closed --limit=5 -f tags=peal
glo-issue closed --with-archived --limit=5 -f tags=peal
glo-issue query --only-archived -f plan=accept
glo-issue ls -f 'assignee=Jane Doe'
glo-issue query -f plan=review '.type == "epic"'
```

- **Combination:** Every filter must match (AND). Existing status, assignee
  and tag options still apply, as does the optional jq expression on `query`.
- **Values:** Scalars use exact, case-sensitive text equality; inline lists
  use exact member equality. Values use their stored spelling with surrounding
  frontmatter whitespace trimmed. Filters are neither regular expressions nor
  executable expressions. The first `=` separates key and value, so values
  can contain additional `=` characters. Quote the entire argument for spaces
  or shell metacharacters. Filters must fit on one line.
- **Empty fields:** `assignee=` matches a present empty scalar. Missing
  attributes never match, and an empty list has no matching member.
- **Scope:** Filters and archive options select candidates. Readiness and
  blockers always use dependency records from both locations, including those
  outside the selected scope or filters. `closed --limit=N` returns up to N
  matching issues in modification-time order across the selected locations,
  without a separate candidate-count cutoff.

### Status and archives

An issue's status describes its work state. Archiving changes its storage
location to `base/issue/archive/` and keeps its status and ID. The active
directory can contain closed or iceboxed issues until they are archived.

Issue statuses have distinct lifecycle meanings:

- **`open`:** Planned work eligible for ready or blocked queues.
- **`in_progress`:** Active work, also eligible for those queues.
- **`icebox`:** Deferred, incomplete work excluded from active queues;
  dependencies on it remain unresolved.
- **`closed`:** Completed work, excluded from active queues.

Choose which storage locations a listing searches:

- **No archive flag:** Only issues in the active directory.
- **`--with-archived`:** Issues in both the active directory and the archive.
- **`--only-archived`:** Only issues in the archive.

These options work on `ls`, `ready`, `blocked`, `closed` and `query`, and
combine with status, attribute and other supported filters. Use at most one
archive flag. The command's status rules still apply: `ready` and `blocked`
consider only open or in-progress issues, while `closed` selects completed
issues. Selecting the archive does not make closed or iceboxed issues ready.

```sh
glo-issue ls                                  # active directory, all statuses
glo-issue ls --with-archived -f tags=peal       # matching issues in both locations
glo-issue ls --only-archived --status=icebox    # archived deferred work
glo-issue closed --with-archived --limit=5      # five most recently modified matches
glo-issue query --only-archived -f plan=accept  # archived matches as JSON lines
```

`glo-issue archive <id>` moves a closed or iceboxed issue to
`base/issue/archive/`. It refuses to archive open or in-progress work.
`glo-issue unarchive <id>` restores the file without changing its status.
Both moves preserve the file's content, permissions and modification time,
refuse destination collisions, and succeed without changes if the issue is
already in the requested location.

`glo-notes precommit` uses these commands to archive closed and iceboxed issues
and restore archived issues whose status has become active. A closed or
iceboxed issue restored with `unarchive` will therefore be archived again on
the next notes precommit. Until archival, closed and iceboxed issues remain
visible in active-directory listings. Archived issues remain addressable by ID.
`glo-issue start <id>`, `glo-issue reopen <id>` or setting status to `open` or
`in_progress` immediately restores an archived issue to `base/issue/`;
`glo-agent focus push <id>` does the same while assigning and focusing it.

Archiving does not change dependency resolution: a closed dependency is
satisfied in either location. An iceboxed, open, in-progress or missing
dependency remains unresolved. For example, if A depends on B, closing and
archiving B leaves that dependency satisfied when running `ready` for A,
even without an archive flag. ID-based commands such as `show`, `set`,
`dep` and `link` find archived issues without a listing flag.

```sh
glo-issue close <id>      # mark completed; the file remains in its current location
glo-issue archive <id>    # move the completed issue into the archive
glo-issue show <id>       # inspect it by ID in the archive
glo-issue reopen <id>     # restore it to the active directory and set status open
```

Use `unarchive` when you want only to move the file. Use `reopen` or `start`
when you want to resume the work as open or in progress, respectively.

## Kanban Board

`glo board` (or `glo-board`) opens an interactive terminal board. The UI is
written in Bash and uses `jq`, `stty` and `tput`; all issue reads and changes
go through `glo-issue`. It inherits `GLO_BASE` and the direct issue command's
`TICKETS_DIR` override. Help works without an interactive terminal.

```sh
glo board                  # active issues; detail wrap width defaults to 120
glo board --wrap-width 80  # target 80 columns when opening details
glo board --wrap-width 0   # automatic terminal width, including on resize
glo board --help           # full argument and keyboard reference
```

Board settings are controlled inside the board; `--wrap-width N` (also
`--wrap-width=N`) additionally sets the detail viewer's initial target width.
For an epic planning board, press `g`, type `plan`, and press Enter;
then press `f`, type `type=epic`, and press Enter. Escape cancels a prompt.

- **Grouping:** `g` prompts for a scalar field; an empty response restores
  `status`. Status columns default to `open`, `in_progress`, `closed`.
  `plan` uses `create`, `review`, `reject`, `accept`. Other scalar fields
  discover existing values in alphabetical order. Changing the group resets
  custom columns and keeps filters.
- **Columns:** `c` adds a column value. The first addition replaces automatic
  columns; subsequent additions append in order, including empty destinations.
  `C` resets columns to their automatic order; use `C` then `c` to start a
  different custom list. For example, group by `team`, then add `core` and `tools`.
  List-valued grouping is rejected. Missing or empty values appear in **Unassigned**;
  unlisted values appear in **Other**. These are display buckets, not move
  destinations; use attribute editing to set an empty value.
- **Icebox:** `i` toggles the icebox column on status boards. It starts hidden,
  and hidden iceboxed cards do not appear under **Other**. Adding `icebox`
  with `c` also shows it. Resetting columns keeps the icebox visibility choice.
  This setting applies only to status grouping; other groups include matching
  iceboxed issues normally.
- **Filters:** `f` adds a literal `key=value` filter; repeat it to require all
  matches, using the same semantics as `glo-issue query`. `F` clears attribute
  filters. For example, enter `tags=peal` to match that tag. Invalid settings
  display an error and retain the previous view.
- **Archive scope:** `v` cycles between active issues, all issues (active and
  archived), and archived issues only. The current scope appears in the header.
  Archive selection concerns storage, independently of grouping and filters.
- **Epics:** Each column groups cards under epic headings using explicit
  `parent` ancestry, including archived or filtered-out ancestors. `deps`
  never determine grouping. Epics sort by title and ID; each group shows its
  epic card first when selected by the filters, then children by priority and
  ID. Standalone issues remain visible under **No epic**. Broken references
  and manually edited cycles receive visible diagnostic headings. Use `s`
  with `parent=<epic-id>` to change membership, or `parent=` to clear it.
- **Navigation:** Arrow keys or `h/j/k/l` select columns and cards. Cards
  show the four-character ID suffix and priority, such as `abcd P2`, followed
  by up to three title lines wrapped at word boundaries. Continuation lines align with the title;
  overflow ends in an ellipsis. Archived cards also show `[A]`. Actions use
  full IDs internally, including when suffixes coincide.
  Enter opens issue details in the external pager; use that pager's controls
  to search and scroll, then quit it to return to the board. `?` opens built-in
  help (`j/k` scroll, Escape or `q` returns); `q` on the board exits.
  Narrow terminals scroll columns horizontally.
- **Pager:** `$PAGER` overrides the details viewer. Otherwise, use `bat` when
  it is on `PATH`, with Markdown highlighting and `--style=plain --wrap=never`.
  Bat passes complete source lines to `less -R --wordwrap -+S`, which wraps at
  spaces. `-R` preserves highlighting
  colors; `-+S` disables line chopping even if enabled in `$LESS`.
  The same less options apply to the plain-text fallback when bat is absent.
  This requires less with
  `--wordwrap` support (introduced in version 621); Glo installs less in its
  image and base host tooling. These are display wraps; issue files are unchanged.
  `PAGER='less -R'` accepts whitespace-separated arguments without shell
  evaluation or glob expansion. A single executable path can contain spaces;
  use a wrapper script for commands requiring quoted arguments or shell syntax.
  The pager receives a temporary, sanitized issue snapshot. On exit the
  snapshot is removed and the board refreshes; pager failures are shown on
  the board without ending the session.
- **Detail width:** The default target is 120 columns. Set `--wrap-width N`
  at startup or press `w` in the board to change it. `N` must be a nonnegative
  integer. A positive width sets `LESS_COLUMNS` for the default viewer, clamped
  to the terminal width when details open. It stays fixed for that pager session;
  reopen details after resizing to recalculate. `0` removes the override and
  lets less follow the full terminal width, including live resizing. These
  settings override ambient `LESS_COLUMNS` for the default viewer only; an
  explicit `$PAGER` keeps its own configuration. The Kanban layout is unaffected.
- **Changes:** `m` opens a destination picker; arrows or `h/j/k/l` choose,
  Enter applies, and Escape cancels. Moving updates only the grouping field.
  `n` prompts for a title and creates an issue with backend defaults; `s`
  prompts for one literal `key=value` assignment; `e` opens `$EDITOR` (or `vi`)
  through `glo-issue edit`. `a` archives or unarchives after `y` and Enter.
  Backend rules still apply: only closed or iceboxed issues may be archived,
  and setting an active status restores an archived issue. Changing `plan`
  does not change status.
- **Refresh:** `r` reloads, preserving the selected ID where possible. Changes
  and editor exit refresh automatically. A new or changed issue may disappear
  from the current filters or archive scope. Errors appear on the board without
  exiting. There is no background refresh or saved board configuration.
- **Terminal:** Exiting or receiving an interrupt restores terminal settings.
  The editor and pager receive the normal terminal. Text control characters are removed
  from display; Unicode remains visible, with approximate wide-character
  alignment. The minimum usable size is 20 columns by 8 rows.

The board uses `glo-issue query --details`, an opt-in JSON Lines format:

```json
{"attributes":{"id":"example","status":"open","priority":"2"},"title":"Example","archived":false}
```

`attributes` contains the existing query record; `title` is the first Markdown
level-one heading, or an empty string if absent; `archived` is a boolean derived
from storage location. Without `--details`, query output remains frontmatter
only. Attribute filters and optional jq predicates still select frontmatter
attributes, including when `--details` is present.

## Agent Focus

Use `glo-agent` when acting as an agent. It wraps issue operations with ownership checks and a focus stack.

```sh
glo-agent focus push <id>                 # start issue, assign to self, push focus
glo-agent focus pop                       # pop current issue, mark it open
glo-agent focus list                      # show focus stack
glo-agent focus get                       # print current issue ID
glo-agent focus show                      # show current issue
glo-agent focus icebox                    # defer current issue and remove from stack
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
glo-agent issue icebox <id>
glo-agent issue pause <id>
glo-agent issue close <id>
glo-agent issue show <id>
glo-agent issue add-note <id> "Update"
glo-agent issue block <id> <blocker-id>
glo-agent issue link <id> <other-id>
glo-agent issue unlink <id> <other-id>
glo-agent issue assign <id> <name>
glo-agent issue unassign <id>
```

`issue ready`, `issue blocked` and `focus ready` forward listing options,
including `-f KEY=VALUE`, `--with-archived` and `--only-archived`, to
`glo-issue`. The separate `issue list` view does not
apply those options. Use `glo-issue ls` for filtered listings and
`glo-issue set` or `glo-issue query` for attribute updates or JSON output.

Typical agent loop:

```sh
glo-agent issue ready
glo-agent focus push <id>
# do the work
glo-agent focus add-note "Implemented X; validating Y"
just precommit
glo-agent focus close
```

Follow the workspace's required validation before closing an issue.
`glo-agent precommit` runs only `glo-build --filter=work precommit`.
The workspace's `just precommit` recipe can add notes maintenance and other
checks; inspect that recipe and the workspace instructions for its scope.

## Builds

`glo-build` discovers `build.json` files at one, two, or three directory levels
below `lib/`. For example, `lib/foo/build.json`, `lib/foo/bar/build.json`, and
`lib/foo/bar/baz/build.json` are detected, but `lib/foo/bar/baz/quux/build.json`
is not. Discovery does not descend into deeper directories. Exact project
selectors use the same boundary. Changed files belong to their nearest
discovered project ancestor. Each project declares a `language`;
optional fields include `py_package`, `extra_deps`, `targets`, and `enabled`.

Local source checkouts use the editable Glo build package. If a workspace uses
an installed copy under `/opt/glo`, rebuild its Glo image to pick up changes to
discovery or templates.

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
glo-build clean                   # language-specific artifact/cache cleanup
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

Use explicit paths for Rocq projects, such as
`glo-build /lib/my_proofs typecheck`; `/rocq` is not currently a language
selector. `clean` removes
project environments for some languages, but is not a universal venv deletion
command; Rust, for example, uses `cargo clean`.

Change filters narrow the selected projects:

- **`--filter=none`:** No change filter (the default).
- **`--filter=work`:** Projects with staged, unstaged or untracked changes,
  plus projects that depend on them.
- **`--filter=workonly`:** Only projects with those working-tree changes.
- **`--filter=head`:** Projects changed by the latest commit, plus projects
  that depend on them.

For example, `glo-build --filter=work precommit` checks affected projects.
Only changed paths inside discovered project directories select projects;
changes elsewhere, such as shared workspace config or Glo itself, do not
automatically select projects. No matching projects means no tasks run.
`--dryrun` prints the planned task scripts without executing them.

Parallel workers receive `/dev/null` as standard input. They cannot consume
the caller's input or be suspended by terminal reads while running in the
background. Commands that need interactive or piped input must run in the
foreground: select a single task, or use `-j1` for sequential execution.

Haskell formatting uses Fourmolu for `src/`, `test/`, and `app/`. Glo selects
`fourmolu.yaml` next to the project's `build.json` first, then falls back to
`config/hs/fourmolu.yaml` in the workspace. It passes the selected file explicitly;
if neither exists, it passes no config argument. Point editor integrations at
the same file to share these settings.
A missing formatter fails the format target; install it with `glo-local hs`.

Targets declared in a project's `build.json` are project-local: invoke them
with an explicit selector such as `glo-build /lib/foo serve`. Their names do
not become workspace-wide commands and cannot consume arguments to another
project's target. Arguments after `--` are passed to the selected target
exactly, even when they match a core command or another project's target name.

Document a custom target with a `doc` object as the first array entry:

```json
{
  "language": "meta",
  "targets": {
    "report": [
      { "doc": "Generate the project report.\n\nPass --output PATH to choose the destination." },
      { "command": "./report.sh" }
    ]
  }
}
```

`glo-build /lib/foo` shows the first documentation paragraph as a summary,
wrapping descriptions to the terminal width. `glo-build /lib/foo report --help`
shows the full description, usage, and numbered executable steps. Plain-text
paragraphs and bullet lists are wrapped; indented examples retain their layout.
Targets without docs still show a short command preview.

The `doc` value must be a nonempty string in its own object, at the start of the
array, followed by executable steps. Misplaced or malformed docs are errors.
Documentation never runs or consumes arguments; arguments after `--` still go
to the last executable step. Use `report -- --help` to pass help to the command
itself.

Mode flags must come before selectors and other options:

```sh
glo-build --local precommit       # plan and execute locally
glo-build --container precommit   # plan and execute in a container
glo-build --plan-local --exec-container precommit
glo-build --plan-container --exec-local precommit
```

Local planning and execution are the default. `GLO_CONTAINER_ENGINE` selects
`podman` or `docker` for containerized operations. The platform default is
Docker on macOS and Podman on other
supported hosts. Inside a container, containerized mode is forced back to local
mode. Container builds run as the image's `user` account by default; set
`GLO_CONTAINER_USER` for a compatible custom image that uses a different
account name. A workspace-specific volume stores container-created project
environments under `.glo/venv`, preventing host interpreter paths from leaking
into container builds.

Build state locations:

- `.glo/build`: glo tooling venv in the workspace.
- `/opt/glo/.venv`: image-provided glo tooling venv.
- `.glo/venv/<project>`: project-specific dependency/build state.

Project names in state paths omit `lib/` and replace `/` with `_`:
`lib/foo/bar` uses `.glo/venv/foo_bar`.

Language tools and state:

- **Python (`py`):** uv, ruff, ty and pytest; environment under
  `.glo/venv/<name>/`.
- **PureScript (`ps`):** spago, purs and purs-tidy; dependencies and outputs
  under `.glo/venv/<name>/`.
- **Haskell (`hs`):** cabal, fourmolu and hlint; config and package index in
  `.glo/venv/<name>/cabal/`, store in `.glo/venv/<name>/store/`, and build
  output in `.glo/venv/<name>/dist-newstyle/`.
- **Rust (`rs`):** cargo, rustfmt and clippy; target directory at
  `.glo/venv/<name>/target/`.
- **TypeScript (`ts`):** npm, tsc, eslint, prettier and jest; dependencies in
  `.glo/venv/<name>/node_modules/`.
- **Rocq (`rocq`):** rocq and make; `_CoqProject` generates a local Makefile,
  with compiled proof artifacts in the project tree.
- **Metadata (`meta`):** Custom targets and their own state locations.

Rust projects have a standard compilation command, so ordinary crates do not
need to repeat Cargo recipes in `build.json`:

```sh
glo-build /lib/example compile debug
glo-build /lib/example compile release
glo-build /lib/example compile release x86_64-pc-windows-gnu
glo-build /lib/example compile release -- --bin app
glo-build /lib/example release-test -- --test cli
```

`compile` requires an explicit project and a `debug` or `release` profile. Its
optional cross environment is passed to Cargo as `--target`; the toolchain,
linker, and any sysroot must already be configured by the workspace or project.
Remaining arguments are forwarded to Cargo. `release-test` remains available
for optimized test execution. A project may override either command with a
custom target or reference a built-in command while adding arguments.

Rust commands that can produce build artifacts also keep each project's complete
`.glo/venv/<name>/target` tree bounded. Glo records target-producing invocations
in `.glo/venv/<name>/.rust-target-prune-iterations` and checks the target tree at
most once every 10 invocations by default. When a due check finds that the tree
exceeds 32 GiB, Glo runs a package-scoped clean for the host and every recognized
cross-target directory. That removes old and current root-crate artifacts across
debug, release, custom, and cross profiles while retaining compiled dependencies.
If the remaining target tree still exceeds 64 GiB, Glo removes the complete
project target tree to clear obsolete dependency generations.

Set `GLO_RUST_TARGET_SOFT_LIMIT_GIB` or `GLO_RUST_TARGET_HARD_LIMIT_GIB` to tune
the integer GiB limits. Set `GLO_RUST_TARGET_PRUNE_MIN_ITERATIONS` to a positive
integer to tune the minimum number of target-producing invocations between
checks; `1` checks every invocation. Set the soft limit to `0` to disable
automatic cleanup and counter updates, or the hard limit to `0` to retain only
package-scoped cleanup. Fetching, formatting, explicit cleaning, and non-Cargo
custom targets do not increment the counter or run the retention check.

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
- `hs`: Haskell package with a shared `common defaults` stanza (GHC2024 and
  default extensions) imported by the library and test suite. Its `cabal.project`
  includes the local package and enables tests; repository-specific dependency
  policy imports can be added by the consuming workspace. Tests use
  `-threaded -rtsopts` so they support the threaded runtime and runtime options.
- `rocq`: Rocq proof project.
- `rs`: Rust crate.
- `ts`: TypeScript package.

Generated projects include `build.json` so `glo-build` can discover them.

## Notes

`glo-notes` wraps `zk` for the notebook selected by `GLO_BASE` (default `base/`).

```sh
glo-notes index                  # update zk index and generated indexes
glo-notes precommit              # reconcile archives through glo-issue, then index
glo-notes zk <subcommand> [args]  # pass remaining arguments to zk in the selected notebook
glo-notes zk list --tag peal
glo-notes zk new --group wiki --title "Project notes"
glo-notes zk --help
```

Only `glo-notes zk ...` passes commands through, with `ZK_NOTEBOOK_DIR` set to
the resolved notebook directory. This overrides an ambient `ZK_NOTEBOOK_DIR`.
Unknown top-level commands are errors;
for example, use `glo-notes zk list` instead of `glo-notes list`.

`glo-notes precommit` delegates issue moves to `glo-issue archive` and
`glo-issue unarchive`, then updates the notebook and generated indexes.
Closed and iceboxed issues move into the archive; archived issues whose status
has been changed to open or in progress return to the active directory.

Notes layout below the selected notebook root (shown with the default `base/`):

- `base/issue/`: active issue notes, including closed and iceboxed issues
  awaiting archival.
- `base/issue/archive/`: completed closed issues and deferred iceboxed issues;
  resuming an iceboxed issue restores it to `base/issue/`.
- `base/wiki/`: project wiki notes.
- `base/**/TITLES.md`: generated title index.
- `base/**/TAGS.md`: generated tag index.

Generated title and tag indexes exclude archived notes. The SQLite index at
`<notebook>/.zk/notebook.db` is generated. Bootstrap adds it to the workspace's
`.gitignore` for notebooks inside that workspace; external notebooks are
outside that Git repository's scope.

## Workspace `justfile`

Bootstrapped workspaces get a small `justfile`:

```sh
just image                       # build the workspace devcontainer image
just shell                       # start an interactive devcontainer shell
just precommit                   # run build precommit and notes precommit
```

`just shell` delegates to glo's `devcontainer/justfile` and passes the workspace
path explicitly. Nested `just` calls preserve it through `GLO_WORKSPACE`.
Host lifecycle and image recipes default to Docker on macOS and Podman on other
supported hosts. Set `GLO_CONTAINER_ENGINE` explicitly to override that choice.
The Dev Container CLI receives the selected executable through `--docker-path`.
Podman selects the CLI's non-BuildKit path so rootless builds use Podman's
native builder.

## Local Host Tooling

Use `glo-local` outside the devcontainer when you want the host OS to have the same toolchain families as the image. It detects Arch Linux or macOS and installs packages with `pacman` or `brew`. Haskell and Rust versions are pinned to the image versions. On other Linux distributions, only `wasm`, `smt` and `doctor` are supported, assuming base tools are already installed.

```sh
glo-local doctor                  # show detected OS/arch and installed tools
glo-local --dry-run all           # print install commands without running them
glo-local need                    # install toolchains enabled by workspace config
glo-local base                    # common CLI tools
glo-local py                      # Python and uv
glo-local rs                      # Rust 1.97.1 + rustfmt/clippy/rust-analyzer/rust-src
glo-local hs                      # GHC 9.14.1, cabal 3.16.1.0, stack 3.11.1, HLS 2.14.0.0, fourmolu, hlint via ghcup
glo-local wasm                    # wasm32-wasi GHC, wasm32-wasi-cabal, wasmtime, binaryen
glo-local rocq                    # Rocq 9.2.0 and companion packages via opam
glo-local smt                     # checksummed cvc5 1.4.2
glo-local ts                      # Node/npm
glo-local ps                      # PureScript tooling via npm
glo-local notes                   # zk/sqlite
glo-local secretspec              # checksummed Apache-2.0 SecretSpec release
```

`glo local ...` is equivalent to `glo-local ...`.

The image's `SMT_ENABLED=1` and `glo-local smt` install
[cvc5 1.4.2](https://github.com/cvc5/cvc5/releases/tag/cvc5-1.4.2).
Both use the official static archives with pinned SHA-256 checksums. The image
supports Linux x86_64 and arm64; the local installer also supports macOS on
both architectures. `CVC5_PREFIX` overrides the local installation directory,
which defaults to `~/.local/opt/cvc5-1.4.2`.

### Optional PostgreSQL 18 test cluster

The devcontainer has no PostgreSQL packages or service by default. A workspace
that sets the `POSTGRES_ENABLED` image build argument to `1` receives the
PostgreSQL 18 client, server, and development packages plus a disposable local
cluster helper. Start it explicitly and map its neutral URL to the project test
setting:

```sh
glo postgres start
eval "$(glo postgres env)"
export MY_PROJECT_TEST_DATABASE_URL="$GLO_POSTGRES_URL"
```

The cluster listens only on `127.0.0.1`, on port `55432` by default
(`GLO_POSTGRES_PORT` overrides it), uses the fixed local-only
`glo:glo` credential and `glo_test` database, and stores disposable state under
`${XDG_STATE_HOME:-$HOME/.local/state}/glo/postgres-18`. The remaining commands
are `glo postgres status`, `url`, and `stop`. `glo postgres run` initializes the
same cluster and then owns PostgreSQL in the foreground for container use. No
cluster is initialized or started merely by enabling the image feature.

On a host without PostgreSQL 18, the same enabled devcontainer image can own a
dedicated container while exposing only the host loopback port:

```sh
export GLO_POSTGRES_ROOT="$PWD/temp/run/postgres"
glo-postgres --container start
eval "$(glo-postgres --container env)"
glo-postgres --container stop
```

Container mode bind-mounts the absolute `GLO_POSTGRES_ROOT`, so cluster files
survive container removal. It defaults to the image
`devcontainer-WORKSPACE`; `GLO_POSTGRES_CONTAINER_IMAGE` and
`GLO_POSTGRES_CONTAINER_NAME` select explicit alternatives.

### Optional Garage object store

`GARAGE_ENABLED=1` installs the pinned, SHA-256-verified Garage release binary
for the image architecture. It defaults to `0`, and enabling it installs no
service or configuration and starts no process. `glo garage run` requires an
absolute `GARAGE_CONFIG_FILE` and owns Garage's single-node development process
in the foreground for container use.

### Optional Caddy HTTPS edge

`CADDY_ENABLED=1` builds Caddy with `caddy-l4` from exact commit-SHA source
archives whose SHA-256 digests are pinned in the image Dockerfile. The temporary
Go toolchain is also checksummed, and the source trees are supplied to `xcaddy`
as local module replacements. It defaults to `0`, installs no service or
configuration, and starts no process. Projects supply their own Caddyfile and
set `CADDY_CONFIG_FILE` to its absolute path. Both `validate` and `run` require
that file to exist:

```sh
export CADDY_CONFIG_FILE="$PWD/config/Caddyfile"
glo caddy validate
glo caddy run                      # own Caddy in the foreground
```

### Local KDBX credentials

`glo-secrets` is a foreground wrapper around SecretSpec's built-in KDBX and
keyring providers. It does not install a service, broker, socket, systemd unit,
TPM helper, or devcontainer integration.

First choose a user-level alias and KDBX path. Initialization configures the
alias and asks SecretSpec to store the database master password in one
alias-specific entry in the operating system's standard keychain:

```sh
glo-secrets --provider local init \
  --database "$HOME/.local/share/example/example.kdbx" \
  --file lib/example/secretspec.toml
```

The KDBX file is created on the first `put`. Values are prompted for rather
than accepted in command arguments:

```sh
glo-secrets --provider local put \
  --file lib/example/secretspec.toml API_TOKEN
glo-secrets --provider local check \
  --file lib/example/secretspec.toml --scope runtime
glo-secrets --provider local build /lib/example serve
```

The alias is selected at runtime and lives in the user's SecretSpec
configuration, so checked-in component manifests remain provider neutral. The
keychain must be available in the environment where the command runs; Glo does
not expose a host keychain or D-Bus session inside a container. `build` requires
one concrete `/lib/...` project with both `build.json` and `secretspec.toml`,
exports that manifest and the provider, then forwards its arguments to
`glo-build`. Use `run` when SecretSpec must materialize the selected scope for a
child that has no SDK integration.

## When Finishing Work

Before handing off:

```sh
glo-agent focus add-note "Summary of changes and validation"
just precommit
glo-agent focus close
```

If work is incomplete, leave the issue open and add a note with the blocker or
next step. If it is intentionally deferred and should leave active queues, add
a note and run `glo-agent focus icebox`.
