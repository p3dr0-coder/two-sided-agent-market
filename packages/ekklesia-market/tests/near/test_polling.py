"""Polling defaults stay at the compute-reduced 0.5 s interval."""

import asyncio

import pytest

from magentic_marketplace.marketplace.actions import FetchMessagesResponse
from magentic_marketplace.marketplace.agents.scripted_business import (
    DeterministicBusinessAgent,
)
from magentic_marketplace.marketplace.agents.scripted_customer import (
    DeterministicCustomerAgent,
)
from magentic_marketplace.marketplace.shared.models import Business, Customer


async def _empty_messages() -> FetchMessagesResponse:
    return FetchMessagesResponse(messages=[], has_more=False)


@pytest.mark.asyncio
async def test_biz_poll_default(monkeypatch) -> None:
    """Verify business agents default to 0.5 s polling."""
    business = Business(
        id="b1",
        name="B",
        description="",
        rating=1.0,
        progenitor_customer="c1",
        menu_features={"x": 1.0},
        amenity_features={},
        min_price_factor=1.0,
    )
    agent = DeterministicBusinessAgent(business, "http://127.0.0.1:1", None)  # type: ignore[arg-type]
    monkeypatch.setattr(agent, "fetch_messages", _empty_messages)
    calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        calls.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    await agent.step()
    assert calls == [0.5]


@pytest.mark.asyncio
async def test_cust_poll_default(monkeypatch) -> None:
    """Verify customer agents default to 0.5 s polling."""
    customer = Customer(
        id="c1",
        name="C",
        request="x",
        menu_features={"x": 1.0},
        amenity_features=[],
    )
    agent = DeterministicCustomerAgent(customer, "http://127.0.0.1:1")
    agent._ranked = [(type("P", (), {"id": "b1"})(), 100)]  # type: ignore[list-item]
    monkeypatch.setattr(agent, "fetch_messages", _empty_messages)
    calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        calls.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    await agent.step()
    assert calls == [0.5]
