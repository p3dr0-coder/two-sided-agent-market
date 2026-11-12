#!/usr/bin/env bash
# Shared bootstrap for the ekklesia demo/measure scripts.
# Callers set ROOT, then `source "$ROOT/scripts/lib.sh"` after `set -euo pipefail`.

export PYTHONPATH="$ROOT/packages/ekklesia-market/src${PYTHONPATH:+:$PYTHONPATH}"

PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  for candidate in python3 python python.exe; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys" >/dev/null 2>&1; then
      PYTHON="$candidate"
      break
    fi
  done
fi
if [[ -z "$PYTHON" ]]; then
  echo "$(basename "${BASH_SOURCE[1]}") requires Python 3" >&2
  exit 1
fi

near_cli() {
  if command -v near-ekklesia >/dev/null 2>&1; then
    near-ekklesia "$@"
  else
    "$PYTHON" -m magentic_marketplace.cli "$@"
  fi
}
