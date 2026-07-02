#!/usr/bin/env python3
"""
Lightweight build system for glo.

Usage:
    glo-build                          # List all commands
    glo-build <command>                # Run command on all projects
    glo-build <project> <command>      # Run command on specific project
    glo-build <project> <command> ...  # Run command with extra args
    glo-build --dryrun <command>       # Print bash script without executing

Project patterns:
    / or /lib                           # All projects
    /py, /ps, /hs                       # All projects by language
    /py/core or /lib/core               # Specific project
    ^/py/core                           # Exclude a project

Target exclusions:
    precommit ^test                     # Run precommit without test subtargets

Argument passing:
    Arguments after a single target are passed to that target's command.
    Meta-commands (like precommit) do not accept arguments.
    Use -- to pass flags to the target: glo-build train -- --help

Examples:
    glo-build /py/core format
    glo-build /lib/core test
    glo-build precommit
    glo-build /py ^/py/core precommit  # All Python projects except core
    glo-build precommit ^test          # Precommit without running tests
    glo-build /py/web dev --port 9000
    glo-build precommit -- -k test_foo # Pass -k to test subtarget
    glo-build --dryrun /py/core precommit
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from enum import auto, Enum
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Workspace root configuration
# ---------------------------------------------------------------------------

_workspace_root: Path | None = None


def set_workspace_root(root: Path) -> None:
    """Set the workspace root directory."""
    global _workspace_root
    _workspace_root = root.resolve()


def get_workspace_root() -> Path:
    """Get the workspace root directory."""
    if _workspace_root is None:
        raise RuntimeError(
            "Workspace root not set. Call set_workspace_root() or main(workspace_root=...) first."
        )
    return _workspace_root


# ANSI color codes
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
RESET = "\033[0m"


def log_error(msg: str) -> None:
    """Print error message with red [E] tag to stderr."""
    print(f"{RED}[E]{RESET} {msg}", file=sys.stderr)


def log_info(msg: str) -> None:
    """Print info message with green [I] tag."""
    print(f"{GREEN}[I]{RESET} {msg}")


def log_warn(msg: str) -> None:
    """Print warning message with yellow [W] tag."""
    print(f"{YELLOW}[W]{RESET} {msg}")


def get_git_info() -> dict[str, str]:
    """Capture git info at plan time for embedding in build scripts.

    Returns dict with: sha, sha_short, branch, dirty (all strings).
    Returns "unknown" for values that can't be determined.
    """
    info = {
        "sha": "unknown",
        "sha_short": "unknown",
        "branch": "unknown",
        "dirty": "true",
    }
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            info["sha"] = result.stdout.strip()
            info["sha_short"] = info["sha"][:7]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            info["branch"] = result.stdout.strip() or "unknown"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            info["dirty"] = "true" if result.stdout.strip() else "false"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return info


# ---------------------------------------------------------------------------
# Task model for parallel execution
# ---------------------------------------------------------------------------


class Lang(Enum):
    """Programming language for a project."""

    Python = auto()
    Purescript = auto()
    Meta = auto()
    Haskell = auto()
    Rust = auto()
    TypeScript = auto()
    Rocq = auto()


class TaskStatus(Enum):
    """Status of a task in parallel execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # Skipped due to dependency failure


@dataclass
class Task:
    """A single atomic task (project + command) for parallel execution."""

    id: str  # Unique ID like "/lib/core:format"
    project_path: str  # e.g., "/lib/core"
    command_name: str  # Atomic command name, e.g., "format"
    args: list[str]
    meta_command: str | None  # Original meta-command if expanded, e.g., "precommit"
    status: TaskStatus = TaskStatus.PENDING
    error: str | None = None  # Error message if failed
    dependencies: list[str] = field(default_factory=list)  # Task IDs this depends on
    phase: int = 0  # Execution phase (0-indexed)
    enabled: bool = True


# ---------------------------------------------------------------------------
# Script builder
# ---------------------------------------------------------------------------


def shquote(s: str) -> str:
    """Quote a string for shell, returning unquoted if safe."""
    # Allow $ for variable references
    if s and all(c.isalnum() or c in "-_/.=:${}*" for c in s):
        return s
    return shlex.quote(s)


def shcmd(cmd: list[str]) -> str:
    """Convert command list to shell string."""
    return " ".join(shquote(arg) for arg in cmd)


class Script:
    """Accumulates bash commands for later execution or printing."""

    def __init__(self, workspace: Path, color: bool = True) -> None:
        self._lines: list[str] = []
        self._indent: int = 0
        self._workspace = workspace
        self._color = color
        self._export_stack: list[list[str]] = []  # Track exports per pushd level
        self._current_project_path: str | None = None  # Track current project context

    def _add(self, line: str) -> None:
        """Add a line with current indentation."""
        indent = "    " * self._indent
        self._lines.append(f"{indent}{line}")

    def comment(self, msg: str) -> None:
        """Add a comment."""
        self._add(f"# {msg}")

    def echo(self, msg: str) -> None:
        """Add an echo statement."""
        self._add(f"echo {shquote(msg)}")

    def info(self, msg: str) -> None:
        """Add an info message (green [I] prefix)."""
        if self._color:
            self._add(f"echo -e '\\033[0;32m[I]\\033[0m {msg}'")
        else:
            self._add(f"echo '[I] {msg}'")

    def warn(self, msg: str) -> None:
        """Add a warning message (yellow [W] prefix)."""
        if self._color:
            self._add(f"echo -e '\\033[1;33m[W]\\033[0m {msg}'")
        else:
            self._add(f"echo '[W] {msg}'")

    def pushd(self, path: Path | str) -> None:
        """Add pushd and increase indent."""
        self._add(f"pushd {shquote(str(path))} >/dev/null")
        self._indent += 1
        self._export_stack.append([])  # New scope for exports

    def popd(self) -> None:
        """Unset exports from this scope, decrease indent, and add popd."""
        if self._export_stack:
            exports = self._export_stack.pop()
            for name in reversed(exports):
                self._add(f"unset {name}")
        # Restore PATH if it was saved (from emit_ps_env)
        self._add(
            'if [ -n "${_SAVED_PATH+x}" ]; then PATH=$_SAVED_PATH; unset _SAVED_PATH; fi'
        )
        self._indent = max(0, self._indent - 1)
        self._add("popd >/dev/null")

    def enter_project(self, path: str) -> bool:
        """Enter a project context. Returns True if new context was created.

        If already in this project, returns False and does nothing.
        If in a different project, closes it first then opens new one.
        """
        if self._current_project_path == path:
            return False  # Already in this project context

        if self._current_project_path is not None:
            # Leave current project first
            self.popd()

        self.pushd(path)
        self._current_project_path = path
        return True

    def leave_project(self) -> None:
        """Leave the current project context if any."""
        if self._current_project_path is not None:
            self.popd()
            self._current_project_path = None

    def finalize(self) -> None:
        """Close any open project context. Call before generating script."""
        self.leave_project()

    def export(self, name: str, value: str) -> None:
        """Add an export statement, tracking it for later unset. Idempotent within context."""
        # Skip if already exported in current context
        if self._export_stack and name in self._export_stack[-1]:
            return
        self._add(f"export {name}={shquote(value)}")
        if self._export_stack:
            self._export_stack[-1].append(name)

    def unset(self, name: str) -> None:
        """Add an unset statement."""
        self._add(f"unset {name}")

    def run(self, cmd: list[str]) -> None:
        """Add a command to run, echoing it first."""
        cmd_str = shcmd(cmd)
        self._add(f"echo '+ {cmd_str}'")
        self._add(cmd_str)

    def raw(self, line: str) -> None:
        """Add a raw line of bash."""
        self._add(line)

    def blank(self) -> None:
        """Add a blank line."""
        self._lines.append("")

    def workspace_path(self, path: Path | str) -> str:
        """Convert an absolute path to use ${WORKSPACE} if under workspace."""
        path_str = str(path)
        workspace_str = str(self._workspace)
        if path_str.startswith(workspace_str):
            return "${WORKSPACE}" + path_str[len(workspace_str) :]
        return path_str

    def venv_path(self, path: Path | str) -> str:
        """Convert a path to use ${VIRTUAL_ENV} if it starts with the venv path."""
        path_str = str(path)
        # This is called after VIRTUAL_ENV is set, so use that variable
        if "/bin/" in path_str or path_str.endswith("/bin"):
            # Try to use ${VIRTUAL_ENV} for paths in venv
            parts = path_str.split("/.glo/venv/")
            if len(parts) == 2:
                subparts = parts[1].split("/", 1)
                if len(subparts) == 2:
                    return "${VIRTUAL_ENV}/" + subparts[1]
        return self.workspace_path(path)

    def to_bash(self) -> str:
        """Generate the complete bash script."""
        self.finalize()  # Close any open project context
        header = [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            f"export WORKSPACE=${{WORKSPACE:-{shquote(str(self._workspace))}}}",
            '[ -f "${WORKSPACE}/.python-version" ] && export UV_PYTHON="$(cat "${WORKSPACE}/.python-version")"',
            "",
        ]
        return "\n".join(header + self._lines) + "\n"

    def write_to(self, path: Path) -> None:
        """Write the script to a file."""
        path.write_text(self.to_bash())
        path.chmod(0o755)

    def print(self) -> None:
        """Print the script to stdout."""
        print(self.to_bash())


# ---------------------------------------------------------------------------
# Project discovery
# ---------------------------------------------------------------------------


def get_project_package_name(project_path: Path) -> str | None:
    """Get the package name from a project's pyproject.toml."""
    pyproject_path = project_path / "pyproject.toml"
    if not pyproject_path.exists():
        return None

    content = pyproject_path.read_text()
    in_project = False

    for line in content.splitlines():
        if line.strip() == "[project]":
            in_project = True
            continue
        if in_project and line.startswith("["):
            break
        if in_project and line.startswith("name"):
            match = re.search(r'"([^"]+)"', line)
            if match:
                return match.group(1)
    return None


def get_git_changed_files(mode: str, workspace_root: Path) -> list[str]:
    """Get list of changed files from git.

    Args:
        mode: 'work' for working copy (staged + unstaged), 'head' for HEAD commit
        workspace_root: Root directory of the workspace
    """
    if mode == "work":
        # Get staged, unstaged, and untracked changes
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=workspace_root,
        )
        unstaged = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True,
            text=True,
            cwd=workspace_root,
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            cwd=workspace_root,
        )
        files = set(
            staged.stdout.strip().split("\n")
            + unstaged.stdout.strip().split("\n")
            + untracked.stdout.strip().split("\n")
        )
    elif mode == "head":
        # Get changes from HEAD commit
        result = subprocess.run(
            ["git", "show", "--name-only", "--format="],
            capture_output=True,
            text=True,
            cwd=workspace_root,
        )
        files = set(result.stdout.strip().split("\n"))
    else:
        return []

    return [f for f in files if f]  # Filter empty strings


def files_to_projects(files: list[str], all_projects: list[str]) -> list[str]:
    """Map changed files to affected projects."""
    affected = set()
    for f in files:
        for proj in all_projects:
            # proj has leading "/" (e.g. "/lib/lplean"), git paths don't
            proj_prefix = proj.lstrip("/") + "/"
            if f.startswith(proj_prefix):
                affected.add(proj)
                break
    return list(affected)


def get_dependent_projects(
    projects: list[str], all_projects: list[str], project_deps: dict[str, list[str]]
) -> list[str]:
    """Get projects that depend on the given projects (children/dependents).

    Args:
        projects: List of directly affected projects
        all_projects: All projects in dependency order
        project_deps: Map of project -> list of parent dependencies
    """
    # Build reverse dependency map: parent -> list of children
    dependents: dict[str, list[str]] = {p: [] for p in all_projects}
    for proj, parents in project_deps.items():
        for parent in parents:
            if parent in dependents:
                dependents[parent].append(proj)

    # BFS to find all transitive dependents
    affected = set(projects)
    queue = list(projects)
    while queue:
        current = queue.pop(0)
        for child in dependents.get(current, []):
            if child not in affected:
                affected.add(child)
                queue.append(child)

    # Return in dependency order
    return [p for p in all_projects if p in affected]


def filter_projects(
    all_projects: list[str],
    project_deps: dict[str, list[str]],
    filter_mode: str,
    workspace_root: Path,
) -> list[str]:
    """Filter projects based on git changes.

    Args:
        all_projects: All projects in dependency order
        project_deps: Map of project -> list of parent dependencies
        filter_mode: 'none', 'work', 'workonly', or 'head'
        workspace_root: Root directory of the workspace

    Returns:
        Filtered list of projects in dependency order
    """
    if filter_mode == "none":
        return all_projects

    # Map filter mode to git mode (workonly uses same git check as work)
    git_mode = "work" if filter_mode == "workonly" else filter_mode

    changed_files = get_git_changed_files(git_mode, workspace_root)
    if not changed_files:
        log_warn(f"No changed files found for --filter={filter_mode}")
        return []

    directly_affected = files_to_projects(changed_files, all_projects)
    if not directly_affected:
        log_warn("Changed files don't affect any projects")
        return []

    # workonly: only directly affected, no dependents
    if filter_mode == "workonly":
        filtered = [p for p in all_projects if p in directly_affected]
        log_info(f"Filter: {len(filtered)}/{len(all_projects)} projects affected")
        for proj in filtered:
            log_info(f"  * {proj}")
        return filtered

    # work/head: include affected projects and their dependents (children)
    filtered = get_dependent_projects(directly_affected, all_projects, project_deps)

    log_info(f"Filter: {len(filtered)}/{len(all_projects)} projects affected")
    for proj in filtered:
        marker = "*" if proj in directly_affected else "+"
        log_info(f"  {marker} {proj}")

    return filtered


def get_path_dependencies(workspace_root: Path, project: str) -> list[str]:
    """Get path dependencies for a project from [tool.uv.sources]."""
    # Project paths are like "/lib/core", strip leading "/" for filesystem access
    rel_path = project.lstrip("/")
    pyproject_path = workspace_root / rel_path / "pyproject.toml"
    if not pyproject_path.exists():
        return []

    # Build package name to project path mapping
    package_to_project: dict[str, str] = {}
    lib_dir = workspace_root / "lib"
    if lib_dir.exists():
        for build_json in lib_dir.rglob("build.json"):
            project_dir = build_json.parent
            pkg_name = get_project_package_name(project_dir)
            if pkg_name:
                rel_path = str(project_dir.relative_to(lib_dir))
                package_to_project[pkg_name] = f"/lib/{rel_path}"

    content = pyproject_path.read_text()
    in_sources = False
    deps: list[str] = []

    for line in content.splitlines():
        if "[tool.uv.sources]" in line:
            in_sources = True
            continue
        if in_sources and line.startswith("["):
            in_sources = False
            continue
        if in_sources:
            # Parse: package_name = { path = "../other" }
            match = re.match(r"\s*([a-zA-Z0-9_-]+)\s*=\s*\{.*path\s*=", line)
            if match:
                dep_name = match.group(1)
                if dep_name in package_to_project:
                    deps.append(package_to_project[dep_name])

    return deps


def discover_projects(workspace_root: Path) -> list[str]:
    """Discover workspace projects in dependency order (topological sort)."""
    # Discover projects from lib/ directory by finding build.json files
    lib_dir = workspace_root / "lib"
    projects: list[str] = []

    if lib_dir.exists():
        for build_json in sorted(lib_dir.rglob("build.json")):
            # Get path relative to lib/, e.g., "core" or "comm/gen"
            rel_path = build_json.parent.relative_to(lib_dir)
            projects.append(f"/lib/{rel_path}")

    if not projects:
        return []

    # Topological sort based on dependencies
    indegree: dict[str, int] = {p: 0 for p in projects}
    dependents: dict[str, list[str]] = {p: [] for p in projects}

    for project in projects:
        deps = get_path_dependencies(workspace_root, project)
        for dep in deps:
            if dep in indegree:
                indegree[project] += 1
                dependents[dep].append(project)

    # Kahn's algorithm
    ready = sorted([p for p in projects if indegree[p] == 0])
    order: list[str] = []

    while ready:
        current = ready.pop(0)
        order.append(current)
        for dependent in dependents[current]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
                ready.sort()

    if len(order) != len(projects):
        log_error("Detected dependency cycle among workspace members")
        sys.exit(1)

    return order


# ---------------------------------------------------------------------------
# Project class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TargetStep:
    """A step in a custom target definition."""

    target: str | None = None  # Reference to another target/command
    command: str | list[str] | None = None  # Raw bash command(s) to run
    args: list[str] | None = None  # Args for target/command steps


@dataclass(frozen=True)
class BuildConfig:
    """Build configuration from build.json.

    Each project has a language field in build.json:
    - lib/core with language: py -> language=Python, name=core
    - lib/edit with language: ps -> language=Purescript, name=edit
    """

    _path: str  # e.g., "lib/core"
    language_str: str  # "py", "ps", or "meta"
    py_package: str | None = None  # e.g., "glo_core" (Python only)
    extra_deps: list[str] | None = None
    targets: dict[str, list[TargetStep]] | None = None  # Custom targets
    enabled: bool = True

    @property
    def path(self) -> str:
        """Get the project path (e.g., 'lib/core')."""
        return self._path

    @property
    def ident(self) -> str:
        """Get the project identifier with leading slash (e.g., '/lib/core')."""
        return f"/{self._path}"

    @property
    def name(self) -> str:
        """Get the project name derived from path (e.g., 'core' from 'lib/core')."""
        return Path(self._path).name

    @property
    def language(self) -> Lang:
        """Get the project language from build.json."""
        if self.language_str == "py":
            return Lang.Python
        elif self.language_str == "ps":
            return Lang.Purescript
        elif self.language_str == "meta":
            return Lang.Meta
        elif self.language_str == "hs":
            return Lang.Haskell
        elif self.language_str == "rs":
            return Lang.Rust
        elif self.language_str == "ts":
            return Lang.TypeScript
        elif self.language_str == "rocq":
            return Lang.Rocq
        raise ValueError(f"Unknown language: {self.language_str}")


