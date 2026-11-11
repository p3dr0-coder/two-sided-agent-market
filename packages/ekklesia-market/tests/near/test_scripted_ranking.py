"""The scripted customer's menu/amenity/price policy matches the origin rules."""

from magentic_marketplace.marketplace.agents.scripted_customer import (
    proposal_meets_policy,
    rank_businesses,
)
from magentic_marketplace.marketplace.actions import OrderItem, OrderProposal
from magentic_marketplace.marketplace.shared.models import (
    Business,
    BusinessAgentProfile,
    Customer,
)


def business(identifier: str, prices: dict[str, float], amenities: dict[str, bool]):
    return BusinessAgentProfile.from_business(
        Business(
            id=identifier,
            name=identifier,
            description=identifier,
            rating=1.0,
            progenitor_customer="customer_0001",
            menu_features=prices,
            amenity_features=amenities,
            min_price_factor=0.8,
        )
    )


def test_rank_requires_menu_and_amenities_then_cheapest():
    customer = Customer(
        id="customer_0001",
        name="Grace Wang",
        request="Door Lock Replacement",
        menu_features={"Door Lock Replacement": 168.99},
        amenity_features=["multilingual staff"],
    )
    expensive = business(
        "business_0001",
        {"Door Lock Replacement": 170.0},
        {"multilingual staff": True},
    )
    cheap = business(
        "business_0002",
        {"Door Lock Replacement": 154.45},
        {"multilingual staff": True},
    )
    missing_amenity = business(
        "business_0003",
        {"Door Lock Replacement": 100.0},
        {"multilingual staff": False},
    )
    missing_item = business(
        "business_0004", {"Mulch Delivery": 10.0}, {"multilingual staff": True}
    )

    ranked = rank_businesses(
        customer, [expensive, cheap, missing_amenity, missing_item]
    )
    assert [profile.id for profile, _ in ranked] == ["business_0002", "business_0001"]
    assert [total for _, total in ranked] == [15_445, 17_000]


def test_proposal_cap_is_twice_requested_total():
    customer = Customer(
        id="customer_0001",
        name="Grace Wang",
        request="Door Lock Replacement",
        menu_features={"Door Lock Replacement": 168.99},
        amenity_features=[],
    )
    seller = business(
        "business_0001", {"Door Lock Replacement": 154.45}, {}
    ).business
    at_cap = OrderProposal(
        id="p1",
        items=[
            OrderItem(
                id="x",
                item_name="Door Lock Replacement",
                quantity=2,
                unit_price=168.99,
            )
        ],
        total_price=337.98,
    )
    over_cap = OrderProposal(
        id="p2",
        items=[
            OrderItem(
                id="x",
                item_name="Door Lock Replacement",
                quantity=2,
                unit_price=169.0,
            )
        ],
        total_price=338.0,
    )
    assert proposal_meets_policy(customer, seller, at_cap) is True
    assert proposal_meets_policy(customer, seller, over_cap) is False
