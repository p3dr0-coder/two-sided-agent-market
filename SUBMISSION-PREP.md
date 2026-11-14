# SUBMISSION-PREP — ekklesia (LOCAL DRAFT, NOT SUBMITTED)

Track: `swarms` (spec `p0-swarms.md`). Deadline 2026-11-14T23:59:00Z.
No push, no remote, no tags, no X post, no submit. Local commit only.

## Judge quickstart (do X → see Y), MEASURED pre-Celesto-only

```
cargo test --workspace    -> 8 passed; 0 failed (370.87s), warnings=0
                             (rust 1.100.0, near-sdk 5.30.2)
pytest packages/ekklesia-market/tests/near -q -> 22 passed, 2 warnings (8.60s)
pytest -q (full)          -> 230 passed, 119 skipped, 3 failed, 3 errors
                             (728.64s) — PRE-EXISTING env gaps: numpy rnr
                             extra absent, no Postgres; diff touches NONE
scripts/wasm_opt.sh       -> EXIT 0, 193,330 B (wasm-opt 116)
deploy oracle raw 234,859 B vs opt 193,330 B -> ORACLE_EQUAL True
uv lock                   -> EXIT 0 (140 pkgs)
uv sync --frozen          -> "Checked 78 packages"
ruff HEAD vs WORKTREE     -> client 6/6, events 4/4, bootstrap 0/0, tests 33/33
                             => NEW=0
git diff 20af4e9..HEAD --check -> EXIT 0
```

Suppression: 50 EXISTING / 0 NEW. Do NOT claim the 3 full-suite failures fixed.

## Recordable demo outline (human records, human posts)

1. Two agent sub-accounts post an OrderProposal and a Payment message.
2. Show the two-sided market clearing on-chain and the welfare/trade-count
   readback. One moment, visible result.
Q-012 video required when judges cannot open the demo. Tags @NEARProtocol,
#NEARHackathon. Main writes no post.

## Payload fields — ALL EMPTY, human supplies every value

| Field | Rule | Value |
|---|---|---|
| requestId | UUID, generated ONCE, reused on 400/503 | EMPTY |
| projectName | 2-80 chars | EMPTY |
| leadName | 2-80 chars | EMPTY |
| email | valid, <=160, max 2 submissions per address (Q-015) | EMPTY |
| size | `1` / `2 - 4` / `4 - 6` / `6 - 8` / `8+` | EMPTY |
| tracks | >=1 track id, each once; `swarms` fits | EMPTY |
| nearAddress | 2-64 lowercase mainnet account the team creates | EMPTY |
| projectUrl | http(s), <=300, public repo, unique | EMPTY |
| demoUrl | http(s), <=300, published X post | EMPTY |
| idea | 20-2000 chars | EMPTY |
| consent | `true` only after verbatim notice + human yes | EMPTY |

Never add `website`. Print full JSON, wait for explicit yes. 201 saved;
400 fix `fields` + same requestId; 403 stop; 409 stop; 413 shorten; 503 retry
same requestId.

## Rules checklist

- Q-003: 8 pre-existing tags, none of the required pair; no README diff link.
  **Not satisfied**; local tags deliberately not created.
- Q-012 video required when judges cannot open the demo.
- Q-014 `LICENSE` present. Q-017 README "Quickstart (sandbox tokens only)"
  line 7 and explicit "Do X -> see Y" section at line 31.
- Q-015 second project on same email must be named in README. Unresolved.
- Q-002/Q-005 disclosure: README "Attribution" line 144 (`ATTRIBUTION.md`,
  port of microsoft/multi-agent-marketplace MIT).
- W8 CORRECTED BOUNDED: core nearcore UPHELD for that state only; dRPC
  gateway N<=3 measured, N>=4 HTTP 400 code 31. Stale 2026-07-21 quotes
  tagged UNVERIFIED and dropped; invalid N>3 ladder RETRACTED.

## Blockers (do not block submission)

Celesto `Trial credit is too low to start this sandbox` → clippy/fmt/
cargo-near-check/full pytest with rnr extra + Postgres BLOCKED-BY-CELESTO.
Firecrawl daily credits BLOCKED. Exa MCP 402 → direct REST. BoxLite §6
MEASURED `By93HSGvFqAo`. Orphan near-sandbox PID 136079 KILLED,
`/tmp/ekk-sb-w3` removed.

## Attestation

Nothing published, pushed, tagged, or submitted. No payload value invented.
