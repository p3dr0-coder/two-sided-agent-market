"""Shared setup for the sandbox probes.

Both probes start from the demo agents registered by ``scripts/fixtures.sh``
and the deterministic first customer/business pair, so the agent lookups and
menus live here once.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from .client import NearClient

T = TypeVar("T")

DEMO_BIZ = "business_0001"
DEMO_CUST = "customer_0001"


def not_registered() -> RuntimeError:
    """Error raised when the demo fixture agents are missing."""
    return RuntimeError("demo agents are not registered")


def business_menu(agent: dict[str, Any]) -> dict[str, int]:
    """Menu item name -> integer USD cents from an on-chain profile."""
    return {name: int(price) for name, price in agent["menu"]}


def single_item(name: str, price_cents: int) -> list[dict[str, Any]]:
    """One-item proposal payload in origin dollar units (exact cents)."""
    return [{"item_name": name, "quantity": 1, "unit_price": price_cents / 100}]


async def load_demo_agents(
    client: NearClient,
) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    """Fetch the demo customer and business profiles, or fail if unregistered."""
    customer_agent = await client.get_agent(client.account_for(DEMO_CUST))
    business_agent = await client.get_agent(client.account_for(DEMO_BIZ))
    if customer_agent is None or business_agent is None:
        raise not_registered()
    return DEMO_CUST, DEMO_BIZ, customer_agent, business_agent


async def run_probe(
    probe: Callable[[NearClient], Awaitable[T]],
    experiment_name: str | None = None,
) -> T:
    """Run ``probe`` against a fresh client and always close the client."""
    client = NearClient(experiment_name=experiment_name)
    try:
        return await probe(client)
    finally:
        await client.close()
