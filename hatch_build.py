"""Hatchling build hook: no wheel or sdist unless every test passes at 100% coverage.

``uv build``, ``pip install .`` and every other PEP 517 build of a wheel or
sdist call :meth:`CoverageGateHook.initialize` first, which runs the test
suite (``uv run --locked pytest``; ``pyproject.toml`` sets 100% line and
branch coverage and warnings as errors) and aborts the build if it fails.

Exempt, and only these:

- editable installs (``uv sync``, ``pip install -e .``): the test suite itself
  runs from the editable install, so requiring the tests to build it first
  would be circular;
- builds started from inside that test run (``SLOPTOPOP_COVERAGE_GATE`` set),
  the recursion guard.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from hatchling.builders.config import BuilderConfig
from hatchling.builders.hooks.plugin.interface import BuildHookInterface

GUARD_VAR = "SLOPTOPOP_COVERAGE_GATE"
"""Set while the hook's test run is going on, so nested builds don't recurse."""


class CoverageGateError(RuntimeError):
    """The build was refused because the coverage gate did not pass."""


def run_gate(root: str, version: str) -> None:
    """Run the tests with the coverage thresholds unless the build is exempt.

    Raises:
        CoverageGateError: uv is missing, or a test failed, or coverage is
            below 100%.

    """
    if version == "editable" or os.environ.get(GUARD_VAR):
        return
    uv = shutil.which("uv")
    if uv is None:
        msg = (
            "building sloptopop runs its tests first and needs uv "
            "(https://docs.astral.sh/uv/getting-started/installation/)"
        )
        raise CoverageGateError(msg)
    env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    env[GUARD_VAR] = "1"
    code = subprocess.call(  # noqa: S603 - fixed command; uv comes from PATH like any build tool
        [uv, "run", "--locked", "pytest", "-p", "no:cacheprovider"],
        cwd=root,
        env=env,
    )
    if code != 0:
        msg = (
            f"build refused: the test suite failed or coverage is below 100% "
            f"(pytest exit code {code})"
        )
        raise CoverageGateError(msg)


class CoverageGateHook(BuildHookInterface[BuilderConfig]):
    """Runs :func:`run_gate` before hatchling builds any target."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:  # noqa: ARG002 - hatchling's signature; build_data isn't needed
        """Refuse the build unless the tests pass at 100% coverage."""
        run_gate(self.root, version)
