#!/usr/bin/env python3
"""Exercise the board and structured issue queries with private files and real PTYs."""

import fcntl
import json
import os
import pty
import re
import select
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import time
import unittest
from pathlib import Path

GLO_ROOT = Path(__file__).resolve().parents[1]
BIN = GLO_ROOT / "devcontainer/image/files/glo/bin"


class Terminal:
    """Drive a real terminal process and inspect its output and saved terminal mode."""

    def __init__(self, workspace: Path, environment: dict[str, str], *args: str):
        self.master, self.slave = pty.openpty()
        self.original = termios.tcgetattr(self.slave)
        self.pending = b""
        self.output = b""
        self.resize(30, 120)
        self.process = subprocess.Popen(
            [str(BIN / "glo"), "board", *args],
            cwd=workspace,
            env=environment,
            stdin=self.slave,
            stdout=self.slave,
            stderr=self.slave,
        )

    def resize(self, rows: int, columns: int) -> None:
        """Change terminal geometry and notify an already running application."""
        fcntl.ioctl(
            self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0)
        )
        if hasattr(self, "process"):
            self.process.send_signal(signal.SIGWINCH)

    def expect(self, text: str) -> str:
        """Wait for fresh output containing text, failing with the terminal transcript."""
        target = text.encode()
        deadline = time.monotonic() + 5
        while target not in self.pending:
            if time.monotonic() > deadline:
                raise AssertionError(
                    f"Missing {text!r}: {self.output.decode(errors='replace')[-6000:]}"
                )
            if select.select([self.master], [], [], 0.05)[0]:
                chunk = os.read(self.master, 65536)
                self.pending += chunk
                self.output += chunk
        preceding, self.pending = self.pending.split(target, 1)
        return preceding.decode(errors="replace")

    def frame(self, marker: str) -> str:
        """Read through a frame's final marker and return only its last cleared screen."""
        return self.expect(marker).rsplit("\x1b[2J", 1)[-1]

    def send(self, text: str) -> None:
        """Send literal keyboard bytes."""
        os.write(self.master, text.encode())

    def finish(self, expected: int = 0) -> None:
        """Require process termination and exact terminal-mode restoration."""
        code = self.process.wait(timeout=5)
        if code != expected:
            raise AssertionError(f"Exit {code}, expected {expected}: {self.output!r}")
        if termios.tcgetattr(self.slave) != self.original:
            raise AssertionError("The board did not restore terminal settings")

    def close(self) -> None:
        """Reap a failed test process before releasing its terminal."""
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        os.close(self.master)
        os.close(self.slave)


