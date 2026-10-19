"""Fail unless every installed distribution's licence is on the allow-list.

Run inside the project environment (``uv run python scripts/check_licences.py``)
after ``uv sync --locked``, so the installed set is exactly ``uv.lock``
(runtime and dev). Licences come from pip-licenses (``--from=mixed``: the
``License-Expression`` metadata, else trove classifiers, else ``License``).
The allow-list and the explicit ``dev-only-exceptions`` list are read from
``[tool.sloptopop.licences]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import cast

# Licence names found in classifiers / free-text metadata, mapped to SPDX ids.
# Only unambiguous names: "BSD License" (which BSD?) stays unknown and fails.
SPDX_ALIASES = {
    "MIT License": "MIT",
    "Apache Software License": "Apache-2.0",
    "Apache License 2.0": "Apache-2.0",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Python Software Foundation License": "PSF-2.0",
    "ISC License (ISCL)": "ISC",
}

# Trove "License ::" classifiers that state an approval, not a licence. They
# are ignored, but at least one real licence must remain.
NOT_LICENCES = {"DFSG approved", "OSI Approved"}


def main() -> int:
    """Check every installed distribution; print offenders; return the exit code."""
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["sloptopop"]["licences"]
    allowed = set(cast("list[str]", config["allow"]))
    exceptions = {
        entry["package"]: entry["licence"]
        for entry in cast("list[dict[str, str]]", config["dev-only-exceptions"])
    }
    listing = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--from=mixed", "--format=json", "--with-system"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    packages = cast("list[dict[str, str]]", json.loads(listing))
    failures = [
        f"{p['Name']} {p['Version']}: {p['License']}"
        for p in packages
        if not acceptable(p["License"], allowed) and exceptions.get(p["Name"]) != p["License"]
    ]
    for name, licence in sorted(exceptions.items()):
        print(f"licences: dev-only exception: {name} ({licence})", file=sys.stderr)  # noqa: T201 - CLI output
    if failures:
        print("licences: not on the allow-list:", *failures, sep="\n  ", file=sys.stderr)  # noqa: T201 - CLI output
        return 1
    print(f"licences: {len(packages)} distributions, all allowed", file=sys.stderr)  # noqa: T201 - CLI output
    return 0


def acceptable(licence: str, allowed: set[str]) -> bool:
    """Whether a licence string is allowed.

    Several licences separated by ``;`` (multiple classifiers) must all be
    allowed; approval labels in :data:`NOT_LICENCES` are ignored, but one real
    licence must remain. Each is an alias from :data:`SPDX_ALIASES` or an SPDX
    expression of ``OR``/``AND`` without parentheses (anything fancier fails).
    """
    parts = [part.strip() for part in licence.split(";")]
    licences = [part for part in parts if part not in NOT_LICENCES]
    return bool(licences) and all(_allowed_expression(part, allowed) for part in licences)


def _allowed_expression(expression: str, allowed: set[str]) -> bool:
    expression = SPDX_ALIASES.get(expression, expression)
    if "(" in expression or ")" in expression:
        return False
    return any(
        all(term.strip() in allowed for term in alternative.split(" AND "))
        for alternative in expression.split(" OR ")
    )


if __name__ == "__main__":
    sys.exit(main())
