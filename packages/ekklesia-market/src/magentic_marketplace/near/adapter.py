"""Route the simulation's OrderProposal/Payment messages into on-chain escrow.

The off-chain ``SimpleMarketplaceProtocol`` still records every message in the
simulation database. Settlement is an additional side effect: a proposal is
posted by the business sub-account and a payment escrows the exact cent total as
the customer sub-account.
"""

from __future__ import annotations

from typing import Any

from magentic_marketplace.marketplace.actions import (
    ActionAdapter,
    OrderProposal,
    Payment,
    SendMessage,
)
from magentic_marketplace.marketplace.protocol.protocol import SimpleMarketplaceProtocol
from magentic_marketplace.platform.database.base import BaseDatabaseController
from magentic_marketplace.platform.shared.models import (
    ActionExecutionRequest,
    ActionExecutionResult,
    AgentProfile,
)

from .client import NearClient, expiry_ns, total_cents


class NearSettlementProtocol(SimpleMarketplaceProtocol):
    """Simple marketplace protocol with a NEAR escrow side effect."""

    def __init__(self, client: NearClient):
        """Store the settlement client and initialize the origin protocol."""
        super().__init__()
        self.near = client

    async def _route_send_message(self, send_message: SendMessage) -> None:
        message = send_message.message
        if isinstance(message, OrderProposal):
            total = total_cents(message.items)
            expiry = expiry_ns(
                message.expiry_time,
                await self.near.block_timestamp_ns(),
            )
            await self.near.post_proposal(
                proposal_id=message.id,
                business_sim_id=send_message.from_agent_id,
                customer_sim_id=send_message.to_agent_id,
                items=message.items,
                total_price_cents=total,
                expiry_ns_value=expiry,
            )
        elif isinstance(message, Payment):
            await self.near.accept_proposal(
                proposal_id=message.proposal_message_id,
                customer_sim_id=send_message.from_agent_id,
            )

    async def execute_action(
        self,
        *,
        agent: AgentProfile,
        action: ActionExecutionRequest,
        database: BaseDatabaseController,
    ) -> ActionExecutionResult:
        """Settle the message on-chain, then always record it in the sim database."""
        parsed = ActionAdapter.validate_python(action.parameters)
        route_error: Exception | None = None
        if isinstance(parsed, SendMessage):
            try:
                await self._route_send_message(parsed)
            except Exception as exc:  # noqa: BLE001 - re-raised after delegation
                route_error = exc

        result = await super().execute_action(
            agent=agent, action=action, database=database
        )
        if route_error is not None:
            raise route_error
        return result


def route_targets(send_message: SendMessage) -> tuple[str, str] | None:
    """Return ``(kind, proposal_id)`` for unit tests without touching a client."""
    message: Any = send_message.message
    if isinstance(message, OrderProposal):
        return ("order_proposal", message.id)
    if isinstance(message, Payment):
        return ("payment", message.proposal_message_id)
    return None