class BoardTests(unittest.TestCase):
    """Check observable mutations, display behavior and lifecycle cleanup."""

    def setUp(self) -> None:
        """Own every issue and notebook used by the CLI subprocesses."""
        temporary = tempfile.TemporaryDirectory(prefix="glo board ")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        (self.workspace / ".git").mkdir()
        self.issues = self.workspace / "notebook with spaces/issue"
        self.issues.mkdir(parents=True)
        self.environment = dict(
            os.environ,
            GLO_BASE="notebook with spaces",
            TERM="xterm-256color",
            LESS="-X",
            LESSHISTFILE="/dev/null",
            LESSKEYIN="/dev/null",
        )
        for key in (
            "TICKETS_DIR",
            "AGENT_NAME",
            "ZK_NOTEBOOK_DIR",
            "PAGER",
            "LESSOPEN",
            "LESSCLOSE",
        ):
            self.environment.pop(key, None)
        self.snapshots = self.workspace / "snapshots"
        self.snapshots.mkdir()
        self.environment["TMPDIR"] = str(self.snapshots)
        self.environment["PAGER"] = "less"

    def _issue(
        self,
        name: str,
        title: str = "A useful title",
        archived: bool = False,
        **fields: str,
    ) -> Path:
        metadata = {
            "id": name,
            "status": "open",
            "priority": "2",
            "type": "task",
            "deps": "[]",
            **fields,
        }
        folder = self.issues / "archive" if archived else self.issues
        folder.mkdir(exist_ok=True)
        path = folder / f"{name}.md"
        path.write_text(
            "---\n"
            + "".join(f"{k}: {v}\n" for k, v in metadata.items())
            + f"---\n# {title}\n\nDescription here.\n"
        )
        return path

    def _run(self, command: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(BIN / command), *args],
            cwd=self.workspace,
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def _query(self, *args: str) -> list[dict]:
        result = self._run("glo-issue", "query", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def _terminal(
        self,
        *,
        group: str | None = None,
        columns: tuple[str, ...] = (),
        filters: tuple[str, ...] = (),
        archive: str = "active",
        icebox: bool = False,
    ) -> Terminal:
        terminal = Terminal(self.workspace, self.environment)
        self.addCleanup(terminal.close)
        terminal.expect("glo-board |")
        settings = []
        if group is not None:
            settings.append("g" + group + "\r")
        settings.extend("+" + value + "\r" for value in columns)
        settings.extend("f" + value + "\r" for value in filters)
        settings.extend(
            "v" for _ in range({"active": 0, "all": 1, "archived": 2}[archive])
        )
        if icebox:
            settings.append("i")
        for keys in settings:
            terminal.send(keys)
            terminal.expect("View updated")
        if settings:
            terminal.send("r")
            terminal.expect("glo-board |")
        return terminal

    def test_query_details_preserve_legacy_and_filter_attributes(self) -> None:
        """Titles and storage metadata must not collide with custom frontmatter fields."""
        title = 'Quotes " and backslash \\ and tab\t and ESC\x1b and NUL\x00 and café'
        self._issue(
            "active", title=title, plan="review", archived=False, attributes="literal"
        )
        self._issue("old", archived=True, status="closed", plan="review")
        self._issue("skip", plan="accept")
        legacy = self._query("-f", "id=active")[0]
        detailed = self._query("--details", "-f", "id=active")[0]
        self.assertEqual(
            detailed, {"attributes": legacy, "title": title, "archived": False}
        )
        both = self._query(
            "--with-archived", "--details", "-f", "plan=review", '.status == "closed"'
        )
        self.assertEqual([entry["attributes"]["id"] for entry in both], ["old"])
        self.assertTrue(both[0]["archived"])
        self.assertEqual(self._query("--details", "--only-archived"), both)

    def test_query_without_heading_and_empty_results(self) -> None:
        """A missing title yields an empty string without leaking the preceding title."""
        self._issue("aaa")
        self._issue("zzz").write_text("---\nid: zzz\nstatus: open\n---\nNo heading\n")
        self.assertEqual(self._query("--details")[-1]["title"], "")
        self.assertEqual(self._query("--details", "-f", "id=absent"), [])

    def test_move_and_filtered_disappearance(self) -> None:
        """Moving the selected issue changes storage and removes it from the current filter."""
        self._issue("target")
        terminal = self._terminal(filters=("status=open",))
        terminal.send("m")
        terminal.expect("Move status to open")
        terminal.send("\x1b[C\r")
        terminal.expect("open (0)")
        terminal.expect("Updated target")
        self.assertEqual(self._query()[0]["status"], "in_progress")
        terminal.send("q")
        terminal.finish()

    def test_icebox_toggle_and_custom_columns_do_not_leak_hidden_cards(self) -> None:
        """Iceboxed cards stay out of Other until explicitly requested, without edits."""
        frozen = self._issue("cold", title="Frozen card", status="icebox")
        active = self._issue("live", title="Active card")
        before = {path: path.read_bytes() for path in (frozen, active)}
        terminal = self._terminal()
        frame = terminal.frame("q quit")
        self.assertIn("Active card", frame)
        self.assertNotIn("Frozen card", frame)
        self.assertNotIn("icebox (", frame)
        self.assertNotIn("Other (", frame)
        for keys, visible, other in (
            ("i", True, False),
            ("i", False, False),
            ("+closed\r", False, True),
            ("+icebox\r", True, True),
            ("i", False, True),
            ("C", False, False),
        ):
            with self.subTest(keys=keys):
                terminal.send(keys)
                frame = terminal.frame("View updated")
                self.assertEqual("Frozen card" in frame, visible)
                self.assertEqual("icebox (1)" in frame, visible)
                self.assertEqual("Other (1)" in frame, other)
                self.assertIn("Active card", frame)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        terminal.send("q")
        terminal.finish()

    def test_filters_combine_with_archive_scope_and_clear_in_session(self) -> None:
        """Keyboard filters use AND across each archive scope, and clearing restores cards."""
        self._issue("core", title="Core task", team="core")
        self._issue("tools", title="Tools task", team="tools")
        self._issue("epic", title="Core epic", team="core", type="epic")
        self._issue(
            "past", title="Past task", team="core", archived=True, status="closed"
        )
        before = self._query("--with-archived")
        terminal = self._terminal()
        terminal.frame("q quit")
        for keys, visible in (
            ("fteam=core\r", ("Core task", "Core epic")),
            ("ftype=task\r", ("Core task",)),
            ("v", ("Core task", "Past task")),
            ("v", ("Past task",)),
            ("v", ("Core task",)),
            ("F", ("Core task", "Core epic", "Tools task")),
        ):
            with self.subTest(keys=keys, visible=visible):
                terminal.send(keys)
                frame = terminal.frame("View updated")
                for title in ("Core task", "Core epic", "Tools task", "Past task"):
                    self.assertEqual(title in frame, title in visible, frame)
        self.assertEqual(self._query("--with-archived"), before)
        terminal.send("q")
        terminal.finish()

    def test_group_change_resets_columns_keeps_filters_and_cancel_keeps_view(
        self,
    ) -> None:
        """Switching grouping clears obsolete destinations without losing the chosen filter."""
        self._issue("target", title="Chosen task", plan="review", team="core")
        self._issue("skip", title="Skipped task", plan="review", team="tools")
        terminal = self._terminal(filters=("team=core",), columns=("closed",))
        terminal.frame("Refreshed")
        terminal.send("gplan\r")
        frame = terminal.frame("View updated")
        self.assertIn("review (1)", frame)
        self.assertIn("Chosen task", frame)
        self.assertNotIn("Skipped task", frame)
        self.assertNotIn("closed (", frame)
        terminal.send("g")
        terminal.expect("Group by field")
        terminal.send("\x1b")
        terminal.frame("Cancelled")
        terminal.send("m")
        terminal.expect("Move plan to review")
        terminal.send("\x1b")
        terminal.frame("Cancelled")
        terminal.send("g\r")
        frame = terminal.frame("View updated")
        self.assertIn("open (1)", frame)
        self.assertNotIn("Skipped task", frame)
        terminal.send("q")
        terminal.finish()

    def test_icebox_destination_and_hidden_status_update(self) -> None:
        """Icebox can receive a move when shown, and hidden iceboxed cards can be recovered."""
        self._issue("target", title="Moving card")
        terminal = self._terminal(icebox=True)
        terminal.frame("Refreshed")
        terminal.send("mh\r")
        terminal.frame("Updated target")
        self.assertEqual(self._query()[0]["status"], "icebox")
        terminal.send("i")
        frame = terminal.frame("View updated")
        self.assertNotIn("Moving card", frame)
        terminal.send("i")
        frame = terminal.frame("View updated")
        self.assertIn("Moving card", frame)
        terminal.send("ml\r")
        terminal.frame("Updated target")
        terminal.send("i")
        terminal.frame("View updated")
        terminal.send("sstatus=icebox\r")
        frame = terminal.frame("Updated target")
        self.assertNotIn("Moving card", frame)
        self.assertEqual(self._query()[0]["status"], "icebox")
        terminal.send("i")
        frame = terminal.frame("View updated")
        self.assertIn("Moving card", frame)
        terminal.send("q")
        terminal.finish()

    def test_compact_cards_wrap_three_lines_and_keep_full_action_ids(self) -> None:
        """Cards wrap at word boundaries, while duplicate short suffixes cannot redirect edits."""
        first = "first-long-filename-ab12"
        second = "second-long-filename-ab12"
        self._issue(
            first,
            title="Fix old task links across notebooks safely for all users everywhere",
            priority="1",
        )
        self._issue(second, title="Other card")
        terminal = self._terminal(icebox=True)
        terminal.expect("ab12 P1 Fix old task links")
        terminal.expect("        across notebooks")
        terminal.expect("        safely for all users…")
        terminal.expect("ab12 P2 Other card")
        self.assertNotIn(first.encode(), terminal.output)
        self.assertNotIn(second.encode(), terminal.output)
        terminal.resize(30, 80)
        terminal.expect("ab12 P1 Fix old task links across")
        terminal.expect("        notebooks safely for all users")
        terminal.expect("        everywhere")
        terminal.send("splan=accept\r")
        terminal.expect("Updated " + first)
        accepted = self._query("-f", "plan=accept")
        self.assertEqual([record["id"] for record in accepted], [first])
        terminal.send("q")
        terminal.finish()

    def test_plan_move_preserves_status_and_cancel_is_read_only(self) -> None:
        """Attribute moves target the selected field; Escape cannot accidentally commit a move."""
        path = self._issue("target", plan="review")
        before = path.read_bytes()
        terminal = self._terminal(group="plan")
        terminal.send("m")
        terminal.expect("Move plan to review")
        terminal.send("\x1b")
        terminal.expect("Cancelled")
        self.assertEqual(path.read_bytes(), before)
        terminal.send("mll\r")
        terminal.expect("Updated target")
        record = self._query()[0]
        self.assertEqual((record["plan"], record["status"]), ("accept", "open"))
        terminal.send("q")
        terminal.finish()

    def test_archive_error_then_archive_and_unarchive(self) -> None:
        """Backend eligibility errors stay visible; confirmed valid actions move real files."""
        self._issue("target")
        terminal = self._terminal(archive="all")
        terminal.send("a")
        terminal.expect("archive target?")
        terminal.send("y\r")
        terminal.expect("only closed or iceboxed")
        self.assertTrue((self.issues / "target.md").exists())
        terminal.send("sstatus=closed\r")
        terminal.expect("Updated target")
        terminal.send("a")
        terminal.expect("archive target?")
        terminal.send("y\r")
        terminal.expect("archive: target")
        self.assertTrue((self.issues / "archive/target.md").exists())
        terminal.send("a")
        terminal.expect("unarchive target?")
        terminal.send("y\r")
        terminal.expect("unarchive: target")
        self.assertTrue((self.issues / "target.md").exists())
        terminal.send("q")
        terminal.finish()

    def test_archived_status_move_restores_storage(self) -> None:
        """Moving archived closed work to open delegates the backend restore rule."""
        self._issue("target", archived=True, status="closed")
        terminal = self._terminal(archive="archived")
        terminal.send("llm")
        terminal.expect("Move status to closed")
        terminal.send("hh\r")
        terminal.expect("Updated target")
        self.assertTrue((self.issues / "target.md").exists())
        self.assertEqual(self._query()[0]["status"], "open")
        terminal.send("q")
        terminal.finish()

    def test_custom_columns_empty_destinations_and_unassigned(self) -> None:
        """Explicit empty destinations work and unmatched or missing values remain reachable."""
        self._issue("one", team="old")
        self._issue("two")
        terminal = self._terminal(group="team", columns=("new",))
        terminal.expect("new (0)")
        terminal.expect("Unassigned (1)")
        terminal.expect("Other (1)")
        terminal.send("llm")
        terminal.expect("Move team to Other")
        terminal.send("l\r")
        terminal.expect("Updated one")
        self.assertEqual(self._query("-f", "id=one")[0]["team"], "new")
        terminal.send("q")
        terminal.finish()

    def test_creation_and_literal_attribute_prompt(self) -> None:
        """User input is data even when it contains executable shell syntax."""
        terminal = self._terminal()
        terminal.send("n")
        terminal.expect("New title:")
        title = "--literal $(touch INJECTED) `title` café"
        terminal.send(title + "\r")
        terminal.expect("open (1)")
        terminal.send("s")
        terminal.expect("Set key=value:")
        terminal.send("plan=$(touch INJECTED)\r")
        terminal.expect("Updated")
        self.assertEqual(self._query()[0]["plan"], "$(touch INJECTED)")
        self.assertEqual(self._query("--details")[0]["title"], title)
        self.assertFalse((self.workspace / "INJECTED").exists())
        terminal.send("q")
        terminal.finish()

    def test_pager_help_resize_and_signal_cleanup(self) -> None:
        """External control characters cannot execute terminal commands; resize and signals restore state."""
        self._issue("target", title="Safe\x1b]2;INJECTED\x07 title")
        terminal = self._terminal()
        terminal.send("\r")
        terminal.expect("Description here.")
        self.assertNotIn(b"\x1b]2;INJECTED", terminal.output)
        terminal.expect("(END)")
        terminal.send("q")
        terminal.expect("Pager closed")
        self.assertEqual(list(self.snapshots.iterdir()), [])
        terminal.resize(12, 32)
        terminal.expect("open (1)")
        terminal.resize(4, 16)
        terminal.expect("Resize terminal")
        terminal.resize(30, 120)
        terminal.send("?")
        terminal.expect("Usage: glo-board")
        terminal.process.send_signal(signal.SIGTERM)
        terminal.finish(143)

    def test_editor_handoff_and_refresh(self) -> None:
        """An external editor gets restored tty settings and its changes appear after returning."""
        self._issue("target")
        editor = self.workspace / "editor"
        editor.write_text(
            '#!/usr/bin/env bash\nstty -a > editor-mode\nprintf "\\nEdited body.\\n" >> "$1"\n'
        )
        editor.chmod(0o755)
        self.environment["EDITOR"] = str(editor)
        terminal = self._terminal()
        terminal.send("e")
        terminal.expect("Editor closed")
        self.assertIn("Edited body.", (self.issues / "target.md").read_text())
        mode = (self.workspace / "editor-mode").read_text()
        self.assertNotIn("-icanon", mode)
        self.assertNotIn("-echo ", mode)
        terminal.send("\r")
        terminal.expect("Edited body.")
        terminal.send("q")
        terminal.expect("open (1)")
        terminal.send("q")
        terminal.finish()

    def test_copy_full_selected_id_and_clipboard_failures(self) -> None:
        """Copy exact selected IDs; unavailable clipboards must leave the board usable."""
        first = self._issue("first-1234")
        second = self._issue("second-1234")
        before = {path: path.read_bytes() for path in (first, second)}
        tools = self.workspace / "clipboard-tools"
        tools.mkdir()
        for command in (
            "bash",
            "dirname",
            "readlink",
            "jq",
            "stty",
            "tput",
            "awk",
            "cat",
        ):
            executable = shutil.which(command)
            self.assertIsNotNone(executable, command)
            (tools / command).symlink_to(executable)
        self.environment["PATH"] = str(tools)
        for platform, command, outcome in (
            ("Linux", "wl-copy", "success"),
            ("Darwin", "pbcopy", "success"),
            ("Linux", "wl-copy", "failure"),
            ("Darwin", "pbcopy", "failure"),
            ("Linux", "wl-copy", "missing"),
            ("Darwin", "pbcopy", "missing"),
            ("FreeBSD", "", "unsupported"),
        ):
            with self.subTest(platform=platform, outcome=outcome):
                uname = tools / "uname"
                uname.write_text(f"#!/usr/bin/env bash\nprintf '%s\\n' {platform}\n")
                uname.chmod(0o755)
                for utility in ("wl-copy", "pbcopy"):
                    capture = self.workspace / f"copied-{utility}"
                    capture.unlink(missing_ok=True)
                    script = tools / utility
                    script.unlink(missing_ok=True)
                    if outcome == "missing" and utility == command:
                        continue
                    script.write_text(
                        f"#!/usr/bin/env bash\ncat > copied-{utility}\n"
                        "printf 'CLIPBOARD_STDOUT\\n'\n"
                        "printf '\\033]2;CLIPBOARD_STDERR\\007' >&2\n"
                        f"exit {7 if outcome == 'failure' else 0}\n"
                    )
                    script.chmod(0o755)
                terminal = self._terminal()
                terminal.frame("q quit")
                terminal.send("jc")
                if outcome == "success":
                    status = "Copied issue ID: second-1234"
                elif outcome == "failure":
                    status = f"Copy failed: {command} (exit 7)"
                elif outcome == "missing":
                    status = f"Copy failed: {command} not found"
                else:
                    status = "Copy failed: unsupported platform FreeBSD"
                frame = terminal.frame(status)
                self.assertIn("\x1b[30;1H", frame)
                for utility in ("wl-copy", "pbcopy"):
                    capture = self.workspace / f"copied-{utility}"
                    if utility == command and outcome in ("success", "failure"):
                        self.assertEqual(capture.read_bytes(), b"second-1234")
                    else:
                        self.assertFalse(capture.exists())
                terminal.send("lc")
                terminal.frame("No issue selected")
                terminal.send("hr")
                terminal.frame("Refreshed")
                self.assertNotIn(b"CLIPBOARD_STDOUT", terminal.output)
                self.assertNotIn(b"CLIPBOARD_STDERR", terminal.output)
                terminal.send("q")
                terminal.finish()
        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_invalid_group_retains_current_view(self) -> None:
        """An unsupported list grouping leaves the previous board usable."""
        self._issue("target", teams="[a, b]")
        terminal = self._terminal()
        terminal.send("gteams\r")
        terminal.expect("grouping requires a scalar field")
        terminal.send("splan=accept\r")
        terminal.expect("Updated target")
        self.assertEqual(self._query()[0]["plan"], "accept")
        terminal.send("q")
        terminal.finish()

    def test_invalid_filter_keeps_previous_filter_after_refresh(self) -> None:
        """A rejected filter must not poison future refreshes or clear existing filters."""
        self._issue("target", title="Chosen card")
        self._issue("skip", title="Skipped card")
        terminal = self._terminal(filters=("id=target",))
        terminal.frame("Refreshed")
        terminal.send("finvalid\r")
        terminal.expect("invalid filter")
        terminal.send("r")
        frame = terminal.frame("Refreshed")
        self.assertIn("Chosen card", frame)
        self.assertNotIn("Skipped card", frame)
        terminal.send("F")
        frame = terminal.frame("View updated")
        self.assertIn("Chosen card", frame)
        self.assertIn("Skipped card", frame)
        terminal.send("q")
        terminal.finish()

    def test_help_and_nonterminal_error(self) -> None:
        """Help works in scripts; normal operation rejects pipes without terminal escape output."""
        self.assertEqual(self._run("glo", "board", "--help").returncode, 0)
        result = self._run("glo-board")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("interactive terminal", result.stderr)
        self.assertNotIn("\x1b", result.stdout)
        for args in (("--group-by", "plan"), ("--with-archived",)):
            result = self._run("glo-board", *args)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("keyboard controls", result.stderr)
        for args in (
            ("--wrap-width",),
            ("--wrap-width=-1",),
            ("--wrap-width=invalid",),
            ("--wrap-width=",),
            ("--wrap-width=999999999999999999999",),
        ):
            result = self._run("glo-board", *args)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("nonnegative integer", result.stderr)
            self.assertNotIn("\x1b", result.stdout)

    def test_notebook_override_from_nested_working_directory(self) -> None:
        """Relative GLO_BASE resolves from the workspace; an absolute value selects the same notebook."""
        self._issue("selected", title="Chosen notebook")
        nested = self.workspace / "lib/nested"
        nested.mkdir(parents=True)
        for base in ("notebook with spaces", str(self.issues.parent)):
            with self.subTest(base=base):
                environment = dict(self.environment, GLO_BASE=base)
                terminal = Terminal(nested, environment)
                self.addCleanup(terminal.close)
                terminal.expect("Chosen notebook")
                terminal.send("q")
                terminal.finish()

    def test_parent_links_are_canonical_and_do_not_block_children(self) -> None:
        """Parent membership works across archives without adding prerequisite edges."""
        self._issue("epic-1234", type="epic", archived=True, status="icebox")
        self._issue("prerequisite", status="closed")
        self._issue("child", deps="[prerequisite]")
        result = self._run("glo-issue", "set", "child", "parent=1234")
        self.assertEqual(result.returncode, 0, result.stderr)
        child = self._query("-f", "id=child")[0]
        self.assertEqual(child["parent"], "epic-1234")
        self.assertEqual(child["deps"], ["prerequisite"])
        self.assertIn("child", self._run("glo-issue", "ready").stdout)
        created = self._run("glo-issue", "create", "New child", "--parent", "1234")
        self.assertEqual(created.returncode, 0, created.stderr)
        new = self._query("-f", "id=" + created.stdout.strip())[0]
        self.assertEqual(new["parent"], "epic-1234")
        self.assertEqual(new["deps"], [])
        self.assertIn("child", self._run("glo-issue", "show", "epic-1234").stdout)

    def test_invalid_parent_update_is_atomic_and_cycles_are_rejected(self) -> None:
        """Bad membership cannot partially update attributes or create cyclic ancestry."""
        root = self._issue("root", type="epic")
        self._issue("child", parent="root")
        self._issue("grandchild", parent="child")
        original = root.read_bytes()
        for parent in ("missing", "root", "grandchild"):
            with self.subTest(parent=parent):
                result = self._run(
                    "glo-issue", "set", "root", "priority=0", "parent=" + parent
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(root.read_bytes(), original)
        before = set(self.issues.glob("*.md"))
        result = self._run("glo-issue", "create", "Invalid child", "--parent", "absent")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(set(self.issues.glob("*.md")), before)
        self.assertEqual(
            self._run("glo-issue", "set", "child", "parent=").returncode, 0
        )
        self.assertEqual(self._query("-f", "id=child")[0]["parent"], "")

    def test_epic_groups_use_parent_not_dependencies_despite_filters(self) -> None:
        """Filtered-out and archived epics label their children; a dependency does not imply membership."""
        self._issue(
            "alpha", title="Alpha epic", type="epic", archived=True, status="closed"
        )
        self._issue("beta", title="Beta epic", type="epic")
        self._issue("first", title="First child", parent="alpha", priority="4")
        self._issue(
            "second", title="Second child", parent="beta", priority="0", deps="[first]"
        )
        self._issue("standalone", title="Standalone task", deps="[alpha]", priority="0")
        terminal = self._terminal(filters=("type=task",))
        terminal.expect("Alpha epic")
        terminal.expect("First child")
        terminal.expect("Beta epic")
        terminal.expect("Second child")
        terminal.expect("No epic")
        terminal.expect("Standalone task")
        terminal.send("sparent=beta\r")
        terminal.expect("Updated first")
        self.assertEqual(self._query("-f", "id=first")[0]["parent"], "beta")
        self.assertEqual(self._query("-f", "id=second")[0]["deps"], ["first"])
        terminal.send("q")
        terminal.finish()

    def test_epic_group_follows_nested_parent_and_survives_broken_metadata(
        self,
    ) -> None:
        """Follow parent ancestry without hanging on manually edited cycles."""
        self._issue(
            "epic", title="Nested epic", type="epic", archived=True, status="closed"
        )
        self._issue("parent", parent="epic")
        child = self._issue("child", parent="parent")
        terminal = self._terminal(filters=("id=child",))
        terminal.expect("Nested epic")
        child.write_text(child.read_text().replace("parent: parent", "parent: child"))
        terminal.send("r")
        terminal.expect("Parent cycle: child")
        terminal.send("q")
        terminal.finish()

    def test_priority_order_refresh_and_deleted_selection(self) -> None:
        """Selection follows priority ordering and survives external changes or deletion."""
        self._issue("low", priority="4", team="zebra")
        urgent = self._issue("urgent", priority="0", team="zebra")
        terminal = self._terminal(group="team")
        terminal.send("splan=accept\r")
        terminal.expect("Updated urgent")
        self.assertEqual(self._query("-f", "plan=accept")[0]["id"], "urgent")
        self._issue("earlier", priority="0", team="apple")
        terminal.send("r")
        terminal.expect("apple (1)")
        terminal.expect("Refreshed")
        terminal.send("\r")
        terminal.expect("id: urgent")
        terminal.send("q")
        terminal.expect("zebra (2)")
        urgent.unlink()
        terminal.send("r")
        terminal.expect("zebra (1)")
        terminal.send("splan=review\r")
        terminal.expect("Updated low")
        self.assertEqual(self._query("-f", "plan=review")[0]["id"], "low")
        terminal.process.send_signal(signal.SIGINT)
        terminal.finish(130)

    def test_less_pager_searches_full_details(self) -> None:
        """The real less pager can search content beyond the first screen."""
        path = self._issue("target")
        with path.open("a") as stream:
            stream.write("long line " * 30 + "END OF BODY\n")
        terminal = self._terminal()
        terminal.resize(12, 32)
        terminal.send("\r")
        terminal.expect("id: target")
        terminal.send("/END OF BODY\r")
        terminal.expect("END OF BODY")
        terminal.expect("(END)")
        terminal.send("q")
        terminal.expect("open (1)")
        terminal.send("q")
        terminal.finish()

    def test_default_bat_and_less_fallback(self) -> None:
        """Default and custom widths retain words; auto and narrow terminals use available space."""
        path = self._issue("target")
        paragraph = (
            "Alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
            "mike november oscar papa quebec romeo sierra tango uniform victor whiskey."
        )
        with path.open("a") as stream:
            stream.write("\nWORDWRAP_BEGIN\n" + paragraph + "\nWORDWRAP_END\n")
        config = self.workspace / "bat.conf"
        config.write_text("--wrap=character\n--style=numbers\n")
        for with_bat in (False, True):
            with self.subTest(bat_available=with_bat):
                tools = self.workspace / ("with-bat" if with_bat else "without-bat")
                tools.mkdir()
                commands = [
                    "bash",
                    "dirname",
                    "readlink",
                    "jq",
                    "stty",
                    "tput",
                    "awk",
                    "cat",
                    "basename",
                    "mktemp",
                    "rm",
                    "less",
                ]
                if with_bat:
                    commands.append("bat")
                for command in commands:
                    executable = shutil.which(command)
                    self.assertIsNotNone(executable, command)
                    (tools / command).symlink_to(executable)
                environment = dict(
                    self.environment,
                    PATH=str(tools),
                    BAT_CONFIG_PATH=str(config),
                    BAT_PAGER="less -RS",
                    BAT_STYLE="header",
                    LESS="-XS",
                    LESS_COLUMNS="20",
                )
                environment.pop("PAGER")
                for args, columns, expected_width in (
                    ((), 180, 120),
                    (("--wrap-width", "80"), 180, 80),
                    (("--wrap-width=0",), 180, 180),
                    (("--wrap-width", "00080"), 48, 48),
                ):
                    with self.subTest(args=args, columns=columns):
                        terminal = Terminal(self.workspace, environment, *args)
                        self.addCleanup(terminal.close)
                        terminal.resize(40, columns)
                        terminal.expect("glo-board |")
                        terminal.send("\r")
                        terminal.expect("WORDWRAP_BEGIN")
                        rendered = terminal.expect("WORDWRAP_END")
                        plain = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", rendered)
                        # less forces auto-wrap after a full row with space/backspace.
                        plain = plain.replace(" \b", "\n")
                        lines = [
                            line.strip() for line in plain.splitlines() if line.strip()
                        ]
                        self.assertTrue(
                            all(len(line) <= expected_width for line in lines), lines
                        )
                        self.assertEqual(" ".join(lines), paragraph)
                        # The first line should use the requested width, not an ambient
                        # override or a stale width left over from the board's rendering.
                        first = lines[0]
                        if len(lines) > 1:
                            self.assertGreater(
                                len(first) + 1 + len(lines[1].split()[0]),
                                expected_width,
                            )
                        else:
                            self.assertLessEqual(len(paragraph), expected_width)
                        terminal.expect("(END)")
                        terminal.send("q")
                        terminal.expect("Pager closed")
                        self.assertEqual(list(self.snapshots.iterdir()), [])
                        terminal.send("q")
                        terminal.finish()

    def test_configured_pager_gets_normal_terminal_and_literal_arguments(self) -> None:
        """A configured viewer receives complete safe text, real tty input and literal options."""
        self._issue("target", title="Safe\x1b]2;INJECTED\x07 title")
        pager = self.workspace / "probe-pager"
        pager.write_text(
            "#!/usr/bin/env bash\n"
            "stty -g > pager-mode\n"
            'printf "%s\\n" "$@" > pager-arguments\n'
            'cat -- "${@: -1}" > pager-content\n'
            'printf "PAGER READY\\n"\n'
            "read -r answer\n"
        )
        pager.chmod(0o755)
        self.environment["PATH"] = (
            str(self.workspace) + os.pathsep + self.environment["PATH"]
        )
        self.environment["PAGER"] = "probe-pager --literal=$GLO_BASE *.md"
        terminal = self._terminal()
        terminal.send("\r")
        terminal.expect("PAGER READY")
        self.assertEqual(termios.tcgetattr(terminal.slave), terminal.original)
        arguments = (self.workspace / "pager-arguments").read_text().splitlines()
        self.assertEqual(arguments[:2], ["--literal=$GLO_BASE", "*.md"])
        content = (self.workspace / "pager-content").read_text()
        self.assertIn("id: target", content)
        self.assertIn("Description here.", content)
        self.assertNotIn("\x1b", content)
        terminal.send("done\r")
        terminal.expect("Pager closed")
        self.assertFalse(Path(arguments[-1]).exists())
        terminal.send("q")
        terminal.finish()
        # A single executable path containing spaces must not be split into words.
        self.environment["PAGER"] = str(pager)
        terminal = self._terminal()
        terminal.send("\r")
        terminal.expect("PAGER READY")
        self.assertEqual(
            len((self.workspace / "pager-arguments").read_text().splitlines()), 1
        )
        terminal.send("done\r")
        terminal.expect("Pager closed")
        terminal.send("q")
        terminal.finish()

    def test_pager_failure_returns_to_a_usable_board(self) -> None:
        """A failing configured pager must not strand the user or leak its temporary file."""
        self._issue("target")
        self.environment["PAGER"] = "false"
        terminal = self._terminal()
        terminal.send("\r")
        terminal.expect("Pager failed (exit 1)")
        self.assertEqual(list(self.snapshots.iterdir()), [])
        terminal.send("splan=accept\r")
        terminal.expect("Updated target")
        self.assertEqual(self._query()[0]["plan"], "accept")
        terminal.send("q")
        terminal.finish()


if __name__ == "__main__":
    unittest.main()