def read_build_json(project_path: Path, rel_path: str) -> BuildConfig | None:
    """Read build.json from a project directory.

    Args:
        project_path: Absolute path to the project directory
        rel_path: Relative path like 'lib/core' (without leading slash)
    """
    build_json = project_path / "build.json"
    if not build_json.exists():
        return None
    with build_json.open() as f:
        data = json.load(f)

    # Parse language field (required)
    language_str = data.get("language")
    if language_str is None:
        raise ValueError(f"Missing 'language' field in {build_json}")
    if language_str not in ("py", "ps", "meta", "hs", "rs", "ts", "rocq"):
        raise ValueError(f"Invalid language '{language_str}' in {build_json}")

    # Parse targets if present
    targets: dict[str, list[TargetStep]] | None = None
    if "targets" in data:
        targets = {}
        for target_name, steps in data["targets"].items():
            target_steps = []
            for step in steps:
                target_steps.append(
                    TargetStep(
                        target=step.get("target"),
                        command=step.get("command"),
                        args=step.get("args"),
                    )
                )
            targets[target_name] = target_steps

    return BuildConfig(
        _path=rel_path,
        language_str=language_str,
        py_package=data.get("py_package"),
        extra_deps=data.get("extra_deps"),
        targets=targets,
        enabled=data.get("enabled", True),
    )


@dataclass(frozen=True)
class Project:
    """Represents a subproject in the monorepo."""

    path: str  # e.g., "/lib/core" or "/lib/edit"
    workspace_root: Path = field(default_factory=get_workspace_root)

    @property
    def name(self) -> str:
        """Get the directory name (e.g., 'core')."""
        return Path(self.path).name

    @property
    def language(self) -> Lang:
        """Get the project language from build.json."""
        config = self.build_config
        if config is None:
            raise ValueError(f"No build.json found for {self.path}")
        return config.language

    @property
    def package_name(self) -> str:
        """Get the Python package name from build.json."""
        rel_path = self.path.lstrip("/")
        config = read_build_json(self.abs_path, rel_path)
        if config and config.py_package:
            return config.py_package
        # Fallback: use directory name
        return self.name

    @property
    def abs_path(self) -> Path:
        """Get absolute path to the project."""
        # Strip leading "/" from path for filesystem access
        return self.workspace_root / self.path.lstrip("/")

    @property
    def venv_name(self) -> str:
        """Get the venv directory name (e.g., 'core' or 'comm_gen' for nested)."""
        # Strip leading /lib/ and replace / with _ for nested projects
        rel_path = self.path.lstrip("/")
        if rel_path.startswith("lib/"):
            rel_path = rel_path[4:]  # Remove "lib/"
        return rel_path.replace("/", "_")

    @property
    def venv_path(self) -> Path:
        """Get path to the virtual environment."""
        return self.workspace_root / ".glo" / "venv" / self.venv_name

    @property
    def python(self) -> Path:
        """Get path to the Python interpreter."""
        return self.venv_path / "bin" / "python3"

    @property
    def build_config(self) -> BuildConfig | None:
        """Get the build configuration from build.json."""
        rel_path = self.path.lstrip("/")
        return read_build_json(self.abs_path, rel_path)

    def get_custom_target(self, name: str) -> list[TargetStep] | None:
        """Get a custom target by name from build.json, or None if not defined."""
        config = self.build_config
        if config and config.targets:
            return config.targets.get(name)
        return None

    def emit_env(self, script: Script) -> None:
        """Emit Python environment setup to script using ${WORKSPACE}."""
        venv = script.workspace_path(self.venv_path)
        script.export("VIRTUAL_ENV", venv)
        script.export("RUFF_CACHE_DIR", "${VIRTUAL_ENV}/cache/ruff")
        script.export("PYTHONPYCACHEPREFIX", "${VIRTUAL_ENV}/cache/pycache")
        script.export(
            "HYPOTHESIS_STORAGE_DIRECTORY", "${VIRTUAL_ENV}/cache/hypothesis-storage"
        )

    def emit_ps_env(self, script: Script) -> None:
        """Emit PureScript environment setup to script using ${WORKSPACE}."""
        cache_dir = script.workspace_path(
            self.workspace_root / ".glo" / "cache" / "ps" / self.venv_name
        )
        script.export("XDG_CACHE_HOME", cache_dir)
        script.export(
            "NPM_CONFIG_CACHE",
            script.workspace_path(self.workspace_root / ".glo" / "cache" / "npm"),
        )
        # Set directories in .venv (use relative paths for spago/purs compatibility)
        rel_venv = os.path.relpath(self.venv_path, self.abs_path)
        script.export("PS_VENV", rel_venv)
        script.export("PS_OUTPUT_DIR", f"{rel_venv}/output")
        script.export("PS_OUTPUT_ES_DIR", f"{rel_venv}/output-es")
        script.export("PS_BUILD_DIR", f"{rel_venv}/build")
        script.export("PS_NODE_MODULES", f"{rel_venv}/node_modules")
        script.export("PS_SPAGO_PACKAGES", f"{rel_venv}/.spago")
        # NODE_PATH for node module resolution without symlinks
        script.export("NODE_PATH", "$PS_NODE_MODULES")
        # Add tools to PATH (save original so we can restore later, not unset)
        script.raw("_SAVED_PATH=$PATH")
        self.emit_nvm_node_bin(script)
        script.raw("export PATH=$PS_NODE_MODULES/.bin:$GLO_NODE_BIN:$PATH")

    def emit_python(
        self, script: Script, args: list[str], extra_args: list[str] | None = None
    ) -> None:
        """Emit a Python command. Consolidates pushd/popd for consecutive same-project calls."""
        cmd = ["${VIRTUAL_ENV}/bin/python3"] + args
        if extra_args:
            cmd.extend(extra_args)
        path = script.workspace_path(self.abs_path)
        is_new = script.enter_project(path)
        if is_new:
            self.emit_env(script)
        script.run(cmd)
        # Don't popd - leave context open for reuse, finalize() closes it

    def emit_spago(self, script: Script, args: list[str]) -> None:
        """Emit a spago/purs command. Uses purs directly for build/test to support relocated packages."""
        path = script.workspace_path(self.abs_path)
        is_new = script.enter_project(path)
        if is_new:
            self.emit_ps_env(script)

        if args and args[0] == "build":
            # Use purs directly with sources from spago, relocated to $PS_SPAGO_PACKAGES
            extra_args = args[1:] if len(args) > 1 else []
            # Parse -u/--purs-args if present
            purs_extra = ""
            i = 0
            while i < len(extra_args):
                if extra_args[i] in ("-u", "--purs-args"):
                    if i + 1 < len(extra_args):
                        purs_extra = extra_args[i + 1]
                    break
                i += 1
            # Get codegen flags from purs_extra
            codegen = ""
            if "--codegen" in purs_extra:
                codegen = purs_extra
            script._add("echo '+ purs compile ...'")
            # Use spago sources with sed to relocate .spago -> $PS_SPAGO_PACKAGES
            # set -f disables glob expansion so purs receives the glob patterns directly
            # Pipe through tee and check for warnings (fail if any found)
            script._add(
                f'set -f; purs compile --output "$PS_OUTPUT_DIR" {codegen} '
                '"src/**/*.purs" "test/**/*.purs" '
                '$(spago sources | sed "s|^\\.spago/|$PS_SPAGO_PACKAGES/|") 2>&1 | tee /tmp/purs_output.txt; '
                'set +f; if grep -q "^Warning" /tmp/purs_output.txt; then echo "Build failed: warnings found"; exit 1; fi'
            )
        elif args and args[0] == "test":
            # Build first, then run test
            extra_args = args[1:] if len(args) > 1 else []
            purs_extra = ""
            i = 0
            while i < len(extra_args):
                if extra_args[i] in ("-u", "--purs-args"):
                    if i + 1 < len(extra_args):
                        purs_extra = extra_args[i + 1]
                    break
                i += 1
            codegen = ""
            if "--codegen" in purs_extra:
                codegen = purs_extra
            script._add("echo '+ purs compile ...'")
            # set -f disables glob expansion so purs receives the glob patterns directly
            # Pipe through tee and check for warnings (fail if any found)
            script._add(
                f'set -f; purs compile --output "$PS_OUTPUT_DIR" {codegen} '
                '"src/**/*.purs" "test/**/*.purs" '
                '$(spago sources | sed "s|^\\.spago/|$PS_SPAGO_PACKAGES/|") 2>&1 | tee /tmp/purs_output.txt; '
                'set +f; if grep -q "^Warning" /tmp/purs_output.txt; then echo "Build failed: warnings found"; exit 1; fi'
            )
            script._add("echo '+ node $PS_OUTPUT_DIR/Test.Main/index.js'")
            script._add('node "$PS_OUTPUT_DIR/Test.Main/index.js"')
        else:
            # For other commands (install, repl, etc.), use spago directly
            script.run(["spago"] + args)

    def emit_hs_env(self, script: Script) -> None:
        """Emit Haskell environment setup to script using ${WORKSPACE}."""
        hs_venv = script.workspace_path(self.venv_path)
        script.export("CABAL_DIR", f"{hs_venv}/cabal")
        script.export("HS_VENV", hs_venv)

    def emit_hs_cabal_setup(self, script: Script) -> None:
        """Emit Cabal config and ensure the package index exists."""
        self.emit_hs_env(script)
        # Write cabal config with correct paths. cabal update auto-generates one
        # with hardcoded absolute paths that break when the workspace moves.
        script.raw('mkdir -p "${CABAL_DIR}"')
        script.raw(
            'printf "%s\\n"'
            ' "repository hackage.haskell.org"'
            ' "  url: http://hackage.haskell.org/"'
            ' ""'
            ' "remote-repo-cache: ${CABAL_DIR}/packages"'
            ' "installdir: ${CABAL_DIR}/bin"'
            ' "build-summary: ${CABAL_DIR}/logs/build.log"'
            ' ""'
            ' "install-dirs user"'
            ' "  prefix: ${CABAL_DIR}"'
            ' ""'
            ' "jobs: \\$ncpus"'
            ' > "${CABAL_DIR}/config"'
        )
        script.raw(
            'if [ ! -f "${CABAL_DIR}/packages/hackage.haskell.org/01-index.tar" ]; then '
            'cabal --config-file=${CABAL_DIR}/config update; '
            'fi'
        )
        script.raw(
            'for _pkgdb in "${HS_VENV}"/store/ghc-*/package.db; do '
            '[ -d "${_pkgdb}" ] || continue; '
            'if ! ghc-pkg check --package-db="${_pkgdb}" >/tmp/glo-ghc-pkg-check 2>&1; then '
            'echo "[W] Cabal store package DB is inconsistent; rebuilding ${HS_VENV}/store"; '
            'cat /tmp/glo-ghc-pkg-check; '
            'rm -rf "${HS_VENV}/store" "${HS_VENV}/dist-newstyle"; '
            'break; '
            'fi; '
            'done'
        )

    def emit_cabal(self, script: Script, args: list[str]) -> None:
        """Emit a cabal command for Haskell builds."""
        path = script.workspace_path(self.abs_path)
        script.enter_project(path)
        self.emit_hs_cabal_setup(script)
        if args and args[0] != "update":
            script.run(
                [
                    "cabal",
                    "--config-file=${CABAL_DIR}/config",
                    "--store-dir=${HS_VENV}/store",
                ]
                + args
                + ["--builddir=${HS_VENV}/dist-newstyle"]
            )
        else:
            script.run(["cabal", "--config-file=${CABAL_DIR}/config"] + args)

    def emit_rs_env(self, script: Script) -> None:
        """Emit Rust environment setup, routing build artifacts into the venv."""
        rs_venv = script.workspace_path(self.venv_path)
        script.export("CARGO_TARGET_DIR", f"{rs_venv}/target")
        script.export("RS_VENV", rs_venv)
        script.raw(
            'if command -v glo-cargo-run-bin >/dev/null 2>&1; then '
            'export GLO_CARGO_RUN_BIN="$(command -v glo-cargo-run-bin)"; '
            'else export GLO_CARGO_RUN_BIN="${WORKSPACE}/submodules/glo/devcontainer/image/files/glo/bin/glo-cargo-run-bin"; fi'
        )

    def emit_cargo(self, script: Script, args: list[str]) -> None:
        """Emit a cargo command for Rust builds."""
        path = script.workspace_path(self.abs_path)
        is_new = script.enter_project(path)
        if is_new:
            self.emit_rs_env(script)
        script.run(["cargo"] + args)

    def emit_ts_env(self, script: Script) -> None:
        """Emit TypeScript/Node environment, routing node_modules into the venv."""
        ts_venv = script.workspace_path(self.venv_path)
        script.export("TS_VENV", ts_venv)
        script.export("TS_NODE_MODULES", f"{ts_venv}/node_modules")
        script.export(
            "NPM_CONFIG_CACHE",
            script.workspace_path(self.workspace_root / ".glo" / "cache" / "npm"),
        )
        script.export("NODE_PATH", "$TS_NODE_MODULES")
        script.raw("_SAVED_PATH=$PATH")
        self.emit_nvm_node_bin(script)
        script.raw("export PATH=$TS_NODE_MODULES/.bin:$GLO_NODE_BIN:$PATH")

    def emit_nvm_node_bin(self, script: Script) -> None:
        """Resolve latest LTS Node via nvm and expose its bin directory."""
        script.raw('export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"')
        script.raw('_GLO_NOUNSET_WAS_ON=0')
        script.raw('case $- in *u*) _GLO_NOUNSET_WAS_ON=1; set +u ;; esac')
        script.raw(
            'for _glo_nvm_sh in "$NVM_DIR/nvm.sh" '
            '"/usr/local/nvm/nvm.sh" '
            '"/opt/homebrew/opt/nvm/nvm.sh" '
            '"/usr/local/opt/nvm/nvm.sh" '
            '"/usr/share/nvm/init-nvm.sh" '
            '"/usr/share/nvm/nvm.sh"; do'
        )
        script.raw(
            '    if [ -s "$_glo_nvm_sh" ]; then . "$_glo_nvm_sh"; break; fi'
        )
        script.raw('done')
        script.raw(
            'if ! command -v nvm >/dev/null 2>&1; then '
            'echo "[E] nvm not found; run glo-local ts" >&2; exit 1; fi'
        )
        script.raw('nvm use --silent --lts >/dev/null')
        script.raw('GLO_NODE_BIN="$(dirname "$(command -v node)")"')
        script.raw('if [ "$_GLO_NOUNSET_WAS_ON" -eq 1 ]; then set -u; fi')
        script.raw('unset _GLO_NOUNSET_WAS_ON')

    def emit_rocq(self, script: Script, args: list[str]) -> None:
        """Emit a Rocq command from the project root."""
        path = script.workspace_path(self.abs_path)
        script.enter_project(path)
        self.emit_rocq_env(script)
        script.run(["rocq"] + args)

    def emit_rocq_env(self, script: Script) -> None:
        """Make Rocq available for this build without requiring shell PATH setup."""
        script.raw('if ! command -v rocq >/dev/null 2>&1; then')
        script.raw('    if command -v opam >/dev/null 2>&1 && opam switch list --short 2>/dev/null | grep -qx rocq; then')
        script.raw('        eval "$(opam env --switch=rocq --set-switch)"')
        script.raw('    fi')
        script.raw('fi')
        script.raw('if ! command -v rocq >/dev/null 2>&1; then echo "[E] rocq not found; run glo-local rocq or enable ROCQ_ENABLED in the devcontainer" >&2; exit 1; fi')

    def emit_rocq_make(self, script: Script, args: list[str]) -> None:
        """Emit a make-backed Rocq project build using _CoqProject."""
        path = script.workspace_path(self.abs_path)
        script.enter_project(path)
        self.emit_rocq_env(script)
        script.raw("if [ -f _CoqProject ]; then rocq makefile -f _CoqProject -o Makefile; fi")
        make_args = shcmd(args)
        make_cmd = "make" + (f" {make_args}" if make_args else "")
        script.raw(f"if [ -f Makefile ]; then {make_cmd}; else find . -name '*.v' -print0 | xargs -0 -r -n1 rocq compile; fi")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


# Command handler type: takes script, project, and args, emits bash to script
CommandHandler = Callable[[Script, Project, list[str]], None]


@dataclass
class Command:
    """A build command with language-specific handlers."""

    name: str
    help: str
    handlers: dict[Lang | None, CommandHandler] = field(default_factory=dict)
    project_only: bool = False  # True if this command only works on projects
    root_only: bool = False  # True if this command only works at root level
    subtargets: tuple[str, ...] = ()  # For meta-commands: run these in sequence

    def get_handler(self, lang: Lang) -> CommandHandler | None:
        """Get handler for a specific language, falling back to default."""
        return self.handlers.get(lang) or self.handlers.get(None)


