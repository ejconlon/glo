"""Custom target documentation is useful in help and never changes execution."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from glo_build import cli


@pytest.mark.parametrize("language", ["py", "rs", "hs", "ps", "ts", "rocq"])
@pytest.mark.parametrize("name", ["compile", "ghci", "repl", "release-test"])
def test_removed_language_shortcuts_are_not_advertised_or_executable(
    tmp_path: Path, monkeypatch, capsys, language: str, name: str
) -> None:
    """Unsupported shortcuts must fail instead of planning a tool or a no-op."""
    project = write_project(tmp_path, {})
    (project / "build.json").write_text(json.dumps({"language": language}))
    monkeypatch.setattr(sys, "argv", ["glo-build"])
    assert cli.main(tmp_path) == 0
    help_text = capsys.readouterr().out
    assert "Project-specific commands:" not in help_text
    assert not any(line.split()[:1] == [name] for line in help_text.splitlines())
    monkeypatch.setattr(sys, "argv", ["glo-build", "--dryrun", "/lib/example", name])
    assert cli.main(tmp_path) != 0
    output = capsys.readouterr()
    assert f"Unknown command: {name}" in output.err


@pytest.mark.parametrize("name", ["compile", "ghci", "repl", "release-test"])
def test_removed_shortcuts_can_only_run_when_defined_by_the_project(
    tmp_path: Path, monkeypatch, capsys, name: str
) -> None:
    """Removing builtins must preserve concrete custom targets with those names."""
    project = write_project(tmp_path, {name: [{"command": "printf '%s' > result.txt"}]})
    monkeypatch.setenv("WORKSPACE", str(tmp_path))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "glo-build",
            "--dryrun",
            "-j1",
            "/lib/example",
            name,
            "--",
            "custom implementation",
        ],
    )
    assert cli.main(tmp_path) == 0
    script = capsys.readouterr().out
    subprocess.run(
        ["bash"], input=script, text=True, cwd=tmp_path, check=True, capture_output=True
    )
    assert (project / "result.txt").read_text() == "custom implementation"


def write_project(root: Path, targets: dict[str, list[dict]]) -> Path:
    """Create a metadata-only project so command tests need no language toolchain."""
    project = root / "lib" / "example"
    project.mkdir(parents=True)
    (project / "build.json").write_text(
        json.dumps({"language": "meta", "targets": targets})
    )
    return project


def test_help_summarizes_docs_and_renders_details_without_running_steps(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Show wrapped prose instead of shell previews, with full details on demand."""
    name = "generate-the-calendar-refinement-example"
    summary = (
        "Generate the calendar refinement example with both models and shared types."
    )
    detail = "Writes the generated program to /tmp/generated-calendar-refinement."
    doc = f"{summary}\n\n{detail}\n\n- Pass --output PATH to choose a directory.\n- Existing files are replaced."
    project = write_project(
        tmp_path,
        {
            name: [{"doc": doc}, {"command": "touch should-not-run"}],
            "legacy": [{"command": "echo legacy"}],
        },
    )
    monkeypatch.setenv("COLUMNS", "60")
    monkeypatch.setattr(sys, "argv", ["glo-build", "/lib/example"])
    assert cli.main(tmp_path) == 0
    output = capsys.readouterr().out
    custom = output.split("Custom targets:\n", 1)[1].split("Built-in commands:", 1)[0]
    assert summary in " ".join(custom.split())
    assert detail not in custom
    assert "touch should-not-run" not in custom
    assert "echo legacy" in custom
    assert all(len(line) <= 60 for line in custom.splitlines())

    monkeypatch.setattr(sys, "argv", ["glo-build", "/lib/example", name, "--help"])
    assert cli.main(tmp_path) == 0
    output = capsys.readouterr().out
    description = output.split("\n\n", 1)[1].split("\nUsage:", 1)[0]
    assert summary in " ".join(description.split())
    assert detail in " ".join(description.split())
    assert "\n- Pass --output PATH" in description
    assert all(len(line) <= 60 for line in description.splitlines())
    assert "1. Run: touch should-not-run" in output
    assert "2. Run:" not in output
    assert not (project / "should-not-run").exists()


@pytest.mark.parametrize("jobs", [1, 4])
def test_documented_nested_targets_preserve_passthrough_arguments(
    tmp_path: Path, monkeypatch, capsys, jobs: int
) -> None:
    """Docs are absent from executable plans; nested targets forward exact argv."""
    project = write_project(
        tmp_path,
        {
            "capture": [
                {"doc": "Capture arguments. $(touch doc-executed)"},
                {"command": ["true", "python3 capture.py"], "args": ["fixed"]},
            ],
            "outer": [
                {"doc": "Run the documented capture target."},
                {"target": "capture", "args": ["nested"]},
            ],
        },
    )
    (project / "capture.py").write_text(
        "import json, pathlib, sys\n"
        "pathlib.Path('received.json').write_text(json.dumps(sys.argv[1:]))\n"
    )
    monkeypatch.setenv("WORKSPACE", str(tmp_path))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "glo-build",
            "--dryrun",
            f"-j{jobs}",
            "/lib/example",
            "outer",
            "--",
            "two words",
            "lint",
            "--help",
        ],
    )
    assert cli.main(tmp_path) == 0
    script = capsys.readouterr().out
    assert "doc-executed" not in script
    completed = subprocess.run(
        ["bash"],
        input=script,
        text=True,
        capture_output=True,
        cwd=tmp_path,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads((project / "received.json").read_text()) == [
        "fixed",
        "nested",
        "two words",
        "lint",
        "--help",
    ]
    assert not (project / "doc-executed").exists()


@pytest.mark.parametrize(
    ("entries", "reason"),
    [
        ([{"command": "true"}, {"doc": "Too late."}], "first entry"),
        ([{"doc": "First."}, {"doc": "Again."}, {"command": "true"}], "first entry"),
        ([{"doc": "Mixed.", "command": "true"}], "own object"),
        ([{"doc": "Mixed.", "args": []}, {"command": "true"}], "own object"),
        ([{"doc": 123}, {"command": "true"}], "nonempty string"),
        ([{"doc": "  \n "}, {"command": "true"}], "nonempty string"),
        ([{"doc": "Nothing to execute."}], "executable steps"),
    ],
)
def test_invalid_docs_fail_at_cli_with_a_target_diagnostic(
    tmp_path: Path, monkeypatch, capsys, entries: list[dict], reason: str
) -> None:
    """Reject misplaced metadata instead of silently discarding it or arguments."""
    write_project(tmp_path, {"broken": entries})
    monkeypatch.setattr(
        sys, "argv", ["glo-build", "--dryrun", "/lib/example", "broken"]
    )
    assert cli.main(tmp_path) == 1
    output = capsys.readouterr()
    assert "build.json: target 'broken'" in output.err
    assert reason in output.err
    assert "Traceback" not in output.err
    assert "#!/usr/bin/env bash" not in output.out
