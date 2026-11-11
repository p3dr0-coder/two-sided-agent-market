#!/usr/bin/env bash
# NUMBERS pin: scripted market + 3 invalid proposals + one measured headline.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
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
  echo "measure.sh requires Python 3" >&2
  exit 1
fi

near_cli() {
  if command -v near-ekklesia >/dev/null 2>&1; then
    near-ekklesia "$@"
  else
    "$PYTHON" -m magentic_marketplace.cli "$@"
  fi
}

bash scripts/setup_local.sh
# shellcheck disable=SC1091
source .sandbox/env.sh

rm -f data/numbers.db data/numbers-tx.jsonl
near_cli run data/demo_small \
  --near --scripted --experiment-name numbers --db-type sqlite --override-db
"$PYTHON" -m magentic_marketplace.near.manipulation_probe --experiment-name numbers
near_cli analyze data/numbers.db --db-type sqlite --near \
  | grep -E '^Total marketplace customer utility = '
