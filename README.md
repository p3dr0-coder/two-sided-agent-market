# near-ekklesia

**The primitive:** a two-sided agent market where every participant is a NEAR
sub-account. A Rust contract turns the origin simulation's `OrderProposal` and
`Payment` messages into native-NEAR escrow, and emits the origin welfare
formula as NEP-297 `EVENT_JSON` logs. Businesses get a FunctionCall key scoped
to `post_proposal,settle`; customers get a FullAccess key on their own
sub-account because only a FullAccess key can attach the escrow deposit.
Welfare is readable from `get_welfare()` and reconstructable from
`TradeSettled` events.

This is a port of
[microsoft/multi-agent-marketplace](https://github.com/microsoft/multi-agent-marketplace)
(MIT) to NEAR. See [ATTRIBUTION.md](ATTRIBUTION.md).

## Quickstart (sandbox tokens only)

Prerequisites: Docker, Rust 1.95 (the `rust-toolchain.toml` pins it), Python
3.11+, and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras
source .venv/bin/activate
bash scripts/demo.sh
```

`scripts/demo.sh`:

1. starts a fresh `nearprotocol/sandbox:2.13.4` container on
   `127.0.0.1:3030`;
2. builds `contracts/market` for `wasm32-unknown-unknown`, creates
   `ekklesia.sandbox`, deploys it, and initializes `new({"fee_bps": 0})`;
3. registers five business sub-accounts (`b1..b5.ekklesia.sandbox`) and twenty
   customer sub-accounts (`c1..c20.ekklesia.sandbox`), generating one key per
   agent and writing `.sandbox/agents.json` with mode `0600`;
4. funds each customer with its escrow plus gas money;
5. runs the deterministic no-LLM market into `data/demo.db`;
6. analyzes the simulation and prints the on-chain headline;
7. posts, escrows, expires, and refunds one proposal to prove the refund path.


No Docker? Start a native nearcore sandbox (`near-sandbox --home DIR init`,
then `near-sandbox --home DIR run`), export `NEAR_SANDBOX_URL`,
`NEAR_ROOT_ACCOUNT`, `NEAR_ROOT_PRIVATE_KEY`, and a matching
`MARKET_CONTRACT_ID` (e.g. `ekklesia.test.near`), then run the same scripts;
`setup_local.sh` uses the native node instead of starting a container.

No LLM keys and no real funds are used. The demo peg is `1 NEAR = $1000`
(`CENTS_PER_NEAR = 100_000`), so `1` USD cent escrows exactly `1e19` yoctoNEAR.

## Do X -> see Y

| Do this | See this |
|---|---|
| `bash scripts/demo.sh` | a fresh sandbox, 5x20 registration, `data/demo.db`, a computed headline, and `refund probe OK` |
| `near-ekklesia run data/demo_small --near --scripted --experiment-name demo --db-type sqlite --override-db` | the scripted market runs over SQLite and settles every payment on-chain |
| `near-ekklesia analyze data/demo.db --db-type sqlite --near` | the origin analytics report plus the on-chain headline and a welfare assertion |
| `bash scripts/measure.sh` | the same run under experiment `numbers`, three invalid proposals, and exactly one headline line |
| `python -m magentic_marketplace.near.bootstrap --network testnet --no-deploy` | registers testnet sub-accounts from `NEAR_ACCOUNT_ID`/`NEAR_PRIVATE_KEY` |
| `pytest packages/ekklesia-market/tests/near` | exact-cent, fixture-coverage, adapter-routing, and scripted-ranking tests (no network) |
| `cargo test --workspace` | the pure-Rust unit vectors and the near-workspaces sandbox test |

The `run` command saves `data/<experiment_name>.db` by default; `--db-path`
overrides it. `--override-db` unlinks an existing SQLite file (or drops the
Postgres schema). Postgres is opt-in: `docker compose up -d postgres` and
`--db-type postgres`. SQLite is the default because the scripted demo is
sequential.

`scripts/measure.sh` prints one measured headline. Sandbox run 2026-11-12
(`nearprotocol/sandbox`-equivalent native nearcore 2.14, 5 businesses × 20
customers, `fee_bps = 0`):

```
Total marketplace customer utility = 1542308; purchase completion rate = 100% (R = 10000/100); needs-met = 20/20; invalid proposals accepted = 0 of 23 attempts (3 soft-rejected); gas/settle = 3.617 TGas
```

`W = 1,542,308` USD cents (`$15,423.08`), `R = 100%`, `N = 20/20`, `K = 23`,
`J = 3`, `G = 3.617 TGas` (median). The same W/R/N/G values were produced by
two independent fresh sandbox runs (`demo.sh`: 20 attempts, 0 rejected;
`measure.sh`: 23 attempts, 3 rejected). The transcript is
`remote-w4/w4-demo.log` and `remote-w4/w4-numbers.log` in the coordinator
workspace. Bounds: 20 customers × 5 businesses is a port-only scale; the
paper's §4.1 markets are 33/99 and 100/300, so W and N are not
paper-comparable.

## Architecture map

```
contracts/market/src/
  lib.rs          Contract state + #[init] new(fee_bps)
  types.rs        Role, AgentProfile, OrderItem, Proposal(+Status),
                  TradeReceipt, WelfareCounters, WelfareSummary, caps, peg,
                  StorageKey prefixes b"a"/b"p"/b"t"/b"c"/b"n"/b"q"
  settlement.rs   register_agent, post_proposal, accept_proposal, settle, refund
  welfare.rs      get_welfare, get_proposal, get_agent, get_trade_count
  events.rs       #[near(event_json(standard="ekklesia-market"))]
packages/ekklesia-market/src/magentic_marketplace/
  near/client.py       async near-kit client + tx log + exact cents
  near/adapter.py      NearSettlementProtocol(SimpleMarketplaceProtocol)
  near/events.py       EVENT_JSON feed, welfare assertion, headline
  near/bootstrap.py    deploy/init/5x20 registration/funding/agents.json
  near/refund_probe.py / manipulation_probe.py
  marketplace/agents/scripted_business.py / scripted_customer.py
  experiments/run_experiment.py  SQLite default, optional NEAR settlement
  experiments/run_analytics.py   origin formulas + --near cross-check
tests/sandbox_market.rs           near-workspaces integration test
scripts/fixtures.sh               reproduces data/demo_small deterministically
```

The simulation engine (protocol, search, database, analytics) is the origin
code; settlement is additive. The settlement adapter always delegates to the
original protocol after routing a message, so the simulation database still
contains the full trace.

### Agent model

`register_agent(agent_name, profile, public_key)` derives
`"{agent_name}.{contract}"`, creates it, transfers the 0.007 NEAR account
creation cost, and installs:

- **Business:** `add_access_key_allowance(pk, Unlimited, contract,
  "post_proposal,settle")`. A FunctionCall key cannot attach NEAR, so proposal
  storage draws on the reserve funded at registration. Settlement pays
  `profile.payout_account`, which must have a FullAccess key (the scoped
  business sub-account is rejected as a payout target).
- **Customer:** `add_full_access_key(pk)` on its own sub-account, because
  `accept_proposal` must attach the escrow. The bootstrap funds that account.

### Contract methods

| Method | Caller | Behavior |
|---|---|---|
| `new(fee_bps)` | deployer | owner = predecessor; fee must be ≤ 10,000 bps |
| `register_agent(agent_name, profile, public_key)` | orchestrator, payable | validates name/caps, rejects duplicates, quotes storage + 0.007 NEAR |
| `post_proposal(proposal_id, customer, items, total_price, expiry)` | business | non-payable; exact-cent checks; invalid input is a **soft reject** (counter + event, nothing stored) |
| `accept_proposal(proposal_id)` | customer, payable | status `Posted`, exact `total_price * 1e19` deposit, not expired; becomes `Funded` |
| `settle(proposal_id)` | business | status `Funded`; sets `Settled` before paying `price - fee` to `payout_account`; updates welfare; emits `trade_settled` + `welfare_snapshot` |
| `refund(proposal_id)` | anyone | status `Funded` and expired; sets `Refunded` before returning escrow to the customer |
| `get_welfare()` | free | counters + completion basis points + average utility |
| `get_proposal(id)`, `get_agent(id)`, `get_trade_count()` | free | state reads |

Welfare is the origin formula in integer cents: on the first matching trade for
a customer, `utility += 2 * requested_total_cents - price_cents`; every other
settled trade subtracts `price_cents`. `purchasing_customers` counts the first
payment of a distinct customer, `needs_met_count` counts a customer once, and
`purchase_completion_bps = purchasing_customers * 10000 /
registered_customers`.

### Events

```json
EVENT_JSON:{"standard":"ekklesia-market","version":"1.0.0","event":"trade_settled","data":[{"proposal_id":"...","customer":"c1.ekklesia.sandbox","business":"b1.ekklesia.sandbox","price_cents":"15445","fee_cents":"0","needs_met":true,"customer_utility_delta_cents":"18353","business_revenue_delta_cents":"15445"}]}
```

Events: `agent_registered`, `proposal_posted`, `proposal_accepted`,
`trade_settled`, `proposal_rejected`, `welfare_snapshot`. The Python feed keys
on those snake_case names and asserts
`get_welfare().total_customer_utility_cents == Σ trade_settled.customer_utility_delta_cents`.

### Testnet deployment

```bash
near account create-account sponsor-by-faucet-service ekklesia.testnet \
  autogenerate-new-keypair save-to-keychain network-config testnet create
cargo near build
cargo near deploy ekklesia.testnet
near contract call-function as-transaction ekklesia.testnet new \
  json-args '{"fee_bps": 0}' prepaid-gas '100 Tgas' \
  attached-deposit '0 N' sign-as ekklesia.testnet \
  network-config testnet sign-with-keychain send
export MARKET_CONTRACT_ID=ekklesia.testnet NEAR_NETWORK=testnet \
  NEAR_RPC_URL=https://test.rpc.fastnear.com
python -m magentic_marketplace.near.bootstrap --network testnet --no-deploy
```

Testnet keys belong in your shell or a gitignored `.env`; nothing secret is
committed. The demo never needs testnet funds.

## Data

`data/demo_small` is 5 businesses × 20 customers. Origin
`competitive_description/contractors_control` is only 3×3, so the fixture uses
those three pairs plus two pairs from `contractors/contractors_10_30`
(`business_0005/customer_0002`, `business_0008/customer_0003`) and replicates
each base customer four times with fresh ids/names. Every customer menu key is
covered by the union of the five business menus, and every required amenity is
true in that customer's base business. `scripts/fixtures.sh` reproduces and
asserts the layout.

## Limits and trust model

- **Sandbox/demo only.** No real funds, no mainnet deployment in this repo.
- **Honest valuation inputs.** Welfare is computed from the committed YAML
  prices. The contract checks exact cents and rejects invalid proposals, but it
  cannot know whether a customer's stated valuation is honest.
- **Orchestrator trust.** Anyone can call `register_agent` for a new
  sub-account; the bootstrap account pays for it. The owner is fixed at
  initialization and fees cannot be changed.
- **Payout discipline.** Business revenue goes to `payout_account`; a
  FullAccess account is required or the revenue would be trapped in an
  FCK-only account.
- **Expiry semantics.** Proposals use block timestamps. Refunds are
  permissionless after expiry, so an unresponsive business cannot hold escrow
  forever.
- **No upgrade proxy.** A NEAR upgrade redeploys WASM to the same account with
  `#[init(ignore_state)]` migration if the layout changes.

## Verification status

This commit is the W1 scaffold. No local build or test was executed while
producing it; the remote gate commands and their recorded output belong in
`WORKLOG.md`. The test commands above are the intended verification surface:
`cargo test --workspace`, `pytest packages/ekklesia-market/tests/near`, and
`bash scripts/demo.sh`.

## Attribution

Origin: [microsoft/multi-agent-marketplace](https://github.com/microsoft/multi-agent-marketplace),
MIT. Paper: [arXiv 2510.25779](https://arxiv.org/abs/2510.25779). Details and
the exact reused directories/modifications are in
[ATTRIBUTION.md](ATTRIBUTION.md). `LICENSE` is the unchanged Microsoft MIT
license.
