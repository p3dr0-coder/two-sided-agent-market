# Attribution

NEAR port of [microsoft/multi-agent-marketplace](https://github.com/microsoft/multi-agent-marketplace) (MIT). `LICENSE` unchanged: Copyright (c) Microsoft Corporation. Upstream https://github.com/microsoft/multi-agent-marketplace (`main`, `9a651c76`, 2026-09-14), local baseline `126ffe4`, paper *Magentic Marketplace* ([arXiv 2510.25779](https://arxiv.org/abs/2510.25779)).

Reused from origin (MIT), copied into `packages/ekklesia-market/` and `data/`, import package `magentic_marketplace`:

- `src/magentic_marketplace/platform/` — FastAPI server, client, SQLite/PostgreSQL controllers, models, launcher, logger. `src/magentic_marketplace/marketplace/` — protocol, search algorithms, actions, LLM agents/clients, marketplace models.
- `src/magentic_marketplace/experiments/` — runner, analytics engine/models, audit/export/trace utilities. `src/magentic_marketplace/ui/` — served visualizer assets.
- `tests/` — origin unit tests (two TODO comments rephrased, `list` subcommand naming fixed). `data/competitive_description/`, `data/contractors/`, `data/malicious_description/`, `data/mexican_*`, `data/position_bias/` — YAML corpus.

Modified:

- Package, CLI and `prog` renamed to `near-ekklesia`, `list` dropped `list-experiments` wording. Added `near-kit>=1.3.0` as the single Python signing stack.
- Removed origin infra: `.devcontainer/`, `.github/`, `docs/`, `experiments/`, `packages/marketplace-visualizer/`, `data/data_generation_scripts/`, origin `uv.lock`, `sample.env`, `dev.env`, `TRANSPARENCY.md`, `SECURITY.md`, origin README.
- Added `contracts/market` (Rust, near-sdk 5.30.2): sub-accounts, scoped keys, escrow, soft rejects, EVENT_JSON welfare. Added `packages/ekklesia-market/src/magentic_marketplace/near/` (client, adapter, events, bootstrap, probes) and deterministic agents in `marketplace/agents/scripted_business.py`, `scripted_customer.py`.
- `run_experiment.py` defaults to SQLite (`data/<experiment_name>.db`) and keeps the Postgres path. `run_analytics.py` adds the `near=True` cross-check.
- Added `data/demo_small` (5×20), `scripts/fixtures.sh`, `scripts/setup_local.sh`, `scripts/demo.sh`, `scripts/measure.sh`, the sandbox test, `README.md`, `.env.example`, `ATTRIBUTION.md`, the Cargo workspace, and `.gitignore` entries. All reused code remains MIT.
