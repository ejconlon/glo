"""Parallel build workers must finish through notifications and leave no descendants."""

import fcntl
import json
import os
from pathlib import Path
import pty
import selectors
import shlex
import signal
import subprocess
import sys
import termios

import pytest

from glo_build.cli import (
    Task,
    generate_parallel_script,
    generate_sequential_script,
    set_workspace_root,
)


def plan(tmp_path: Path, command: str, *, parallel: bool = True) -> Path:
    """Generate a real build plan around one shell task."""
    project = tmp_path / "lib" / "fixture"
    project.mkdir(parents=True)
    (project / "build.json").write_text(
        json.dumps({"language": "meta", "targets": {"run": [{"command": command}]}})
    )
    set_workspace_root(tmp_path)
    task = Task("/lib/fixture:run", "/lib/fixture", "run", [], None)
    script = tmp_path / "plan.sh"
    tasks = {task.id: task}
    script.write_text(
        generate_parallel_script(tasks, tmp_path, False, 2)
        if parallel
        else generate_sequential_script(tasks, tmp_path, False)
    )
    return script


def attach_terminal() -> None:
    """Give the child session a controlling terminal with normal job-control signals."""
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    for kind in (signal.SIGTTIN, signal.SIGTTOU, signal.SIGTSTP):
        signal.signal(kind, signal.SIG_DFL)


@pytest.mark.parametrize("parallel", [False, True])
@pytest.mark.parametrize("terminal", [False, True])
def test_only_foreground_tasks_receive_input(
    tmp_path: Path, parallel: bool, terminal: bool
) -> None:
    """Background tasks must neither consume caller input nor probe its terminal."""
    payload = "reserved for the foreground\n"
    expected = "" if parallel else payload
    source = (
        "import sys; "
        f"assert sys.stdin.isatty() == {terminal and not parallel!r}; "
        f"assert sys.stdin.readline() == {expected!r}; "
        "print('input ownership preserved')"
    )
    script = plan(
        tmp_path,
        f"{shlex.quote(sys.executable)} -c {shlex.quote(source)}",
        parallel=parallel,
    )
    env = {**os.environ, "WORKSPACE": str(tmp_path)}
    if terminal:
        master, slave = pty.openpty()
        try:
            os.write(master, payload.encode())
            result = subprocess.run(
                ["bash", str(script)],
                stdin=slave,
                capture_output=True,
                text=True,
                timeout=5,
                start_new_session=True,
                preexec_fn=attach_terminal,
                env=env,
            )
        finally:
            os.close(master)
            os.close(slave)
    else:
        result = subprocess.run(
            ["bash", str(script)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "input ownership preserved" in result.stdout


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
            env={**os.environ, "WORKSPACE": str(script.parent)},
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
            ["bash", str(script)],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "WORKSPACE": str(script.parent)},
        )
        assert (result.returncode == 0) == success, result.stdout + result.stderr
