"""Network-free unit vectors for the near adapter, search, and welfare feed."""

import json
from types import SimpleNamespace

import pytest

from magentic_marketplace.marketplace.actions import Search, SearchAlgorithm
from magentic_marketplace.marketplace.protocol.search.lexical_algo import (
    lexical_rank,
    shingle_overlap_score,
)
from magentic_marketplace.marketplace.protocol.search.utils import (
    paginate_search_response,
)
from magentic_marketplace.marketplace.shared.models import (
    Business,
    BusinessAgentProfile,
)
from magentic_marketplace.near.client import (
    TTL_NS,
    NearClient,
    expiry_ns,
    total_cents,
)
from magentic_marketplace.near.events import NearAnalyticsFeed


def _event(name: str, data: list[dict]) -> dict:
    return {
        "standard": "ekklesia-market",
        "version": "1.0.0",
        "event": name,
        "data": data,
    }


def test_total_cents() -> None:
    """Verify total_cents handles mixed numeric and string prices."""
    items = [
        {"unit_price": 419.15, "quantity": 1},
        {"unit_price": "154.45", "quantity": 2},
    ]
    assert total_cents(items) == 41_915 + 2 * 15_445


def test_expiry_default() -> None:
    """Verify expiry_ns adds TTL_NS when expiry is omitted."""
    assert expiry_ns(None, 1_000) == 1_000 + TTL_NS


def test_expiry_iso() -> None:
    """Verify expiry_ns parses ISO-8601 timestamps."""
    assert expiry_ns("1970-01-01T00:00:01+00:00", 0) == 1_000_000_000


def test_feed_cross_check() -> None:
    """Verify NearAnalyticsFeed cross-checks welfare and formats headline."""
    feed = NearAnalyticsFeed(None)  # type: ignore[arg-type]
    feed.records = [
        {
            "method": "post_proposal",
            "total_gas_burnt": 0,
            "events": [_event("proposal_posted", [{"proposal_id": "p1"}])],
        },
        {
            "method": "post_proposal",
            "total_gas_burnt": 0,
            "events": [_event("proposal_rejected", [{"proposal_id": "p2"}])],
        },
        {
            "method": "settle",
            "total_gas_burnt": 50_000_000_000_000,
            "events": [
                _event(
                    "trade_settled",
                    [
                        {
                            "customer": "c1",
                            "needs_met": True,
                            "customer_utility_delta_cents": "18353",
                        }
                    ],
                )
            ],
        },
    ]
    welfare = {
        "total_customer_utility_cents": "18353",
        "settled_count": 1,
        "rejected_proposals": 1,
        "needs_met_count": 1,
        "purchase_completion_bps": 10_000,
        "registered_customers": 1,
    }
    feed.assert_welfare(welfare)
    line = feed.headline(welfare)
    assert "customer utility = 18353" in line
    assert "0 of 2 attempts (1 soft-rejected)" in line
    assert "gas/settle = 50.000 TGas" in line


def test_client_for_o1(tmp_path) -> None:
    """Verify NearClient resolves sub-account signers via O(1) index."""
    from near import KeyPairSigner, generate_key

    kp = generate_key()
    agents_file = tmp_path / "agents.json"
    agents_file.write_text(
        json.dumps(
            {
                "businesses": {
                    f"b_{i}": {
                        "account_id": f"b{i}.mkt.sandbox",
                        "secret_key": str(kp.secret_key),
                    }
                    for i in range(50)
                },
                "customers": {},
            }
        ),
        encoding="utf-8",
    )
    nc = NearClient(
        contract_id="mkt.sandbox",
        network="sandbox",
        rpc_url="http://127.0.0.1:3030",
        signer=KeyPairSigner("root.sandbox", kp),
        agents_file=agents_file,
    )
    client = nc._client_for("b49.mkt.sandbox")
    assert client.signer is not None
    assert client.signer.account_id == "b49.mkt.sandbox"
    assert nc._account_to_sim_id["b49.mkt.sandbox"] == "b_49"


