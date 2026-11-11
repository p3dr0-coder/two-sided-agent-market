# Attribution

This repository is a NEAR port of
[microsoft/multi-agent-marketplace](https://github.com/microsoft/multi-agent-marketplace),
licensed under the MIT License. The original `LICENSE` file is kept unchanged:
Copyright (c) Microsoft Corporation.

- Upstream repository: https://github.com/microsoft/multi-agent-marketplace
- Upstream branch: `main`
- Upstream commit used for the download: `9a651c76` (2026-09-14)
- Local baseline commit created from that download: `126ffe4`
- Paper: *Magentic Marketplace: An Open-Source Environment for Studying Agentic
  Markets*, [arXiv 2510.25779](https://arxiv.org/abs/2510.25779)

## Reused from the origin (MIT)

The Python simulation engine and data were copied into
`packages/ekklesia-market/` and `data/`:

- `src/magentic_marketplace/platform/` — FastAPI server, client, SQLite and
  PostgreSQL controllers, shared models, launcher, logger.
- `src/magentic_marketplace/marketplace/` — protocol, search algorithms,
  messaging actions, LLM agents and clients, shared marketplace models.
- `src/magentic_marketplace/experiments/` — experiment runner, analytics
  engine, analytics models, audit/export/trace utilities.
- `src/magentic_marketplace/ui/` — the served visualizer assets.
- `tests/` — the origin unit tests, with the two TODO comments rephrased and
  the `list` subcommand naming corrected.
- `data/competitive_description/`, `data/contractors/`,
  `data/malicious_description/`, `data/mexican_*`, `data/position_bias/` — the
  YAML scenario corpus.

The import package remains `magentic_marketplace` to avoid churning every
import.

## Modifications

- Distribution and console script renamed to `near-ekklesia`; CLI `prog`
  changed to `near-ekklesia`; `list-experiments` wording removed from the
  `list` subcommand.
- Removed origin-only infrastructure: `.devcontainer/`, `.github/`, `docs/`,
  `experiments/`, `packages/marketplace-visualizer/`,
  `data/data_generation_scripts/`, root/package `uv.lock`, `sample.env`,
  `dev.env`, `TRANSPARENCY.md`, `SECURITY.md`, and the origin root README.
- Added `near-kit>=1.3.0` as the single Python signing stack.
- Added `contracts/market` (Rust, near-sdk 5.30.1): per-agent sub-accounts,
  scoped keys, native-NEAR escrow, soft-rejected proposals, and EVENT_JSON
  welfare counters.
- Added `packages/ekklesia-market/src/magentic_marketplace/near/` — async
  client, settlement adapter, event feed, bootstrap, refund/manipulation
  probes.
- Added deterministic no-LLM agents in
  `marketplace/agents/scripted_business.py` and `scripted_customer.py`.
- `run_experiment.py` now defaults to SQLite (`data/<experiment_name>.db`) and
  optionally wires the settlement protocol; the PostgreSQL path remains.
- `run_analytics.py` gained `near=True`, which cross-checks welfare against
  the event stream and prints the measured headline.
- Added `data/demo_small` (5 businesses × 20 customers reconstructed from the
  origin scenarios), `scripts/fixtures.sh`, `scripts/setup_local.sh`,
  `scripts/demo.sh`, `scripts/measure.sh`, and the sandbox test.
- Added `README.md`, `.env.example`, this attribution file, the Cargo
  workspace, and `.gitignore` entries for local sandbox state.

No origin source file was relicensed; all reused code remains MIT.
