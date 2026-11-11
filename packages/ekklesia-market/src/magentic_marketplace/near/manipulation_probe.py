"""Drive three invalid proposals through the contract and assert soft rejection.

The three attempts are the doc's unknown-item, mispriced-unit, and wrong-total
cases. Each must leave no proposal and advance ``rejected_proposals`` by one.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from .client import NearClient

INVALID_ATTEMPTS = 3


async def run_probe(experiment_name: str | None = None) -> int:
    """Run the manipulation probe and return the rejected-proposal count."""
    client = NearClient(experiment_name=experiment_name)
    try:
        before = await client.get_welfare()
        baseline = int(before["rejected_proposals"])
        customer = "customer_0001"
        business = "business_0001"
        customer_agent = await client.get_agent(client.account_for(customer))
        business_agent = await client.get_agent(client.account_for(business))
        if customer_agent is None or business_agent is None:
            raise RuntimeError("demo agents are not registered")
        business_menu = {name: int(price) for name, price in business_agent["menu"]}
        item_name = next(iter(business_menu))
        menu_price = business_menu[item_name]
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
    finally:
        await client.close()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-name", default=None)
    args = parser.parse_args()
    asyncio.run(run_probe(args.experiment_name))


if __name__ == "__main__":
    main()
