#!/bin/sh
# User-only installation; does not install packages or restart the desktop.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$ROOT/scripts/build.sh" "$@"
exec python3 "$ROOT/scripts/install.py"
