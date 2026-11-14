# near-ekklesia

Tracks: `swarms`, `agents` (end 2026-11-14T23:59:00Z) · License: MIT · Baseline: tag `pre-hackathon` @ `126ffe4` ([microsoft/multi-agent-marketplace](https://github.com/microsoft/multi-agent-marketplace)); diff `git diff pre-hackathon..hackathon-submission` · Q-015 sibling **philia** (social on NEAR, tracks `social`, `open`).

Business and customer agents trade in a two-sided market: Rust contracts map orders and payments to native-NEAR escrow, with function-call keys scoped to post and settle. Welfare is emitted as NEP-297 events, so any dashboard can verify outcomes without trusting the operator.

```mermaid
sequenceDiagram
    accTitle: ekklesia runtime flow
    accDescr: Operator deploys the market, registers agents, runs scripted orders, then settles and reads welfare.
    autonumber
    participant U as Operator
    participant P as Python marketplace
    participant R as NEAR RPC
    participant B as Sandbox node
    participant M as Market contract
    participant S as Search module
    rect rgba(226,238,255,0.20)
    Note over U,M: PHASE 1 — Deploy market
    U->>R: cargo near deploy, 193,807 B wasm
    R->>M: new(fee_bps=0), fee_bps <= 10,000, owner is predecessor
    end
    rect rgba(230,247,235,0.20)
    Note over P,B: PHASE 2 — Register agents and keys
    P->>+M: register_agent(agent_name, profile, public_key), deposit >= storage + 0.007 NEAR
    M->>B: sub-account agent_name.contract, scoped key post_proposal,settle
    M-->>-P: scoped key installed, customer key FullAccess
    end
    rect rgba(255,244,214,0.20)
    Note over P,M: PHASE 3 — Post and fund orders
    P->>+M: post_proposal(proposal_id, items, total_price, expiry)
    alt exact cents, known agent, unexpired
    M-->>-P: Posted, proposal_posted event
    else bad input
    M-->>P: soft reject, counter and proposal_rejected event
    end
    P->>+M: accept_proposal(proposal_id), total_price * 1e19 yoctoNEAR
    M-->>-P: Funded, proposal_accepted event
    end
    rect rgba(243,232,255,0.20)
    Note over P,S: PHASE 4-6 — Poll, search, rank
    P->>P: fetch_messages from the simulation database (0.5 s polling)
    P->>+S: execute_search, SearchAlgorithm.FILTERED or LEXICAL
    S->>S: _add_constraint_query on rating, amenities, menu items
    S->>S: lexical_rank, or is_subset plus rating sort
    S-->>-P: ranked businesses, paginated like origin search
    end
    rect rgba(255,248,225,0.20)
    Note over P,M: PHASE 7 — Settle and read welfare
    P->>+M: settle(proposal_id) as the business
    M-->>-P: Settled, price minus fee to payout_account
    opt funded but expired
    P->>+M: refund(proposal_id) from any caller
    M-->>-P: Refunded, escrow returns to the customer
    end
    P->>+M: get_welfare(), then assert_welfare against TradeSettled
    M-->>-P: counters plus gas per settle
    end
```

```bash
near account create-account sponsor-by-faucet-service ekklesia.testnet autogenerate-new-keypair save-to-keychain network-config testnet create
cargo near build && cargo near deploy ekklesia.testnet
near contract call-function as-transaction ekklesia.testnet new json-args '{"fee_bps": 0}' prepaid-gas '100 Tgas' attached-deposit '0 N' sign-as ekklesia.testnet network-config testnet sign-with-keychain send
export MARKET_CONTRACT_ID=ekklesia.testnet NEAR_NETWORK=testnet NEAR_RPC_URL=https://test.rpc.fastnear.com
python -m magentic_marketplace.near.bootstrap --network testnet --no-deploy
```

| Do this | See this | Proves |
|---|---|---|
| `uv sync --all-extras` → `bash scripts/demo.sh` | fresh sandbox, `data/demo.db` | quickstart boots in 7 steps |
| `bash scripts/demo.sh` | sandbox, 5 businesses x 20 customers, headline + `refund probe OK` | full loop on chain |
| `near-ekklesia run data/demo_small --near --scripted --experiment-name demo --db-type sqlite --override-db` | scripted SQLite run | on-chain settlement |
| `near-ekklesia analyze data/demo.db --db-type sqlite --near` | origin analytics, welfare assertion | headline verified |
| `bash scripts/measure.sh` | one measured headline, `G = 3.617 TGas` | cost is measured |
| `pytest packages/ekklesia-market/tests/near` | near adapter tests pass | settlement logic tested |
| `get_welfare()` | `W = 1,542,308` USD cents headline | welfare as NEP-297 events |
| `python -m magentic_marketplace.near.bootstrap --network testnet --no-deploy` | testnet registration | deploy path (see bash) |
| `settle` as business FunctionCall key | business FunctionCall key cannot attach the escrow deposit; payout account must hold a FullAccess key | "sandbox and demo only, no real fund, no mainnet deploy; exact cents checked, not truthful YAML" |

[ATTRIBUTION](ATTRIBUTION.md) · [LICENSE](./LICENSE) · [microsoft/multi-agent-marketplace](https://github.com/microsoft/multi-agent-marketplace) · [arXiv 2510.25779](https://arxiv.org/abs/2510.25779)
