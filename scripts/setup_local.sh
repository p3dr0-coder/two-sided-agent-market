#!/usr/bin/env bash
# Fresh Docker sandbox -> contract build/deploy/init -> 5x20 registration.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib.sh
source "$ROOT/scripts/lib.sh"

CONTAINER="${NEAR_SANDBOX_CONTAINER:-ekklesia-sandbox}"
IMAGE="${NEAR_SANDBOX_IMAGE:-nearprotocol/sandbox:2.13.4}"
RPC_URL="${NEAR_RPC_URL:-http://127.0.0.1:3030}"

if [[ -n "${NEAR_SANDBOX_URL:-}" ]]; then
  RPC_URL="$NEAR_SANDBOX_URL"
  echo "Using native sandbox at $RPC_URL"
else
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required for the sandbox; set NEAR_SANDBOX_URL to a native node" >&2
    exit 1
  fi
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker run -d --name "$CONTAINER" -p 127.0.0.1:3030:3030 "$IMAGE" >/dev/null
  export NEAR_SANDBOX_URL="$RPC_URL"
fi

echo "Waiting for sandbox RPC at $RPC_URL"
ready=0
for _ in $(seq 1 120); do
  if curl -fsS -X POST -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":"1","method":"status","params":[]}' \
    "$RPC_URL" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.5
done
if [[ "$ready" != "1" ]]; then
  echo "sandbox did not become healthy at $RPC_URL" >&2
  exit 1
fi

if [[ -n "${MARKET_WASM:-}" && -f "${MARKET_WASM}" ]]; then
  echo "Using MARKET_WASM=$MARKET_WASM"
else
  cargo build -p ekklesia-market --target wasm32-unknown-unknown --release
  MARKET_WASM=""
  for candidate in \
    target/wasm32-unknown-unknown/release/ekklesia_market.wasm \
    target/near/ekklesia_market/ekklesia_market.wasm; do
    if [[ -f "$candidate" ]]; then
      MARKET_WASM="$candidate"
      break
    fi
  done
  if [[ -z "$MARKET_WASM" ]]; then
    echo "contract WASM not found after cargo build" >&2
    exit 1
  fi
  export MARKET_WASM
fi

"$PYTHON" -m magentic_marketplace.near.bootstrap \
  --network sandbox \
  --rpc-url "$RPC_URL" \
  --contract-id "${MARKET_CONTRACT_ID:-ekklesia.sandbox}" \
  --wasm "$MARKET_WASM"

# shellcheck disable=SC1091
source .sandbox/env.sh
echo "Sandbox ready. Sourced .sandbox/env.sh"
