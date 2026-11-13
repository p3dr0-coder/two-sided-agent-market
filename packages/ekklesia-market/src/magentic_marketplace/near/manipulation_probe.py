"""Drive three invalid proposals through the contract and assert soft rejection.

The three attempts are the doc's unknown-item, mispriced-unit, and wrong-total
cases. Each must leave no proposal and advance ``rejected_proposals`` by one.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from .client import NearClient
from .probes import business_menu, load_demo_agents, run_probe

INVALID_ATTEMPTS = 3


async def probe(client: NearClient) -> int:
    """Run the manipulation probe and return the rejected-proposal count."""
    before = await client.get_welfare()
    baseline = int(before["rejected_proposals"])
    customer, business, _customer_agent, business_agent = await load_demo_agents(
        client
    )
    menu = business_menu(business_agent)
    item_name = next(iter(menu))
    menu_price = menu[item_name]
    expiry = await client.block_timestamp_ns() + 300_000_000_000
    suffix = int(time.time() * 1000)

    attempts = [
        (
            f"manip-unknown-{suffix}",
            [{"item_name": "Unobtainium", "quantity": 1, "unit_price": 100}],
            100,
        ),
        (
            f"manip-price-{suffix}",
            [
                {
                    "item_name": item_name,
                    "quantity": 1,
                    "unit_price": (menu_price + 1) / 100,
                }
            ],
            menu_price + 1,
        ),
        (
            f"manip-total-{suffix}",
            [{"item_name": item_name, "quantity": 1, "unit_price": menu_price / 100}],
            menu_price + 1,
        ),
    ]

    for proposal_id, items, total in attempts:
        await client.post_proposal(
            proposal_id, business, customer, items, total, expiry
        )
        stored = await client.get_proposal(proposal_id)
        if stored is not None:
            raise AssertionError(f"invalid proposal {proposal_id} was stored")

    after = await client.get_welfare()
    rejected = int(after["rejected_proposals"]) - baseline
    if rejected != INVALID_ATTEMPTS:
        raise AssertionError(
            f"expected {INVALID_ATTEMPTS} rejections, measured {rejected}"
        )
    print(
        f"manipulation probe OK: {INVALID_ATTEMPTS} invalid proposals, "
        f"{rejected} soft-rejected, 0 stored"
    )
    return int(after["rejected_proposals"])


async def run_manipulation_probe(experiment_name: str | None = None) -> int:
    """Run the manipulation probe with the shared client lifecycle."""
    return await run_probe(probe, experiment_name)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-name", default=None)
    args = parser.parse_args()
    asyncio.run(run_manipulation_probe(args.experiment_name))


if __name__ == "__main__":
    main()
