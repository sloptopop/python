#!/bin/sh
# Quality gate for the sloptopop Python client. Enforces every item of the
# sloptopop standard (STANDARDS.md, kept in sloptopop/rust policy/); a missing
# tool fails the gate, nothing is ever skipped. Python specifics: LANGUAGE.md.
#
#   scripts/gate.sh          everything: items 1-11 plus the coverage-gated
#                            build (pre-push hook and CI)
#   scripts/gate.sh --fast   items 1-5 and 9
#   scripts/gate.sh --check  items 1-3 only (seconds)
#
# Environment:
#   SLOPTOPOP_BIN              binary (default ../cli/target/debug/sloptopop)
#   SLOPTOPOP_CONFORMANCE_DIR  cases (default ../cli/conformance/cases)
#   SLOPTOPOP_GATE_JOBS        parallel mutation workers (default 3)
set -eu
cd "$(dirname "$0")/.."
root=$(pwd)

mode=full
case "${1:-}" in
    "") ;;
    --fast) mode=fast ;;
    --check) mode=check ;;
    *)
        echo "usage: scripts/gate.sh [--fast | --check]" >&2
        exit 2
        ;;
esac

# Exact versions of the tools that are not in uv.lock.
OSV_SCANNER_VERSION=2.6.0

fail() {
    echo "gate: $*" >&2
    exit 1
}

need() {
    command -v "$1" >/dev/null 2>&1 || fail "$1 not installed ($2)"
}

step() {
    echo "gate: $*" >&2
}

jobs="${SLOPTOPOP_GATE_JOBS:-3}"
case "$jobs" in
    '' | *[!0-9]* | 0) fail "SLOPTOPOP_GATE_JOBS must be a positive integer (got '$jobs')" ;;
esac

need uv "https://docs.astral.sh/uv/getting-started/installation/"
need git "https://git-scm.com/downloads"
if [ "$mode" = full ]; then
    need osv-scanner "brew install osv-scanner, or go install github.com/google/osv-scanner/v2/cmd/osv-scanner@v$OSV_SCANNER_VERSION"
fi

# --- 1. pinned toolchain ------------------------------------------------------
step "1 toolchain: uv, Python and uv.lock pinned"
uv_pin=$(sed -n 's/^required-version = "==\(.*\)"$/\1/p' pyproject.toml)
uv_have=$(uv --version | cut -d' ' -f2)
[ -n "$uv_pin" ] || fail "pyproject.toml has no exact [tool.uv] required-version"
[ "$uv_have" = "$uv_pin" ] || fail "uv $uv_have found, uv $uv_pin required (pyproject.toml)"
# --locked: uv.lock must already match pyproject.toml exactly.
uv sync --locked --quiet
python_pin=$(cat .python-version)
python_have=$(uv run --locked python -c 'import platform; print(platform.python_version())')
[ "$python_have" = "$python_pin" ] || fail "Python $python_have found, Python $python_pin required (.python-version)"
if [ "$mode" = full ]; then
    osv_have=$(osv-scanner --version | sed -n 's/^osv-scanner version: //p')
    [ "$osv_have" = "$OSV_SCANNER_VERSION" ] ||
        fail "osv-scanner $osv_have found, osv-scanner $OSV_SCANNER_VERSION required (scripts/gate.sh)"
fi

# --- 2. formatting ------------------------------------------------------------
step "2 format"
uv run --locked ruff format --check .

# --- 3. zero warnings ---------------------------------------------------------
step "3 zero warnings: compile, ruff (ALL rules), mypy --strict"
uv run --locked python -W error -m compileall -q src tests examples scripts hatch_build.py >/dev/null
uv run --locked ruff check .
uv run --locked mypy

if [ "$mode" = check ]; then
    step "passed (--check: items 1-3)"
    exit 0
fi

