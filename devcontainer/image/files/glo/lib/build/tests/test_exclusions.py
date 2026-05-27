"""Tests for project and target exclusion patterns."""

import pytest
from pathlib import Path
from loupe_build.cli import (
    expand_project_pattern,
    parse_args_sequence,
    validate_exclusion,
    get_all_target_names,
    expand_to_atomic_commands,
    set_workspace_root,
    COMMANDS,
    ProjectItem,
    CommandItem,
)


# Mock project list for testing
MOCK_PROJECTS = [
    "/lib/admin",
    "/lib/core",
    "/lib/edit",
    "/lib/gen",
    "/lib/model",
    "/lib/ops",
    "/lib/prover",
    "/lib/research",
    "/lib/web",
]

# Mock project list with nested projects for subproject expansion tests
MOCK_PROJECTS_WITH_NESTED = [
    "/lib/admin",
    "/lib/comm/gen",
    "/lib/comm/ps",
    "/lib/comm/py",
    "/lib/core",
    "/lib/edit",
    "/lib/tool/exe",
    "/lib/tool/ps",
    "/lib/tool/py",
    "/lib/ops",
    "/lib/persist/gen",
    "/lib/persist/py",
    "/lib/prover",
    "/lib/web",
]


@pytest.fixture(autouse=True)
def setup_workspace(tmp_path: Path) -> None:
    """Set up a minimal workspace for testing."""
    set_workspace_root(tmp_path)

    # Create lib directory with mock projects
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()

    # Create project directories with build.json files
    py_projects = ["admin", "core", "model", "ops", "prover", "research", "web"]
    ps_projects = ["edit"]

    for name in py_projects:
        proj_dir = lib_dir / name
        proj_dir.mkdir()
        (proj_dir / "build.json").write_text(
            f'{{"language": "py", "py_package": "loupe_{name}"}}'
        )

    for name in ps_projects:
        proj_dir = lib_dir / name
        proj_dir.mkdir()
        (proj_dir / "build.json").write_text('{"language": "ps"}')

    # Create nested project directories for subproject expansion tests
    nested_projects = {
        "comm/gen": "meta",
        "comm/ps": "ps",
        "comm/py": "py",
        "tool/exe": "meta",
        "tool/ps": "ps",
        "tool/py": "py",
        "persist/gen": "meta",
        "persist/py": "py",
    }

    for path, lang in nested_projects.items():
        proj_dir = lib_dir / path
        proj_dir.mkdir(parents=True)
        (proj_dir / "build.json").write_text(f'{{"language": "{lang}"}}')


