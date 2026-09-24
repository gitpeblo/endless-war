#!/usr/bin/env bash
# Launch the War Room. Works from any directory.
set -e
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m endless_war.ui.app "$@"