SLOPTOPOP_BIN="${SLOPTOPOP_BIN:-$root/../cli/target/debug/sloptopop}"
SLOPTOPOP_CONFORMANCE_DIR="${SLOPTOPOP_CONFORMANCE_DIR:-$root/../cli/conformance/cases}"
[ -x "$SLOPTOPOP_BIN" ] || fail "sloptopop binary not found at $SLOPTOPOP_BIN (build sloptopop/cli with cargo build, or set SLOPTOPOP_BIN)"
[ -d "$SLOPTOPOP_CONFORMANCE_DIR" ] || fail "conformance cases not found at $SLOPTOPOP_CONFORMANCE_DIR (set SLOPTOPOP_CONFORMANCE_DIR)"
export SLOPTOPOP_BIN SLOPTOPOP_CONFORMANCE_DIR

# --- 4 + 5. all tests pass, 100% coverage --------------------------------------
# Unit tests, the example, the real binary and every conformance case. Line
# and branch coverage at 100% (coverage.py's only metrics) and warnings as
# errors are set in pyproject.toml, so a bare `pytest` enforces them too.
step "4+5 tests + 100% line and branch coverage"
uv run --locked pytest

# --- 9. docs ------------------------------------------------------------------
step "9 docs: every public module, class and function documented (ruff D)"
uv run --locked ruff check --select D src hatch_build.py scripts examples

if [ "$mode" = fast ]; then
    step "passed (--fast: items 1-5 and 9)"
    exit 0
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# --- 6. mutation testing ------------------------------------------------------
# A fresh run over the package and the build hook; every mutant must be
# killed. A timeout counts as killed; anything else (survived, no tests,
# suspicious, skipped, segfault, not checked) fails.
step "6 mutation testing (mutmut, $jobs workers)"
rm -rf mutants
uv run --locked mutmut run --max-children "$jobs" >"$tmp/mutmut.log" 2>&1 || {
    tr '\r' '\n' <"$tmp/mutmut.log" | tail -n 40 >&2
    fail "mutmut run failed"
}
uv run --locked mutmut results --all true >"$tmp/mutants.txt"
grep -v -E ': (killed|timeout)$' "$tmp/mutants.txt" >"$tmp/alive.txt" || true
if [ -s "$tmp/alive.txt" ]; then
    cat "$tmp/alive.txt" >&2
    fail "mutants not killed (inspect one with: uv run mutmut show <name>)"
fi
grep -q ': killed$' "$tmp/mutants.txt" || fail "mutmut produced no mutants"
step "$(wc -l <"$tmp/mutants.txt" | tr -d ' ') mutants, all killed"

# --- 7. dependency vulnerabilities --------------------------------------------
step "7 vulnerabilities: osv-scanner, pip-audit, uv audit (runtime + dev)"
osv-scanner scan source -r .
uv export --locked --all-groups --no-emit-project --format requirements-txt --quiet -o "$tmp/requirements.txt"
uv run --locked pip-audit --strict --require-hashes --disable-pip -r "$tmp/requirements.txt"
uv audit --locked --preview-features audit-command

# --- 8. dependency licences ---------------------------------------------------
step "8 licences: every locked distribution on the allow-list"
uv run --locked python scripts/check_licences.py

# --- coverage-gated build -----------------------------------------------------
# hatch_build.py runs the tests (100% coverage) before building; prove the
# real build path works end to end (sdist, then the wheel from that sdist).
step "build: sdist + wheel through the coverage-gated hatchling hook"
uv build --quiet --out-dir "$tmp/dist"

# --- 10. pre-push hook --------------------------------------------------------
step "10 pre-push hook installed"
[ -x .githooks/pre-push ] || fail ".githooks/pre-push missing or not executable"
grep -q 'scripts/gate.sh"$' .githooks/pre-push || fail ".githooks/pre-push does not run scripts/gate.sh"
[ "$(git config core.hooksPath || true)" = .githooks ] ||
    fail "pre-push hook not enabled: run git config core.hooksPath .githooks"

# --- 11. CI -------------------------------------------------------------------
step "11 CI runs the full gate"
grep -q -E '^ +run: scripts/gate.sh$' .github/workflows/gate.yml ||
    fail ".github/workflows/gate.yml must run scripts/gate.sh (full gate, no flags)"

step "passed (all items 1-11)"