class TestProjectExclusions:
    """Tests for project pattern exclusions (^/py/core, ^/lib/core)."""

    def test_expand_all_projects(self) -> None:
        """Test / expands to all projects."""
        result = expand_project_pattern("/", MOCK_PROJECTS)
        assert result == MOCK_PROJECTS

    def test_expand_by_language(self) -> None:
        """Test /py expands to all Python projects."""
        result = expand_project_pattern("/py", MOCK_PROJECTS)
        assert result is not None
        # Should include all Python projects (all except edit)
        assert "/lib/edit" not in result
        assert "/lib/core" in result

    def test_expand_specific_project(self) -> None:
        """Test /lib/core expands to just that project."""
        result = expand_project_pattern("/lib/core", MOCK_PROJECTS)
        assert result == ["/lib/core"]

    def test_expand_by_language_and_name(self) -> None:
        """Test /py/core expands to core project."""
        result = expand_project_pattern("/py/core", MOCK_PROJECTS)
        assert result == ["/lib/core"]

    def test_parse_with_project_exclusion(self) -> None:
        """Test parsing /py ^/py/core format."""
        args = ["/py", "^/lib/core", "format"]
        result = parse_args_sequence(args, MOCK_PROJECTS)

        assert result is not None
        # Should have projects (excluding core) followed by format command
        project_items = [i for i in result if isinstance(i, ProjectItem)]
        command_items = [i for i in result if isinstance(i, CommandItem)]

        # Core should be excluded
        project_paths = [p.path for p in project_items]
        assert "/lib/core" not in project_paths
        assert "/lib/admin" in project_paths

        # Should have format command
        assert len(command_items) == 1
        assert command_items[0].name == "format"

    def test_parse_multiple_project_exclusions(self) -> None:
        """Test parsing with multiple project exclusions."""
        args = ["/py", "^/lib/core", "^/lib/model", "format"]
        result = parse_args_sequence(args, MOCK_PROJECTS)

        assert result is not None
        project_items = [i for i in result if isinstance(i, ProjectItem)]
        project_paths = [p.path for p in project_items]

        assert "/lib/core" not in project_paths
        assert "/lib/model" not in project_paths
        assert "/lib/admin" in project_paths

    def test_invalid_project_exclusion_errors(self) -> None:
        """Test that invalid project exclusion patterns return None."""
        # Non-existent project
        args = ["/py", "^/lib/nonexistent", "format"]
        result = parse_args_sequence(args, MOCK_PROJECTS)
        assert result is None

    def test_validate_project_exclusion(self) -> None:
        """Test validate_exclusion for project patterns."""
        valid_targets = set(COMMANDS.keys())

        # Valid project exclusion
        result = validate_exclusion("^/lib/core", MOCK_PROJECTS, valid_targets, None)
        assert result == ("project", "/lib/core")

        # Invalid project exclusion
        result = validate_exclusion(
            "^/lib/nonexistent", MOCK_PROJECTS, valid_targets, None
        )
        assert result is None


class TestTargetExclusions:
    """Tests for target exclusions (precommit ^test)."""

    def test_get_all_target_names_atomic(self) -> None:
        """Test get_all_target_names for atomic command."""
        result = get_all_target_names("format")
        assert result == {"format"}

    def test_get_all_target_names_meta(self) -> None:
        """Test get_all_target_names for meta-command."""
        result = get_all_target_names("precommit")
        # precommit -> format, lint, test
        # test -> typecheck, unit
        expected = {"precommit", "gen", "format", "lint", "test", "typecheck", "unit"}
        assert result == expected

    def test_expand_with_exclusion(self) -> None:
        """Test expand_to_atomic_commands with exclusions."""
        cmd = COMMANDS["precommit"]

        # Without exclusion
        result = expand_to_atomic_commands(cmd, None)
        assert "typecheck" in result
        assert "unit" in result

        # With test exclusion
        result = expand_to_atomic_commands(cmd, {"test"})
        assert "typecheck" not in result
        assert "unit" not in result
        assert "format" in result
        assert "lint" in result

    def test_parse_with_target_exclusion(self) -> None:
        """Test parsing precommit ^test."""
        args = ["precommit", "^test"]
        result = parse_args_sequence(args, MOCK_PROJECTS)

        assert result is not None
        command_items = [i for i in result if isinstance(i, CommandItem)]

        assert len(command_items) == 1
        assert command_items[0].name == "precommit"
        assert "test" in command_items[0].excluded_targets

    def test_parse_with_multiple_target_exclusions(self) -> None:
        """Test parsing precommit ^test ^lint."""
        args = ["precommit", "^test", "^lint"]
        result = parse_args_sequence(args, MOCK_PROJECTS)

        assert result is not None
        command_items = [i for i in result if isinstance(i, CommandItem)]

        assert len(command_items) == 1
        assert command_items[0].name == "precommit"
        assert "test" in command_items[0].excluded_targets
        assert "lint" in command_items[0].excluded_targets

    def test_invalid_target_exclusion_errors(self) -> None:
        """Test that invalid target exclusions return None."""
        # Target not part of the command
        args = ["format", "^test"]
        result = parse_args_sequence(args, MOCK_PROJECTS)
        assert result is None

    def test_target_exclusion_without_command_errors(self) -> None:
        """Test that target exclusion without preceding command returns None."""
        args = ["^test", "format"]
        result = parse_args_sequence(args, MOCK_PROJECTS)
        assert result is None

    def test_validate_target_exclusion(self) -> None:
        """Test validate_exclusion for target patterns."""
        valid_targets = set(COMMANDS.keys())

        # Valid target exclusion (test is part of precommit)
        result = validate_exclusion("^test", MOCK_PROJECTS, valid_targets, "precommit")
        assert result == ("target", "test")

        # Invalid target (not part of the command)
        result = validate_exclusion("^test", MOCK_PROJECTS, valid_targets, "format")
        assert result is None

        # Non-existent target
        result = validate_exclusion(
            "^nonexistent", MOCK_PROJECTS, valid_targets, "precommit"
        )
        assert result is None


