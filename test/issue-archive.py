#!/usr/bin/env python3
"""Exercise archive relationships, lifecycle and notes commands in private notebooks."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

GLO = Path(__file__).resolve().parents[1] / "devcontainer/image/files/glo"


class IssueArchiveTests(unittest.TestCase):
    """Verify that moving issue files preserves their meaning and relationships."""

    def setUp(self) -> None:
        """Own a private workspace and notebook without invoking Git."""
        self.temporary = tempfile.TemporaryDirectory(prefix="glo archive tests ")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        (self.workspace / ".git").mkdir()
        self.issues = self.workspace / "base/issue"
        self.archive = self.issues / "archive"
        self.archive.mkdir(parents=True)
        shutil.copytree(GLO / "base-scaffold/.zk", self.workspace / "base/.zk")
        (self.workspace / "base/wiki").mkdir()
        self.environment = dict(
            os.environ, TICKETS_DIR=str(self.issues), AGENT_NAME="tester"
        )
        self.environment.pop("GLO_BASE", None)

    def _issue(self, name: str, *, archived: bool = False, **fields: str) -> Path:
        attributes = {
            "id": name,
            "status": "open",
            "deps": "[]",
            "links": "[]",
            "priority": "2",
            "assignee": "",
            **fields,
        }
        path = (self.archive if archived else self.issues) / f"{name}.md"
        metadata = "\n".join(f"{key}: {value}" for key, value in attributes.items())
        path.write_text(
            f"---\n{metadata}\n---\n# Title for {name}\n\nBody for {name}\n"
        )
        return path

    def _run(
        self, *arguments: str, tool: str = "glo-issue"
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(GLO / "bin" / tool), *arguments],
            cwd=self.workspace,
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )

    def _output(self, *arguments: str, tool: str = "glo-issue") -> str:
        result = self._run(*arguments, tool=tool)
        self.assertEqual(
            result.returncode, 0, (arguments, result.stdout, result.stderr)
        )
        return result.stdout

    def _ids(self, *arguments: str) -> list[str]:
        output = self._output(*arguments)
        if arguments[0] == "query":
            return [json.loads(line)["id"] for line in output.splitlines()]
        return [line.split()[0] for line in output.splitlines()]

    def test_archiving_dependencies_preserves_readiness_and_agent_queues(self) -> None:
        """Closing and archiving a blocker must not block its dependent again."""
        self._issue("complete-1234", plan="accept", status="closed")
        self._issue("deferred-5678", plan="accept", status="icebox")
        self._issue("ready", plan="review")
        self._issue("blocked", plan="review", deps="[deferred-5678]")
        self._issue("missing", plan="review", deps="[absent]")
        self._output("dep", "ready", "1234")
        self.assertIn("deps: [complete-1234]", (self.issues / "ready.md").read_text())
        for issue in ("complete-1234", "deferred-5678"):
            self._output("archive", issue)
        self.assertEqual(self._ids("ready", "-f", "plan=review"), ["ready"])
        self.assertEqual(
            set(self._ids("blocked", "-f", "plan=review")), {"blocked", "missing"}
        )
        self.assertNotIn("## Blockers", self._output("show", "ready"))
        self.assertIn(
            "deferred-5678 [icebox] Title for deferred-5678",
            self._output("show", "blocked"),
        )
        self.assertIn(
            "ready",
            self._output("issue", "ready", "-f", "plan=review", tool="glo-agent"),
        )
        self.assertNotIn("## Blocking", self._output("show", "1234"))

    def test_all_listings_combine_archive_scope_and_attribute_filters(self) -> None:
        """Archive scope must select candidates without hiding dependency records."""
        for archived, prefix in ((False, "active"), (True, "archived")):
            self._issue(
                f"{prefix}-ready", archived=archived, plan="review", deps="[complete]"
            )
            self._issue(
                f"{prefix}-blocked", archived=archived, plan="review", deps="[absent]"
            )
            self._issue(
                f"{prefix}-closed", archived=archived, plan="review", status="closed"
            )
            self._issue(f"{prefix}-other", archived=archived, plan="accept")
        self._issue("complete", archived=True, status="closed", plan="accept")
        kinds = {
            "ls": ["ready", "blocked", "closed"],
            "query": ["ready", "blocked", "closed"],
            "ready": ["ready"],
            "blocked": ["blocked"],
            "closed": ["closed"],
        }
        for command, suffixes in kinds.items():
            for flag, prefixes in (
                ([], ["active"]),
                (["--only-archived"], ["archived"]),
                (["--with-archived"], ["active", "archived"]),
            ):
                with self.subTest(command=command, flag=flag):
                    expected = {
                        f"{prefix}-{suffix}"
                        for prefix in prefixes
                        for suffix in suffixes
                    }
                    self.assertEqual(
                        set(self._ids(command, *flag, "-f", "plan=review")), expected
                    )
        self.assertEqual(
            self._ids(
                "query", "--only-archived", "-f", "plan=review", '.status == "closed"'
            ),
            ["archived-closed"],
        )

    def test_closed_sorts_and_limits_matching_results_across_locations(self) -> None:
        """An archived matching issue must compete for the limit by modification time."""
        for name, archived, timestamp, plan in (
            ("new-unmatched", False, 400, "accept"),
            ("archived-newest", True, 300, "review"),
            ("active-next", False, 200, "review"),
            ("archived-oldest", True, 100, "review"),
        ):
            path = self._issue(name, archived=archived, status="closed", plan=plan)
            os.utime(path, (timestamp, timestamp))
        self.assertEqual(
            self._ids("closed", "--with-archived", "--limit=2", "-f", "plan=review"),
            ["archived-newest", "active-next"],
        )
        self.assertEqual(
            self._ids("closed", "--only-archived", "--limit=1"), ["archived-newest"]
        )
        self.assertEqual(self._ids("closed", "--with-archived", "--limit=0"), [])

    def test_archive_only_workspace_supports_views_and_exact_tree_roots(self) -> None:
        """No active files must not make archived roots or graph context disappear."""
        self._issue(
            "root",
            archived=True,
            status="icebox",
            deps="[dependency]",
            links="[related]",
        )
        self._issue("root-longer", archived=True, status="icebox", parent="root")
        self._issue("dependency", archived=True, status="closed")
        self._issue("related", archived=True, status="closed")
        self.assertEqual(self._ids("ls"), [])
        self.assertEqual(len(self._ids("query", "--only-archived")), 4)
        shown = self._output("show", "root")
        self.assertIn(
            "## Children\n\n- root-longer [icebox] Title for root-longer", shown
        )
        self.assertIn("## Linked\n\n- related [closed] Title for related", shown)
        self.assertIn(
            "parent: root  # Title for root", self._output("show", "root-longer")
        )
        for flags in ([], ["--full"]):
            tree = self._output("dep", "tree", *flags, "root")
            self.assertIn("dependency [closed] Title for dependency", tree)

    def test_cycles_remain_visible_through_archived_iceboxed_issues(self) -> None:
        """Archival must not hide an unresolved cycle; closing an endpoint resolves it."""
        self._issue("first", deps="[second]")
        self._issue("second", status="icebox", deps="[first]")
        self._output("archive", "second")
        cycle = self._output("dep", "cycle")
        self.assertIn("Cycle 1:", cycle)
        self.assertIn("first", cycle)
        self.assertIn("second", cycle)
        self._output("close", "second")
        self.assertEqual(
            self._output("dep", "cycle").strip(), "No dependency cycles found"
        )

    def test_relationship_mutations_use_full_ids_and_keep_archived_bodies(self) -> None:
        """Partial IDs must not leave broken edges or alter lookalike IDs and body text."""
        active = self._issue("active-1234", deps="[target-5678-extra]")
        archived = self._issue("target-5678", archived=True, status="closed")
        body = "\n---\nlinks: [body-example]\ndeps: [body-example]\n"
        archived.write_text(archived.read_text() + body)
        self._output("dep", "1234", "5678")
        self.assertIn("deps: [target-5678-extra, target-5678]", active.read_text())
        self._output("undep", "1234", "5678")
        self.assertIn("deps: [target-5678-extra]", active.read_text())
        self._output("link", "1234", "5678")
        self.assertIn("\nlinks: [target-5678]\n", active.read_text())
        self.assertIn("\nlinks: [active-1234]\n", archived.read_text())
        self._output("unlink", "1234", "5678")
        self.assertIn("\nlinks: []\n", active.read_text())
        self.assertIn("\nlinks: []\n", archived.read_text())
        self.assertTrue(archived.read_text().endswith(body))
        self.assertFalse((self.issues / archived.name).exists())
        self._output("undep", "1234", "target-5678-extra")
        self.assertIn("deps: []", active.read_text())

    def test_archive_moves_preserve_status_bytes_mode_and_modification_time(
        self,
    ) -> None:
        """Archive/unarchive must move the original file without rewriting its history."""
        active = self._issue("movable", status="closed")
        active.chmod(0o640)
        os.utime(active, ns=(1234567890, 1234567890))
        before = (active.read_bytes(), active.stat().st_mode, active.stat().st_mtime_ns)
        archived = self.archive / active.name
        self._output("archive", "movable")
        self._output("archive", "movable")
        self.assertFalse(active.exists())
        self.assertEqual(
            (
                archived.read_bytes(),
                archived.stat().st_mode,
                archived.stat().st_mtime_ns,
            ),
            before,
        )
        self._output("unarchive", "movable")
        self._output("unarchive", "movable")
        self.assertFalse(archived.exists())
        self.assertEqual(
            (active.read_bytes(), active.stat().st_mode, active.stat().st_mtime_ns),
            before,
        )
        self._output("archive", "movable")
        self._output("reopen", "movable")
        self.assertTrue(active.exists())
        self.assertIn("status: open", active.read_text())

    def test_invalid_moves_and_conflicting_scopes_do_not_change_issues(self) -> None:
        """Bad arguments, active statuses and destination conflicts must be harmless."""
        active = self._issue("active")
        running = self._issue("running", status="in_progress")
        duplicate = self._issue("duplicate", status="closed")
        collision = self._issue("duplicate", archived=True, status="icebox")
        snapshots = {
            path: path.read_bytes() for path in (active, running, duplicate, collision)
        }
        for command in (
            ("archive", "active"),
            ("archive", "running"),
            ("archive", "duplicate"),
            ("unarchive", "duplicate"),
            ("archive", "active", "extra"),
        ):
            self.assertNotEqual(self._run(*command).returncode, 0, command)
        for command in ("ls", "query", "closed", "ready", "blocked"):
            result = self._run(command, "--only-archived", "--with-archived")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
        for path, content in snapshots.items():
            self.assertEqual(path.read_bytes(), content)

    def test_lookup_ambiguity_includes_archive_and_partial_ids_are_literal(
        self,
    ) -> None:
        """An archived match must prevent a partial ID from mutating the wrong issue."""
        paths = [
            self._issue("active-shared"),
            self._issue("archived-shared", archived=True),
        ]
        snapshots = [path.read_bytes() for path in paths]
        for pattern in ("shared", "*"):
            self.assertNotEqual(self._run("set", pattern, "plan=accept").returncode, 0)
        self.assertEqual([path.read_bytes() for path in paths], snapshots)

    def test_notes_reconciles_archives_and_retains_dependency_context(self) -> None:
        """Notes maintenance must archive completed work and restore manually resumed work."""
        closed = self._issue("complete", status="closed")
        icebox = self._issue("deferred", status="icebox")
        self._issue("dependent", deps="[complete]")
        self._issue("resumed", archived=True, status="in_progress")
        self._output("precommit", tool="glo-notes")
        for path in (closed, icebox):
            self.assertFalse(path.exists())
            self.assertTrue((self.archive / path.name).exists())
        self.assertTrue((self.issues / "resumed.md").exists())
        self.assertFalse((self.archive / "resumed.md").exists())
        self.assertIn("dependent", self._ids("ready"))
        self.assertIn("Title for dependent", (self.issues / "TITLES.md").read_text())
        self.assertNotIn("Title for complete", (self.issues / "TITLES.md").read_text())
        self._output("unarchive", "complete")
        self._output("precommit", tool="glo-notes")
        self.assertTrue((self.archive / "complete.md").exists())

    def test_notes_refuses_archive_collision_without_overwriting(self) -> None:
        """Notes must use issue move safeguards instead of silently replacing history."""
        paths = [
            self._issue("duplicate", status="closed"),
            self._issue("duplicate", archived=True, status="icebox"),
        ]
        snapshots = [path.read_bytes() for path in paths]
        result = self._run("precommit", tool="glo-notes")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate ID", result.stderr)
        self.assertEqual([path.read_bytes() for path in paths], snapshots)

    def test_notes_requires_explicit_zk_passthrough_and_preserves_arguments(
        self,
    ) -> None:
        """An unmatched zk command must not create a note; the explicit form must work."""
        arguments = (
            "new",
            "--group",
            "wiki",
            "--title",
            "Title with spaces",
            "--no-input",
            "--print-path",
        )
        result = self._run(*arguments, tool="glo-notes")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown glo-notes command", result.stderr)
        self.assertEqual(list((self.workspace / "base/wiki").glob("*.md")), [])
        self._output("zk", *arguments, tool="glo-notes")
        notes = list((self.workspace / "base/wiki").glob("*.md"))
        self.assertEqual(len(notes), 1)
        self.assertIn("Title with spaces", notes[0].read_text())
        self.assertIn(
            "Note: wiki/title-with-spaces.md",
            self._output(
                "zk", "list", "--quiet", "--format", "Note: {{path}}", tool="glo-notes"
            ),
        )
        self.assertIn("glo-notes zk", self._output("--help", tool="glo-notes"))


if __name__ == "__main__":
    unittest.main()
