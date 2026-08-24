"""Tests for bounded Rust target-cache retention."""

import os
import subprocess
from pathlib import Path

from glo_build.cli import (
    Project,
    Script,
    TargetStep,
    cmd_clean_rs,
    cmd_compile_rs,
    cmd_format_rs,
    cmd_release_test_rs,
    cmd_typecheck_rs,
    cmd_venv_rs,
    emit_custom_target,
    emit_target,
    raw_command_uses_cargo_target,
)


def make_rust_project(tmp_path: Path, manifest: str) -> Project:
    """Create a minimal Rust project for command-emission tests."""
    project_directory = tmp_path / "lib" / "example"
    project_directory.mkdir(parents=True)
    (project_directory / "build.json").write_text('{"language": "rs"}')
    (project_directory / "Cargo.toml").write_text(manifest)
    return Project("/lib/example", tmp_path)


def test_target_producing_command_emits_bounded_total_cleanup(tmp_path: Path) -> None:
    """Prune root artifacts first and retain a complete-target hard fallback."""
    project = make_rust_project(
        tmp_path,
        '[package]\nname = "example-package"\nversion = "0.1.0"\n',
    )
    script = Script(tmp_path, color=False)

    cmd_typecheck_rs(script, project, [])

    rendered = script.to_bash()
    assert "GLO_RUST_TARGET_SOFT_LIMIT_GIB:-32" in rendered
    assert "GLO_RUST_TARGET_HARD_LIMIT_GIB:-64" in rendered
    assert "GLO_RUST_TARGET_PRUNE_MIN_ITERATIONS:-10" in rendered
    assert ".rust-target-prune-iterations" in rendered
    assert "cargo clean --package example-package" in rendered
    assert "cargo clean --package example-package --target" in rendered
    assert "cargo clean --profile" not in rendered
    assert 'du -sk "${CARGO_TARGET_DIR}"' in rendered
    assert 'du -sk "${CARGO_TARGET_DIR}/debug"' not in rendered
    assert rendered.index("cargo clean --package") < rendered.index("cargo check")
    subprocess.run(["bash", "-n"], input=rendered, text=True, check=True)


def test_standard_compile_commands_use_profiles_crossenv_and_retention(
    tmp_path: Path,
) -> None:
    """Compile native and cross artifacts through the shared retention path."""
    project = make_rust_project(
        tmp_path,
        '[package]\nname = "example-package"\nversion = "0.1.0"\n',
    )

    debug_script = Script(tmp_path, color=False)
    cmd_compile_rs(debug_script, project, ["debug", "--bin", "example"])
    assert "cargo build --bin example" in debug_script.to_bash()

    release_script = Script(tmp_path, color=False)
    cmd_compile_rs(
        release_script,
        project,
        ["release", "x86_64-pc-windows-gnu", "--bin", "example"],
    )
    rendered_release = release_script.to_bash()
    assert (
        "cargo build --release --target x86_64-pc-windows-gnu --bin example"
        in rendered_release
    )
    assert rendered_release.index("cargo clean --package") < rendered_release.index(
        "cargo build --release"
    )

    test_script = Script(tmp_path, color=False)
    cmd_release_test_rs(test_script, project, ["--test", "cli"])
    rendered_test = test_script.to_bash()
    assert "cargo test --release --test cli" in rendered_test
    assert rendered_test.index("cargo clean --package") < rendered_test.index(
        "cargo test --release"
    )


def test_compile_requires_a_supported_profile(tmp_path: Path) -> None:
    """Emit a usage failure instead of guessing a Cargo profile."""
    project = make_rust_project(
        tmp_path,
        '[package]\nname = "example-package"\nversion = "0.1.0"\n',
    )

    for arguments in ([], ["optimized"]):
        script = Script(tmp_path, color=False)
        cmd_compile_rs(script, project, arguments)
        rendered = script.to_bash()
        assert "compile debug|release [crossenv]" in rendered
        assert "exit 2" in rendered
        assert "cargo build" not in rendered


def test_custom_compile_target_overrides_standard_command(tmp_path: Path) -> None:
    """Keep project-specific compile contracts available under the standard name."""
    project = make_rust_project(
        tmp_path,
        '[package]\nname = "example-package"\nversion = "0.1.0"\n',
    )
    (project.abs_path / "build.json").write_text(
        '{"language":"rs","targets":{"compile":[{"command":"./special-build"}]}}'
    )
    script = Script(tmp_path, color=False)

    emit_target(script, "compile", project, ["release"])

    rendered = script.to_bash()
    assert "./special-build release" in rendered
    assert "cargo build --release" not in rendered


def test_virtual_workspace_uses_workspace_package_selection(tmp_path: Path) -> None:
    """Use Cargo's workspace selector when a Rust project has no root package."""
    project = make_rust_project(tmp_path, "[workspace]\nmembers = []\n")
    script = Script(tmp_path, color=False)

    cmd_typecheck_rs(script, project, [])

    assert "cargo clean --workspace" in script.to_bash()


def test_non_building_cargo_commands_do_not_prune(tmp_path: Path) -> None:
    """Avoid retention work for fetch, formatting, and explicit cleaning."""
    project = make_rust_project(
        tmp_path,
        '[package]\nname = "example-package"\nversion = "0.1.0"\n',
    )

    for command in (cmd_venv_rs, cmd_format_rs, cmd_clean_rs):
        script = Script(tmp_path, color=False)
        command(script, project, [])
        assert "GLO_RUST_TARGET_SOFT_LIMIT_GIB" not in script.to_bash()


