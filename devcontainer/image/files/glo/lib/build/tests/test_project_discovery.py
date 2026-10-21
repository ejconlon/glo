"""Tests for bounded project discovery and exact project selection."""

import json
import os
import sys
from pathlib import Path

import pytest

from glo_build import cli


def _project(root: Path, name: str) -> None:
    path = root / "lib" / name
    path.mkdir(parents=True)
    (path / "build.json").write_text(json.dumps({"language": "meta"}))


def test_discovery_stops_at_three_project_levels_and_sorts_dependencies(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Honor nested package dependencies without enumerating out-of-scope subtrees."""
    for name in (
        "alpha",
        "zeta",
        "group/child",
        "group/child/deep",
        "group/child/deep/ignored",
    ):
        _project(tmp_path, name)
    (tmp_path / "lib/alpha/pyproject.toml").write_text(
        '[project]\nname = "alpha"\n[tool.uv.sources]\ndeep = { path = "../group/child/deep" }\n'
    )
    (tmp_path / "lib/group/child/deep/pyproject.toml").write_text(
        '[project]\nname = "deep"\n[tool.uv.sources]\nzeta = { path = "../../../zeta" }\n'
    )
    (tmp_path / "lib/zeta/pyproject.toml").write_text('[project]\nname = "zeta"\n')
    real_scandir = os.scandir

    def bounded_scandir(path):
        assert len(Path(path).relative_to(tmp_path / "lib").parts) <= 3
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", bounded_scandir)

    projects = cli.discover_projects(tmp_path)

    assert set(projects) == {
        "/lib/alpha",
        "/lib/zeta",
        "/lib/group/child",
        "/lib/group/child/deep",
    }
    assert projects.index("/lib/zeta") < projects.index("/lib/group/child/deep")
    assert projects.index("/lib/group/child/deep") < projects.index("/lib/alpha")
    assert cli.is_exact_project_path(tmp_path, "/lib/group/child/deep")
    assert not cli.is_exact_project_path(tmp_path, "/lib/group/child/deep/ignored")
    assert (
        cli.expand_project_pattern("/lib/group/child/deep/ignored", projects, tmp_path)
        == []
    )


@pytest.mark.parametrize("name", ["alpha", "group/child", "group/child/deep"])
def test_exact_project_skips_workspace_discovery(
    tmp_path: Path, monkeypatch, capsys, name: str
) -> None:
    """Plan one exact project even when scanning the workspace is unavailable."""
    _project(tmp_path, name)
    project_path = f"/lib/{name}"
    (tmp_path / "lib" / name / "build.json").write_text(
        json.dumps({"language": "meta", "targets": {"ping": [{"command": "true"}]}})
    )

    def reject_discovery(_root: Path) -> list[str]:
        raise AssertionError("exact project selection scanned the workspace")

    monkeypatch.setattr(cli, "discover_projects", reject_discovery)
    monkeypatch.setattr(sys, "argv", ["glo-build", "--dryrun", project_path, "ping"])

    assert cli.main(tmp_path) == 0
    assert "true" in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["glo-build", project_path, "ping", "--help"])
    assert cli.main(tmp_path) == 0
    assert "Custom target: ping" in capsys.readouterr().out


def test_changed_nested_project_selects_leaf_and_dependents(
    tmp_path: Path, monkeypatch
) -> None:
    """A parent manifest must not hide changed third-level projects from work filters."""
    for name in ("group", "group/child", "group/child/deep", "consumer"):
        _project(tmp_path, name)
    (tmp_path / "lib/consumer/build.json").write_text(
        json.dumps({"language": "meta", "extra_deps": ["group/child/deep"]})
    )
    cli.set_workspace_root(tmp_path)
    projects = cli.discover_projects(tmp_path)
    dependencies = cli.get_all_project_deps(tmp_path, projects)
    assert dependencies["/lib/consumer"] == ["/lib/group/child/deep"]
    monkeypatch.setattr(
        cli, "get_git_changed_files", lambda *_: ["lib/group/child/deep/src/main.py"]
    )
    assert cli.filter_projects(projects, dependencies, "workonly", tmp_path) == [
        "/lib/group/child/deep"
    ]
    assert cli.filter_projects(projects, dependencies, "work", tmp_path) == [
        project
        for project in projects
        if project in ("/lib/group/child/deep", "/lib/consumer")
    ]
