#!/usr/bin/env bash
# DRY-RUN pin: fresh sandbox, scripted 5x20 market, SQLite analytics, refund probe.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib.sh
source "$ROOT/scripts/lib.sh"

bash scripts/setup_local.sh
# shellcheck disable=SC1091
source .sandbox/env.sh

rm -f data/demo.db data/demo-tx.jsonl
near_cli run data/demo_small \
  --near --scripted --experiment-name demo --db-type sqlite --override-db
near_cli analyze data/demo.db --db-type sqlite --near
"$PYTHON" -m magentic_marketplace.near.refund_probe --experiment-name demo

echo "Demo complete: data/demo.db and data/demo-tx.jsonl"
