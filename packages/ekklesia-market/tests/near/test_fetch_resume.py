"""Fetch polling resumes after the agent's highest seen message index."""

from datetime import UTC, datetime

import pytest

from magentic_marketplace.marketplace.actions import (
    FetchMessages,
    FetchMessagesResponse,
    OrderItem,
    OrderProposal,
    ReceivedMessage,
)
from magentic_marketplace.marketplace.agents.scripted_customer import (
    DeterministicCustomerAgent,
)
from magentic_marketplace.marketplace.agents.scripted_business import (
    DeterministicBusinessAgent,
)
from magentic_marketplace.marketplace.shared.models import Business, Customer
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
)


def _sent(from_id: str, to_id: str, index: int) -> ReceivedMessage:
    message = OrderProposal(
        id=f"p{index}",
        items=[
            OrderItem(
                id=f"item-{index}",
                item_name="Widget",
                quantity=1,
                unit_price=100,
            )
        ],
        total_price=100.0,
    )
    return ReceivedMessage(
        from_agent_id=from_id,
        to_agent_id=to_id,
        created_at=datetime.now(UTC),
        message=message,
        index=index,
    )


class RecordingExecutor:
    """Serve queued fetch pages and record the requested after_index."""

    def __init__(self, pages: list[list[ReceivedMessage]]):
        self.pages = pages
        self.turn = 0
        self.after_indexes: list[int | None] = []
        self.requests: list[FetchMessages] = []

    async def __call__(self, action: FetchMessages):
        self.requests.append(action)
        if isinstance(action, FetchMessages):
            self.after_indexes.append(action.after_index)
            page = (
                self.pages[self.turn]
                if self.turn < len(self.pages)
                else []
            )
            self.turn += 1
            return ActionExecutionResult(
                content=FetchMessagesResponse(
                    messages=page, has_more=False
                ).model_dump(mode="json")
            )
        raise AssertionError(f"unexpected action {action.get_name()}")


def _customer_agent(executor: RecordingExecutor) -> DeterministicCustomerAgent:
    customer = Customer(
        id="c1",
        name="Customer One",
        request="widget",
        menu_features={"Widget": 1.0},
        amenity_features=[],
    )
    agent = DeterministicCustomerAgent(customer, "http://127.0.0.1:1")
    agent.execute_action = executor.__call__  # type: ignore[method-assign]
    return agent


def _business_agent(executor: RecordingExecutor) -> DeterministicBusinessAgent:
    business = Business(
        id="b1",
        name="Business One",
        description="Sells widgets.",
        rating=1.0,
        progenitor_customer="c1",
        menu_features={"Widget": 1.0},
        amenity_features={"gift wrapping": True},
        min_price_factor=1.0,
    )
    agent = DeterministicBusinessAgent(business, "http://127.0.0.1:1", None)
    agent.execute_action = executor.__call__  # type: ignore[method-assign]
    return agent


@pytest.mark.asyncio
async def test_business_fetch_resumes_after_last_index():
    executor = RecordingExecutor(
        [[_sent("c1", "b1", 7), _sent("c1", "b1", 9)], []]
    )
    agent = _business_agent(executor)

    first = await agent.fetch_messages()
    assert [m.index for m in first.messages] == [7, 9]
    assert executor.after_indexes == [None]
    assert agent.last_fetch_index == 9

    second = await agent.fetch_messages()
    assert second.messages == []
    assert executor.after_indexes == [None, 9]


@pytest.mark.asyncio
async def test_customer_fetch_never_rescans_seen_rows():
    """The second poll asks the database only for rows after the last seen index."""
    executor = RecordingExecutor(
        [[_sent("b1", "c1", 3), _sent("b1", "c1", 4)], [_sent("b1", "c1", 11)]]
    )
    agent = _customer_agent(executor)

    await agent.fetch_messages()
    await agent.fetch_messages()
    assert executor.after_indexes == [None, 4]
    assert agent.last_fetch_index == 11

    third = await agent.fetch_messages()
    assert third.messages == []
    assert executor.after_indexes == [None, 4, 11]


@pytest.mark.asyncio
async def test_fetch_messages_action_carries_resume_index():
    """The built action object carries the resume index for the server side."""
    executor = RecordingExecutor([[]])
    agent = _business_agent(executor)
    await agent.fetch_messages()
    (request,) = executor.requests
    assert request.get_name() == "FetchMessages"
    assert request.after_index is None
