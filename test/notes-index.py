#!/usr/bin/env python3
"""Exercise notebook-relative navigation and selective zk diagnostics."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


NOTES = Path(__file__).resolve().parents[1] / "devcontainer/image/files/glo/bin/glo-notes"


class NotesIndexTests(unittest.TestCase):
    """Use a private notebook and the installed zk indexer."""

    def setUp(self):
        """Create notebook links that cross its boundary without crossing owners."""
        self.temporary = tempfile.TemporaryDirectory(prefix="glo-notes-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()
        self.base = self.root / "base"
        (self.base / ".zk").mkdir(parents=True)
        (self.base / "wiki").mkdir()
        (self.base / "issue").mkdir()
        (self.base / ".zk/config.toml").write_text(
            '[note]\nexclude = ["**/TAGS.md", "**/TITLES.md"]\n'
        )
        (self.root / "source.md").write_text("# External source\n")
        (self.base / "wiki/page.md").write_text(
            "# Current guide\n\n#guide\n\n[Source](../../source.md)\n"
        )
        self.environment = dict(os.environ, GLO_BASE=str(self.base))

    def run_notes(self):
        """Run the real index and generator entry point."""
        return subprocess.run(
            [str(NOTES), "precommit"], cwd=self.root, env=self.environment,
            text=True, capture_output=True, timeout=30, check=False,
        )

    def inject_diagnostics(self, fail=False):
        """Wrap zk to exercise stderr and exit propagation at the process boundary."""
        real_zk = shutil.which("zk")
        self.assertIsNotNone(real_zk)
        directory = self.root / "bin"
        directory.mkdir()
        shim = directory / "zk"
        shim.write_text(
            "#!/usr/bin/env python3\nimport os, subprocess, sys\n"
            "print('zk: warning: /outside: path is outside the notebook at ' + "
            "os.environ['ZK_NOTEBOOK_DIR'], file=sys.stderr)\n"
            "print('zk: warning: unrelated diagnostic', file=sys.stderr)\n"
            "print('index stdout survives')\n"
            + ("sys.exit(7)\n" if fail else
               f"sys.exit(subprocess.call([{real_zk!r}, *sys.argv[1:]]))\n")
        )
        shim.chmod(0o755)
        self.environment["PATH"] = str(directory) + os.pathsep + os.environ["PATH"]

    def test_external_link_and_relative_indexes(self):
        """A valid source link is quiet and generated navigation resolves locally."""
        result = self.run_notes()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("outside the notebook", result.stderr)
        for filename in ("TAGS.md", "TITLES.md"):
            self.assertIn(
                "[Current guide](page.md)",
                (self.base / "wiki" / filename).read_text(),
            )
            self.assertIn(
                "[Current guide](wiki/page.md)",
                (self.base / filename).read_text(),
            )

    def test_other_warnings_and_stdout_survive(self):
        """Only the exact successful-index outside-reference diagnostic is hidden."""
        self.inject_diagnostics()
        result = self.run_notes()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("unrelated diagnostic", result.stderr)
        self.assertIn("index stdout survives", result.stdout)
        self.assertNotIn("outside the notebook", result.stderr)

    def test_failure_retains_all_diagnostics_and_status(self):
        """A failed index cannot become a successful precommit or lose evidence."""
        self.inject_diagnostics(fail=True)
        result = self.run_notes()
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertIn("outside the notebook", result.stderr)
        self.assertIn("unrelated diagnostic", result.stderr)
        self.assertIn("index stdout survives", result.stdout)
        self.assertFalse((self.base / "wiki/TITLES.md").exists())

    def test_malformed_configuration_still_fails(self):
        """Real zk configuration errors remain visible and stop generation."""
        (self.base / ".zk/config.toml").write_text("invalid = [\n")
        result = self.run_notes()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("config", result.stderr)
        self.assertFalse((self.base / "wiki/TITLES.md").exists())


if __name__ == "__main__":
    unittest.main()
