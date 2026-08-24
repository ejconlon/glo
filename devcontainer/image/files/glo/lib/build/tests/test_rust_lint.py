"""Tests for Rust lint command emission."""

from pathlib import Path

from glo_build.cli import Project, Script, cmd_lint_rs


def test_rust_lint_covers_all_targets_and_features(tmp_path: Path) -> None:
    """Pass every package target and feature to the standard Clippy command."""

    project_directory = tmp_path / "lib" / "example"
    project_directory.mkdir(parents=True)
    (project_directory / "build.json").write_text('{"language": "rs"}')
    (project_directory / "Cargo.toml").write_text(
        '[package]\nname = "example"\nversion = "0.1.0"\n'
    )
    script = Script(tmp_path, color=False)

    cmd_lint_rs(script, Project("/lib/example", tmp_path), [])

    assert (
        "cargo clippy --all-targets --all-features -- -D warnings" in script.to_bash()
    )
