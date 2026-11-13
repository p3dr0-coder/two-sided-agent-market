"""Deterministic no-LLM customer policy derived from the origin ranking."""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from ...near.client import to_cents
from ..actions import (
    OrderProposal,
    Payment,
    ReceivedMessage,
    Search,
    SearchAlgorithm,
    SearchResponse,
    TextMessage,
)
from ..shared.models import (
    Business,
    BusinessAgentProfile,
    Customer,
    CustomerAgentProfile,
)
from .base import BaseSimpleMarketplaceAgent

logger = logging.getLogger(__name__)

MAX_STEPS = 12
SEARCH_BANDWIDTH = 50


def menu_total_cents(customer: Customer, business: Business) -> int | None:
    """Exact menu total if the business covers every requested item."""
    if not set(customer.menu_features).issubset(business.menu_features):
        return None
    return sum(to_cents(business.menu_features[name]) for name in customer.menu_features)


def offers_required_amenities(customer: Customer, business: Business) -> bool:
    """The origin's ``required_amenities.issubset(available_amenities)``."""
    available = {
        name for name, offered in business.amenity_features.items() if offered
    }
    return set(customer.amenity_features).issubset(available)


def rank_businesses(
    customer: Customer, businesses: list[BusinessAgentProfile]
) -> list[tuple[BusinessAgentProfile, int]]:
    """Menu-cover and amenity-cover matches, cheapest exact total first."""
    ranked: list[tuple[BusinessAgentProfile, int]] = []
    for profile in businesses:
        total = menu_total_cents(customer, profile.business)
        if total is None or not offers_required_amenities(customer, profile.business):
            continue
        ranked.append((profile, total))
    ranked.sort(key=lambda item: (item[1], item[0].id))
    return ranked


def proposal_meets_policy(
    customer: Customer,
    business: Business,
    proposal: OrderProposal,
    *,
    cap_multiplier: int = 2,
) -> bool:
    """Check coverage, amenities, and the origin price cap."""
    proposed_items = {item.item_name: item for item in proposal.items}
    if not set(customer.menu_features).issubset(proposed_items):
        return False
    if not offers_required_amenities(customer, business):
        return False
    requested_total = sum(to_cents(price) for price in customer.menu_features.values())
    proposal_total = sum(
        to_cents(item.unit_price) * item.quantity for item in proposal.items
    )
    return proposal_total <= cap_multiplier * requested_total


class DeterministicCustomerAgent(BaseSimpleMarketplaceAgent[CustomerAgentProfile]):
    """Search, rank, inquire, and pay the cheapest fulfilling business."""

    def __init__(
        self,
        customer: Customer,
        base_url: str,
        *,
        search_bandwidth: int = SEARCH_BANDWIDTH,
        max_steps: int = MAX_STEPS,
        polling_interval: float = 0.5,
    ):
        """Build a customer profile and configure the deterministic policy."""
        super().__init__(CustomerAgentProfile.from_customer(customer), base_url)
        self._search_bandwidth = search_bandwidth
        self._max_steps = max_steps
        self._polling_interval = polling_interval
        self._steps = 0
        self._ranked: list[tuple[BusinessAgentProfile, int]] = []
        self._inquiry_index = 0
        self._done = False

    @property
    def customer(self) -> Customer:
        """The served customer record."""
        return self.profile.customer

    async def _search(self) -> None:
        action = Search(
            query=self.customer.request,
            search_algorithm=SearchAlgorithm.LEXICAL,
            limit=self._search_bandwidth,
            page=1,
        )
        result = await self.execute_action(action)
        if result.is_error:
            raise RuntimeError(f"search failed: {result.content}")
        response = SearchResponse.model_validate(result.content)
        self._ranked = rank_businesses(self.customer, response.businesses)
        self.logger.info(
            f"Ranked {len(self._ranked)} fulfilling businesses for {self.customer.id}"
        )

    async def _inquire(self) -> bool:
        while self._inquiry_index < len(self._ranked):
            profile, total = self._ranked[self._inquiry_index]
            self._inquiry_index += 1
            message = TextMessage(
                content=(
                    f"Please quote {len(self.customer.menu_features)} requested item(s) "
                    f"from your menu. My request: {self.customer.request}"
                )
            )
            result = await self.send_message(profile.id, message)
            if not result.is_error:
                self.logger.info(
                    f"Inquired with {profile.id} (menu total {total} cents)"
                )
                return True
        return False

    async def _handle_proposals(self, messages: list[ReceivedMessage]) -> bool:
        for received in messages:
            proposal = received.message
            if not isinstance(proposal, OrderProposal):
                continue
            profile = next(
                (item for item, _ in self._ranked if item.id == received.from_agent_id),
                None,
            )
            if profile is None:
                continue
            if not proposal_meets_policy(
                self.customer, profile.business, proposal
            ):
                self.logger.warning(
                    f"Rejected proposal {proposal.id} from {received.from_agent_id}"
                )
                if self._inquiry_index < len(self._ranked):
                    await self._inquire()
                continue
            payment = Payment(
                proposal_message_id=proposal.id,
                payment_method="near",
                payment_message=(
                    f"Accepting {len(proposal.items)} item(s) for "
                    f"${Decimal(proposal.total_price):.2f}"
                ),
            )
            result = await self.send_message(received.from_agent_id, payment)
            if result.is_error:
                raise RuntimeError(f"payment failed: {result.content}")
            self.logger.info(f"Paid proposal {proposal.id}")
            return True
        return False

    async def step(self) -> None:
        """One deterministic shopping step; errors shut the agent down."""
        try:
            if self._done:
                self.shutdown()
                return
            self._steps += 1
            if self._steps > self._max_steps:
                self.logger.warning("Max steps exceeded, shutting down early")
                self.shutdown()
                return
            if not self._ranked:
                await self._search()
                if not await self._inquire():
                    self.logger.warning("No fulfilling business found")
                    self._done = True
                    self.shutdown()
                    return
                return

            messages = await self.fetch_messages()
            if await self._handle_proposals(messages.messages):
                self._done = True
                self.shutdown()
                return
            await asyncio.sleep(self._polling_interval)
        except Exception as exc:  # noqa: BLE001 - deterministic run fails closed
            self.logger.exception(f"Deterministic customer failed: {exc}")
            self.shutdown()
