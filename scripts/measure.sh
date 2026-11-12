#!/usr/bin/env bash
# NUMBERS pin: scripted market + 3 invalid proposals + one measured headline.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib.sh
source "$ROOT/scripts/lib.sh"

bash scripts/setup_local.sh
# shellcheck disable=SC1091
source .sandbox/env.sh

rm -f data/numbers.db data/numbers-tx.jsonl
near_cli run data/demo_small \
  --near --scripted --experiment-name numbers --db-type sqlite --override-db
"$PYTHON" -m magentic_marketplace.near.manipulation_probe --experiment-name numbers
near_cli analyze data/numbers.db --db-type sqlite --near \
  | grep -E '^Total marketplace customer utility = '
