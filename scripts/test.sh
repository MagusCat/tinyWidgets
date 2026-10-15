#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
export CARGO_TARGET_DIR="$ROOT/target"
export PYTHONPATH="$ROOT/python${PYTHONPATH:+:$PYTHONPATH}"
TEST_PROFILE=$(mktemp -d "${TMPDIR:-/tmp}/tinywidgets-tests.XXXXXXXX")
trap 'rm -rf "$TEST_PROFILE"' EXIT HUP INT TERM
cp -R "$ROOT/eww/." "$TEST_PROFILE/"
: > "$TEST_PROFILE/.modular-active"
export RANDLY_WIDGETS_CONFIG="$TEST_PROFILE"
cargo fmt --all -- --check
cargo test --locked "$@"
# Test-only IPC fixture support; never install this binary.
cargo build --locked --features test-transport "$@"
cargo build --release --locked --no-default-features "$@"
python3 -m unittest discover -s python/randly_widgets/tests -q
python3 -m unittest discover -s tests -q
