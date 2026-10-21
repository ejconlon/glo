#!/usr/bin/env python3
"""Verify notebook overrides through real bootstrap and CLI workflows in private fixtures."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GLO_ROOT = Path(__file__).resolve().parents[1]
GLO = GLO_ROOT / "devcontainer/image/files/glo"


class BasePathTests(unittest.TestCase):
    """Check that bootstrap, issues, agents and notes select the same notebook."""

    def setUp(self) -> None:
        """Own all filesystem state and reuse Python without installing dependencies."""
        self.temporary = tempfile.TemporaryDirectory(prefix="glo-base-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        (self.workspace / ".git").mkdir(parents=True)
        self.nested = self.workspace / "lib/nested"
        self.nested.mkdir(parents=True)
        build_bin = self.workspace / ".glo/build/bin"
        build_bin.mkdir(parents=True)
        (build_bin / "python3").symlink_to(Path(sys.executable).resolve())
        self.environment = dict(os.environ, AGENT_NAME="base-test")
        for name in ("GLO_BASE", "TICKETS_DIR", "ZK_NOTEBOOK_DIR"):
            self.environment.pop(name, None)

    def _run(
        self, *arguments: str, bootstrap: bool = False
    ) -> subprocess.CompletedProcess[str]:
        command = GLO_ROOT / "bootstrap.sh" if bootstrap else GLO / "bin/glo"
        return subprocess.run(
            [str(command), *arguments],
            cwd=self.workspace if bootstrap else self.nested,
            env=self.environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )

    def _output(self, *arguments: str, bootstrap: bool = False) -> str:
        result = self._run(*arguments, bootstrap=bootstrap)
        self.assertEqual(
            result.returncode, 0, (arguments, result.stdout, result.stderr)
        )
        return result.stdout

    def _exercise_notebook(self, base: Path) -> None:
        """Use the selected notebook from a nested cwd, through archival and resumption."""
        self._output(bootstrap=True)
        for relative in ("issue/.gitkeep", "wiki/.gitkeep", ".zk/config.toml"):
            self.assertTrue((base / relative).is_file(), base / relative)
        if base != self.workspace / "base":
            self.assertFalse((self.workspace / "base").exists())
        self.assertTrue((self.workspace / "bin/glo-notes").is_file())

        # The notebook should survive repeated bootstrap without configuration loss.
        config = base / ".zk/config.toml"
        config.write_text(config.read_text() + "\n# Keep this local configuration\n")
        before = config.read_bytes()
        self._output(bootstrap=True)
        self.assertEqual(config.read_bytes(), before)

        issue = self._output(
            "agent", "issue", "create", "Configured notebook task"
        ).strip()
        issue_file = base / "issue" / f"{issue}.md"
        self.assertTrue(issue_file.is_file())
        self._output("agent", "focus", "push", issue)
        self.assertEqual(self._output("agent", "focus", "get").strip(), issue)
        self.assertIn("status: in_progress", self._output("issue", "show", issue))
        self.assertEqual(
            (self.workspace / ".glo/agent/base-test/focus").read_text().strip(), issue
        )
        self._output("agent", "focus", "close")

        dependent = self._output("issue", "create", "Waits for completed task").strip()
        self._output("issue", "dep", dependent, issue)
        self._output(
            "notes",
            "zk",
            "new",
            "--group",
            "wiki",
            "--title",
            "Notebook path test",
            "--print-path",
            "--no-input",
        )
        self._output("notes", "precommit")
        self.assertTrue((base / "issue/archive" / issue_file.name).is_file())
        self.assertFalse(issue_file.exists())
        self.assertIn(dependent, self._output("issue", "ready"))
        self.assertTrue((base / "wiki/notebook-path-test.md").is_file())
        self.assertTrue((base / ".zk/notebook.db").is_file())
        self.assertIn("Waits for completed task", (base / "TITLES.md").read_text())
        self.assertIn("wiki-notebook-path-test", (base / "TAGS.md").read_text())
        self._output("issue", "reopen", issue)
        self.assertTrue(issue_file.is_file())
        self.assertIn("status: open", issue_file.read_text())
        if base != self.workspace / "base":
            self.assertFalse((self.workspace / "base").exists())

    def test_default_notebook_for_unset_and_empty_values(self) -> None:
        """Unset and empty overrides must retain the ordinary base layout and workflow."""
        self._exercise_notebook(self.workspace / "base")
        self.environment["GLO_BASE"] = ""
        self._output(bootstrap=True)
        issue = self._output("issue", "create", "Empty override uses default").strip()
        self.assertTrue((self.workspace / "base/issue" / f"{issue}.md").is_file())
        ignored = (self.workspace / ".gitignore").read_text().splitlines()
        self.assertEqual(ignored.count("/base/.zk/notebook.db"), 1)

    def test_relative_notebook_with_spaces_quotes_and_glob_characters(self) -> None:
        """Relative paths must stay workspace-relative and remain literal in indexes/ignores."""
        self.environment["GLO_BASE"] = "docs/team's notes [draft]/"
        base = self.workspace / "docs/team's notes [draft]"
        self._exercise_notebook(base)
        ignored = (self.workspace / ".gitignore").read_text().splitlines()
        self.assertEqual(
            ignored.count("/docs/team's notes \\[draft\\]/.zk/notebook.db"), 1
        )
        self.assertNotIn("/base/.zk/notebook.db", ignored)
        self.assertFalse((self.nested / "docs").exists())

    def test_absolute_notebook_inside_workspace_uses_relative_ignore(self) -> None:
        """An absolute override inside the workspace must still generate a useful ignore entry."""
        base = self.workspace / "knowledge"
        self.environment["GLO_BASE"] = str(base)
        self._exercise_notebook(base)
        self.assertIn(
            "/knowledge/.zk/notebook.db",
            (self.workspace / ".gitignore").read_text().splitlines(),
        )

    def test_external_notebook_does_not_create_default_or_bake_path_into_wrappers(
        self,
    ) -> None:
        """An external notebook must work without a bogus Git ignore or persistent override."""
        base = self.root / "outside team's notebook"
        self.environment["GLO_BASE"] = str(base)
        self._exercise_notebook(base)
        ignored = (self.workspace / ".gitignore").read_text()
        self.assertNotIn("notebook.db", ignored)
        for wrapper in (self.workspace / "bin").iterdir():
            self.assertNotIn(str(base), wrapper.read_text())
        self.environment.pop("GLO_BASE")
        result = self._run("issue", "ls")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(self.workspace / "base/issue"), result.stderr)
        self._output(bootstrap=True)
        issue = self._output("issue", "create", "Back to the default notebook").strip()
        self.assertTrue((self.workspace / "base/issue" / f"{issue}.md").is_file())
        self.assertFalse((base / "issue" / f"{issue}.md").exists())

    def test_missing_custom_notebook_errors_identify_selected_paths(self) -> None:
        """A missing override must fail clearly instead of silently using another notebook."""
        self._output(bootstrap=True)
        self.environment["GLO_BASE"] = "not-initialized"
        for arguments in (
            ("issue", "ls"),
            ("agent", "issue", "list"),
            ("notes", "index"),
        ):
            with self.subTest(arguments=arguments):
                result = self._run(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(str(self.workspace / "not-initialized"), result.stderr)
        self.assertFalse((self.workspace / "not-initialized").exists())

    def test_direct_issue_override_cannot_redirect_agent_or_notes(self) -> None:
        """Keep TICKETS_DIR compatibility without splitting an agent/notes workflow."""
        base = self.workspace / "custom"
        self.environment["GLO_BASE"] = "custom"
        self._output(bootstrap=True)
        other = self.root / "other issues"
        other.mkdir()
        self.environment["TICKETS_DIR"] = str(other)
        direct = self._output("issue", "create", "Direct override").strip()
        self._output("issue", "close", direct)
        self.assertTrue((other / f"{direct}.md").is_file())
        agent = self._output("agent", "issue", "create", "Agent notebook").strip()
        self._output("agent", "issue", "close", agent)
        self._output("notes", "precommit")
        self.assertTrue((base / "issue/archive" / f"{agent}.md").is_file())
        self.assertTrue((other / f"{direct}.md").is_file())
        self.assertFalse((other / "archive").exists())


if __name__ == "__main__":
    unittest.main()
