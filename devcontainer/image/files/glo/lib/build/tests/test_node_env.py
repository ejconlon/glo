"""Tests for nvm-backed Node environment emission."""

from pathlib import Path

from glo_build.cli import Project, Script, set_workspace_root


def test_ts_env_uses_nvm_lts_node_bin(tmp_path: Path) -> None:
    set_workspace_root(tmp_path)
    project_dir = tmp_path / "lib" / "app"
    project_dir.mkdir(parents=True)
    (project_dir / "build.json").write_text('{"language": "ts"}')

    script = Script(tmp_path, color=False)
    Project("/lib/app", tmp_path).emit_ts_env(script)

    bash = script.to_bash()

    assert 'export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"' in bash
    assert '"/usr/local/nvm/nvm.sh"' in bash
    assert "nvm use --silent --lts >/dev/null" in bash
    assert 'GLO_NODE_BIN="$(dirname "$(command -v node)")"' in bash
    assert "export PATH=$TS_NODE_MODULES/.bin:$GLO_NODE_BIN:$PATH" in bash


def test_ps_env_uses_nvm_lts_node_bin(tmp_path: Path) -> None:
    set_workspace_root(tmp_path)
    project_dir = tmp_path / "lib" / "app"
    project_dir.mkdir(parents=True)
    (project_dir / "build.json").write_text('{"language": "ps"}')

    script = Script(tmp_path, color=False)
    Project("/lib/app", tmp_path).emit_ps_env(script)

    bash = script.to_bash()

    assert "nvm use --silent --lts >/dev/null" in bash
    assert "export PATH=$PS_NODE_MODULES/.bin:$GLO_NODE_BIN:$PATH" in bash
