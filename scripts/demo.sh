#!/usr/bin/env bash
# DRY-RUN pin: fresh sandbox, scripted 5x20 market, SQLite analytics, refund probe.
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
  echo "demo.sh requires Python 3" >&2
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

rm -f data/demo.db data/demo-tx.jsonl
near_cli run data/demo_small \
  --near --scripted --experiment-name demo --db-type sqlite --override-db
near_cli analyze data/demo.db --db-type sqlite --near
"$PYTHON" -m magentic_marketplace.near.refund_probe --experiment-name demo

echo "Demo complete: data/demo.db and data/demo-tx.jsonl"