class TestCombinedExclusions:
    """Tests for combining project and target exclusions."""

    def test_project_and_target_exclusion(self) -> None:
        """Test /py ^/py/core precommit ^test."""
        args = ["/py", "^/lib/core", "precommit", "^test"]
        result = parse_args_sequence(args, MOCK_PROJECTS)

        assert result is not None
        project_items = [i for i in result if isinstance(i, ProjectItem)]
        command_items = [i for i in result if isinstance(i, CommandItem)]

        # Core should be excluded
        project_paths = [p.path for p in project_items]
        assert "/lib/core" not in project_paths

        # test should be excluded from precommit
        assert len(command_items) == 1
        assert command_items[0].name == "precommit"
        assert "test" in command_items[0].excluded_targets


class TestSubprojectExpansion:
    """Tests for subproject path expansion patterns."""

    def test_lib_parent_expands_to_children(self) -> None:
        """Test /lib/comm expands to all child projects."""
        result = expand_project_pattern("/lib/comm", MOCK_PROJECTS_WITH_NESTED)
        assert result is not None
        assert set(result) == {"/lib/comm/gen", "/lib/comm/ps", "/lib/comm/py"}

    def test_lib_parent_with_multiple_children(self) -> None:
        """Test /lib/tool expands to all tool child projects."""
        result = expand_project_pattern("/lib/tool", MOCK_PROJECTS_WITH_NESTED)
        assert result is not None
        assert set(result) == {"/lib/tool/exe", "/lib/tool/ps", "/lib/tool/py"}

    def test_py_filter_under_parent(self) -> None:
        """Test /py/comm selects all py projects under /lib/comm."""
        result = expand_project_pattern("/py/comm", MOCK_PROJECTS_WITH_NESTED)
        assert result == ["/lib/comm/py"]

    def test_ps_filter_under_parent(self) -> None:
        """Test /ps/comm selects all ps projects under /lib/comm."""
        result = expand_project_pattern("/ps/comm", MOCK_PROJECTS_WITH_NESTED)
        assert result == ["/lib/comm/ps"]

    def test_filter_for_persist(self) -> None:
        """Test language filter works for other nested projects like persist."""
        result = expand_project_pattern("/py/persist", MOCK_PROJECTS_WITH_NESTED)
        assert result == ["/lib/persist/py"]

    def test_direct_nested_path_still_works(self) -> None:
        """Test /lib/comm/py still works as a direct path."""
        result = expand_project_pattern("/lib/comm/py", MOCK_PROJECTS_WITH_NESTED)
        assert result == ["/lib/comm/py"]

    def test_nonexistent_shortcut_returns_empty(self) -> None:
        """Test /py/nonexistent returns empty list."""
        result = expand_project_pattern("/py/nonexistent", MOCK_PROJECTS_WITH_NESTED)
        assert result == []

    def test_nonexistent_parent_returns_empty(self) -> None:
        """Test /lib/nonexistent returns empty list."""
        result = expand_project_pattern("/lib/nonexistent", MOCK_PROJECTS_WITH_NESTED)
        assert result == []

    def test_py_core_still_matches_by_name(self) -> None:
        """Test /py/core still matches project by name (not as shortcut)."""
        result = expand_project_pattern("/py/core", MOCK_PROJECTS_WITH_NESTED)
        assert result == ["/lib/core"]
