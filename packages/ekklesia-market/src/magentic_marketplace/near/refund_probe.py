"""Exercise the permissionless refund path on a live sandbox.

Posts one valid proposal, escrows it, fast-forwards past expiry, refunds it, and
asserts the proposal reached ``Refunded``. The proposal never settles.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from .client import NearClient
from .probes import business_menu, load_demo_agents, run_probe, single_item


async def probe(client: NearClient) -> None:
    """Run the refund probe against the given client."""
    welfare_before = await client.get_welfare()
    proposal_id = f"refund-probe-{int(time.time() * 1000)}"

    customer, business, customer_agent, business_agent = await load_demo_agents(client)
    custom = business_menu(customer_agent)
    biz = business_menu(business_agent)
    item_name = next(name for name in custom if name in biz)
    unit_price = biz[item_name]
    now = await client.block_timestamp_ns()

    await client.post_proposal(
        proposal_id,
        business,
        customer,
        single_item(item_name, unit_price),
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


async def run_refund_probe(experiment_name: str | None = None) -> None:
    """Run the refund probe with the shared client lifecycle."""
    await run_probe(probe, experiment_name)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-name", default=None)
    args = parser.parse_args()
    asyncio.run(run_refund_probe(args.experiment_name))


if __name__ == "__main__":
    main()