COMMANDS: dict[str, Command] = {}


def cli_invocation() -> str:
    """Return the command name the user used to invoke glo-build."""
    return os.environ.get("GLO_BUILD_CMD") or Path(sys.argv[0]).name


def command(
    name: str,
    help: str,  # noqa: A002 - shadowing builtin is fine here
    project_only: bool = False,
    root_only: bool = False,
    lang: Lang | None = None,
) -> Callable[[CommandHandler], CommandHandler]:
    """Decorator to register a command handler.

    Args:
        name: Command name
        help: Help text (only used on first registration)
        project_only: True if command only works on projects
        root_only: True if command only works at root level
        lang: Language this handler is for (None = default for all languages)
    """

    def decorator(fn: CommandHandler) -> CommandHandler:
        if name not in COMMANDS:
            COMMANDS[name] = Command(
                name=name,
                help=help,
                project_only=project_only,
                root_only=root_only,
            )
        COMMANDS[name].handlers[lang] = fn
        return fn

    return decorator


def meta_command(
    name: str,
    help: str,  # noqa: A002
    subtargets: list[str],
    project_only: bool = False,
    root_only: bool = False,
) -> None:
    """Register a meta-command that runs subtargets in sequence."""
    COMMANDS[name] = Command(
        name=name,
        help=help,
        project_only=project_only,
        root_only=root_only,
        subtargets=tuple(subtargets),
    )


# ---------------------------------------------------------------------------
# Common project commands - Python
# ---------------------------------------------------------------------------


@command("venv", "Sync dependencies", lang=Lang.Python)
def cmd_venv_py(script: Script, project: Project, args: list[str]) -> None:
    """Sync virtual environment with uv."""
    del args  # unused
    script.info(f"Syncing {project.path}")
    script.pushd(script.workspace_path(project.abs_path))
    script.unset("VIRTUAL_ENV")
    venv = script.workspace_path(project.venv_path)
    script.export("UV_PYTHON_INSTALL_DIR", "${WORKSPACE}/.glo/python")
    script.export("UV_PROJECT_ENVIRONMENT", venv)
    script.raw('if [ ! -x "$UV_PROJECT_ENVIRONMENT/bin/python3" ]; then rm -rf "$UV_PROJECT_ENVIRONMENT"; fi')
    script.run(["uv", "sync", "--package", project.package_name])
    # Install Playwright Firefox browser if playwright is in any dependency group
    script.raw(
        "if grep -q 'playwright' pyproject.toml 2>/dev/null; then "
        f'XDG_CACHE_HOME="${{WORKSPACE}}/.glo/venv/cache" {shquote(str(venv))}/bin/playwright install firefox; '
        "fi"
    )
    script.popd()


@command("format", "Format code", lang=Lang.Python)
def cmd_format_py(script: Script, project: Project, args: list[str]) -> None:
    """Format code with ruff."""
    del args  # unused
    script.info(f"Formatting {project.path}")
    project.emit_python(script, ["-m", "ruff", "format"])


@command("typecheck", "Typecheck code", lang=Lang.Python)
def cmd_typecheck_py(script: Script, project: Project, args: list[str]) -> None:
    """Typecheck with mypy."""
    del args  # unused
    script.info(f"Typechecking {project.path}")
    project.emit_python(
        script,
        [
            "-m",
            "mypy",
            "--strict",
            "--config-file=pyproject.toml",
            project.package_name,
            "tests",
        ],
    )


@command("lint", "Lint code", lang=Lang.Python)
def cmd_lint_py(script: Script, project: Project, args: list[str]) -> None:
    """Lint with ruff."""
    del args  # unused
    script.info(f"Linting {project.path}")
    project.emit_python(script, ["-m", "ruff", "check", "--fix"])


@command("unit", "Run unit tests", lang=Lang.Python)
def cmd_unit_py(script: Script, project: Project, args: list[str]) -> None:
    """Run unit tests with pytest."""
    script.info(f"Unit testing {project.path}")
    tests_dir = project.abs_path / "tests"
    if not tests_dir.exists():
        script.warn(f"No tests directory in {project.path}")
        return
    project.emit_python(script, ["-m", "pytest", "-rs", "tests"], extra_args=args)


@command("clean", "Clean generated files and caches", lang=Lang.Python)
def cmd_clean_py(script: Script, project: Project, args: list[str]) -> None:
    """Clean generated files."""
    del args  # unused
    script.info(f"Cleaning {project.path}")
    dirs_to_remove = [
        ".mypy_cache",
        ".mypy_cache_strict",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        f"{project.package_name}.egg-info",
    ]
    script.pushd(script.workspace_path(project.abs_path))
    script.run(["rm", "-rf"] + dirs_to_remove)
    script.raw("find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true")
    script.raw("find . -type f -name '*.pyc' -delete 2>/dev/null || true")
    venv = script.workspace_path(project.venv_path)
    script.run(["rm", "-rf", venv])
    script.popd()


@command("repl", "Start a REPL", project_only=True, lang=Lang.Python)
def cmd_repl_py(script: Script, project: Project, args: list[str]) -> None:
    """Start a Python REPL."""
    del args  # unused
    script.info(f"Starting REPL for {project.path}")
    project.emit_python(script, [])


@command("pypackage", "Package project into distributable zip", lang=Lang.Python)
def cmd_pypackage_py(script: Script, project: Project, args: list[str]) -> None:
    """Package a Python project into a distributable zip with dependencies.

    Creates a zip file containing:
    - All production dependencies
    - The project's source code
    - Workspace dependency sources
    - build_info.json with git metadata
    - entrypoint.sh for execution

    Args (via command line):
        --debug: Preserve .py source files (default: compile to .pyc and remove sources)
        [destination]: Optional output path (default: .build/<package_name>.zip)
    """
    package_name = project.package_name
    project_path = script.workspace_path(project.abs_path)
    venv_python = script.workspace_path(project.python)

    # Parse args
    debug = "--debug" in args
    destination = None
    for arg in args:
        if arg != "--debug" and not arg.startswith("-"):
            destination = arg
            break

    script.info(f"Packaging {project.path}")

    # Check venv exists
    script.raw(f"if [ ! -x {shquote(venv_python)} ]; then")
    script.raw(f"    echo 'Virtual environment not found at {venv_python}' >&2")
    script.raw(f"    echo 'Please run: {cli_invocation()} venv' >&2")
    script.raw("    exit 1")
    script.raw("fi")

    # Check package directory exists
    script.raw(f"if [ ! -d {shquote(project_path)}/{shquote(package_name)} ]; then")
    script.raw(
        f"    echo 'Package directory {project_path}/{package_name} does not exist' >&2"
    )
    script.raw("    exit 1")
    script.raw("fi")

    # Set destination
    if destination:
        if destination.startswith("/"):
            dest_path = destination
        else:
            dest_path = "${WORKSPACE}/" + destination
    else:
        dest_path = f"${{WORKSPACE}}/.build/{package_name}.zip"

    # Create temp directory
    script.raw('PACKAGE_TEMP_DIR="$(mktemp -d)"')
    script.raw("trap 'rm -rf \"$PACKAGE_TEMP_DIR\"' EXIT")
    script.raw(f'ASSEMBLY_DIR="${{PACKAGE_TEMP_DIR}}/{package_name}"')
    script.raw('mkdir -p "$ASSEMBLY_DIR"')

    # Export production dependencies
    script.info("Exporting production dependencies")
    script.pushd(project_path)
    script.raw(
        "uv export --project . --no-dev --no-editable --no-emit-project "
        "--no-emit-workspace --no-hashes --frozen "
        '--output-file "$PACKAGE_TEMP_DIR/requirements.txt"'
    )

    # Fix wheel paths if wheels directory exists
    script.raw('WHEELS_ABS="${WORKSPACE}/wheels"')
    script.raw('if [[ -d "$WHEELS_ABS" ]]; then')
    script.raw(
        '    sed -i "s|../../wheels|$WHEELS_ABS|g" "$PACKAGE_TEMP_DIR/requirements.txt"'
    )
    script.raw("fi")

    # Handle .packageignore if present
    script.raw(f"if [ -f {shquote(project_path)}/.packageignore ]; then")
    script.raw('    echo "[I] Found .packageignore, filtering dependencies"')
    script.raw(
        "    BLACKLIST=$(grep -v '^#' "
        f"{shquote(project_path)}/.packageignore | grep -v '^[[:space:]]*$' || true)"
    )
    script.raw('    if [ -n "$BLACKLIST" ]; then')
    script.raw(
        '        BLACKLIST_PATTERN=$(echo "$BLACKLIST" | '
        "sed 's/^/^/' | sed 's/$/==/' | paste -sd'|' -)"
    )
    script.raw(
        '        grep -vE "$BLACKLIST_PATTERN" "$PACKAGE_TEMP_DIR/requirements.txt" '
        '> "$PACKAGE_TEMP_DIR/requirements_filtered.txt"'
    )
    script.raw(
        '        uv pip install --link-mode=copy --target "$ASSEMBLY_DIR" '
        '--no-deps -r "$PACKAGE_TEMP_DIR/requirements_filtered.txt"'
    )
    script.raw("    else")
    script.raw(
        '        uv pip install --link-mode=copy --target "$ASSEMBLY_DIR" '
        '-r "$PACKAGE_TEMP_DIR/requirements.txt"'
    )
    script.raw("    fi")
    script.raw("else")
    script.info("Installing dependencies to package directory")
    script.raw(
        '    uv pip install --link-mode=copy --target "$ASSEMBLY_DIR" '
        '-r "$PACKAGE_TEMP_DIR/requirements.txt"'
    )
    script.raw("fi")

    # Install workspace dependencies
    script.raw(
        f'if grep -q "workspace = true" {shquote(project_path)}/pyproject.toml 2>/dev/null; then'
    )
    script.raw('    echo "[I] Installing workspace dependencies"')
    script.raw(
        f"    WORKSPACE_DEPS=$(grep 'workspace = true' "
        f"{shquote(project_path)}/pyproject.toml | awk '{{print $1}}')"
    )
    script.raw("    for DEP in $WORKSPACE_DEPS; do")
    script.raw(
        '        DEP_DIR=$(find "${WORKSPACE}/lib" -maxdepth 2 -name "pyproject.toml" '
        '-exec grep -l "name = \\"$DEP\\"" {} \\; 2>/dev/null | head -1 | xargs dirname 2>/dev/null || true)'
    )
    script.raw('        if [ -n "$DEP_DIR" ] && [ -d "$DEP_DIR" ]; then')
    script.raw('            echo "[I] Installing workspace dependency: $DEP"')
    script.raw(
        '            uv pip install --link-mode=copy --target "$ASSEMBLY_DIR" "$DEP_DIR"'
    )
    script.raw("        fi")
    script.raw("    done")
    script.raw("fi")

    # Install the project itself (no deps)
    script.info(f"Installing {package_name} to package directory")
    script.raw(
        f'uv pip install --link-mode=copy --target "$ASSEMBLY_DIR" '
        f"--no-deps {shquote(project_path)}"
    )

    # Copy source code
    script.info("Copying source code to package directory")
    script.raw(
        f'cp -r {shquote(project_path)}/{shquote(package_name)} "$ASSEMBLY_DIR/"'
    )

    # Copy workspace dependency sources by looking for .pth files pointing to workspace
    script.raw('echo "[I] Copying workspace dependency source code from .pth files"')
    script.raw('for PTH_FILE in "$ASSEMBLY_DIR"/_*.pth; do')
    script.raw('    [ -f "$PTH_FILE" ] || continue')
    script.raw('    PTH_TARGET=$(cat "$PTH_FILE")')
    script.raw("    # Check if .pth points to a workspace lib directory")
    script.raw('    if [[ "$PTH_TARGET" == */lib/* ]]; then')
    script.raw('        PKG_NAME=$(basename "$PTH_FILE" .pth | sed "s/^_//")')
    script.raw('        if [ -d "$PTH_TARGET/$PKG_NAME" ]; then')
    script.raw('            echo "[I] Copying workspace dependency source: $PKG_NAME"')
    script.raw('            cp -r "$PTH_TARGET/$PKG_NAME" "$ASSEMBLY_DIR/"')
    script.raw("        fi")
    script.raw("    fi")
    script.raw("done")
    script.raw("# Remove .pth files as we now have the actual source")
    script.raw('rm -f "$ASSEMBLY_DIR"/_*.pth 2>/dev/null || true')

    # Clean up unnecessary files
    script.info("Cleaning up unnecessary files")
    script.raw('rm -f "$ASSEMBLY_DIR"/.lock 2>/dev/null || true')
    script.raw('rm -rf "$ASSEMBLY_DIR"/include 2>/dev/null || true')
    script.raw('rm -rf "$ASSEMBLY_DIR"/bin 2>/dev/null || true')

    # Compile to .pyc and remove sources in non-debug builds
    if not debug:
        script.info("Compiling .py files to .pyc for internal packages")
        # Compile main package and any glo_* workspace dependencies
        script.raw(
            f'for PKG_DIR in "$ASSEMBLY_DIR"/{shquote(package_name)} "$ASSEMBLY_DIR"/glo_*; do'
        )
        script.raw('    if [ -d "$PKG_DIR" ]; then')
        script.raw('        DIR_NAME=$(basename "$PKG_DIR")')
        script.raw('        PY_COUNT=$(find "$PKG_DIR" -type f -name "*.py" | wc -l)')
        script.raw('        if [ "$PY_COUNT" -gt 0 ]; then')
        script.raw('            echo "[I] Compiling $PY_COUNT .py files in $DIR_NAME"')
        script.raw(
            f'            {shquote(venv_python)} -m compileall -b -q -o 2 "$PKG_DIR"'
        )
        script.raw("        fi")
        script.raw("    fi")
        script.raw("done")

        script.info("Removing .py source files from internal packages")
        script.raw(
            f'for PKG_DIR in "$ASSEMBLY_DIR"/{shquote(package_name)} "$ASSEMBLY_DIR"/glo_*; do'
        )
        script.raw('    if [ -d "$PKG_DIR" ]; then')
        script.raw('        find "$PKG_DIR" -type f -name "*.py" -delete')
        script.raw(
            '        find "$PKG_DIR" -type d -name "__pycache__" '
            "-exec rm -rf {} + 2>/dev/null || true"
        )
        script.raw("    fi")
        script.raw("done")
    else:
        script.info("Preserving .py source files (debug build)")

    # Create build_info.json (git info captured at plan time)
    script.info("Creating build_info.json")
    debug_str = "true" if debug else "false"
    git_info = get_git_info()
    script.raw('BUILD_TIME="$(date -u +"%Y%m%dT%H%M%S")"')
    script.raw(
        "printf '%s\\n' "
        "'{' "
        f'\'  "package_name": "{package_name}",\' '
        f'\'  "project_name": "{project.name}",\' '
        f'\'  "project_path": "{project.path.lstrip("/")}",\' '
        '\'  "project_type": "py",\' '
        f'\'  "git_sha": "{git_info["sha"]}",\' '
        f'\'  "git_sha_short": "{git_info["sha_short"]}",\' '
        f'\'  "git_branch": "{git_info["branch"]}",\' '
        '\'  "build_time": "\'"$BUILD_TIME"\'",\' '
        f"'  \"git_dirty\": {git_info['dirty']},' "
        f'\'  "date_with_sha": "\'"$BUILD_TIME"\'_{git_info["sha_short"]},\' '
        f"'  \"debug\": {debug_str}' "
        "'}' > \"$ASSEMBLY_DIR/build_info.json\""
    )

    # Create entrypoint.sh
    script.info("Checking for entrypoint")
    script.raw(f"if [ -f {shquote(project_path)}/entrypoint.sh ]; then")
    script.raw('    echo "[I] Found existing entrypoint.sh, copying it"')
    script.raw(f'    cp {shquote(project_path)}/entrypoint.sh "$ASSEMBLY_DIR/"')
    script.raw('    chmod +x "$ASSEMBLY_DIR/entrypoint.sh"')
    script.raw(
        f"elif [ -f {shquote(project_path)}/{shquote(package_name)}/main.py ]; then"
    )
    script.raw(f'    echo "[I] Creating entrypoint.sh for {package_name}.main"')
    # Use printf to avoid heredoc indentation issues
    script.raw(
        "printf '%s\\n' "
        "'#!/usr/bin/env bash' "
        "'set -euo pipefail' "
        '\'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\' '
        "'cd \"${SCRIPT_DIR}\"' "
        "'export PYTHONPATH=\"${SCRIPT_DIR}:${PYTHONPATH:-}\"' "
        f"'exec python3 -m {package_name}.main \"$@\"' "
        '> "$ASSEMBLY_DIR/entrypoint.sh"'
    )
    script.raw('    chmod +x "$ASSEMBLY_DIR/entrypoint.sh"')
    script.raw(
        f"elif [ -f {shquote(project_path)}/{shquote(package_name)}/cli.py ]; then"
    )
    script.raw(f'    echo "[I] Creating entrypoint.sh for {package_name}.cli"')
    # Use printf to avoid heredoc indentation issues
    script.raw(
        "printf '%s\\n' "
        "'#!/usr/bin/env bash' "
        "'set -euo pipefail' "
        '\'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\' '
        "'cd \"${SCRIPT_DIR}\"' "
        "'export PYTHONPATH=\"${SCRIPT_DIR}:${PYTHONPATH:-}\"' "
        f"'exec python3 -m {package_name}.cli \"$@\"' "
        '> "$ASSEMBLY_DIR/entrypoint.sh"'
    )
    script.raw('    chmod +x "$ASSEMBLY_DIR/entrypoint.sh"')
    script.raw("else")
    script.raw(
        f'    echo "[W] No entrypoint.sh, main.py, or cli.py found in {package_name}"'
    )
    script.raw('    echo "[W] Skipping entrypoint creation"')
    script.raw("fi")

    # Create zip file
    script.info(f"Creating zip file: {package_name}.zip")
    script.raw("(")
    script.raw('    cd "$PACKAGE_TEMP_DIR"')
    script.raw(
        f'    zip -rq "${{PACKAGE_TEMP_DIR}}/{package_name}.zip" "{package_name}"'
    )
    script.raw(")")

    # Create destination directory and copy
    script.raw(f'mkdir -p "$(dirname {shquote(dest_path)})"')
    script.raw(f'cp "${{PACKAGE_TEMP_DIR}}/{package_name}.zip" {shquote(dest_path)}')

    script.info("Package created successfully")
    script.raw(f'echo "[I] Output: {dest_path}"')
    script.raw(f"ls -lh {shquote(dest_path)}")

    script.popd()


