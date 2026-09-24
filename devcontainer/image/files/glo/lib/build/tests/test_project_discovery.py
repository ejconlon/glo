"""Tests for bounded project discovery and exact project selection."""

import json
import sys
from pathlib import Path

from glo_build import cli


def _project(root: Path, name: str) -> None:
    path = root / "lib" / name
    path.mkdir(parents=True)
    (path / "build.json").write_text(json.dumps({"language": "meta"}))


def test_discovery_stops_at_two_project_levels_and_sorts_dependencies(
    tmp_path: Path,
) -> None:
    """Honor path dependencies while excluding deeper build manifests."""
    for name in ("alpha", "zeta", "group/child", "group/child/deep"):
        _project(tmp_path, name)
    (tmp_path / "lib/alpha/pyproject.toml").write_text(
        '[project]\nname = "alpha"\n[tool.uv.sources]\nzeta = { path = "../zeta" }\n'
    )
    (tmp_path / "lib/zeta/pyproject.toml").write_text('[project]\nname = "zeta"\n')

    projects = cli.discover_projects(tmp_path)

    assert set(projects) == {"/lib/alpha", "/lib/zeta", "/lib/group/child"}
    assert projects.index("/lib/zeta") < projects.index("/lib/alpha")
    assert not cli.is_exact_project_path(tmp_path, "/lib/group/child/deep")


def test_exact_project_skips_workspace_discovery(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Plan one exact project even when scanning the workspace is unavailable."""
    _project(tmp_path, "alpha")
    (tmp_path / "lib/alpha/build.json").write_text(
        json.dumps({"language": "meta", "targets": {"ping": [{"command": "true"}]}})
    )

    def reject_discovery(_root: Path) -> list[str]:
        raise AssertionError("exact project selection scanned the workspace")

    monkeypatch.setattr(cli, "discover_projects", reject_discovery)
    monkeypatch.setattr(sys, "argv", ["glo-build", "--dryrun", "/lib/alpha", "ping"])

    assert cli.main(tmp_path) == 0
    assert "true" in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["glo-build", "/lib/alpha", "ping", "--help"])
    assert cli.main(tmp_path) == 0
    assert "Custom target: ping" in capsys.readouterr().out