def test_custom_cargo_target_emits_cleanup(tmp_path: Path) -> None:
    """Apply retention to raw Cargo commands from project-local targets."""
    project = make_rust_project(
        tmp_path,
        '[package]\nname = "example-package"\nversion = "0.1.0"\n',
    )
    script = Script(tmp_path, color=False)

    emit_custom_target(
        script,
        project,
        [TargetStep(command="cargo test --release")],
        [],
    )

    rendered = script.to_bash()
    assert "cargo clean --package example-package" in rendered
    assert rendered.index("cargo clean --package") < rendered.index(
        "cargo test --release"
    )


def test_non_cargo_custom_target_does_not_prune(tmp_path: Path) -> None:
    """Leave generator-style custom commands free of Rust cache side effects."""
    project = make_rust_project(
        tmp_path,
        '[package]\nname = "example-package"\nversion = "0.1.0"\n',
    )
    script = Script(tmp_path, color=False)

    emit_custom_target(script, project, [TargetStep(command="./gen.py")], [])

    assert "GLO_RUST_TARGET_SOFT_LIMIT_GIB" not in script.to_bash()


def test_raw_cargo_detection_handles_toolchains_and_shell_sequences() -> None:
    """Recognize building commands without treating maintenance commands as builds."""
    assert raw_command_uses_cargo_target("cargo test")
    assert raw_command_uses_cargo_target("prepare; cargo +nightly build --release")
    assert not raw_command_uses_cargo_target("cargo fmt")
    assert not raw_command_uses_cargo_target("cargo fetch")


def test_oversized_cache_cleans_host_cross_targets_then_complete_tree(
    tmp_path: Path,
) -> None:
    """Wait ten invocations before pruning and reset the persistent counter."""
    project = make_rust_project(
        tmp_path,
        '[package]\nname = "example-package"\nversion = "0.1.0"\n',
    )
    target_directory = tmp_path / ".glo" / "venv" / "example" / "target"
    (target_directory / "debug").mkdir(parents=True)
    (target_directory / "release").mkdir()
    (target_directory / "x86_64-pc-windows-gnu" / "release").mkdir(parents=True)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    cargo_log = tmp_path / "cargo.log"
    fake_cargo = fake_bin / "cargo"
    fake_cargo.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "${GLO_TEST_CARGO_LOG}"\n')
    fake_cargo.chmod(0o755)
    fake_du = fake_bin / "du"
    fake_du.write_text('#!/bin/sh\nprintf "73400320\\t%s\\n" "$2"\n')
    fake_du.chmod(0o755)
    fake_rustc = fake_bin / "rustc"
    fake_rustc.write_text('#!/bin/sh\nprintf "x86_64-pc-windows-gnu\\n"\n')
    fake_rustc.chmod(0o755)
    script = Script(tmp_path, color=False)
    script.enter_project(script.workspace_path(project.abs_path))
    project.emit_rs_env(script)
    project.emit_rust_target_prune(script)

    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    environment["GLO_TEST_CARGO_LOG"] = str(cargo_log)
    counter_file = target_directory.parent / ".rust-target-prune-iterations"
    for expected_iteration in range(1, 10):
        subprocess.run(
            ["bash"],
            input=script.to_bash(),
            text=True,
            check=True,
            env=environment,
            capture_output=True,
        )
        assert not cargo_log.exists()
        assert counter_file.read_text() == f"{expected_iteration}\n"

    subprocess.run(
        ["bash"],
        input=script.to_bash(),
        text=True,
        check=True,
        env=environment,
        capture_output=True,
    )

    assert cargo_log.read_text().splitlines() == [
        "clean --package example-package",
        "clean --package example-package --target x86_64-pc-windows-gnu",
        "clean",
    ]
    assert counter_file.read_text() == "0\n"

    subprocess.run(
        ["bash"],
        input=script.to_bash(),
        text=True,
        check=True,
        env=environment,
        capture_output=True,
    )
    assert len(cargo_log.read_text().splitlines()) == 3
    assert counter_file.read_text() == "1\n"


def test_prune_iteration_configuration_and_counter_recovery(tmp_path: Path) -> None:
    """Validate the interval and recover malformed project-local state."""
    project = make_rust_project(
        tmp_path,
        '[package]\nname = "example-package"\nversion = "0.1.0"\n',
    )
    target_directory = tmp_path / ".glo" / "venv" / "example" / "target"
    target_directory.mkdir(parents=True)
    counter_file = target_directory.parent / ".rust-target-prune-iterations"
    counter_file.write_text("not-a-counter\n")
    script = Script(tmp_path, color=False)
    script.enter_project(script.workspace_path(project.abs_path))
    project.emit_rs_env(script)
    project.emit_rust_target_prune(script)
    rendered = script.to_bash()

    environment = os.environ.copy()
    environment["GLO_RUST_TARGET_PRUNE_MIN_ITERATIONS"] = "3"
    subprocess.run(
        ["bash"],
        input=rendered,
        text=True,
        check=True,
        env=environment,
        capture_output=True,
    )
    assert counter_file.read_text() == "1\n"

    environment["GLO_RUST_TARGET_PRUNE_MIN_ITERATIONS"] = "1"
    subprocess.run(
        ["bash"],
        input=rendered,
        text=True,
        check=True,
        env=environment,
        capture_output=True,
    )
    assert counter_file.read_text() == "0\n"

    environment["GLO_RUST_TARGET_PRUNE_MIN_ITERATIONS"] = "0"
    invalid = subprocess.run(
        ["bash"],
        input=rendered,
        text=True,
        check=False,
        env=environment,
        capture_output=True,
    )
    assert invalid.returncode == 2
    assert "must be a positive integer" in invalid.stderr

    counter_file.unlink()
    environment["GLO_RUST_TARGET_SOFT_LIMIT_GIB"] = "0"
    subprocess.run(
        ["bash"],
        input=rendered,
        text=True,
        check=True,
        env=environment,
        capture_output=True,
    )
    assert not counter_file.exists()
