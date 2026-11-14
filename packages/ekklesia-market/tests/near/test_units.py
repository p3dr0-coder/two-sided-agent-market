"""Network-free unit vectors for the near adapter math and welfare feed."""

from magentic_marketplace.near.client import TTL_NS, expiry_ns, total_cents
from magentic_marketplace.near.events import NearAnalyticsFeed


def _event(name: str, data: list[dict]) -> dict:
    return {
        "standard": "ekklesia-market",
        "version": "1.0.0",
        "event": name,
        "data": data,
    }


def test_total_cents() -> None:
    items = [
        {"unit_price": 419.15, "quantity": 1},
        {"unit_price": "154.45", "quantity": 2},
    ]
    assert total_cents(items) == 41_915 + 2 * 15_445


def test_expiry_default() -> None:
    assert expiry_ns(None, 1_000) == 1_000 + TTL_NS


def test_expiry_parses_iso_strings() -> None:
    assert expiry_ns("1970-01-01T00:00:01+00:00", 0) == 1_000_000_000


def test_feed_cross_check() -> None:
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
