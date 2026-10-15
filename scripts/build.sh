#!/bin/sh
# Build production artifacts. No test-transport feature is enabled here.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
for arg in "$@"; do
    case "$arg" in --offline) ;; *) echo "Uso: $0 [--offline]" >&2; exit 2 ;; esac
done
cd "$ROOT"
export CARGO_TARGET_DIR="$ROOT/target"
cargo build --release --locked --no-default-features "$@"