@pytest.mark.asyncio
async def test_fetch_events_parallel_order(tmp_path, monkeypatch) -> None:
    """Verify fetch_events preserves transaction log order under concurrency."""
    tx_log = tmp_path / "tx.jsonl"
    tx_log.write_text(
        "\n".join(
            json.dumps(
                {
                    "method": "settle",
                    "account": "b1.mkt.sandbox",
                    "tx_hash": f"h{i}",
                    "ts": "2026-11-14T00:00:00Z",
                }
            )
            for i in range(10)
        )
        + "\n",
        encoding="utf-8",
    )

    async def fake_status(tx_hash: str, **_kwargs):
        idx = int(tx_hash[1:])
        return SimpleNamespace(
            transaction_outcome=SimpleNamespace(gas_burnt=1_000 + idx),
            receipts_outcome=[SimpleNamespace(gas_burnt=2_000)],
            logs=[
                "EVENT_JSON:"
                + json.dumps(
                    {
                        "standard": "ekklesia-market",
                        "version": "1.0.0",
                        "event": "trade_settled",
                        "data": [{"proposal_id": f"p{idx}"}],
                    }
                )
            ],
        )

    nc = NearClient(
        contract_id="mkt.sandbox",
        network="sandbox",
        rpc_url="http://127.0.0.1:3030",
        tx_log_path=tx_log,
    )
    monkeypatch.setattr(nc._client, "transaction_status", fake_status)
    try:
        records = await nc.fetch_events(concurrency=4)
    finally:
        await nc.close()
    assert [r["tx_hash"] for r in records] == [f"h{i}" for i in range(10)]
    assert [r["total_gas_burnt"] for r in records] == [3_000 + i for i in range(10)]
    assert records[7]["events"][0]["data"] == [{"proposal_id": "p7"}]


def test_lexical_rank_oracle() -> None:
    """Verify lexical_rank matches pairwise scoring and preserves tie order."""
    base = Business(
        id="b0",
        name="Lock Pro",
        description="Fast repair",
        rating=4.5,
        progenitor_customer="c1",
        menu_features={"Door Lock": 100.0},
        amenity_features={"licensed": True},
        min_price_factor=0.8,
    )
    items = [
        BusinessAgentProfile.from_business(
            base.model_copy(update={"id": "b1", "name": "Bakery", "rating": 4.9})
        ),
        BusinessAgentProfile.from_business(
            base.model_copy(update={"id": "b2", "name": "Lock Smith", "rating": 4.8})
        ),
        BusinessAgentProfile.from_business(
            base.model_copy(update={"id": "b3", "name": "Bakery", "rating": 4.1})
        ),
    ]
    query = "lock smith"
    got = [b.id for b in lexical_rank(query, items)]
    expected = [
        b.id
        for b in sorted(
            items,
            key=lambda b: shingle_overlap_score(
                query, b.business.get_searchable_text()
            ),
            reverse=True,
        )
    ]
    assert got == expected == ["b2", "b1", "b3"]


def test_paginate_search() -> None:
    """Verify paginate_search_response slices pages and computes page counts."""
    base = Business(
        id="b0",
        name="Shop",
        description="Desc",
        rating=4.0,
        progenitor_customer="c1",
        menu_features={"Item": 10.0},
        amenity_features={},
        min_price_factor=0.8,
    )
    items = [
        BusinessAgentProfile.from_business(base.model_copy(update={"id": f"b{i}"}))
        for i in range(5)
    ]
    search = Search(query="", search_algorithm=SearchAlgorithm.SIMPLE, limit=2, page=2)
    resp = paginate_search_response(search, items)
    assert [b.id for b in resp.businesses] == ["b2", "b3"]
    assert resp.total_possible_results == 5
    assert resp.total_pages == 3
