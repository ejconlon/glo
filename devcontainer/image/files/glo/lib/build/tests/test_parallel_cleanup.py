"""Parallel build workers must finish through notifications and leave no descendants."""

import json
import os
from pathlib import Path
import selectors
import shlex
import signal
import subprocess
import sys

import pytest

from glo_build.cli import Task, generate_parallel_script, set_workspace_root


def plan(tmp_path: Path, command: str) -> Path:
    """Generate a real parallel plan around one shell task."""
    project = tmp_path / "lib" / "fixture"
    project.mkdir(parents=True)
    (project / "build.json").write_text(
        json.dumps({"language": "meta", "targets": {"run": [{"command": command}]}})
    )
    set_workspace_root(tmp_path)
    task = Task("/lib/fixture:run", "/lib/fixture", "run", [], None)
    script = tmp_path / "plan.sh"
    script.write_text(generate_parallel_script({task.id: task}, tmp_path, False, 2))
    return script


@pytest.mark.parametrize("cancellation", [signal.SIGINT, signal.SIGTERM])
def test_cancellation_terminates_nested_worker_processes(
    tmp_path: Path, cancellation: signal.Signals
) -> None:
    """Cancelling the coordinator must close a pipe held by its task's grandchild."""
    reader, writer = os.pipe()
    source = f"import os,signal; os.write({writer}, b'ready'); signal.pause()"
    script = plan(tmp_path, f"{shlex.quote(sys.executable)} -c {shlex.quote(source)}")
    with selectors.DefaultSelector() as events:
        events.register(reader, selectors.EVENT_READ)
        with subprocess.Popen(
            ["bash", str(script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            pass_fds=(writer,),
            start_new_session=True,
        ) as process:
            os.close(writer)
            try:
                assert events.select(10), "worker never became ready"
                assert os.read(reader, 5) == b"ready"
                process.send_signal(cancellation)
                output, _ = process.communicate(timeout=10)
                assert process.returncode == 128 + cancellation, output.decode()
                assert events.select(10), "cancelled build retained a live descendant"
                assert os.read(reader, 1) == b"", "descendant still owns the pipe"
            finally:
                if process.poll() is None:
                    process.kill()
                os.close(reader)


def test_fast_and_failed_workers_report_their_exit_status(tmp_path: Path) -> None:
    """Immediate completion and signal termination must neither spin nor lose status."""
    for index, (command, success) in enumerate(
        [("true", True), ("exit 7", False), ("kill -TERM $BASHPID", False)]
    ):
        script = plan(tmp_path / str(index), command)
        result = subprocess.run(
            ["bash", str(script)], capture_output=True, text=True, timeout=10
        )
        assert (result.returncode == 0) == success, result.stdout + result.stderr
