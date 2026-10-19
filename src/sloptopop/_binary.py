"""Finding the ``sloptopop`` binary."""

from __future__ import annotations

import os
import shutil
import sysconfig
from pathlib import Path

from sloptopop._errors import TransportError

ENV_VAR = "SLOPTOPOP_BIN"
"""Environment variable naming the binary to run."""

BINARY_NAME = "sloptopop.exe" if os.name == "nt" else "sloptopop"

_BUNDLED_DIR = Path(__file__).parent / "_bin"


def find_binary(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Return the binary to run; the first match wins.

    1. ``explicit``, if given;
    2. the ``SLOPTOPOP_BIN`` environment variable, if set and non-empty;
    3. a binary bundled inside this package (``sloptopop/_bin/``);
    4. ``sloptopop`` on ``PATH``, skipping this environment's own
       ``sloptopop`` console script (which would just run this lookup again).

    Raises:
        TransportError: the chosen path is not a file, or nothing was found.

    """
    if explicit is not None:
        return _existing(Path(explicit), "explicit path")
    from_env = os.environ.get(ENV_VAR)
    if from_env:
        return _existing(Path(from_env), ENV_VAR)
    bundled = _BUNDLED_DIR / BINARY_NAME
    if bundled.is_file():
        return bundled
    on_path = _search_path()
    if on_path is not None:
        return on_path
    msg = f"sloptopop binary not found: pass a path, set {ENV_VAR}, or put sloptopop on PATH"
    raise TransportError(msg)


def _existing(path: Path, source: str) -> Path:
    if not path.is_file():
        msg = f"sloptopop binary not found at {path} ({source})"
        raise TransportError(msg)
    return path


def _search_path() -> Path | None:
    own_scripts = Path(sysconfig.get_path("scripts")).resolve()
    # Like shutil.which: an unset PATH means os.defpath.
    for directory in os.environ.get("PATH", os.defpath).split(os.pathsep):
        found = shutil.which("sloptopop", path=directory)
        if found is not None and Path(found).resolve().parent != own_scripts:
            return Path(found)
    return None
