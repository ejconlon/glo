"""Exercise Haskell formatting and config precedence with the real formatter."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest

from glo_build.cli import Project, Script, cmd_format_haskell


@pytest.mark.skipif(shutil.which("fourmolu") is None, reason="Fourmolu is required")
@pytest.mark.parametrize("config_source", ["project", "workspace", "defaults"])
def test_format_config_precedence_across_source_directories(
    tmp_path: Path,
    config_source: str,
) -> None:
    """Prefer project settings, then workspace settings, and tolerate missing configs."""
    workspace = tmp_path
    project_dir = workspace / "lib" / "example"
    project_dir.mkdir(parents=True)
    (project_dir / "build.json").write_text('{"language": "hs"}')
    config_args = []
    if config_source != "defaults":
        config = workspace / "config" / "hs" / "fourmolu.yaml"
        config.parent.mkdir(parents=True)
        config.write_text("indentation: 2\ncolumn-limit: 60\n")
        config_args = ["--config", str(config)]
    if config_source == "project":
        config = project_dir / "fourmolu.yaml"
        config.write_text("indentation: 4\ncolumn-limit: 60\n")
        config_args = ["--config", str(config)]
    source = (
        "module Example where\n"
        "values = [firstComponent, secondComponent, thirdComponent, "
        "fourthComponent, fifthComponent, sixthComponent]\n"
    )
    files = []
    for directory in ("src", "test", "app"):
        path = project_dir / directory / "Example.hs"
        path.parent.mkdir()
        path.write_text(source)
        files.append(path)

    script = Script(workspace, color=False)
    cmd_format_haskell(script, Project("/lib/example", workspace), [])
    subprocess.run(
        ["bash"],
        input=script.to_bash(),
        text=True,
        env={**os.environ, "WORKSPACE": str(workspace)},
        check=True,
        capture_output=True,
    )

    for path in files:
        formatted = path.read_text()
        assert formatted != source
        if config_source != "defaults":
            assert max(map(len, formatted.splitlines())) <= 60
        assert "firstComponent" in formatted and "sixthComponent" in formatted
    subprocess.run(
        ["fourmolu", *config_args, "--mode", "check", *map(str, files)],
        check=True,
        capture_output=True,
    )
