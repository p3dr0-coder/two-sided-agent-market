"""Exercise the permissionless refund path on a live sandbox.

Posts one valid proposal, escrows it, fast-forwards past expiry, refunds it, and
asserts the proposal reached ``Refunded``. The proposal never settles.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from .client import NearClient


async def run_probe(experiment_name: str | None = None) -> None:
    """Run the refund probe against the configured contract."""
    client = NearClient(experiment_name=experiment_name)
    try:
        welfare_before = await client.get_welfare()
        proposal_id = f"refund-probe-{int(time.time() * 1000)}"

        customer = "customer_0001"
        business = "business_0001"
        customer_agent = await client.get_agent(client.account_for(customer))
        business_agent = await client.get_agent(client.account_for(business))
        if customer_agent is None or business_agent is None:
            raise RuntimeError("demo agents are not registered")

        customer_menu = {name: int(price) for name, price in customer_agent["menu"]}
        business_menu = {name: int(price) for name, price in business_agent["menu"]}
        item_name = next(name for name in customer_menu if name in business_menu)
        unit_price = business_menu[item_name]
        now = await client.block_timestamp_ns()

        await client.post_proposal(
            proposal_id,
            business,
            customer,
            [{"item_name": item_name, "quantity": 1, "unit_price": unit_price / 100}],
            unit_price,
            now + 30_000_000_000,
        )
        await client.accept_proposal(proposal_id, customer)
        funded = await client.get_proposal(proposal_id)
        if funded is None or funded["status"] != "Funded":
            raise RuntimeError(f"expected Funded, got {funded}")

        await client.fast_forward(40)
        await client.refund(proposal_id, client.account_for(customer))
        refunded = await client.get_proposal(proposal_id)
        if refunded is None or refunded["status"] != "Refunded":
            raise RuntimeError(f"expected Refunded, got {refunded}")

        welfare_after = await client.get_welfare()
        if welfare_after["settled_count"] != welfare_before["settled_count"]:
            raise RuntimeError("refund must not increment settled_count")
        print(f"refund probe OK: {proposal_id} -> Refunded; escrow returned")
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
