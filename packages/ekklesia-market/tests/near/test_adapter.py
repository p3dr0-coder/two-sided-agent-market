"""Adapter routes only OrderProposal/Payment and still records the message."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from magentic_marketplace.marketplace.actions import (
    OrderItem,
    OrderProposal,
    Payment,
    SendMessage,
    TextMessage,
)
from magentic_marketplace.marketplace.protocol.protocol import SimpleMarketplaceProtocol
from magentic_marketplace.near.adapter import NearSettlementProtocol
from magentic_marketplace.platform.database.base import (
    ActionTableController,
    AgentTableController,
    BaseDatabaseController,
    LogTableController,
)
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
    AgentProfile,
)


class DummyDB(BaseDatabaseController):
    """Typed stub database controller for protocol-routing unit tests."""

    @property
    def agents(self) -> AgentTableController:
        """Unused agents controller."""
        raise NotImplementedError

    @property
    def actions(self) -> ActionTableController:
        """Unused actions controller."""
        raise NotImplementedError

    @property
    def logs(self) -> LogTableController:
        """Unused logs controller."""
        raise NotImplementedError

    @property
    def row_index_column(self) -> str:
        """Unused row index column."""
        return "id"

    async def execute(self, command):
        """Unused raw SQL executor."""
        raise NotImplementedError


class FakeNear:
    """Record settlement calls without a network."""

    def __init__(self):
        """Initialize an empty call recorder."""
        self.calls: list[tuple] = []

    async def block_timestamp_ns(self) -> int:
        """Return a fixed timestamp in nanoseconds."""
        return 1_000_000_000

    async def post_proposal(self, **kwargs):
        """Record a post_proposal call."""
        self.calls.append(("post_proposal", kwargs))

    async def accept_proposal(self, **kwargs):
        """Record an accept_proposal call."""
        self.calls.append(("accept_proposal", kwargs))


def send_message(
    message, *, from_agent_id="business_0001", to_agent_id="customer_0001"
) -> SendMessage:
    """Build a SendMessage action for tests."""
    return SendMessage(
        from_agent_id=from_agent_id,
        to_agent_id=to_agent_id,
        created_at=datetime.now(UTC),
        message=message,
    )


async def test_route_and_delegate():
    """Verify proposals and payments route on-chain and delegate."""
    near = FakeNear()
    protocol = NearSettlementProtocol(near)  # type: ignore[arg-type]
    delegated: list[ActionExecutionRequest] = []

    async def fake_execute(self, *, agent, action, database):
        delegated.append(action)
        return ActionExecutionResult(content={"recorded": True})

    proposal = OrderProposal(
        id="p1",
        items=[
            OrderItem(
                id="b1:item",
                item_name="Door Lock Replacement",
                quantity=1,
                unit_price=154.45,
            )
        ],
        total_price=154.45,
    )
    payment = Payment(proposal_message_id="p1", payment_method="near")

    with patch.object(SimpleMarketplaceProtocol, "execute_action", fake_execute):
        result = await protocol.execute_action(
            agent=AgentProfile(id="business_0001"),
            action=ActionExecutionRequest(
                name="SendMessage",
                parameters=send_message(proposal).model_dump(mode="json"),
            ),
            database=DummyDB(),
        )
        assert result.content == {"recorded": True}
        await protocol.execute_action(
            agent=AgentProfile(id="customer_0001"),
            action=ActionExecutionRequest(
                name="SendMessage",
                parameters=send_message(
                    payment,
                    from_agent_id="customer_0001",
                    to_agent_id="business_0001",
                ).model_dump(mode="json"),
            ),
            database=DummyDB(),
        )

    assert near.calls[0][0] == "post_proposal"
    assert near.calls[0][1]["proposal_id"] == "p1"
    assert near.calls[0][1]["total_price_cents"] == 15_445
    assert near.calls[0][1]["expiry_ns_value"] == 1_000_000_000 + 300_000_000_000
    assert near.calls[1] == (
        "accept_proposal",
        {"proposal_id": "p1", "customer_sim_id": "customer_0001"},
    )
    assert len(delegated) == 2


async def test_text_untouched():
    """Verify plain text messages do not trigger settlement calls."""
    near = FakeNear()
    protocol = NearSettlementProtocol(near)  # type: ignore[arg-type]
    delegated: list[ActionExecutionRequest] = []

    async def fake_execute(self, *, agent, action, database):
        delegated.append(action)
        return ActionExecutionResult(content={})

    with patch.object(SimpleMarketplaceProtocol, "execute_action", fake_execute):
        await protocol.execute_action(
            agent=AgentProfile(id="business_0001"),
            action=ActionExecutionRequest(
                name="SendMessage",
                parameters=send_message(TextMessage(content="hello")).model_dump(
                    mode="json"
                ),
            ),
            database=DummyDB(),
        )

    assert near.calls == []
    assert len(delegated) == 1


async def test_error_after_delegate():
    """Verify routing errors still delegate to the protocol before raising."""

    class BrokenNear(FakeNear):
        async def post_proposal(self, **kwargs):
            raise RuntimeError("chain rejected")

    protocol = NearSettlementProtocol(BrokenNear())  # type: ignore[arg-type]
    delegated: list[ActionExecutionRequest] = []

    async def fake_execute(self, *, agent, action, database):
        delegated.append(action)
        return ActionExecutionResult(content={})

    proposal = OrderProposal(
        id="p2",
        items=[
            OrderItem(
                id="b1:item",
                item_name="Door Lock Replacement",
                quantity=1,
                unit_price=154.45,
            )
        ],
        total_price=154.45,
    )
    with patch.object(SimpleMarketplaceProtocol, "execute_action", fake_execute):
        with pytest.raises(RuntimeError, match="chain rejected"):
            await protocol.execute_action(
                agent=AgentProfile(id="business_0001"),
                action=ActionExecutionRequest(
                    name="SendMessage",
                    parameters=send_message(proposal).model_dump(mode="json"),
                ),
                database=DummyDB(),
            )
    assert len(delegated) == 1
