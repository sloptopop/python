"""The hatchling build hook, run against a fake ``uv`` that records its calls."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any, cast

import pytest

from hatch_build import GUARD_VAR, CoverageGateError, CoverageGateHook, run_gate

if TYPE_CHECKING:
    from pathlib import Path

    from hatchling.builders.config import BuilderConfig
    from hatchling.metadata.core import ProjectMetadata


@pytest.fixture
def fake_uv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put a fake ``uv`` alone on PATH; it logs argv, cwd and env, exits ``$FAKE_UV_EXIT``."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    log = tmp_path / "uv.log"
    uv.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        f"with open({str(log)!r}, 'w') as f:\n"
        "    json.dump({'argv0': sys.argv[0], 'argv': sys.argv[1:], 'cwd': os.getcwd(),"
        " 'env': dict(os.environ)}, f)\n"
        "sys.exit(int(os.environ.get('FAKE_UV_EXIT', '0')))\n"
    )
    uv.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.delenv(GUARD_VAR, raising=False)
    monkeypatch.setenv("VIRTUAL_ENV", "/somewhere/else")
    return log


def logged(log: Path) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(log.read_text()))


def test_runs_tests_before_a_standard_build(fake_uv: Path, tmp_path: Path) -> None:
    run_gate(str(tmp_path), "standard")
    call = logged(fake_uv)
    assert call["argv0"] == str(fake_uv.parent / "bin" / "uv")
    assert call["argv"] == ["run", "--locked", "pytest", "-p", "no:cacheprovider"]
    assert call["cwd"] == str(tmp_path.resolve())
    env = cast("dict[str, str]", call["env"])
    assert env[GUARD_VAR] == "1"
    assert "VIRTUAL_ENV" not in env
    assert env["PATH"] == str(fake_uv.parent / "bin")


def test_failing_tests_refuse_the_build(
    fake_uv: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_UV_EXIT", "3")
    with pytest.raises(
        CoverageGateError,
        match=(
            r"^build refused: the test suite failed or coverage is below 100% "
            r"\(pytest exit code 3\)$"
        ),
    ):
        run_gate(str(tmp_path), "standard")
    assert fake_uv.is_file()


def test_editable_installs_are_exempt(fake_uv: Path, tmp_path: Path) -> None:
    run_gate(str(tmp_path), "editable")
    assert not fake_uv.exists()


def test_guard_stops_recursion(
    fake_uv: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(GUARD_VAR, "1")
    run_gate(str(tmp_path), "standard")
    assert not fake_uv.exists()


def test_empty_guard_does_not_exempt(
    fake_uv: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(GUARD_VAR, "")
    run_gate(str(tmp_path), "standard")
    assert fake_uv.is_file()


def test_missing_uv_refuses_the_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv(GUARD_VAR, raising=False)
    with pytest.raises(CoverageGateError, match=r"needs uv \(https://docs\.astral\.sh/uv/"):
        run_gate(str(tmp_path), "standard")


def test_hook_runs_the_gate(fake_uv: Path, tmp_path: Path) -> None:
    hook = CoverageGateHook(
        str(tmp_path),
        {},
        cast("BuilderConfig", None),
        cast("ProjectMetadata[Any]", None),
        str(tmp_path / "dist"),
        "wheel",
    )
    assert CoverageGateHook.PLUGIN_NAME == "custom"
    hook.initialize("editable", {})
    assert not fake_uv.exists()
    hook.initialize("standard", {})
    assert logged(fake_uv)["cwd"] == str(tmp_path.resolve())
