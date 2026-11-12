"""Deterministic no-LLM business policy derived from the origin prompts."""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from ...near.client import NearClient
from ..actions import OrderItem, OrderProposal, Payment, ReceivedMessage, TextMessage
from ..shared.models import Business, BusinessAgentProfile, CustomerAgentProfile
from .base import BaseSimpleMarketplaceAgent

logger = logging.getLogger(__name__)


class DeterministicBusinessAgent(BaseSimpleMarketplaceAgent[BusinessAgentProfile]):
    """Quote every requested item at the exact menu price, then settle payment."""

    def __init__(
        self,
        business: Business,
        base_url: str,
        near_client: NearClient,
        *,
        polling_interval: float = 0.2,
    ):
        """Build a business profile and bind the settlement client."""
        super().__init__(BusinessAgentProfile.from_business(business), base_url)
        self._near = near_client
        self._polling_interval = polling_interval
        self._proposal_counter = 0
        self._settled: set[str] = set()

    @property
    def business(self) -> Business:
        """The served business record."""
        return self.profile.business

    async def on_started(self) -> None:
        """Log readiness."""
        self.logger.info("Deterministic business ready")

    async def _propose(self, customer_id: str) -> None:
        profile = await self.client.agents.get(customer_id)
        customer = CustomerAgentProfile.model_validate(profile.model_dump()).customer
        items: list[OrderItem] = []
        total = Decimal(0)
        for item_name in customer.menu_features:
            if item_name not in self.business.menu_features:
                self.logger.warning(
                    f"Cannot quote {item_name!r}: not on {self.business.id}'s menu"
                )
                return
            unit_price = self.business.menu_features[item_name]
            items.append(
                OrderItem(
                    id=f"{self.business.id}:{item_name}",
                    item_name=item_name,
                    quantity=1,
                    unit_price=unit_price,
                )
            )
            total += Decimal(str(unit_price))
        proposal_id = (
            f"{self.business.id}-{customer_id}-{self._proposal_counter}"
        )
        self._proposal_counter += 1
        message = OrderProposal(
            id=proposal_id,
            items=items,
            total_price=float(total),
            expiry_time=None,
        )
        result = await self.send_message(customer_id, message)
        if result.is_error:
            self.logger.error(f"Proposal {proposal_id} rejected: {result.content}")
        else:
            self.logger.info(f"Posted proposal {proposal_id} to {customer_id}")

    async def _settle(self, customer_id: str, payment: Payment) -> None:
        proposal_id = payment.proposal_message_id
        if proposal_id in self._settled:
            return
        await self._near.settle(proposal_id, self.business.id)
        self._settled.add(proposal_id)
        self.logger.info(f"Settled proposal {proposal_id} for {customer_id}")

    async def _handle(self, message: ReceivedMessage) -> None:
        if isinstance(message.message, TextMessage):
            await self._propose(message.from_agent_id)
        elif isinstance(message.message, Payment):
            await self._settle(message.from_agent_id, message.message)

    async def step(self) -> None:
        """Poll once for customer messages and answer each one."""
        messages = await self.fetch_messages()
        if messages.messages:
            await asyncio.gather(*(self._handle(item) for item in messages.messages))
            await asyncio.sleep(0)
        else:
            await asyncio.sleep(self._polling_interval)

