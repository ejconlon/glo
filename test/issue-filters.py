#!/usr/bin/env python3
"""Exercise attribute filters and updates through the CLI with private fixtures."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


GLO_ROOT = Path(__file__).resolve().parents[1]
ISSUE_COMMAND = GLO_ROOT / "devcontainer/image/files/glo/bin/glo-issue"


class IssueFilterTests(unittest.TestCase):
    """Check issue selection, attribute mutations, dependency context and queries."""

    def setUp(self) -> None:
        """Create an isolated workspace without invoking Git or a devstack."""
        self.temporary = tempfile.TemporaryDirectory(prefix="glo issue filters ")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        (self.workspace / ".git").mkdir()
        self.issues = self.workspace / "base/issue"
        self.issues.mkdir(parents=True)
        self.environment = dict(os.environ, TICKETS_DIR=str(self.issues))
        self.environment.pop("GLO_BASE", None)

    def _issue(self, name: str, **fields: str) -> Path:
        attributes = {
            "id": name,
            "status": "open",
            "deps": "[]",
            "type": "task",
            "priority": "2",
            **fields,
        }
        path = self.issues / f"{name}.md"
        metadata = "\n".join(f"{key}: {value}" for key, value in attributes.items())
        path.write_text(f"---\n{metadata}\n---\n# Title for {name}\n")
        return path

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(ISSUE_COMMAND), *arguments],
            cwd=self.workspace,
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def _output(self, *arguments: str) -> str:
        result = self._run(*arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def _ids(self, *arguments: str) -> list[str]:
        output = self._output(*arguments)
        if arguments[0] == "query":
            return [json.loads(line)["id"] for line in output.splitlines()]
        return [line.split()[0] for line in output.splitlines()]

    def test_custom_attributes_filter_every_listing(self) -> None:
        """A plan filter selects candidates while retaining all dependency states."""
        self._issue("ready", plan="review", deps="[closed-dependency]")
        self._issue("blocked", plan="review", deps="[open-dependency]")
        self._issue("closed", plan="review", status="closed")
        self._issue("closed-dependency", plan="accept", status="closed")
        self._issue("open-dependency", plan="accept")
        self._issue("unplanned")
        expected = {
            "ls": {"ready", "blocked", "closed"},
            "ready": {"ready"},
            "blocked": {"blocked"},
            "closed": {"closed"},
            "query": {"ready", "blocked", "closed"},
        }
        for command, selected in expected.items():
            with self.subTest(command=command):
                self.assertEqual(
                    set(self._ids(command, "--filter", "plan=review")), selected
                )
        blocked = self._output("blocked", "-f", "plan=review")
        self.assertIn("<- [open-dependency]", blocked)

    def test_repeated_filters_require_all_attributes(self) -> None:
        """Multiple flag spellings intersect type, plan and parent selections."""
        self._issue("selected", plan="review", type="epic", parent="root")
        self._issue("other-type", plan="review", parent="root")
        self._issue("other-plan", plan="accept", type="epic", parent="root")
        self._issue("other-parent", plan="review", type="epic", parent="elsewhere")
        self.assertEqual(
            self._ids(
                "ls",
                "-f",
                "plan=review",
                "--filter=type=epic",
                "--filter",
                "parent=root",
            ),
            ["selected"],
        )
        self.assertEqual(self._ids("ls", "-f", "plan=review", "-f", "plan=accept"), [])

    def test_existing_status_assignee_and_tag_options_compose(self) -> None:
        """Legacy switches remain restrictions alongside generic field filters."""
        self._issue("selected", plan="review", assignee="agent", tags="[peal, syntax]")
        self._issue("other-owner", plan="review", assignee="other", tags="[peal]")
        self._issue("other-tag", plan="review", assignee="agent", tags="[backend]")
        self._issue(
            "closed", plan="review", assignee="agent", tags="[peal]", status="closed"
        )
        self._issue("other-plan", plan="accept", assignee="agent", tags="[peal]")
        for options in (
            ("-a", "agent", "-T", "peal"),
            ("--assignee=agent", "--tag=peal"),
        ):
            with self.subTest(options=options):
                self.assertEqual(
                    self._ids("ls", "--status=open", *options, "-f", "plan=review"),
                    ["selected"],
                )

    def test_list_filters_match_whole_members(self) -> None:
        """A tag prefix or one matching tag cannot satisfy two membership filters."""
        self._issue("both", tags="[peal, syntax]", deps="[first, second]")
        self._issue("prefix", tags="[peal-extra, syntax]")
        self._issue("one", tags="[peal]")
        self._issue("empty", tags="[]")
        self.assertEqual(
            self._ids("ls", "-f", "tags=peal", "-f", "tags=syntax"), ["both"]
        )
        self.assertEqual(self._ids("query", "-f", "deps=second"), ["both"])
        self.assertEqual(self._ids("ls", "-f", "tags="), [])

    def test_missing_and_empty_attributes_are_distinct(self) -> None:
        """A missing field cannot match a filter for a present empty scalar."""
        self._issue("empty", assignee="")
        self._issue("missing")
        self._issue("assigned", assignee="agent")
        for command in ("ls", "query"):
            with self.subTest(command=command):
                self.assertEqual(self._ids(command, "-f", "assignee="), ["empty"])
                self.assertEqual(self._ids(command, "-f", "unknown="), [])
        record = json.loads(self._output("query", "-f", "assignee="))
        self.assertEqual(record["assignee"], "")
        self.assertNotIn("assignee:", record)

    def test_values_are_literal_and_split_at_the_first_equals(self) -> None:
        """Spaces, colons, equals and metacharacters survive selection and JSON."""
        value = r'a=b: [x].* "quote" \n $(touch unexpected)'
        self._issue("literal", **{"external-ref": value})
        self._issue("different", **{"external-ref": "a=b"})
        expression = f"external-ref={value}"
        for command in ("ls", "query"):
            with self.subTest(command=command):
                self.assertEqual(self._ids(command, "-f", expression), ["literal"])
        record = json.loads(self._output("query", "-f", expression))
        self.assertEqual(record["external-ref"], value)
        self.assertFalse((self.workspace / "unexpected").exists())

    def test_numeric_looking_and_case_different_values_are_distinct(self) -> None:
        """Exact matching must not coerce 01 to 1 or ignore letter case."""
        self._issue("padded", code="01", plan="review")
        self._issue("plain", code="1", plan="Review")
        self.assertEqual(self._ids("ls", "-f", "code=01"), ["padded"])
        self.assertEqual(self._ids("ls", "-f", "plan=Review"), ["plain"])

    def test_body_metadata_does_not_override_frontmatter(self) -> None:
        """A Markdown example after a horizontal rule is not issue metadata."""
        path = self._issue("actual", plan="review")
        with path.open("a") as stream:
            stream.write("\n---\nplan: accept\nid: forged\n---\n")
        self.assertEqual(self._ids("ls", "-f", "plan=accept"), [])
        self.assertEqual(self._ids("query", "-f", "plan=review"), ["actual"])

    def test_query_combines_attributes_with_existing_jq_expression(self) -> None:
        """The existing jq expression still refines the attribute-selected JSON."""
        self._issue("epic", plan="review", type="epic")
        self._issue("task", plan="review")
        self._issue("accepted", plan="accept", type="epic")
        self.assertEqual(
            self._ids("query", '.type == "epic"', "-f", "plan=review"), ["epic"]
        )

    def test_closed_limit_is_applied_after_filters_without_a_scan_cutoff(self) -> None:
        """Older matches remain visible behind more than 100 newer nonmatches."""
        for index in range(105):
            path = self._issue(f"newer-{index}", status="closed", plan="accept")
            os.utime(path, (3000 + index, 3000 + index))
        for name, timestamp in (("older", 1000), ("latest-match", 2000)):
            path = self._issue(name, status="closed", plan="review")
            os.utime(path, (timestamp, timestamp))
        self.assertEqual(
            self._ids("closed", "--limit=1", "-f", "plan=review"), ["latest-match"]
        )
        self.assertEqual(
            self._ids("closed", "--limit=2", "-f", "plan=review"),
            ["latest-match", "older"],
        )
        self.assertEqual(self._ids("closed", "--limit=0", "-f", "plan=review"), [])

    def test_ready_order_and_blockers_survive_candidate_filtering(self) -> None:
        """Retain priority order and distinguish absent, open and closed blockers."""
        self._issue("first", plan="review", priority="1")
        self._issue("second", plan="review", priority="2", deps="[complete]")
        self._issue("complete", plan="accept", status="closed")
        self._issue("missing", plan="review", deps="[absent]")
        self._issue("iceboxed", plan="accept", status="icebox")
        self._issue("blocked", plan="review", deps="[iceboxed]")
        self.assertEqual(self._ids("ready", "-f", "plan=review"), ["first", "second"])
        self.assertEqual(
            set(self._ids("blocked", "-f", "plan=review")), {"blocked", "missing"}
        )

    def test_malformed_filters_fail_without_listing_issues(self) -> None:
        """Mistyped filters must not silently turn into an unfiltered listing."""
        self._issue("visible")
        for command in ("ls", "ready", "blocked", "closed", "query"):
            for options in (
                ("--filter",),
                ("-f", "plan"),
                ("--filter==review",),
                ("-f", "bad key=review"),
                ("-f", "plan=review\nstatus=open"),
            ):
                with self.subTest(command=command, options=options):
                    result = self._run(command, *options)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("key=value", result.stderr)

    def test_empty_and_unmatched_listings_succeed_without_output(self) -> None:
        """Empty fixtures and zero matches are successful empty results."""
        for command in ("ls", "ready", "blocked", "closed", "query"):
            with self.subTest(command=command, empty=True):
                self.assertEqual(self._output(command, "-f", "plan=review"), "")
        self._issue("accepted", plan="accept")
        for command in ("ls", "ready", "blocked", "closed", "query"):
            with self.subTest(command=command, empty=False):
                self.assertEqual(self._output(command, "-f", "plan=review"), "")

    def test_unfiltered_commands_and_ambient_filter_environment(self) -> None:
        """Existing listings keep their scope and ignore ambient internal variables."""
        self.environment["GLO_ISSUE_FILTERS"] = "plan=review"
        self._issue("open", plan="accept")
        self._issue("closed", status="closed")
        self.assertEqual(set(self._ids("ls")), {"open", "closed"})
        self.assertEqual(set(self._ids("query")), {"open", "closed"})
        self.assertEqual(self._ids("ready"), ["open"])
        self.assertEqual(self._ids("blocked"), [])
        self.assertEqual(self._ids("closed"), ["closed"])

    def test_set_adds_attributes_and_updates_filter_results(self) -> None:
        """Set a new plan through a partial ID, then select its persisted value."""
        self._issue("planned-1234")
        self._issue("untouched-5678", plan="review")
        self._output("set", "1234", "plan=accept", "priority=1")
        self.assertEqual(
            self._ids("ready", "-f", "plan=accept", "-f", "priority=1"),
            ["planned-1234"],
        )
        self._output("set", "1234", "plan=review")
        self.assertEqual(self._ids("ls", "-f", "plan=accept"), [])
        self.assertEqual(
            set(self._ids("query", "-f", "plan=review")),
            {"planned-1234", "untouched-5678"},
        )

    def test_set_preserves_body_file_mode_and_literal_values(self) -> None:
        """Metadata writes cannot replace examples or interpret sed/shell syntax."""
        path = self._issue("literal", plan="review", owner="original")
        front, body = path.read_text().split("\n---\n", 1)
        body += (
            "\nplan: review\nexternal-ref: example\n---\nplan: reject\nNo final newline"
        )
        path.write_text(front + "\n---\n" + body)
        path.chmod(0o640)
        value = r'https://example.com/a/b?x=y=z&name="quoted"\n $(touch unexpected)'
        self._output("set", "literal", "plan=accept", f"external-ref={value}")
        actual_front, actual_body = path.read_bytes().split(b"\n---\n", 1)
        self.assertEqual(actual_body, body.encode())
        self.assertIn(b"owner: original\n", actual_front + b"\n")
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        record = json.loads(self._output("query", "-f", "id=literal"))
        self.assertEqual(record["plan"], "accept")
        self.assertEqual(record["external-ref"], value)
        self.assertFalse((self.workspace / "unexpected").exists())

    def test_set_handles_empty_scalars_and_inline_lists(self) -> None:
        """Clear a scalar and replace a tag list, retaining query/filter behavior."""
        self._issue("tagged", plan="review", tags="[old]", assignee="agent")
        self._output("set", "tagged", "plan=", "tags=[peal, syntax]", "assignee=")
        record = json.loads(self._output("query", "-f", "id=tagged"))
        self.assertEqual(record["plan"], "")
        self.assertEqual(record["assignee"], "")
        self.assertEqual(record["tags"], ["peal", "syntax"])
        self.assertEqual(
            self._ids("ls", "-f", "plan=", "-f", "tags=syntax"), ["tagged"]
        )
        self.assertEqual(self._ids("ls", "-f", "tags=old"), [])

    def test_invalid_set_batch_never_partially_changes_the_issue(self) -> None:
        """A later bad assignment cannot leave an earlier plan update behind."""
        path = self._issue("unchanged", plan="review")
        original = path.read_bytes()
        for invalid in (
            "plan",
            "=accept",
            "bad key=value",
            "plan=accept\nstatus=closed",
            "plan=accept\rstatus=closed",
            "status=unknown",
            "id=replaced",
            "deps=[other]",
            "links=[other]",
        ):
            with self.subTest(invalid=invalid):
                result = self._run("set", "unchanged", "plan=accept", invalid)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(self.issues.glob("*.tmp.*")), [])

    def test_set_archive_metadata_and_status_lifecycle(self) -> None:
        """Editing archived metadata keeps it archived until an active status is set."""
        active = self._issue("archived-1234", plan="review", status="icebox")
        archive = self.issues / "archive"
        archive.mkdir()
        archived = archive / active.name
        active.rename(archived)
        self._output("set", "1234", "plan=accept")
        self.assertFalse(active.exists())
        self.assertIn("\nplan: accept\n", archived.read_text())
        self._output("set", "1234", "status=open", "priority=1")
        self.assertFalse(archived.exists())
        self.assertTrue(active.exists())
        self.assertEqual(self._ids("ready", "-f", "plan=accept"), ["archived-1234"])
        self._output("set", "1234", "status=closed")
        self.assertEqual(self._ids("ready", "-f", "plan=accept"), [])
        self.assertEqual(self._ids("closed", "-f", "plan=accept"), ["archived-1234"])

    def test_set_missing_or_ambiguous_issue_does_not_modify_candidates(self) -> None:
        """Partial IDs must resolve uniquely before any document is written."""
        paths = [self._issue("first-shared"), self._issue("second-shared")]
        original = [path.read_bytes() for path in paths]
        for issue in ("shared", "nonexistent"):
            with self.subTest(issue=issue):
                result = self._run("set", issue, "plan=accept")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual([path.read_bytes() for path in paths], original)

    def test_set_rejects_incomplete_frontmatter_without_replacing_the_file(
        self,
    ) -> None:
        """A malformed or empty issue cannot be replaced by partially rendered data."""
        path = self.issues / "broken.md"
        for original in (b"", b"# Missing metadata\n", b"---\nplan: review\n"):
            with self.subTest(original=original):
                path.write_bytes(original)
                result = self._run("set", "broken", "plan=accept")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(list(self.issues.glob("*.tmp.*")), [])

    def test_set_repeated_key_has_one_final_value(self) -> None:
        """Repeated assignments must not create conflicting frontmatter entries."""
        path = self._issue("repeated", plan="create")
        self._output("set", "repeated", "plan=review", "plan=accept")
        self.assertEqual(path.read_text().count("\nplan:"), 1)
        self.assertEqual(self._ids("query", "-f", "plan=accept"), ["repeated"])

    def test_existing_field_commands_preserve_literal_values_and_body(self) -> None:
        """Legacy status and assignee commands use the same safe metadata writer."""
        path = self._issue("legacy", assignee="original")
        front, body = path.read_text().split("\n---\n", 1)
        body += "\nstatus: open\nassignee: example\n"
        path.write_text(front + "\n---\n" + body)
        self._output("set-assignee", "legacy", r"Team/Agent & Reviewer\name")
        self._output("status", "legacy", "in_progress")
        record = json.loads(self._output("query", "-f", "id=legacy"))
        self.assertEqual(record["assignee"], r"Team/Agent & Reviewer\name")
        self.assertEqual(record["status"], "in_progress")
        self.assertEqual(path.read_text().split("\n---\n", 1)[1], body)


if __name__ == "__main__":
    unittest.main()