@command("pypackage", "Package project into distributable zip", lang=Lang.Purescript)
def cmd_pypackage_ps(script: Script, project: Project, args: list[str]) -> None:
    """Skip packaging for PureScript projects."""
    del args  # unused
    script.info(f"Skipping pypackage for {project.path} (PureScript)")


# ---------------------------------------------------------------------------
# Common project commands - PureScript
# ---------------------------------------------------------------------------


@command("venv", "Sync dependencies", lang=Lang.Purescript)
def cmd_venv_ps(script: Script, project: Project, args: list[str]) -> None:
    """Install PureScript dependencies with npm and spago."""
    del args  # unused
    script.info(f"Installing dependencies for {project.path}")
    path = script.workspace_path(project.abs_path)
    script.enter_project(path)
    project.emit_ps_env(script)
    # Install npm packages in venv directory (no symlinks, enables caching)
    script.raw("rm -rf node_modules")
    script.raw("mkdir -p $(dirname $PS_NODE_MODULES)")
    script.raw("cp package.json $(dirname $PS_NODE_MODULES)/")
    script.raw("cp package-lock.json $(dirname $PS_NODE_MODULES)/ 2>/dev/null || true")
    script.raw('echo "+ npm install --prefix $(dirname $PS_NODE_MODULES)"')
    script.raw("npm install --prefix $(dirname $PS_NODE_MODULES)")
    script.raw("cp $(dirname $PS_NODE_MODULES)/package-lock.json . 2>/dev/null || true")
    # Install spago packages in venv directory (enables caching)
    script.raw("rm -rf .spago")
    script.raw("mkdir -p $(dirname $PS_SPAGO_PACKAGES)")
    # Copy spago.yaml, adjusting relative paths in extraPackages (../ -> ../../lib/)
    script.raw(
        r"sed 's|path: \.\./|path: ../../lib/|g' spago.yaml > $(dirname $PS_SPAGO_PACKAGES)/spago.yaml"
    )
    script.raw("pushd $(dirname $PS_SPAGO_PACKAGES) > /dev/null")
    script.raw('echo "+ spago install (in $(pwd))"')
    # New spago requires purs in PATH
    script.raw("PATH=$PWD/node_modules/.bin:$PATH ./node_modules/.bin/spago install")
    script.raw("popd > /dev/null")
    # Install Playwright Firefox browser if playwright is a dependency
    # Use $PS_NODE_MODULES/.bin/playwright directly since npx doesn't respect NODE_PATH
    script.raw("if grep -q '\"playwright\"' package.json 2>/dev/null; then")
    script.raw(
        '  echo "+ XDG_CACHE_HOME=${WORKSPACE}/.glo/venv/cache $PS_NODE_MODULES/.bin/playwright install firefox"'
    )
    script.raw(
        '  XDG_CACHE_HOME="${WORKSPACE}/.venv/cache" $PS_NODE_MODULES/.bin/playwright install firefox'
    )
    script.raw("fi")


@command("format", "Format code", lang=Lang.Purescript)
def cmd_format_ps(script: Script, project: Project, args: list[str]) -> None:
    """Format code with purs-tidy."""
    del args  # unused
    script.info(f"Formatting {project.path}")
    path = script.workspace_path(project.abs_path)
    is_new = script.enter_project(path)
    if is_new:
        project.emit_ps_env(script)
    script.run(["purs-tidy", "format-in-place", "src/**/*.purs"])


@command("typecheck", "Typecheck code", lang=Lang.Purescript)
def cmd_typecheck_ps(script: Script, project: Project, args: list[str]) -> None:
    """Build with spago (includes type checking)."""
    del args  # unused
    script.info(f"Building {project.path}")
    project.emit_spago(script, ["build"])


@command("lint", "Lint code", lang=Lang.Purescript)
def cmd_lint_ps(script: Script, project: Project, args: list[str]) -> None:
    """Lint PureScript code (no-op for now)."""
    del args  # unused
    script.info(f"Linting {project.path} (no-op)")


@command("unit", "Run unit tests", lang=Lang.Purescript)
def cmd_unit_ps(script: Script, project: Project, args: list[str]) -> None:
    """Run tests with spago."""
    del args  # unused
    script.info(f"Testing {project.path}")
    test_dir = project.abs_path / "test"
    if not test_dir.exists():
        script.warn(f"No test directory in {project.path}")
        return
    project.emit_spago(script, ["test"])


@command("clean", "Clean generated files and caches", lang=Lang.Purescript)
def cmd_clean_ps(script: Script, project: Project, args: list[str]) -> None:
    """Clean PureScript build artifacts."""
    del args  # unused
    script.info(f"Cleaning {project.path}")
    path = script.workspace_path(project.abs_path)
    script.enter_project(path)
    # Clean local symlinks
    script.run(["rm", "-rf", ".spago", "node_modules"])
    # Clean directories in .venv
    venv_dir = script.workspace_path(project.venv_path)
    cache_dir = script.workspace_path(
        project.workspace_root / ".cache" / "ps" / project.name
    )
    script.run(
        [
            "rm",
            "-rf",
            f"{venv_dir}/output",
            f"{venv_dir}/output-es",
            f"{venv_dir}/build",
            f"{venv_dir}/node_modules",
            f"{venv_dir}/spago",
            cache_dir,
        ]
    )


@command("repl", "Start a REPL", project_only=True, lang=Lang.Purescript)
def cmd_repl_ps(script: Script, project: Project, args: list[str]) -> None:
    """Start a PureScript REPL."""
    del args  # unused
    script.info(f"Starting REPL for {project.path}")
    project.emit_spago(script, ["repl"])


# ---------------------------------------------------------------------------
# Meta commands (language-agnostic)
# ---------------------------------------------------------------------------


meta_command("test", "Run all tests (typecheck + unit)", ["typecheck", "unit"])
meta_command(
    "precommit",
    "Run gen and all checks (format + lint + test)",
    ["gen", "format", "lint", "test"],
)
meta_command(
    "all",
    "Run full build (precommit + dist + integration)",
    ["precommit", "dist", "integration"],
)


@command("license-check", "Check dependency licenses", lang=Lang.Python)
def cmd_license_check(script: Script, project: Project, args: list[str]) -> None:
    """Check dependency licenses."""
    del args  # unused
    script.info(f"License check for {project.path}")
    project.emit_python(
        script,
        [
            "-m",
            "licensecheck",
            "--ignore-packages",
            "nvidia*",
            "certifi",
            "--only-licenses",
            "MIT",
            "BSD",
            "APACHE",
            "UNLICENSE",
            "PSF-2.0",
        ],
    )


@command("license-check", "Check dependency licenses", lang=Lang.Purescript)
def cmd_license_check_ps(script: Script, project: Project, args: list[str]) -> None:
    """Check dependency licenses (no-op for PureScript)."""
    del args  # unused
    script.info(f"License check for {project.path} (no-op)")


# ---------------------------------------------------------------------------
# Common project commands - Haskell
# ---------------------------------------------------------------------------


@command("venv", "Sync dependencies", lang=Lang.Haskell)
def cmd_venv_haskell(script: Script, project: Project, args: list[str]) -> None:
    """Update Haskell dependencies with cabal."""
    del args  # unused
    script.info(f"Updating dependencies for {project.path}")
    project.emit_hs_cabal_setup(script)
    project.emit_cabal(script, ["build", "--only-dependencies"])


@command("format", "Format code", lang=Lang.Haskell)
def cmd_format_haskell(script: Script, project: Project, args: list[str]) -> None:
    """Format Haskell code with ormolu."""
    del args  # unused
    script.info(f"Formatting {project.path}")
    path = script.workspace_path(project.abs_path)
    script.enter_project(path)
    dirs = ["src"]
    if (project.abs_path / "test").exists():
        dirs.append("test")
    script.raw('if ! command -v ormolu >/dev/null 2>&1; then echo "[I] Skipping Haskell format; ormolu not found"; exit 0; fi')
    script.raw('_ORMOLU_CONF="${WORKSPACE}/config/hs/ormolu.yaml"')
    script.raw(
        '[ -f "$_ORMOLU_CONF" ]'
        ' && _ORMOLU_ARGS="--config=$_ORMOLU_CONF"'
        " || _ORMOLU_ARGS="
    )
    dir_str = " ".join(dirs)
    script.raw(
        f"find {dir_str} -name '*.hs' -type f -print0"
        " | xargs -0 -r ormolu $_ORMOLU_ARGS --mode inplace"
    )


@command("typecheck", "Typecheck code", lang=Lang.Haskell)
def cmd_typecheck_haskell(script: Script, project: Project, args: list[str]) -> None:
    """Typecheck with cabal build."""
    del args  # unused
    script.info(f"Typechecking {project.path}")
    project.emit_cabal(script, ["build"])
    _install_hs_executables(script, project)
    _install_hs_data_files(script, project)


def _install_hs_executables(script: Script, project: Project) -> None:
    """Auto-install Haskell executables into venv bin after build."""
    cabal_files = list(project.abs_path.glob("*.cabal"))
    if not cabal_files:
        return
    exe_names = []
    with open(cabal_files[0]) as f:
        for line in f:
            m = re.match(r"^executable\s+(\S+)", line)
            if m:
                exe_names.append(m.group(1))
    if not exe_names:
        return
    script.raw("mkdir -p ${HS_VENV}/bin")
    for name in exe_names:
        script.raw(
            f"install -m 755 $(cabal --config-file=${{CABAL_DIR}}/config --store-dir=${{HS_VENV}}/store list-bin {name}"
            f" --builddir=${{HS_VENV}}/dist-newstyle) ${{HS_VENV}}/bin/{name}"
        )


def _install_hs_data_files(script: Script, project: Project) -> None:
    """Install cabal data-files to the location expected by Paths_<pkg>."""
    cabal_files = list(project.abs_path.glob("*.cabal"))
    if not cabal_files:
        return
    data_dir = None
    pkg_name = None
    with open(cabal_files[0]) as f:
        for line in f:
            m = re.match(r"^data-dir:\s*(\S+)", line)
            if m:
                data_dir = m.group(1)
            m = re.match(r"^name:\s*(\S+)", line)
            if m:
                pkg_name = m.group(1)
    if not data_dir or not pkg_name:
        return
    data_path = project.abs_path / data_dir
    if not data_path.exists():
        return
    paths_mod = "Paths_" + pkg_name.replace("-", "_")
    src = script.workspace_path(data_path)
    script.raw(
        f"_PATHS_HS=$(find ${{HS_VENV}}/dist-newstyle -name '{paths_mod}.hs'"
        f" -path '*/autogen/*' | head -1)"
    )
    script.raw('_DATADIR=$(sed -n \'s/^datadir  *= *"\\(.*\\)"/\\1/p\' "$_PATHS_HS")')
    script.raw(
        f'if [ -n "$_DATADIR" ]; then mkdir -p "$_DATADIR" && cp -r {src}/* "$_DATADIR/"; fi'
    )


@command("lint", "Lint code", lang=Lang.Haskell)
def cmd_lint_haskell(script: Script, project: Project, args: list[str]) -> None:
    """Lint Haskell code with hlint."""
    del args  # unused
    script.info(f"Linting {project.path}")
    path = script.workspace_path(project.abs_path)
    script.enter_project(path)
    dirs = ["src"]
    if (project.abs_path / "test").exists():
        dirs.append("test")
    dir_args = " ".join(dirs)
    script.raw(
        '_HLINT_CONF="${WORKSPACE}/config/hs/hlint.yaml"'
    )
    script.raw(
        '[ -f "$_HLINT_CONF" ]'
        ' && _HLINT_ARGS="--hint=$_HLINT_CONF"'
        " || _HLINT_ARGS="
    )
    script.raw(f"hlint $_HLINT_ARGS {dir_args}")
    # NOTE: apply-refact is really flaky, so this didn't work so well:
    # script.raw(f"hlint {hint} {dir_args} | tee /tmp/hlint-out.txt || true")
    # script.raw(
    #     f"grep -oP '^[^ :]+\\.hs' /tmp/hlint-out.txt"
    #     f" | sort -u"
    #     f" | xargs -r -n1 -t hlint {hint} --refactor '--refactor-options=--inplace'"
    #     f" || true"
    # )


@command("unit", "Run unit tests", lang=Lang.Haskell)
def cmd_unit_haskell(script: Script, project: Project, args: list[str]) -> None:
    """Run Haskell tests with cabal test."""
    del args  # unused
    script.info(f"Testing {project.path}")
    project.emit_cabal(script, ["test", "--test-show-details=direct"])


@command("doc", "Generate documentation", lang=Lang.Haskell)
def cmd_doc_haskell(script: Script, project: Project, args: list[str]) -> None:
    """Generate Haskell documentation with cabal haddock."""
    script.info(f"Generating docs for {project.path}")
    project.emit_cabal(script, ["haddock"] + args)


@command("clean", "Clean generated files and caches", lang=Lang.Haskell)
def cmd_clean_haskell(script: Script, project: Project, args: list[str]) -> None:
    """Clean Haskell build artifacts."""
    del args  # unused
    script.info(f"Cleaning {project.path}")
    venv = script.workspace_path(project.venv_path)
    script.run(["rm", "-rf", venv])


@command("repl", "Start a REPL", project_only=True, lang=Lang.Haskell)
def cmd_repl_haskell(script: Script, project: Project, args: list[str]) -> None:
    """Start Haskell REPL with cabal repl."""
    del args  # unused
    script.info(f"Starting REPL for {project.path}")
    project.emit_cabal(script, ["repl"])


@command("ghci", "Start GHCi via cabal repl", project_only=True, lang=Lang.Haskell)
def cmd_ghci_haskell(script: Script, project: Project, args: list[str]) -> None:
    """Start GHCi with correct venv paths via cabal repl."""
    script.info(f"Starting GHCi for {project.path}")
    project.emit_cabal(script, ["repl"] + args)


@command("license-check", "Check dependency licenses", lang=Lang.Haskell)
def cmd_license_check_haskell(
    script: Script, project: Project, args: list[str]
) -> None:
    """Check dependency licenses (no-op for Haskell)."""
    del args  # unused
    script.info(f"License check for {project.path} (no-op)")


# ---------------------------------------------------------------------------
# Common project commands - Rust
# ---------------------------------------------------------------------------


@command("venv", "Sync dependencies", lang=Lang.Rust)
def cmd_venv_rs(script: Script, project: Project, args: list[str]) -> None:
    """Fetch Rust dependencies with cargo."""
    del args  # unused
    script.info(f"Fetching dependencies for {project.path}")
    project.emit_cargo(script, ["fetch"])


@command("format", "Format code", lang=Lang.Rust)
def cmd_format_rs(script: Script, project: Project, args: list[str]) -> None:
    """Format Rust code with rustfmt."""
    del args  # unused
    script.info(f"Formatting {project.path}")
    project.emit_cargo(script, ["fmt"])


@command("typecheck", "Typecheck code", lang=Lang.Rust)
def cmd_typecheck_rs(script: Script, project: Project, args: list[str]) -> None:
    """Typecheck Rust code with cargo check."""
    del args  # unused
    script.info(f"Typechecking {project.path}")
    project.emit_cargo(script, ["check"])


@command("lint", "Lint code", lang=Lang.Rust)
def cmd_lint_rs(script: Script, project: Project, args: list[str]) -> None:
    """Lint Rust code with clippy."""
    del args  # unused
    script.info(f"Linting {project.path}")
    project.emit_cargo(script, ["clippy", "--", "-D", "warnings"])


@command("unit", "Run unit tests", lang=Lang.Rust)
def cmd_unit_rs(script: Script, project: Project, args: list[str]) -> None:
    """Run Rust tests with cargo test."""
    script.info(f"Testing {project.path}")
    project.emit_cargo(script, ["test"] + args)


@command("clean", "Clean generated files and caches", lang=Lang.Rust)
def cmd_clean_rs(script: Script, project: Project, args: list[str]) -> None:
    """Clean Rust build artifacts."""
    del args  # unused
    script.info(f"Cleaning {project.path}")
    venv = script.workspace_path(project.venv_path)
    project.emit_cargo(script, ["clean"])
    script.run(["rm", "-rf", venv])


