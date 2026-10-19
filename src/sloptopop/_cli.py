"""The ``sloptopop`` command: runs the binary with the same arguments and stdio."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

from sloptopop._binary import find_binary
from sloptopop._errors import TransportError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

NOT_FOUND_EXIT_CODE = 127
"""Exit code when no binary is found, as a POSIX shell uses."""

CANNOT_RUN_EXIT_CODE = 126
"""Exit code when the binary cannot be started, as a POSIX shell uses."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the binary with ``argv`` (default ``sys.argv[1:]``).

    On POSIX the binary replaces this process (``os.execv``), so stdin,
    stdout, stderr, signals and the exit code are the binary's own. Elsewhere
    it runs as a child and its exit code is returned.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    try:
        binary = find_binary()
    except TransportError as e:
        print(f"error: {e}", file=sys.stderr)  # noqa: T201 - this is a CLI
        return NOT_FOUND_EXIT_CODE
    return run(binary, args, replace_process=os.name == "posix")


def run(binary: Path, args: Sequence[str], *, replace_process: bool) -> int:
    """Run ``binary`` with ``args``, inheriting stdio; return its exit code.

    With ``replace_process`` the binary replaces this process via
    ``os.execv`` and this function returns only if that fails.
    """
    try:
        if replace_process:
            sys.stdout.flush()
            sys.stderr.flush()
            os.execv(binary, [str(binary), *args])  # noqa: S606 - the point of this command
        return subprocess.call([binary, *args])  # noqa: S603 - the point of this command
    except OSError as e:
        print(f"error: cannot run {binary}: {e}", file=sys.stderr)  # noqa: T201 - this is a CLI
        return CANNOT_RUN_EXIT_CODE
