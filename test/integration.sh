#!/usr/bin/env bash
# Integration test: bootstrap a workspace, generate projects, build, exercise issue/agent.
# Expects to run inside the devcontainer (Rust, Haskell, Node, Python toolchains present).
# Haskell venv and precommit steps are slow on first run (cabal downloads packages).
set -euo pipefail

GLO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE="/tmp/glo_test"

step() { echo; echo "=== $* ==="; }
ok()   { echo "[OK] $*"; }

# --- Setup ---
step "Setup"
rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE"
cd "$WORKSPACE"
git init -q
git config user.email "test@glo"
git config user.name "glo test"
export PATH="$WORKSPACE/bin:$PATH"

# --- Bootstrap ---
step "Bootstrap"
"${GLO_DIR}/bootstrap.sh"
[[ -d bin ]]           && ok "bin/ created"
[[ -d base/issue ]]    && ok "base/issue/ created"
[[ -d base/wiki ]]     && ok "base/wiki/ created"
[[ -d lib ]]           && ok "lib/ created"
[[ -d base/.zk ]]      && ok "base/.zk initialized"
[[ -f justfile ]]      && ok "justfile created"

# --- Generate projects ---
step "Generate projects"
bin/glo-gen meta test_meta
bin/glo-gen rs   test_rs
bin/glo-gen hs   test_hs
bin/glo-gen py   test_py
bin/glo-gen ts   test_ts
bin/glo-gen rocq test_rocq
[[ -f lib/test_meta/build.json ]] && ok "meta scaffolded"
[[ -f lib/test_rs/Cargo.toml ]]   && ok "rs scaffolded"
[[ -f lib/test_hs/test_hs.cabal ]] && ok "hs scaffolded"
[[ -f lib/test_py/pyproject.toml ]] && ok "py scaffolded"
[[ -f lib/test_ts/package.json ]]  && ok "ts scaffolded"
[[ -f lib/test_rocq/_CoqProject ]] && ok "rocq scaffolded"

# --- Build: venv ---
step "glo-build venv (all)"
bin/glo-build venv
ok "venv"

# --- Build: precommit ---
step "glo-build precommit (all)"
bin/glo-build precommit
ok "precommit"

# --- glo-issue ---
step "glo-issue: create"
T1=$(bin/glo-issue create "Bootstrap ticket")
T2=$(bin/glo-issue create "Second ticket")
T3=$(bin/glo-issue create "Blocker")
T4=$(bin/glo-issue create "Blocked by T3")
ok "created $T1  $T2  $T3  $T4"

step "glo-issue: ls / show"
bin/glo-issue ls | grep -q "$T1"
bin/glo-issue show "$T1" | grep -q "Bootstrap ticket"
ok "ls / show"

step "glo-issue: start / add-note / close"
bin/glo-issue start "$T1"
bin/glo-issue ls --status=in_progress | grep -q "$T1"
bin/glo-issue add-note "$T1" "progress note"
bin/glo-issue show "$T1" | grep -q "progress note"
bin/glo-issue close "$T1"
bin/glo-issue ls --status=closed | grep -q "$T1"
ok "start / add-note / close"

step "glo-issue: dep / blocked / ready"
bin/glo-issue dep "$T4" "$T3"
bin/glo-issue blocked | grep -q "$T4"
bin/glo-issue ready   | grep -q "$T2"
bin/glo-issue close "$T3"
bin/glo-issue ready   | grep -q "$T4"
ok "dep / blocked / ready"

step "glo-issue: link / dep tree"
bin/glo-issue link "$T2" "$T4"
bin/glo-issue show "$T2" | grep -q "$T4"
bin/glo-issue dep tree "$T4" | grep -q "$T3"
ok "link / dep tree"

step "glo-issue: query"
bin/glo-issue query | jq -e '.' > /dev/null
ok "query (JSON output valid)"

# --- glo-agent ---
step "glo-agent: setup"
export AGENT_NAME=test_agent

A1=$(bin/glo-agent issue create "Agent task one")
A2=$(bin/glo-agent issue create "Agent task two")
ok "created $A1  $A2"

step "glo-agent: focus push / list / get"
bin/glo-agent focus push "$A1"
bin/glo-agent focus list | grep -q "$A1"
[[ "$(bin/glo-agent focus get)" == "$A1" ]]
ok "push / list / get"

step "glo-agent: focus show / add-note"
bin/glo-agent focus show | grep -q "Agent task one"
bin/glo-agent focus add-note "agent note"
bin/glo-issue show "$A1" | grep -q "agent note"
ok "show / add-note"

step "glo-agent: issue block"
bin/glo-agent issue block "$A2" "$A1" --force
bin/glo-agent issue blocked | grep "$A2" > /dev/null
ok "block"

step "glo-agent: focus close -> A2 unblocked"
bin/glo-agent focus close
bin/glo-issue ls --status=closed | grep -q "$A1"
bin/glo-agent issue ready | grep "$A2" > /dev/null
ok "focus close / A2 ready"

step "glo-agent: focus push A2 then pop"
bin/glo-agent focus push "$A2"
bin/glo-agent focus pop
[[ "$(bin/glo-agent focus list)" == "(empty)" ]]
ok "push / pop"

echo
echo "=== All checks passed ==="