@command("repl", "Start a REPL", project_only=True, lang=Lang.Rust)
def cmd_repl_rs(script: Script, project: Project, args: list[str]) -> None:
    """No standard REPL for Rust."""
    del args  # unused
    script.warn(f"No REPL available for Rust project {project.path}")


@command("license-check", "Check dependency licenses", lang=Lang.Rust)
def cmd_license_check_rs(script: Script, project: Project, args: list[str]) -> None:
    """Check dependency licenses (no-op for Rust)."""
    del args  # unused
    script.info(f"License check for {project.path} (no-op)")


@command("run-bin", "Run a project-pinned Rust binary", project_only=True, lang=Lang.Rust)
def cmd_run_bin_rs(script: Script, project: Project, args: list[str]) -> None:
    """Run a binary declared in [package.metadata.bin] via the project venv."""
    if not args:
        script.raw("echo 'usage: run-bin <tool> [args...]' >&2; exit 2")
        return
    path = script.workspace_path(project.abs_path)
    is_new = script.enter_project(path)
    if is_new:
        project.emit_rs_env(script)
    script.run(["${GLO_CARGO_RUN_BIN}"] + args)


# ---------------------------------------------------------------------------
# Common project commands - TypeScript
# ---------------------------------------------------------------------------


@command("venv", "Sync dependencies", lang=Lang.TypeScript)
def cmd_venv_ts(script: Script, project: Project, args: list[str]) -> None:
    """Install TypeScript dependencies with npm into the venv directory."""
    del args  # unused
    script.info(f"Installing dependencies for {project.path}")
    path = script.workspace_path(project.abs_path)
    script.enter_project(path)
    project.emit_ts_env(script)
    script.raw("rm -rf node_modules")
    script.raw("mkdir -p $(dirname $TS_NODE_MODULES)")
    script.raw("cp package.json $(dirname $TS_NODE_MODULES)/")
    script.raw("cp package-lock.json $(dirname $TS_NODE_MODULES)/ 2>/dev/null || true")
    script.raw('echo "+ npm install --prefix $(dirname $TS_NODE_MODULES)"')
    script.raw("npm install --prefix $(dirname $TS_NODE_MODULES)")
    script.raw("cp $(dirname $TS_NODE_MODULES)/package-lock.json . 2>/dev/null || true")


@command("format", "Format code", lang=Lang.TypeScript)
def cmd_format_ts(script: Script, project: Project, args: list[str]) -> None:
    """Format TypeScript code with prettier."""
    del args  # unused
    script.info(f"Formatting {project.path}")
    path = script.workspace_path(project.abs_path)
    is_new = script.enter_project(path)
    if is_new:
        project.emit_ts_env(script)
    script.run(["$TS_NODE_MODULES/.bin/prettier", "--write", "src/"])


@command("typecheck", "Typecheck code", lang=Lang.TypeScript)
def cmd_typecheck_ts(script: Script, project: Project, args: list[str]) -> None:
    """Typecheck TypeScript code with tsc."""
    del args  # unused
    script.info(f"Typechecking {project.path}")
    path = script.workspace_path(project.abs_path)
    is_new = script.enter_project(path)
    if is_new:
        project.emit_ts_env(script)
    script.run(["$TS_NODE_MODULES/.bin/tsc", "--noEmit"])


@command("lint", "Lint code", lang=Lang.TypeScript)
def cmd_lint_ts(script: Script, project: Project, args: list[str]) -> None:
    """Lint TypeScript code with eslint."""
    del args  # unused
    script.info(f"Linting {project.path}")
    path = script.workspace_path(project.abs_path)
    is_new = script.enter_project(path)
    if is_new:
        project.emit_ts_env(script)
    script.run(["$TS_NODE_MODULES/.bin/eslint", "src/"])


@command("unit", "Run unit tests", lang=Lang.TypeScript)
def cmd_unit_ts(script: Script, project: Project, args: list[str]) -> None:
    """Run TypeScript tests."""
    script.info(f"Testing {project.path}")
    path = script.workspace_path(project.abs_path)
    is_new = script.enter_project(path)
    if is_new:
        project.emit_ts_env(script)
    script.run(["$TS_NODE_MODULES/.bin/jest"] + args)


@command("clean", "Clean generated files and caches", lang=Lang.TypeScript)
def cmd_clean_ts(script: Script, project: Project, args: list[str]) -> None:
    """Clean TypeScript build artifacts."""
    del args  # unused
    script.info(f"Cleaning {project.path}")
    venv = script.workspace_path(project.venv_path)
    script.pushd(script.workspace_path(project.abs_path))
    script.run(["rm", "-rf", "node_modules", "dist"])
    script.run(["rm", "-rf", venv])
    script.popd()


@command("repl", "Start a REPL", project_only=True, lang=Lang.TypeScript)
def cmd_repl_ts(script: Script, project: Project, args: list[str]) -> None:
    """Start a Node.js REPL."""
    del args  # unused
    script.info(f"Starting Node REPL for {project.path}")
    path = script.workspace_path(project.abs_path)
    is_new = script.enter_project(path)
    if is_new:
        project.emit_ts_env(script)
    script.run(["node"])


@command("license-check", "Check dependency licenses", lang=Lang.TypeScript)
def cmd_license_check_ts(script: Script, project: Project, args: list[str]) -> None:
    """Check dependency licenses (no-op for TypeScript)."""
    del args  # unused
    script.info(f"License check for {project.path} (no-op)")


# ---------------------------------------------------------------------------
# Common project commands - Rocq
# ---------------------------------------------------------------------------


@command("venv", "Sync dependencies", lang=Lang.Rocq)
def cmd_venv_rocq(script: Script, project: Project, args: list[str]) -> None:
    """Prepare Rocq project build files."""
    del args  # unused
    script.info(f"Preparing Rocq project {project.path}")
    path = script.workspace_path(project.abs_path)
    script.enter_project(path)
    project.emit_rocq_env(script)
    script.raw("if [ -f _CoqProject ]; then rocq makefile -f _CoqProject -o Makefile; fi")


@command("format", "Format code", lang=Lang.Rocq)
def cmd_format_rocq(script: Script, project: Project, args: list[str]) -> None:
    """No standard Rocq formatter is available."""
    del args  # unused
    script.info(f"Formatting {project.path} (no-op)")


@command("typecheck", "Typecheck code", lang=Lang.Rocq)
def cmd_typecheck_rocq(script: Script, project: Project, args: list[str]) -> None:
    """Compile Rocq files."""
    del args  # unused
    script.info(f"Typechecking {project.path}")
    project.emit_rocq_make(script, [])


@command("lint", "Lint code", lang=Lang.Rocq)
def cmd_lint_rocq(script: Script, project: Project, args: list[str]) -> None:
    """No standard Rocq linter is available."""
    del args  # unused
    script.info(f"Linting {project.path} (no-op)")


@command("unit", "Run unit tests", lang=Lang.Rocq)
def cmd_unit_rocq(script: Script, project: Project, args: list[str]) -> None:
    """Rocq tests are checked as part of project compilation."""
    del args  # unused
    script.info(f"Testing {project.path} (covered by typecheck)")


@command("doc", "Generate documentation", lang=Lang.Rocq)
def cmd_doc_rocq(script: Script, project: Project, args: list[str]) -> None:
    """Generate Rocq documentation for project files."""
    script.info(f"Generating docs for {project.path}")
    path = script.workspace_path(project.abs_path)
    script.enter_project(path)
    script.raw("mkdir -p doc")
    script.raw("find . -name '*.v' -print0 | xargs -0 -r rocq doc -d doc " + shcmd(args))


@command("clean", "Clean generated files and caches", lang=Lang.Rocq)
def cmd_clean_rocq(script: Script, project: Project, args: list[str]) -> None:
    """Clean Rocq build artifacts."""
    del args  # unused
    script.info(f"Cleaning {project.path}")
    path = script.workspace_path(project.abs_path)
    script.enter_project(path)
    script.raw("if [ -f Makefile ]; then make cleanall || make clean; fi")
    script.raw("find . -type f \\( -name '*.vo' -o -name '*.vos' -o -name '*.vok' -o -name '*.glob' -o -name '*.aux' \\) -delete")
    script.run(["rm", "-rf", "doc", script.workspace_path(project.venv_path)])


@command("repl", "Start a REPL", project_only=True, lang=Lang.Rocq)
def cmd_repl_rocq(script: Script, project: Project, args: list[str]) -> None:
    """Start Rocq repl."""
    script.info(f"Starting Rocq repl for {project.path}")
    project.emit_rocq(script, ["repl"] + args)


@command("license-check", "Check dependency licenses", lang=Lang.Rocq)
def cmd_license_check_rocq(script: Script, project: Project, args: list[str]) -> None:
    """Check dependency licenses (no-op for Rocq)."""
    del args  # unused
    script.info(f"License check for {project.path} (no-op)")


@command("cli", "Run the project CLI", project_only=True, lang=Lang.Python)
def cmd_cli(script: Script, project: Project, args: list[str]) -> None:
    """Run the project CLI."""
    script.info(f"Running CLI for {project.path}")
    project.emit_python(script, ["-m", f"{project.package_name}.cli"], extra_args=args)


@command("doc", "Generate documentation")
def cmd_doc(script: Script, project: Project, args: list[str]) -> None:
    """Generate documentation (no-op unless the language has a handler)."""
    del args  # unused
    script.info(f"Generating docs for {project.path} (no-op)")


# ---------------------------------------------------------------------------
# Project-specific commands
# ---------------------------------------------------------------------------


@command("gen", "Generate code (runs gen.py if present)")
def cmd_gen(script: Script, project: Project, args: list[str]) -> None:
    """Generate code by running gen.py at project root if present."""
    del args  # unused
    gen_script = project.abs_path / "gen.py"
    if not gen_script.exists():
        script.info(f"No gen.py in {project.path}")
        return
    script.info(f"Generating code for {project.path}")
    path = script.workspace_path(project.abs_path)
    is_new = script.enter_project(path)
    if project.language == Lang.Rust and is_new:
        project.emit_rs_env(script)
    script.run(["python3", "-B", script.workspace_path(gen_script)])


@command("dist", "Build distribution (runs dist.py if present)")
def cmd_dist(script: Script, project: Project, args: list[str]) -> None:
    """Build distribution by running dist.py at project root if present."""
    del args  # unused
    dist_script = project.abs_path / "dist.py"
    if not dist_script.exists():
        script.info(f"No dist.py in {project.path}")
        return
    script.info(f"Building distribution for {project.path}")
    path = script.workspace_path(project.abs_path)
    is_new = script.enter_project(path)
    if project.language == Lang.Rust and is_new:
        project.emit_rs_env(script)
    script.run(["python3", "-B", script.workspace_path(dist_script)])


@command(
    "integration",
    "Run integration tests (if build.json target exists)",
)
def cmd_integration(script: Script, project: Project, args: list[str]) -> None:
    """Run integration tests if a build.json integration target exists.

    This is a fallback handler for projects without an integration target.
    Projects with integration tests should define the target in build.json.
    """
    del args  # unused
    # If we reach here, there's no custom integration target in build.json
    script.info(f"No integration target in {project.path}")


@command("dev", "Run development server", project_only=True, lang=Lang.Python)
def cmd_dev_py(script: Script, project: Project, args: list[str]) -> None:
    """Run development server (web project only)."""
    if project.name != "web":
        script.raw("echo 'dev command is only available for /lib/web' >&2; exit 1")
        return
    script.info(f"Starting dev server for {project.path}")
    port = "8939"
    extra_args = list(args)
    if "--port" not in args and "-p" not in args:
        extra_args = ["--port", port] + extra_args
    project.emit_python(
        script,
        ["-m", "uvicorn", "glo_web.app:app", "--host", "127.0.0.1", "--reload"],
        extra_args=extra_args,
    )


@command("dev", "Run development server", project_only=True, lang=Lang.Purescript)
def cmd_dev_ps(script: Script, project: Project, args: list[str]) -> None:
    """Run development server for PureScript SPA."""
    del args  # unused
    script.info(f"Starting dev server for {project.path}")
    script.pushd(script.workspace_path(project.abs_path))
    script.run(["spago", "build", "--watch"])
    script.popd()


@command("serve", "Run production server", project_only=True, lang=Lang.Python)
def cmd_serve_py(script: Script, project: Project, args: list[str]) -> None:
    """Run production server."""
    if project.name != "web":
        script.raw(
            f"echo 'serve command is not available for {project.path}' >&2; exit 1"
        )
        return
    script.info(f"Starting server for {project.path}")
    port = "8939"
    extra_args = list(args)
    if "--port" not in args and "-p" not in args:
        extra_args = ["--port", port] + extra_args
    project.emit_python(
        script,
        ["-m", "uvicorn", "glo_web.app:app", "--host", "127.0.0.1"],
        extra_args=extra_args,
    )


@command("serve", "Run production server", project_only=True, lang=Lang.Purescript)
def cmd_serve_ps(script: Script, project: Project, args: list[str]) -> None:
    """Serve PureScript SPA (requires bundling first)."""
    del args  # unused
    script.info(f"Serving {project.path}")
    script.pushd(script.workspace_path(project.abs_path))
    script.run(["python3", "-m", "http.server", "--bind", "127.0.0.1", "8080"])
    script.popd()


@command(
    "revision", "Create Alembic migration revision", project_only=True, lang=Lang.Python
)
def cmd_revision(script: Script, project: Project, args: list[str]) -> None:
    """Create Alembic revision (core project only)."""
    if project.name != "core":
        script.raw(
            "echo 'revision command is only available for /lib/core' >&2; exit 1"
        )
        return
    message = args[0] if args else "describe change"
    script.info(f"Creating revision: {message}")
    script.pushd(script.workspace_path(project.abs_path))
    project.emit_env(script)
    script.run(
        [
            "${VIRTUAL_ENV}/bin/alembic",
            "-c",
            "alembic.ini",
            "revision",
            "--autogenerate",
            "-m",
            message,
        ]
    )
    script.popd()


@command(
    "migrate",
    "Run Alembic migrations",
    project_only=True,
    lang=Lang.Python,
)
def cmd_migrate(script: Script, project: Project, args: list[str]) -> None:
    """Run Alembic migrations (core project only)."""
    del args  # unused
    if project.name != "core":
        script.raw("echo 'migrate command is only available for /lib/core' >&2; exit 1")
        return
    script.info("Running migrations")
    script.pushd(script.workspace_path(project.abs_path))
    project.emit_env(script)
    script.run(
        [
            "${VIRTUAL_ENV}/bin/alembic",
            "-c",
            "alembic.ini",
            "upgrade",
            "head",
        ]
    )
    script.popd()


@command("fetch", "Download and cache a model", project_only=True, lang=Lang.Python)
def cmd_fetch(script: Script, project: Project, args: list[str]) -> None:
    """Fetch a model (model project only)."""
    if project.name != "model":
        script.raw("echo 'fetch command is only available for /lib/model' >&2; exit 1")
        return
    if not args:
        script.raw(
            f"echo 'Usage: {cli_invocation()} /lib/model fetch MODEL_NAME' >&2; exit 1"
        )
        return
    model_name = args[0]
    script.info(f"Fetching model: {model_name}")
    project.emit_python(script, ["-m", "glo_model.fetch", model_name])


@command("bench", "Run benchmark on a model", project_only=True, lang=Lang.Python)
def cmd_bench(script: Script, project: Project, args: list[str]) -> None:
    """Run benchmark (model project only)."""
    if project.name != "model":
        script.raw("echo 'bench command is only available for /lib/model' >&2; exit 1")
        return
    if not args:
        script.raw(
            f"echo 'Usage: {cli_invocation()} /lib/model bench MODEL_NAME [--rounds N] [--json]' >&2; exit 1"
        )
        return
    model_name = args[0]
    extra = args[1:] if len(args) > 1 else []
    script.info(f"Benchmarking model: {model_name}")
    project.emit_python(
        script,
        ["-m", "glo_model.cli", "bench", "--model_name", model_name],
        extra_args=extra,
    )


# ---------------------------------------------------------------------------
# Pulumi commands (ops project)
# ---------------------------------------------------------------------------


def emit_pulumi_command(
    script: Script,
    project: Project,
    action: str,
    stack: str,
    extra_args: list[str] | None = None,
) -> None:
    """Emit a Pulumi command to the script."""
    if project.name != "ops":
        script.raw(
            f"echo '{action} command is only available for /lib/ops' >&2; exit 1"
        )
        return

    script.pushd(script.workspace_path(project.abs_path))
    project.emit_env(script)
    script.export("PULUMI_PYTHON_CMD", "${VIRTUAL_ENV}/bin/python3")

    cmd = ["pulumi", action, "--stack", stack]
    if extra_args:
        cmd.extend(extra_args)

    script.info(f"Running: {shcmd(cmd)}")
    script.raw(f"source pulumi_login.sh && {shcmd(cmd)}")
    script.popd()


@command("preview", "Pulumi preview", project_only=True, lang=Lang.Python)
def cmd_preview(script: Script, project: Project, args: list[str]) -> None:
    """Run Pulumi preview."""
    stack = args[0] if args else "prod"
    emit_pulumi_command(script, project, "preview", stack)


@command("up", "Pulumi up (deploy)", project_only=True, lang=Lang.Python)
def cmd_up(script: Script, project: Project, args: list[str]) -> None:
    """Run Pulumi up."""
    stack = args[0] if args else "prod"
    emit_pulumi_command(script, project, "up", stack, ["--yes"])


