#!/usr/bin/env python3
"""Unit tests for the foreground KDBX management command."""

from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import call, patch


GLO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = GLO_ROOT / "devcontainer/image/files/glo/bin/glo-secrets"


def _load_module() -> ModuleType:
    loader = SourceFileLoader("glo_secrets_cli", str(MODULE_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load glo-secrets")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SecretsCliTests(unittest.TestCase):
    """Verify delegation without touching a real database or keychain."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_module()

    def test_init_binds_one_alias_specific_keyring_credential(self) -> None:
        """Configure KDBX with one shared keyring address and then log in."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "share" / "example.kdbx"
            manifest = root / "secretspec.toml"
            with (
                patch.object(
                    self.module.shutil, "which", return_value="/bin/secretspec"
                ),
                patch.object(self.module.subprocess, "run") as run,
            ):
                status = self.module.main(
                    [
                        "--provider",
                        "local",
                        "init",
                        "--database",
                        str(database),
                        "--file",
                        str(manifest),
                    ],
                    environment={"PATH": "/bin"},
                )

        self.assertEqual(status, 0)
        self.assertEqual(
            run.call_args_list,
            [
                call(
                    [
                        "/bin/secretspec",
                        "config",
                        "global",
                        "provider",
                        "add",
                        "local",
                        f"kdbx:{database}",
                        "--credential",
                        "password=keyring://glo-secrets/local/{key}",
                    ],
                    check=True,
                ),
                call(
                    [
                        "/bin/secretspec",
                        "--file",
                        str(manifest),
                        "config",
                        "provider",
                        "login",
                        "local",
                    ],
                    check=True,
                ),
            ],
        )

    def test_put_prompts_instead_of_accepting_a_value_argument(self) -> None:
        """Pass only the declared name to SecretSpec set."""
        completed = subprocess.CompletedProcess([], 0)
        with (
            patch.object(self.module.shutil, "which", return_value="/bin/secretspec"),
            patch.object(self.module.subprocess, "run", return_value=completed) as run,
        ):
            status = self.module.main(
                [
                    "--provider",
                    "local",
                    "put",
                    "--file",
                    "example.toml",
                    "API_TOKEN",
                ],
                environment={"PATH": "/bin"},
            )

        self.assertEqual(status, 0)
        command = run.call_args.args[0]
        self.assertEqual(command[-1:], ["API_TOKEN"])
        self.assertNotIn("--profile", command)
        self.assertNotIn("VALUE", command)

    def test_import_selects_the_destination_alias_in_the_child_environment(
        self,
    ) -> None:
        """Use the runtime alias as SecretSpec's import destination."""
        completed = subprocess.CompletedProcess([], 0)
        with (
            patch.object(self.module.shutil, "which", return_value="/bin/secretspec"),
            patch.object(self.module.subprocess, "run", return_value=completed) as run,
        ):
            status = self.module.main(
                [
                    "--provider",
                    "local",
                    "import",
                    "--file",
                    "example.toml",
                    "dotenv:.env",
                ],
                environment={"PATH": "/bin", "SECRETSPEC_PROFILE": "development"},
            )

        self.assertEqual(status, 0)
        child_environment = run.call_args.kwargs["env"]
        self.assertEqual(child_environment["SECRETSPEC_PROVIDER"], "local")
        self.assertEqual(child_environment["SECRETSPEC_PROFILE"], "secret")

    def test_build_selects_one_manifest_and_forwards_build_arguments(self) -> None:
        """Derive one component manifest before running its glo-build target."""
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            project = workspace / "lib/example"
            project.mkdir(parents=True)
            (project / "build.json").write_text("{}\n", encoding="utf-8")
            manifest = project / "secretspec.toml"
            manifest.write_text("", encoding="utf-8")
            with (
                patch.object(self.module, "_workspace_root", return_value=workspace),
                patch.object(self.module.os, "execve", side_effect=OSError) as execute,
            ):
                status = self.module.main(
                    [
                        "--provider",
                        "local",
                        "build",
                        "/lib/example",
                        "unit",
                    ],
                    environment={"PATH": "/bin"},
                )

        self.assertEqual(status, 2)
        command = execute.call_args.args[1]
        self.assertTrue(command[0].endswith("/glo-build"))
        self.assertEqual(command[1:], ["/lib/example", "unit"])
        child_environment = execute.call_args.args[2]
        self.assertEqual(child_environment["SECRETSPEC_PROVIDER"], "local")
        self.assertEqual(child_environment["SECRETSPEC_FILE"], str(manifest))
        self.assertNotIn("SECRETSPEC_PROFILE", child_environment)
        self.assertNotIn("SECRETSPEC_SCOPE", child_environment)
        self.assertNotIn("SECRETSPEC_KDBX_PASSWORD", child_environment)

    def test_build_rejects_non_project_and_multiple_selectors(self) -> None:
        """Reject selector groups, missing projects, and a second project."""
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            project = workspace / "lib/example"
            project.mkdir(parents=True)
            (project / "build.json").write_text("{}\n", encoding="utf-8")
            (project / "secretspec.toml").write_text("", encoding="utf-8")
            invocations = (
                ["build", "/py", "unit"],
                ["build", "/lib/missing", "unit"],
                ["build", "/lib/example", "unit", "/lib/other", "unit"],
            )
            with patch.object(self.module, "_workspace_root", return_value=workspace):
                for invocation in invocations:
                    with self.subTest(invocation=invocation):
                        status = self.module.main(
                            ["--provider", "local", *invocation],
                            environment={"PATH": "/bin"},
                        )
                        self.assertEqual(status, 2)

    def test_run_delegates_materialization_to_secretspec(self) -> None:
        """Use SecretSpec run only for a child that does not resolve with an SDK."""
        completed = subprocess.CompletedProcess([], 0)
        with (
            patch.object(self.module.shutil, "which", return_value="/bin/secretspec"),
            patch.object(self.module.subprocess, "run", return_value=completed) as run,
        ):
            status = self.module.main(
                [
                    "run",
                    "--provider",
                    "local",
                    "--file",
                    "example.toml",
                    "--scope",
                    "runtime",
                    "--",
                    "example-command",
                ],
                environment={"PATH": "/bin"},
            )

        self.assertEqual(status, 0)
        command = run.call_args.args[0]
        self.assertIn("run", command)
        self.assertEqual(command[-2:], ["--", "example-command"])


if __name__ == "__main__":
    unittest.main()
