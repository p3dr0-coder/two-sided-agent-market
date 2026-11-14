# SUBMISSION-PREP — ekklesia (LOCAL DRAFT, NOT SUBMITTED)

Tracks: `swarms`, `agents`. Deadline 2026-11-14T23:59:00Z. No push, no remote, no tag, no X post, no submit. Local commit only.

Judge quickstart, measured:

```
cargo test --workspace       -> 8 passed, 0 failed, plus 1 sandbox pass (rust 1.100.0, near-sdk 5.30.2)
pytest packages/ekklesia-market/tests/near -q -> 26 passed (9 s wall). pytest -q (full) -> 242 passed, 117 skipped (359 collected)
cargo build --release --target wasm32 -> 234,809 B raw. cargo near build non-reproducible-wasm -> 193,807 B
scripts/wasm_opt.sh -> EXIT 0, 193,278 B (wasm-opt 116). ruff check, ruff format --check, pyright -> 0 findings
uv lock -> EXIT 0 (140 pkgs). uv sync --frozen -> "Checked 78 packages"
ruff HEAD vs WORKTREE 20af4e9 -> client 6/6, events 4/4, bootstrap 0/0, tests 33/33 => NEW=0
git diff 20af4e9..HEAD --check -> EXIT 0
```

Suppression markers: 50 EXISTING, 0 NEW. The 117 skipped tests need the PostgreSQL backend.

Demo outline, human records and human posts:

1. Two agent sub-accounts post an `OrderProposal` and a `Payment` message.
2. Show the two-sided market clearing on-chain and the welfare/trade-count readback.

Q-012 video is required when judges cannot open the demo. Tags @NEARProtocol, #NEARHackathon. Main writes no post.

Payload fields, all EMPTY, and the human supplies every value:

| Field | Rule |
|---|---|
| requestId | UUID, generated ONCE, reused on 400/503 |
| projectName | 2-80 chars |
| leadName | 2-80 chars |
| email | valid, <=160, max 2 submissions per address (Q-015) |
| size | `1` / `2 - 4` / `4 - 6` / `6 - 8` / `8+` |
| tracks | >=1 track id, each once; `swarms`, `agents` fit |
| nearAddress | 2-64 lowercase mainnet account the team creates |
| projectUrl | http(s), <=300, public repo, unique |
| demoUrl | http(s), <=300, published X post |
| idea | 20-2000 chars |
| consent | `true` only after verbatim notice + human yes |

Never add `website`. Print the full JSON and wait for an explicit yes. A 201 is saved. A 400 needs a `fields` fix with the same requestId. A 403 or a 409 stops. A 413 shortens. A 503 retries the same requestId.

- Q-003: 8 pre-existing tags, none of the required pair, and no README diff link. **Not satisfied**, local tags stay uncreated.
- Q-012 covers judges who cannot open the demo. Q-014 finds `LICENSE` present. Q-017 finds the "Quickstart (sandbox tokens only)" line and the "Do X -> see Y" table.
- Q-015 needs a second project on the same email named in README. Unresolved. Q-002/Q-005 disclosure is the README attribution line (`ATTRIBUTION.md`, port of microsoft/multi-agent-marketplace MIT).
- W8 CORRECTED BOUNDED: core nearcore is UPHELD for that state only. The dRPC gateway answers at N<=3 and returns HTTP 400 code 31 at N>=4.

Blockers, which do not block submission. Celesto blocked clippy, fmt, `cargo-near-check`, and full pytest with the rnr extra plus Postgres. The reason is `Trial credit is too low to start this sandbox`. Firecrawl daily credits were blocked, and Exa MCP returned 402, so direct REST was used. BoxLite §6 is MEASURED `By93HSGvFqAo`. The orphan near-sandbox PID 136079 is KILLED and `/tmp/ekk-sb-w3` is removed.

Attestation: nothing is published, pushed, tagged, or submitted, and no payload value is invented.
