# Python specifics

Only what is specific to the Python client. The protocol, the CLI, the
conformance suite and the quality standard are documented once, in
[sloptopop/cli](https://github.com/sloptopop/cli)
([PROTOCOL.md](https://github.com/sloptopop/cli/blob/main/PROTOCOL.md),
[docs/](https://github.com/sloptopop/cli/tree/main/docs),
[conformance/](https://github.com/sloptopop/cli/tree/main/conformance)).

## Tools per standard item

Versions of Python tools are pinned exactly in `uv.lock`.

| # | Item | Python tooling (version, licence) |
|---|---|---|
| 1 | Pinned toolchain | CPython **3.14.8** in `.python-version` (PSF-2.0); uv **0.13.0** in `[tool.uv] required-version` (MIT OR Apache-2.0); osv-scanner **2.6.0** pinned in `scripts/gate.sh`. The gate fails on any other version, and `uv sync --locked` fails if `uv.lock` is stale. |
| 2 | Formatting | `ruff format --check` — ruff 0.17.0 (MIT); this also formats the Python code blocks in Markdown. |
| 3 | Zero warnings | `python -W error -m compileall`; `ruff check` with `select = ["ALL"]`; mypy 2.4.0 (MIT) with `strict`, `warn_unreachable` and extra error codes; pytest with `filterwarnings = ["error"]`. Each inline `# noqa` gives a reason. The config ignores, each commented in `pyproject.toml`: D203/D213 (mutually exclusive docstring rules), COM812 (conflicts with the formatter), CPY001 (licence lives in `LICENSE-*`). The rest are test/script/example-only, like Clippy's test allowances: S101 (assert), PLR2004, S603, D100/D103, INP001, T201 (examples). |
| 4 | All tests pass | pytest 9.1.1 (MIT), pytest-timeout 2.4.0 (MIT, 15 s per test, so a hang fails). Covers unit tests, `examples/hello.py`, the real binary (`SLOPTOPOP_BIN`) and every case in `cli/conformance/cases` (`SLOPTOPOP_CONFORMANCE_DIR`), run through this package's own codec. |
| 5 | 100% coverage | coverage.py 7.16.2 (Apache-2.0) via pytest-cov 7.1.0 (MIT): **lines and branches** at 100%. These are coverage.py's only metrics; it has no function metric, but 100% of lines implies every function body runs. Product code is `src/sloptopop` plus the build hook `hatch_build.py`. |
| 6 | Mutation testing | mutmut 3.8.0 (BSD-3-Clause) over `src/sloptopop` and `hatch_build.py`. Every mutant must be `killed` or `timeout`. Workers: `SLOPTOPOP_GATE_JOBS` (default 3). |
| 7 | Vulnerabilities | osv-scanner 2.6.0 (Apache-2.0) `scan source -r .` (reads `uv.lock`); pip-audit 2.10.1 (Apache-2.0) on the hashed export of `uv.lock`, covering all groups; `uv audit --locked` (uv's own lockfile auditor, still marked experimental). |
| 8 | Licences | pip-licenses 5.5.5 (MIT) lists every installed distribution (= `uv.lock`, runtime + dev). `scripts/check_licences.py` checks it against `[tool.sloptopop.licences] allow` (SPDX ids; classifier names are mapped to SPDX, approval labels such as `DFSG approved` are ignored, unknown names fail). Explicit `dev-only-exceptions` list: currently **empty**. |
| 9 | Docs | ruff's pydocstyle rules (`D`, Google convention) require a docstring on every public module, class, method and function. |
| 10 | Pre-push hook | `.githooks/pre-push` runs `scripts/gate.sh`; enable with `git config core.hooksPath .githooks`. |
| 11 | CI | `.github/workflows/gate.yml` checks out `python/` next to `sloptopop/cli`, builds the binary with cargo, installs uv 0.13.0 and osv-scanner 2.6.0, and runs the full gate. |

## Running the gate

```sh
scripts/gate.sh           # everything (pre-push, CI); mutation testing takes minutes
scripts/gate.sh --fast    # items 1-5 and 9
scripts/gate.sh --check   # items 1-3, seconds
```

Needs uv and osv-scanner on `PATH`; a missing tool fails the gate with an
install hint. The binary defaults to `../cli/target/debug/sloptopop` and the
cases to `../cli/conformance/cases` (override with `SLOPTOPOP_BIN` and
`SLOPTOPOP_CONFORMANCE_DIR`). `SLOPTOPOP_GATE_JOBS` (default 3) caps parallel
mutation workers; the tests themselves run serially.

## Build-time coverage enforcement

The build backend is hatchling 1.32.4 (MIT) with the custom build hook
`hatch_build.py`. Before hatchling builds a wheel or sdist, by any PEP 517
frontend (`uv build`, `pip install .`, `python -m build`), the hook runs
`uv run --locked pytest`. pyproject.toml sets 100% line and branch coverage
and warnings as errors for that run. If the run fails, or uv is missing, the
build fails.

`uv build` builds the sdist first, then the wheel from it, so the suite runs
twice. The sdist contains the tests, `uv.lock` and `.python-version` so the
second run works. It needs `SLOPTOPOP_BIN` and `SLOPTOPOP_CONFORMANCE_DIR` as
absolute paths, because the relative defaults don't exist in a temp dir.

Exempt, and only these:

- **Editable installs** (`uv sync`, `pip install -e .`). The test environment
  is itself an editable install, so gating it on the tests would be circular.
- **Builds nested inside the hook's own test run.** The hook sets
  `SLOPTOPOP_COVERAGE_GATE=1` as a recursion guard, the counterpart of the
  cargo-llvm-cov variable in the Rust `build.rs`. Setting it by hand also
  bypasses the hook. That can't be prevented from inside a build backend.

Consequence: an end user installing from the **sdist** also runs the suite,
and so needs uv and the binary. Wheels install without running anything.

## Bundled binary

Place it at `src/sloptopop/_bin/sloptopop` (`sloptopop.exe` on Windows) before
building a platform-specific wheel. `find_binary()` prefers it over `PATH`.
No such wheel is produced yet.

## Platform limitations

- The gate is POSIX-only. mutmut forks workers, and the tests' fake binaries
  are scripts started via a shebang. CI runs on Ubuntu; development runs on
  macOS.
- On Windows, the `sloptopop` command runs the binary as a child process
  (`os.execv` doesn't keep the exit code there). Only the child-process branch
  is tested, and only on POSIX.
- Only lines and branches can be measured (see item 5).

## Awaiting the user's decision

- `scripts/gate.sh`, `.githooks/pre-push` and `.github/workflows/gate.yml` are
  protected by the workspace's Claude permissions. The versions implementing
  this document have to be installed by the user. `core.hooksPath` is
  already set to `.githooks`.
- `scripts/check_licences.py` is gate tooling, like `gate.sh`. It is linted
  and type-checked but not counted in coverage or mutation testing.
- No licence exceptions are needed: every locked distribution is allow-listed.