@command("destroy", "Pulumi destroy", project_only=True, lang=Lang.Python)
def cmd_destroy(script: Script, project: Project, args: list[str]) -> None:
    """Run Pulumi destroy."""
    stack = args[0] if args else "prod"
    emit_pulumi_command(script, project, "destroy", stack)


@command("refresh", "Pulumi refresh", project_only=True, lang=Lang.Python)
def cmd_refresh(script: Script, project: Project, args: list[str]) -> None:
    """Run Pulumi refresh."""
    stack = args[0] if args else "prod"
    emit_pulumi_command(script, project, "refresh", stack)


# ---------------------------------------------------------------------------
# Root-level only commands
# ---------------------------------------------------------------------------


@command("cuda-deps", "Build llama-cpp-python wheel with CUDA support", root_only=True)
def cmd_cuda_deps(script: Script, project: Project, args: list[str]) -> None:
    """Build llama-cpp-python wheel with CUDA support.

    Runs script/deps/build_lcp_wheel.sh to build the wheel into wheels/.
    """
    del project  # unused
    script.info("Building llama-cpp-python wheel")
    cmd = ["script/deps/build_lcp_wheel.sh"]
    if args:
        cmd.extend(args)
    script.run(cmd)


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------


def expand_to_atomic_commands(
    cmd: Command, excluded_targets: set[str] | None = None
) -> list[str]:
    """Expand a command (possibly meta) to list of atomic command names.

    Args:
        cmd: The command to expand
        excluded_targets: Set of target names to exclude from expansion
    """
    if excluded_targets is None:
        excluded_targets = set()

    if cmd.subtargets:
        result = []
        for subtarget_name in cmd.subtargets:
            if subtarget_name in excluded_targets:
                continue
            subtarget = COMMANDS[subtarget_name]
            result.extend(expand_to_atomic_commands(subtarget, excluded_targets))
        return result
    return [cmd.name]


def build_task_graph(
    items: list[ProjectItem | CommandItem],
    all_projects: list[str],
    project_deps: dict[str, list[str]],  # project -> list of parent projects
) -> dict[str, Task]:
    """Build task graph from parsed items.

    Returns dict mapping task ID to Task objects with dependencies set.
    """
    tasks: dict[str, Task] = {}

    # First pass: collect all (project, command) pairs with meta info
    # Track which projects have which commands
    project_commands: dict[str, list[tuple[str, list[str], str | None]]] = {}

    target_projects: list[str] = []

    for item in items:
        if isinstance(item, ProjectItem):
            target_projects.append(item.path)
        else:
            cmd = COMMANDS.get(item.name)
            if cmd and cmd.root_only:
                continue  # Root-only commands don't participate in parallel execution

            run_on = target_projects if target_projects else all_projects

            # Custom targets are treated as atomic (not expanded)
            if cmd is None:
                # Custom target - treat as atomic
                for proj_path in run_on:
                    project = Project(proj_path)
                    if project.get_custom_target(item.name) is not None:
                        if proj_path not in project_commands:
                            project_commands[proj_path] = []
                        project_commands[proj_path].append((item.name, item.args, None))
            else:
                # Built-in command - expand if meta-command
                atomic_commands = expand_to_atomic_commands(cmd, item.excluded_targets)
                meta_name = item.name if cmd.subtargets else None

                for proj_path in run_on:
                    if proj_path not in project_commands:
                        project_commands[proj_path] = []
                    for atomic_cmd in atomic_commands:
                        project_commands[proj_path].append(
                            (atomic_cmd, item.args, meta_name)
                        )

    # Deduplicate commands per project (after meta-expansion)
    for proj_path in project_commands:
        seen: set[str] = set()
        deduped: list[tuple[str, list[str], str | None]] = []
        for cmd_name, args, meta_name in project_commands[proj_path]:
            if cmd_name not in seen:
                seen.add(cmd_name)
                deduped.append((cmd_name, args, meta_name))
        project_commands[proj_path] = deduped

    # Second pass: create Task objects
    for proj_path, commands in project_commands.items():
        for cmd_name, args, meta_name in commands:
            task_id = f"{proj_path}:{cmd_name}"
            if task_id not in tasks:
                project = Project(proj_path)
                config = project.build_config
                tasks[task_id] = Task(
                    id=task_id,
                    project_path=proj_path,
                    command_name=cmd_name,
                    args=list(args),
                    meta_command=meta_name,
                    enabled=config is None or config.enabled,
                )

    # Third pass: compute dependencies
    for task in tasks.values():
        deps: list[str] = []
        proj = task.project_path
        cmd_name = task.command_name

        # Get the command sequence for this project
        proj_cmds = [c[0] for c in project_commands.get(proj, [])]
        cmd_index = proj_cmds.index(cmd_name) if cmd_name in proj_cmds else -1

        # Dependency 1: Previous command on same project
        if cmd_index > 0:
            prev_cmd = proj_cmds[cmd_index - 1]
            prev_task_id = f"{proj}:{prev_cmd}"
            if prev_task_id in tasks:
                deps.append(prev_task_id)

        # Dependency 2: ALL commands on parent projects
        # (child project waits for all parent tasks, not just matching command)
        for parent_proj in project_deps.get(proj, []):
            for parent_cmd, _, _ in project_commands.get(parent_proj, []):
                parent_task_id = f"{parent_proj}:{parent_cmd}"
                if parent_task_id in tasks and parent_task_id not in deps:
                    deps.append(parent_task_id)

        task.dependencies = deps

    return tasks


def task_id_to_bash_name(task_id: str) -> str:
    """Convert task ID like '/lib/core:format' to bash function name 'task_lib_core_format'."""
    # Strip leading "/" to avoid double underscore in function name
    clean_id = task_id.lstrip("/")
    return "task_" + clean_id.replace("/", "_").replace(":", "_").replace("-", "_")


def calculate_max_parallelism(tasks: dict[str, Task]) -> int:
    """Calculate the maximum number of tasks that can run concurrently.

    Computes topological levels and returns the max width (tasks at any level).
    """
    if not tasks:
        return 1

    # Compute level for each task (longest path from any root)
    levels: dict[str, int] = {}

    def get_level(task_id: str) -> int:
        if task_id in levels:
            return levels[task_id]
        task = tasks.get(task_id)
        if not task or not task.dependencies:
            levels[task_id] = 0
            return 0
        max_dep_level = max(get_level(dep) for dep in task.dependencies if dep in tasks)
        levels[task_id] = max_dep_level + 1
        return levels[task_id]

    for task_id in tasks:
        get_level(task_id)

    # Count tasks at each level
    level_counts: dict[int, int] = {}
    for level in levels.values():
        level_counts[level] = level_counts.get(level, 0) + 1

    return max(level_counts.values()) if level_counts else 1


def topological_sort_tasks(tasks: dict[str, Task]) -> list[str]:
    """Return task IDs in dependency order (dependencies first)."""
    result: list[str] = []
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        visited.add(task_id)
        task = tasks.get(task_id)
        if task:
            for dep in task.dependencies:
                if dep in tasks:
                    visit(dep)
        result.append(task_id)

    for task_id in tasks:
        visit(task_id)

    return result


def generate_sequential_script(
    tasks: dict[str, Task],
    workspace: Path,
    color: bool,
    num_phases: int = 1,
) -> str:
    """Generate a bash script that executes tasks sequentially in dependency order."""
    lines: list[str] = []

    def add(line: str = "") -> None:
        lines.append(line)

    # Header
    add("#!/usr/bin/env bash")
    add("# Sequential build script - generated by build.py")
    add("set -euo pipefail")
    add("")
    add(f"export WORKSPACE=${{WORKSPACE:-{shquote(str(workspace))}}}")
    add('[ -f "${WORKSPACE}/.python-version" ] && export UV_PYTHON="$(cat "${WORKSPACE}/.python-version")"')
    add("")

    # Color codes
    if color:
        add("GREEN='\\033[0;32m'")
        add("RED='\\033[0;31m'")
        add("RESET='\\033[0m'")
    else:
        add("GREEN=''")
        add("RED=''")
        add("RESET=''")
    add("")

    add(f'echo -e "${{GREEN}}[I]${{RESET}} Running {len(tasks)} tasks sequentially"')
    add("")

    # Sort tasks by dependency order
    sorted_task_ids = topological_sort_tasks(tasks)

    # Generate task execution
    for task_id in sorted_task_ids:
        task = tasks[task_id]
        project = Project(task.project_path)

        add(f"# === {task_id} ===")
        add(f'echo -e "${{GREEN}}=== {task_id} ===${{RESET}}"')

        if not task.enabled:
            add('echo -e "${GREEN}[I]${RESET} Skipped (disabled)"')
            add("")
            continue

        # Generate the task script inline
        script = Script(workspace, color=color)
        emit_target(script, task.command_name, project, task.args, set())
        script.leave_project()
        script.finalize()

        # Add the script lines
        for script_line in script._lines:
            add(script_line)
        add("")

    # Summary
    add(f'echo -e "${{GREEN}}[ok] Completed {len(tasks)} tasks${{RESET}}"')

    return "\n".join(lines) + "\n"


def generate_parallel_script(
    tasks: dict[str, Task],
    workspace: Path,
    color: bool,
    jobs: int,
    num_phases: int = 1,
) -> str:
    """Generate a bash script that executes tasks in parallel with phase support."""
    lines: list[str] = []

    def add(line: str = "") -> None:
        lines.append(line)

    # Header
    add("#!/usr/bin/env bash")
    add("# Parallel build script - generated by build.py")
    add("set -uo pipefail  # Note: -e not set, we handle errors ourselves")
    add("")
    add(f"export WORKSPACE=${{WORKSPACE:-{shquote(str(workspace))}}}")
    add('[ -f "${WORKSPACE}/.python-version" ] && export UV_PYTHON="$(cat "${WORKSPACE}/.python-version")"')
    add(f"MAX_JOBS={jobs}")
    add("")

    # Color codes
    if color:
        add("GREEN='\\033[0;32m'")
        add("YELLOW='\\033[1;33m'")
        add("RED='\\033[0;31m'")
        add("RESET='\\033[0m'")
    else:
        add("GREEN=''")
        add("YELLOW=''")
        add("RED=''")
        add("RESET=''")
    add("")

    # Status tracking directory
    add("STATUS_DIR=$(mktemp -d)")
    add("trap 'rm -rf \"$STATUS_DIR\"' EXIT")
    add("")

    # Generate task functions
    add("# " + "=" * 70)
    add("# Task functions")
    add("# " + "=" * 70)
    add("")

    for task in sorted(tasks.values(), key=lambda t: t.id):
        func_name = task_id_to_bash_name(task.id)
        project = Project(task.project_path)

        if not task.enabled:
            add(f"{func_name}() {{")
            add("    true  # Disabled in build.json")
            add("}")
            add("")
            continue

        add(f"{func_name}() {{")
        add("    set -e  # Exit on first error")

        # Build the task body using Script and emit_target (handles both
        # built-in commands and custom targets)
        script = Script(workspace, color=color)
        emit_target(script, task.command_name, project, task.args)
        script.finalize()

        # Extract just the body (skip header, indent everything)
        body_lines = script._lines
        for body_line in body_lines:
            add(f"    {body_line}")

        add("}")
        add("")

    # Task metadata arrays
    add("# " + "=" * 70)
    add("# Task metadata")
    add("# " + "=" * 70)
    add("")

    # Task list
    task_ids = sorted(tasks.keys())
    add("TASKS=(")
    for tid in task_ids:
        add(f"    {shquote(tid)}")
    add(")")
    add("")

    # Dependencies (only same-phase deps - cross-phase deps are satisfied by phase ordering)
    add("declare -A DEPS")
    for task in sorted(tasks.values(), key=lambda t: t.id):
        if task.dependencies:
            # Filter to only dependencies in the same phase
            same_phase_deps = [
                d
                for d in task.dependencies
                if d in tasks and tasks[d].phase == task.phase
            ]
            if same_phase_deps:
                deps_str = " ".join(shquote(d) for d in same_phase_deps)
                add(f"DEPS[{shquote(task.id)}]={shquote(deps_str)}")
    add("")

    # Meta-command mapping for reporting
    add("declare -A META")
    for task in sorted(tasks.values(), key=lambda t: t.id):
        if task.meta_command:
            add(f"META[{shquote(task.id)}]={shquote(task.meta_command)}")
    add("")

    # Phase mapping for sequential phase execution
    add("declare -A PHASE")
    for task in sorted(tasks.values(), key=lambda t: t.id):
        add(f"PHASE[{shquote(task.id)}]={task.phase}")
    add(f"NUM_PHASES={num_phases}")
    add("")

    # Coordinator
    add("# " + "=" * 70)
    add("# Parallel execution coordinator")
    add("# " + "=" * 70)
    add("")

    add(
        """declare -A PIDS      # task_id -> PID
declare -A STARTED   # task_id -> 1 if started
declare -A STATUS    # task_id -> exit code (set when complete)
FAILED=0
RUNNING=0
CURRENT_PHASE=0
LOCK_FILE="$STATUS_DIR/.output_lock"

log_info() { echo -e "${GREEN}[I]${RESET} $1"; }
log_error() { echo -e "${RED}[E]${RESET} $1" >&2; }
log_warn() { echo -e "${YELLOW}[W]${RESET} $1"; }

# Print with lock to prevent interleaved output
print_locked() {
    if command -v flock >/dev/null 2>&1; then
        (
            flock 200
            cat
        ) 200>"$LOCK_FILE"
    else
        cat
    fi
}

# Check if all dependencies of a task are completed successfully
deps_satisfied() {
    local task_id="$1"
    local deps_str="${DEPS[$task_id]:-}"
    if [[ -z "$deps_str" ]]; then
        return 0  # No dependencies
    fi
    local dep
    for dep in $deps_str; do
        if [[ -z "${STATUS[$dep]:-}" ]]; then
            return 1  # Dependency not complete
        fi
        if [[ "${STATUS[$dep]}" != "0" ]]; then
            return 2  # Dependency failed
        fi
    done
    return 0
}

# Run a task in the background
run_task() {
    local task_id="$1"
    local clean_id="${task_id#/}"  # Strip leading /
    local func_name="task_${clean_id//[\\/:]/_}"
    func_name="${func_name//-/_}"
    local output_file="$STATUS_DIR/${task_id//\\//_}.out"
    (
        # Run in nested subshell so set -e in function works, then capture exit code
        ($func_name) > "$output_file" 2>&1
        echo "$?" > "$STATUS_DIR/${task_id//\\//_}"
    ) &
    PIDS[$task_id]=$!
    STARTED[$task_id]=1
    ((RUNNING++))
    log_info "Started: $task_id"
}

# Check for completed tasks and display their output
check_completed() {
    local task_id
    for task_id in "${!PIDS[@]}"; do
        local status_file="$STATUS_DIR/${task_id//\\//_}"
        local output_file="$STATUS_DIR/${task_id//\\//_}.out"
        if [[ -f "$status_file" ]]; then
            wait "${PIDS[$task_id]}" 2>/dev/null || true
            STATUS[$task_id]=$(cat "$status_file")
            unset "PIDS[$task_id]"
            ((RUNNING--))

            # Check failure before printing (can't set vars in pipe subshell)
            local task_failed=0
            if [[ "${STATUS[$task_id]}" != "0" ]]; then
                task_failed=1
                FAILED=1
            fi

            # Build list of still-running tasks
            local waiting_for=""
            local other_id
            for other_id in "${!PIDS[@]}"; do
                if [[ -n "$waiting_for" ]]; then
                    waiting_for="$waiting_for, $other_id"
                else
                    waiting_for="$other_id"
                fi
            done

            # Display output atomically with lock
            {
                echo ""
                echo -e "${GREEN}=== ${task_id} ===${RESET}"
                if [[ -f "$output_file" ]]; then
                    cat "$output_file"
                fi
                if [[ $task_failed -eq 1 ]]; then
                    echo -e "${RED}[x] Failed: $task_id (exit ${STATUS[$task_id]})${RESET}"
                else
                    echo -e "${GREEN}[ok] Completed: $task_id${RESET}"
                fi
                if [[ -n "$waiting_for" ]]; then
                    echo -e "${YELLOW}[..] Waiting for: $waiting_for${RESET}"
                fi
            } | print_locked
        fi
    done
}

# Main execution loop
if [[ $NUM_PHASES -gt 1 ]]; then
    log_info "Running ${#TASKS[@]} tasks with $MAX_JOBS workers in $NUM_PHASES phases"
else
    log_info "Running ${#TASKS[@]} tasks with $MAX_JOBS workers"
fi

while true; do
    check_completed

    # If failed, wait for running tasks and stop
    if [[ $FAILED -eq 1 ]]; then
        if [[ $RUNNING -gt 0 ]]; then
            wait 2>/dev/null || true
            check_completed
        fi
        break
    fi

    # Start ready tasks up to MAX_JOBS (only from current phase)
    for task_id in "${TASKS[@]}"; do
        if [[ -n "${STARTED[$task_id]:-}" ]]; then
            continue  # Already started
        fi
        # Only start tasks in the current phase
        if [[ ${PHASE[$task_id]} -ne $CURRENT_PHASE ]]; then
            continue
        fi
        if [[ $RUNNING -ge $MAX_JOBS ]]; then
            break  # At capacity
        fi
        deps_satisfied "$task_id"
        dep_status=$?
        if [[ $dep_status -eq 0 ]]; then
            run_task "$task_id"
        elif [[ $dep_status -eq 2 ]]; then
            # Dependency failed, mark as skipped
            STARTED[$task_id]=1
            STATUS[$task_id]="skipped"
        fi
    done

    # Check if all tasks in current phase are done
    phase_done=1
    for task_id in "${TASKS[@]}"; do
        if [[ ${PHASE[$task_id]} -eq $CURRENT_PHASE ]]; then
            if [[ -z "${STARTED[$task_id]:-}" || -z "${STATUS[$task_id]:-}" ]]; then
                phase_done=0
                break
            fi
        fi
    done

    # Advance to next phase if current phase is complete
    if [[ $phase_done -eq 1 && $RUNNING -eq 0 ]]; then
        ((CURRENT_PHASE++))
        if [[ $CURRENT_PHASE -ge $NUM_PHASES ]]; then
            break  # All phases complete
        fi
        if [[ $NUM_PHASES -gt 1 ]]; then
            log_info "Starting phase $((CURRENT_PHASE + 1)) of $NUM_PHASES"
        fi
    fi

    sleep 0.1
done

# Report results
echo ""
echo "============================================================"

# Group results by project and meta-command
# Key format: "project:meta" (e.g., "/lib/core:precommit")
declare -A GROUP_STATUS  # group_key -> "completed" | "failed" | "partial"
declare -A GROUP_TASKS   # group_key -> space-separated task_ids

for task_id in "${TASKS[@]}"; do
    # Extract project from task_id (e.g., "/lib/core" from "/lib/core:format")
    project="${task_id%%:*}"
    meta="${META[$task_id]:-}"
    if [[ -n "$meta" ]]; then
        group_key="${project}:${meta}"
    else
        group_key="$task_id"
    fi
    GROUP_TASKS[$group_key]+="$task_id "
done

# Determine status of each group
for group_key in "${!GROUP_TASKS[@]}"; do
    tasks_str="${GROUP_TASKS[$group_key]}"
    all_ok=1
    any_fail=0
    any_skipped=0
    for tid in $tasks_str; do
        st="${STATUS[$tid]:-pending}"
        if [[ "$st" == "0" ]]; then
            : # ok
        elif [[ "$st" == "skipped" || "$st" == "pending" ]]; then
            all_ok=0
            any_skipped=1
        else
            all_ok=0
            any_fail=1
        fi
    done
    if [[ $all_ok -eq 1 ]]; then
        GROUP_STATUS[$group_key]="completed"
    elif [[ $any_fail -eq 1 ]]; then
        GROUP_STATUS[$group_key]="failed"
    else
        GROUP_STATUS[$group_key]="skipped"
    fi
done

# Print completed (grouped by meta-command)
echo -e "\\n${GREEN}Completed:${RESET}"
for group_key in $(echo "${!GROUP_STATUS[@]}" | tr ' ' '\\n' | sort); do
    if [[ "${GROUP_STATUS[$group_key]}" == "completed" ]]; then
        echo "  [ok] ${group_key//:/ }"
    fi
done

# Print remaining - only for groups with failures, show individual tasks
has_remaining=0
for group_key in $(echo "${!GROUP_STATUS[@]}" | tr ' ' '\\n' | sort); do
    if [[ "${GROUP_STATUS[$group_key]}" == "failed" || "${GROUP_STATUS[$group_key]}" == "skipped" ]]; then
        tasks_str="${GROUP_TASKS[$group_key]}"
        for tid in $tasks_str; do
            st="${STATUS[$tid]:-pending}"
            if [[ "$st" == "skipped" || "$st" == "pending" ]]; then
                if [[ $has_remaining -eq 0 ]]; then
                    echo -e "\\n${YELLOW}Remaining (not executed):${RESET}"
                    has_remaining=1
                fi
                echo "  [--] ${tid//:/ }"
            fi
        done
    fi
done

# Print failed - show individual failed tasks
has_failed=0
for group_key in $(echo "${!GROUP_STATUS[@]}" | tr ' ' '\\n' | sort); do
    if [[ "${GROUP_STATUS[$group_key]}" == "failed" ]]; then
        tasks_str="${GROUP_TASKS[$group_key]}"
        for tid in $tasks_str; do
            st="${STATUS[$tid]:-pending}"
            if [[ "$st" != "0" && "$st" != "skipped" && "$st" != "pending" ]]; then
                if [[ $has_failed -eq 0 ]]; then
                    echo -e "\\n${RED}Failed:${RESET}"
                    has_failed=1
                fi
                echo "  [x] ${tid//:/ }"
            fi
        done
    fi
done

echo ""

if [[ $FAILED -eq 1 ]]; then
    exit 1
fi
exit 0"""
    )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def show_help(all_projects: list[str]) -> None:
    """Print general help with projects and commands."""
    cli = cli_invocation()
    print("glo Build System\n")

    # List projects
    print("Projects:")
    for proj in all_projects:
        project = Project(proj)
        config = project.build_config
        custom_targets = (
            list(config.targets.keys()) if config and config.targets else []
        )
        if custom_targets:
            print(f"  {proj:20} (targets: {', '.join(custom_targets)})")
        else:
            print(f"  {proj}")
    print()

    # Group commands
    common = []
    project_specific = []
    root_specific = []

    for name, cmd in sorted(COMMANDS.items()):
        if cmd.root_only:
            root_specific.append((name, cmd.help))
        elif cmd.project_only:
            project_specific.append((name, cmd.help))
        else:
            common.append((name, cmd.help))

    print("Common commands (work on all projects):")
    for name, help_text in common:
        print(f"  {name:20} {help_text}")

    print("\nProject-specific commands:")
    for name, help_text in project_specific:
        print(f"  {name:20} {help_text}")

    print("\nRoot-level commands:")
    for name, help_text in root_specific:
        print(f"  {name:20} {help_text}")

    print("\nUsage:")
    print(f"  {cli}                                   # Show this help")
    print(f"  {cli} <project>                         # Show project help")
    print(f"  {cli} <project> <target>                # Run target on project")
    print(f"  {cli} <command>                         # Run command on all projects")
    print(f"  {cli} --help                            # Show command-line options")


