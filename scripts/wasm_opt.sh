#!/usr/bin/env bash
# Post-process the contract wasm with Binaryen's native wasm-opt.
# Usage: wasm_opt.sh INPUT.wasm [OUTPUT.wasm]
# WASM_OPT overrides the binary (default: wasm-opt on PATH).
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: wasm_opt.sh INPUT.wasm [OUTPUT.wasm]" >&2
  exit 2
fi

INPUT="$1"
OUTPUT="${2:-${INPUT%.wasm}.opt.wasm}"
WASM_OPT="${WASM_OPT:-wasm-opt}"

if ! command -v "$WASM_OPT" >/dev/null 2>&1; then
  echo "wasm-opt not found; install Binaryen (>=133) or set WASM_OPT" >&2
  exit 1
fi
if [[ ! -f "$INPUT" ]]; then
  echo "input wasm not found: $INPUT" >&2
  exit 1
fi

"$WASM_OPT" \
  --enable-bulk-memory \
  --enable-sign-ext \
  --enable-mutable-globals \
  --enable-nontrapping-float-to-int \
  -Oz --converge \
  "$INPUT" -o "$OUTPUT"

if [[ ! -s "$OUTPUT" ]]; then
  echo "wasm-opt produced no output: $OUTPUT" >&2
  exit 1
fi

printf '%s\n' "$OUTPUT"