def show_project_help(project_path: str) -> None:
    """Print help for a specific project."""
    cli = cli_invocation()
    project = Project(project_path)
    config = project.build_config

    print(f"Project: {project_path}")
    print(f"  Language: {project.language.name}")
    print(f"  Path:     {project.abs_path}")
    print()

    # Show custom targets
    if config and config.targets:
        print("Custom targets:")
        for name, steps in config.targets.items():
            step_summary = []
            for step in steps:
                if step.target:
                    step_summary.append(f"target:{step.target}")
                elif step.command:
                    if isinstance(step.command, list):
                        step_summary.append(f"{len(step.command)} commands")
                    else:
                        cmd_preview = (
                            step.command[:30] + "..."
                            if len(step.command) > 30
                            else step.command
                        )
                        step_summary.append(f"'{cmd_preview}'")
            print(f"  {name:20} [{' → '.join(step_summary)}]")
        print()

    # Show applicable built-in commands
    print("Built-in commands:")
    for name, cmd in sorted(COMMANDS.items()):
        if cmd.root_only:
            continue
        handler = cmd.get_handler(project.language)
        if handler:
            print(f"  {name:20} {cmd.help}")
    print()

    print("Usage:")
    print(f"  {cli} {project_path} <target>          # Run a target")
    print(f"  {cli} {project_path} <target> --help   # Show target details")


def show_target_help(project_path: str, target_name: str) -> None:
    """Print help for a specific target."""
    project = Project(project_path)

    # Check if it's a custom target
    custom_steps = project.get_custom_target(target_name)
    if custom_steps:
        print(f"Custom target: {target_name}")
        print(f"Project: {project_path}")
        print()
        print("Steps:")
        for i, step in enumerate(custom_steps, 1):
            if step.target:
                print(f"  {i}. Run target: {step.target}")
            elif step.command:
                if isinstance(step.command, list):
                    print(f"  {i}. Run commands:")
                    for step_cmd in step.command:
                        print(f"       {step_cmd}")
                else:
                    print(f"  {i}. Run: {step.command}")
        return

    # Check if it's a built-in command
    if target_name in COMMANDS:
        builtin_cmd = COMMANDS[target_name]
        print(f"Built-in command: {target_name}")
        print(f"  {builtin_cmd.help}")
        print()
        if builtin_cmd.subtargets:
            print("Meta-command expands to:")
            for sub in builtin_cmd.subtargets:
                print(f"  - {sub}")
        if builtin_cmd.project_only:
            print("Note: This command requires a project argument.")
        if builtin_cmd.root_only:
            print("Note: This command runs at root level only.")
        return

    print(f"Unknown target: {target_name}")
    print(f"Run '{cli_invocation()} {project_path}' to see available targets.")


@dataclass(frozen=True)
class ProjectItem:
    """A project path in the argument sequence."""

    path: str


@dataclass(frozen=True)
class CommandItem:
    """A command with its arguments in the argument sequence."""

    name: str
    args: list[str] = field(default_factory=list)
    excluded_targets: set[str] = field(default_factory=set)


def split_into_phases(
    items: list[ProjectItem | CommandItem],
) -> list[list[ProjectItem | CommandItem]]:
    """Split items into sequential phases.

    Each phase starts when a new ProjectItem appears after a CommandItem.
    This allows `/foo bar /baz quux` to run `/foo bar` to completion
    before starting `/baz quux`.

    Examples:
        [P(a), C(x), C(y)] -> [[P(a), C(x), C(y)]]  # one phase
        [P(a), C(x), P(b), C(y)] -> [[P(a), C(x)], [P(b), C(y)]]  # two phases
        [C(x), P(a), C(y)] -> [[C(x)], [P(a), C(y)]]  # global cmd, then project
    """
    if not items:
        return []

    phases: list[list[ProjectItem | CommandItem]] = []
    current_phase: list[ProjectItem | CommandItem] = []
    saw_command_in_phase = False

    for item in items:
        if isinstance(item, ProjectItem):
            # Start new phase if we already have commands in current phase
            if saw_command_in_phase:
                phases.append(current_phase)
                current_phase = []
                saw_command_in_phase = False
            current_phase.append(item)
        else:  # CommandItem
            current_phase.append(item)
            saw_command_in_phase = True

    # Don't forget the last phase
    if current_phase:
        phases.append(current_phase)

    return phases


def expand_project_pattern(
    pattern: str, all_projects: list[str], workspace_root: Path | None = None
) -> list[str] | None:
    """Expand a project pattern to a list of matching projects.

    Patterns:
        / or /lib      - all projects
        /py, /ps, /hs, /meta - all projects with that language
        /py/core       - project named 'core' with language py
        /lib/core      - specific project by path
        /lib/comm      - all child projects under /lib/comm (e.g., /lib/comm/py, /lib/comm/gen)
        /py/comm       - shortcut for /lib/comm/py

    Returns list of matching projects, or None if pattern is invalid.
    Empty list means pattern is valid but no projects match (caller should error).
    """
    if pattern in ("/", "/lib"):
        return list(all_projects)

    if workspace_root is None:
        workspace_root = get_workspace_root()

    # Language filter patterns: /py, /ps, /hs, /meta, /rs, /ts
    if pattern in ("/py", "/ps", "/hs", "/meta", "/rs", "/ts"):
        lang_filter = pattern[1:]  # "py", "ps", "hs", or "meta"
        matches = []
        for proj_path in all_projects:
            project = Project(proj_path, workspace_root)
            config = project.build_config
            if config and config.language_str == lang_filter:
                matches.append(proj_path)
        return matches  # May be empty

    # Direct path match: /lib/core or /lib/gen/py (hierarchical)
    if pattern.startswith("/lib/"):
        if pattern in all_projects:
            return [pattern]

        # Check for child projects: /lib/comm -> /lib/comm/py, /lib/comm/gen, etc.
        prefix = pattern + "/"
        children = [p for p in all_projects if p.startswith(prefix)]
        if children:
            return children

        return []  # Valid pattern but no match

    # Language + parent filter: /py/comm -> all py projects under /lib/comm
    if pattern.count("/") == 2 and pattern.startswith("/"):
        parts = pattern.split("/")
        lang_filter = parts[1]  # "py", "ps", "hs", or "meta"
        parent_name = parts[2]

        if lang_filter in ("py", "ps", "meta", "hs", "rs", "ts"):
            prefix = f"/lib/{parent_name}/"
            matches = []
            for proj_path in all_projects:
                if proj_path.startswith(prefix) or proj_path == f"/lib/{parent_name}":
                    project = Project(proj_path, workspace_root)
                    config = project.build_config
                    if config and config.language_str == lang_filter:
                        matches.append(proj_path)
            if matches:
                return matches

            # Fallback: /py/core matches project named 'core' with language py
            for proj_path in all_projects:
                project = Project(proj_path, workspace_root)
                config = project.build_config
                if (
                    config
                    and config.language_str == lang_filter
                    and project.name == parent_name
                ):
                    return [proj_path]

        return []  # Valid pattern but no match

    return None  # Invalid pattern


def get_all_custom_targets(all_projects: list[str]) -> set[str]:
    """Get all custom target names defined in any project's build.json."""
    targets: set[str] = set()
    for proj_path in all_projects:
        project = Project(proj_path)
        config = project.build_config
        if config and config.targets:
            targets.update(config.targets.keys())
    return targets


def get_all_target_names(cmd_name: str) -> set[str]:
    """Get all target names that are part of a command (including subtargets).

    For a meta-command, returns the command name and all its subtargets recursively.
    For an atomic command, returns just that command name.
    """
    if cmd_name not in COMMANDS:
        return {cmd_name}  # Custom target, just return the name

    cmd = COMMANDS[cmd_name]
    result = {cmd_name}

    if cmd.subtargets:
        for subtarget in cmd.subtargets:
            result.update(get_all_target_names(subtarget))

    return result


def validate_exclusion(
    exclusion: str,
    all_projects: list[str],
    valid_targets: set[str],
    current_command: str | None,
) -> tuple[str, str] | None:
    """Validate an exclusion pattern.

    Returns (type, value) tuple where type is 'project' or 'target'.
    Returns None if exclusion is invalid (caller should error).
    """
    if exclusion.startswith("^/"):
        # Project exclusion
        pattern = exclusion[1:]  # Remove ^ prefix
        matches = expand_project_pattern(pattern, all_projects)
        if matches is None:
            return None
        if len(matches) == 0:
            return None  # No matches - invalid exclusion
        return ("project", pattern)
    elif exclusion.startswith("^"):
        # Target exclusion
        target = exclusion[1:]
        if target not in valid_targets:
            return None
        # Verify the target is actually part of the current command
        if current_command:
            valid_subtargets = get_all_target_names(current_command)
            if target not in valid_subtargets:
                return None
        return ("target", target)
    return None


def parse_args_sequence(
    args: list[str], all_projects: list[str]
) -> list[ProjectItem | CommandItem] | None:
    """Parse args into a sequence of projects and commands.

    Returns list of ProjectItem and CommandItem, or None on error.
    Projects can appear anywhere and affect subsequent non-root commands.

    Supports exclusions:
        ^/py/core              - exclude project from selection
        ^test                  - exclude target from meta-command expansion

    Supports -- separator:
        target -- args...      - pass remaining args to single target
        target -- --help       - pass --help to target instead of showing global help
        Note: meta-commands (like precommit) do not accept arguments

    Project patterns:
        / or /lib        - all projects
        /py, /ps, /hs, /meta - all projects by language
        /py/core         - project named 'core' with language py
        /lib/core        - specific project by path
    """
    items: list[ProjectItem | CommandItem] = []
    current_cmd: str | None = None
    current_args: list[str] = []
    current_excluded_targets: set[str] = set()
    excluded_projects: set[str] = set()
    pending_projects: list[str] = []
    passthrough_mode = False  # After --, all remaining args go to current command

    # Get all valid target names (built-in commands + custom targets)
    custom_targets = get_all_custom_targets(all_projects)
    valid_targets = set(COMMANDS.keys()) | custom_targets

    def is_meta_command(cmd_name: str) -> bool:
        """Check if a command is a meta-command (has subtargets)."""
        if cmd_name in COMMANDS:
            return bool(COMMANDS[cmd_name].subtargets)
        return False

    def flush_command() -> bool:
        """Flush current command. Returns False on error."""
        nonlocal current_cmd, current_args, current_excluded_targets, passthrough_mode
        if current_cmd is not None:
            # Validate: args are only allowed for single targets (not meta-commands)
            if current_args and is_meta_command(current_cmd):
                log_error(
                    f"Cannot pass arguments to meta-command '{current_cmd}'. "
                    f"Use a single target instead (e.g., 'unit {' '.join(current_args)}')."
                )
                return False
            items.append(
                CommandItem(current_cmd, current_args, current_excluded_targets)
            )
            current_cmd = None
            current_args = []
            current_excluded_targets = set()
            passthrough_mode = False
        return True

    def flush_projects() -> None:
        """Flush pending projects after applying exclusions."""
        nonlocal pending_projects, excluded_projects
        for proj in pending_projects:
            if proj not in excluded_projects:
                items.append(ProjectItem(proj))
        pending_projects = []
        excluded_projects = set()

    for i, arg in enumerate(args):
        # Handle -- separator: everything after goes to current command
        if arg == "--" and not passthrough_mode:
            if current_cmd is None:
                log_error("'--' requires a preceding command")
                return None
            passthrough_mode = True
            # Add all remaining args
            current_args.extend(args[i + 1 :])
            break

        if passthrough_mode:
            # In passthrough mode, everything is an argument
            current_args.append(arg)
        elif arg.startswith("^"):
            # Exclusion
            validation = validate_exclusion(
                arg, all_projects, valid_targets, current_cmd
            )
            if validation is None:
                log_error(f"Invalid exclusion: {arg}")
                return None
            exc_type, exc_value = validation
            if exc_type == "project":
                # Project exclusion
                matches = expand_project_pattern(exc_value, all_projects)
                if matches:
                    excluded_projects.update(matches)
            else:
                # Target exclusion
                if current_cmd is None:
                    log_error(f"Target exclusion {arg} requires a preceding command")
                    return None
                current_excluded_targets.add(exc_value)
        elif arg.startswith("/"):
            # Project pattern
            if not flush_command():
                return None
            flush_projects()
            matches = expand_project_pattern(arg, all_projects)
            if matches is None:
                log_error(f"Unknown project pattern: {arg}")
                log_info(f"Available projects: {', '.join(all_projects)}")
                return None
            if len(matches) == 0:
                log_error(f"No projects match pattern: {arg}")
                return None
            pending_projects.extend(matches)
        elif arg in valid_targets:
            # Command or custom target name
            if not flush_command():
                return None
            flush_projects()
            current_cmd = arg
            current_args = []
            current_excluded_targets = set()
        else:
            # Argument for current command
            if current_cmd is None:
                log_error(f"Unknown command: {arg}")
                return None
            current_args.append(arg)

    if not flush_command():
        return None
    flush_projects()

    return items


def emit_custom_target(
    script: Script, project: Project, steps: list[TargetStep], args: list[str]
) -> None:
    """Emit steps for a custom target from build.json.

    Args are passed to the last step if it's a command.
    """
    path = script.workspace_path(project.abs_path)
    script.enter_project(path)

    # Set up environment based on language
    if project.language == Lang.Python:
        project.emit_env(script)
    elif project.language == Lang.Purescript:
        project.emit_ps_env(script)
    elif project.language == Lang.Haskell:
        project.emit_hs_env(script)
    elif project.language == Lang.Rust:
        project.emit_rs_env(script)
    elif project.language == Lang.TypeScript:
        project.emit_ts_env(script)

    for i, step in enumerate(steps):
        is_last = i == len(steps) - 1
        step_args = list(step.args or [])
        if is_last:
            step_args.extend(args)

        if step.target:
            # Reference to another target/command
            if step.target in COMMANDS:
                cmd = COMMANDS[step.target]
                emit_command(script, cmd, project, step_args)
            else:
                # Check if it's a custom target (recursive)
                nested_steps = project.get_custom_target(step.target)
                if nested_steps:
                    emit_custom_target(script, project, nested_steps, step_args)
                else:
                    script.raw(f"echo 'Unknown target: {step.target}' >&2; exit 1")
        elif step.command:
            # Raw bash command(s)
            # Append args to the last command if any
            if isinstance(step.command, list):
                # Multiple commands - run each in sequence, args go to last
                for j, cmd_str in enumerate(step.command):
                    is_last_cmd = j == len(step.command) - 1
                    if is_last_cmd and step_args:
                        cmd_str = cmd_str + " " + shcmd(step_args)
                    script.raw(f"echo {shquote('+ ' + cmd_str)}")
                    script.raw(cmd_str)
            else:
                cmd_str = step.command
                if step_args:
                    cmd_str = cmd_str + " " + shcmd(step_args)
                script.raw(f"echo {shquote('+ ' + cmd_str)}")
                script.raw(cmd_str)


def emit_command(
    script: Script,
    cmd: Command,
    project: Project,
    args: list[str],
    excluded_targets: set[str] | None = None,
) -> None:
    """Emit a command to the script, expanding meta-commands recursively.

    Args are passed to the last subtarget of a meta-command.
    """
    if excluded_targets is None:
        excluded_targets = set()

    if cmd.subtargets:
        # Meta-command: emit subtargets in sequence (excluding excluded ones)
        subtargets_to_run = [s for s in cmd.subtargets if s not in excluded_targets]
        for i, subtarget_name in enumerate(subtargets_to_run):
            subtarget = COMMANDS[subtarget_name]
            # Pass args only to the last subtarget
            subtarget_args = args if i == len(subtargets_to_run) - 1 else []
            emit_command(script, subtarget, project, subtarget_args, excluded_targets)
    else:
        # Regular command: emit via language-specific handler
        handler = cmd.get_handler(project.language)
        if handler is None:
            if project.language in (Lang.Meta, Lang.Rust, Lang.TypeScript, Lang.Rocq):
                script.info(f"Skipping {cmd.name} for {project.path} ({project.language.name})")
                return
            raise AssertionError(f"No handler for {cmd.name} with {project.language}")
        handler(script, project, args)


def emit_target(
    script: Script,
    target_name: str,
    project: Project,
    args: list[str],
    excluded_targets: set[str] | None = None,
) -> None:
    """Emit a target by name, checking custom targets first then registered commands.

    This is the main entry point for emitting targets - it handles the resolution
    of custom targets from build.json vs registered commands.
    """
    if excluded_targets is None:
        excluded_targets = set()

    # First check for custom target in project's build.json
    custom_steps = project.get_custom_target(target_name)
    if custom_steps:
        emit_custom_target(script, project, custom_steps, args)
        return

    # Fall back to registered command
    if target_name in COMMANDS:
        cmd = COMMANDS[target_name]
        emit_command(script, cmd, project, args, excluded_targets)
        return

    # Unknown target
    script.raw(f"echo 'Unknown target: {target_name}' >&2; exit 1")


def get_all_project_deps(
    workspace_root: Path, projects: list[str]
) -> dict[str, list[str]]:
    """Get dependencies for all projects. Returns dict: project -> list of parent projects."""
    # Build a map from relative path to project path for extra_deps lookup
    # e.g., "comm/py" -> "/lib/comm/py", "core" -> "/lib/core"
    relpath_to_project: dict[str, str] = {}
    for proj in projects:
        # Extract relative path from "/lib/..." (e.g., "/lib/comm/py" -> "comm/py")
        if proj.startswith("/lib/"):
            rel_path = proj[5:]  # Remove "/lib/"
            relpath_to_project[rel_path] = proj

    deps: dict[str, list[str]] = {}
    for proj in projects:
        proj_deps = get_path_dependencies(workspace_root, proj)

        # Add extra_deps from build.json
        project = Project(proj)
        config = project.build_config
        if config and config.extra_deps:
            for extra_name in config.extra_deps:
                extra_path = relpath_to_project.get(extra_name)
                if extra_path and extra_path not in proj_deps:
                    proj_deps.append(extra_path)

        deps[proj] = proj_deps
    return deps


def run_sequential(
    items: list[ProjectItem | CommandItem],
    all_projects: list[str],
    workspace: Path,
    color: bool,
    dryrun: bool,
    plan_path: Path | None = None,
) -> int:
    """Run commands sequentially (original behavior)."""
    script = Script(workspace, color=color)
    target_projects: list[str] = []

    for item in items:
        if isinstance(item, ProjectItem):
            target_projects.append(item.path)
        else:
            # Check if this is a built-in command or custom target
            cmd = COMMANDS.get(item.name)

            if cmd and cmd.root_only:
                script.leave_project()
                script.blank()
                script.comment(f"=== {item.name} ===")
                dummy = Project(".")
                emit_command(script, cmd, dummy, item.args, item.excluded_targets)
            else:
                if cmd and cmd.project_only and not target_projects:
                    log_error(
                        f"{item.name} requires a project "
                        f"(e.g., {cli_invocation()} /lib/core {item.name})"
                    )
                    return 1

                run_on = target_projects if target_projects else all_projects
                for proj_path in run_on:
                    project = Project(proj_path)
                    # Skip if this is a custom target that doesn't exist for this project
                    if cmd is None and project.get_custom_target(item.name) is None:
                        continue
                    script.leave_project()
                    script.blank()
                    script.comment(f"=== {proj_path} {item.name} ===")
                    emit_target(
                        script, item.name, project, item.args, item.excluded_targets
                    )

    if dryrun:
        script.print()
    elif plan_path:
        script.write_to(plan_path)
    return 0


def run_parallel(
    items: list[ProjectItem | CommandItem],
    all_projects: list[str],
    workspace: Path,
    color: bool,
    dryrun: bool,
    jobs: int,
    project_deps: dict[str, list[str]],
    plan_path: Path | None = None,
) -> int:
    """Run commands in parallel respecting dependencies."""
    # Handle root-only commands first (sequentially)
    root_items: list[CommandItem] = []
    project_items: list[ProjectItem | CommandItem] = []

    for item in items:
        if isinstance(item, ProjectItem):
            project_items.append(item)
        else:
            cmd = COMMANDS.get(item.name)
            if cmd and cmd.root_only:
                root_items.append(item)
            else:
                project_items.append(item)

    # Build combined script
    combined_lines: list[str] = []

    # Root commands section (sequential, runs first)
    if root_items:
        script = Script(workspace, color=color)
        for item in root_items:
            script.blank()
            script.comment(f"=== {item.name} ===")
            cmd = COMMANDS[item.name]
            dummy = Project(".")
            # Root commands use default handler (None key)
            handler = cmd.handlers.get(None)
            if handler:
                handler(script, dummy, item.args)
        script.finalize()

        # Add root commands to combined script (will run before parallel section)
        combined_lines.append("# Root-level commands (sequential)")
        combined_lines.extend(script._lines)
        combined_lines.append("")

    # If no project commands, just handle root commands
    if not any(isinstance(item, CommandItem) for item in project_items):
        if combined_lines:
            full_script = (
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n\n"
                f"export WORKSPACE=${{WORKSPACE:-{shquote(str(workspace))}}}\n\n"
                + "\n".join(combined_lines)
                + "\n"
            )
            if dryrun:
                print(full_script)
            elif plan_path:
                plan_path.write_text(full_script)
                plan_path.chmod(0o755)
            return 0
        return 0

    # Build task graph with phase support
    phases = split_into_phases(project_items)
    tasks: dict[str, Task] = {}
    num_phases = len(phases)

    for phase_idx, phase_items in enumerate(phases):
        phase_tasks = build_task_graph(phase_items, all_projects, project_deps)
        for task_id, task in phase_tasks.items():
            task.phase = phase_idx
            tasks[task_id] = task

    if not tasks:
        log_warn("No tasks to execute")
        return 0

    # Cap workers to max possible parallelism
    max_parallelism = calculate_max_parallelism(tasks)
    effective_jobs = min(jobs, max_parallelism)

    # Use sequential execution when parallelism is 1
    if effective_jobs < 2:
        parallel_script = generate_sequential_script(
            tasks, workspace, color, num_phases
        )
    else:
        parallel_script = generate_parallel_script(
            tasks, workspace, color, effective_jobs, num_phases
        )

    # If we have root commands, prepend them
    if combined_lines:
        # Insert root commands after header, before task functions
        header_end = parallel_script.find("# ====")
        if header_end > 0:
            parallel_script = (
                parallel_script[:header_end]
                + "# Root-level commands (sequential)\n"
                + "\n".join(combined_lines)
                + "\n\n"
                + parallel_script[header_end:]
            )

    if dryrun:
        print(parallel_script)
    elif plan_path:
        plan_path.write_text(parallel_script)
        plan_path.chmod(0o755)
    return 0


def main(workspace_root: Path | None = None) -> int:
    """Main entry point.

    Args:
        workspace_root: Root directory of the workspace. If None, computed from
            __file__ location (lib/build/glo_build/cli.py -> workspace root).
    """
    if workspace_root is None:
        env_ws = os.environ.get("WORKSPACE")
        if env_ws:
            workspace_root = Path(env_ws)
        else:
            # Fallback: compute from __file__: lib/build/glo_build/cli.py -> workspace root
            workspace_root = Path(__file__).resolve().parent.parent.parent.parent
    set_workspace_root(workspace_root)

    ws_root = get_workspace_root()

    # Early handling of context-sensitive help before argparse
    # This catches: /project --help, /project target --help
    all_projects = discover_projects(ws_root)
    argv = sys.argv[1:]

    if ("--help" in argv or "-h" in argv) and any(a.startswith("/") for a in argv):
        args_no_help = [a for a in argv if a not in ("--help", "-h")]
        # Find first project pattern
        project_args = [a for a in args_no_help if a.startswith("/")]
        if project_args:
            project_pattern = project_args[0]
            matches = expand_project_pattern(project_pattern, all_projects)
            if matches and len(matches) == 1:
                project_path = matches[0]
                # Get non-project, non-flag args after the project
                idx = args_no_help.index(project_pattern)
                remaining = [
                    a for a in args_no_help[idx + 1 :] if not a.startswith("-")
                ]
                if remaining:
                    show_target_help(project_path, remaining[0])
                else:
                    show_project_help(project_path)
                return 0

    cli = cli_invocation()
    parser = argparse.ArgumentParser(
        description="Lightweight build system for glo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Project patterns:
  / or /lib                                All projects
  /py, /ps, /hs, /meta, /rs, /ts          All projects by language
  /py/core or /lib/core                    Specific project
  ^/py/core                                Exclude a project

Target exclusions:
  precommit ^test                          Run precommit without test subtargets

Passing arguments to targets:
  Arguments after a single target are passed to that target's command.
  Meta-commands (like precommit) do not accept arguments.
  Use -- to pass flags like --help to the target instead of the build system.

Examples:
  {cli}                               List all commands
  {cli} /py/core format               Format core (by language)
  {cli} /lib/core format              Format core (by path)
  {cli} format                        Format all projects
  {cli} /py ^/py/core precommit       Run precommit on all Python except core
  {cli} precommit ^test               Run precommit without running tests
  {cli} /py/web dev --port 9000       Run web dev server on port 9000
  {cli} /py unit -k test_foo          Run specific tests on all Python projects
  {cli} /lib/tuner train -- --help    Pass --help to the train target
  {cli} shellcheck /py/core lint      Run shellcheck, then lint core
  {cli} --dryrun /py/core precommit   Print script without executing
  {cli} -j1 precommit                 Run precommit sequentially
""",
    )
    parser.add_argument(
        "--dryrun",
        action="store_true",
        help="Print the bash script instead of executing it",
    )
    parser.add_argument(
        "--nocolor",
        action="store_true",
        help="Disable colored output",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=os.cpu_count() or 4,
        metavar="N",
        help=f"Run N tasks in parallel (default: {os.cpu_count() or 4}, use -j1 for sequential)",
    )
    parser.add_argument(
        "--filter",
        choices=["none", "work", "workonly", "head"],
        default="none",
        help="Filter projects by git changes: none (all), work (staged+unstaged+deps), workonly (staged+unstaged), head (last commit+deps)",
    )
    parser.add_argument(
        "--plan-path",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,  # Internal: write script to file instead of executing
    )
    parser.add_argument(
        "args",
        nargs="*",
        help="[command [args...]] [project...] [command [args...]]...",
    )

    parsed, extra = parser.parse_known_args()

    # Combine positional args with any extra args that weren't consumed
    all_args = (parsed.args or []) + extra

    # Restore -- separator if it was in original argv
    # argparse consumes -- but we need it for passthrough mode
    if "--" in argv:
        dd_idx = argv.index("--")
        # Count non-flag args before -- (these are the positional args before --)
        before_dd = [a for a in argv[:dd_idx] if not a.startswith("-")]
        # Insert -- after those positional args in all_args
        insert_pos = len(before_dd)
        if insert_pos <= len(all_args):
            all_args = all_args[:insert_pos] + ["--"] + all_args[insert_pos:]

    # Handle no-args case: show general help
    if not all_args:
        show_help(all_projects)
        return 0

    # Handle single project arg: show project help
    if len(all_args) == 1 and all_args[0].startswith("/"):
        matches = expand_project_pattern(all_args[0], all_projects)
        if matches and len(matches) == 1:
            show_project_help(matches[0])
            return 0

    project_deps = get_all_project_deps(ws_root, all_projects)

    # Apply git filter if specified
    filtered_projects = filter_projects(
        all_projects, project_deps, parsed.filter, ws_root
    )
    if parsed.filter != "none" and not filtered_projects:
        return 0  # No projects affected, nothing to do

    # Parse into sequence of projects and commands
    items = parse_args_sequence(all_args, all_projects)
    if items is None:
        show_help(all_projects)
        return 1

    # Check we have at least one command
    has_command = any(isinstance(item, CommandItem) for item in items)
    if not has_command:
        # If we have just a project, show project help instead of error
        project_items = [i for i in items if isinstance(i, ProjectItem)]
        if len(project_items) == 1:
            show_project_help(project_items[0].path)
            return 0
        log_error("No command specified")
        return 1

    color = not parsed.nocolor

    # Use filtered projects for commands that run on "all"
    run_projects = filtered_projects if parsed.filter != "none" else all_projects

    if parsed.jobs > 1:
        return run_parallel(
            items,
            run_projects,
            ws_root,
            color,
            parsed.dryrun,
            parsed.jobs,
            project_deps,
            parsed.plan_path,
        )
    else:
        return run_sequential(
            items, run_projects, ws_root, color, parsed.dryrun, parsed.plan_path
        )


if __name__ == "__main__":
    raise SystemExit(main())
