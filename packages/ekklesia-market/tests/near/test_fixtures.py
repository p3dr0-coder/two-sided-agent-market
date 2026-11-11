"""The seeded demo market is 5 businesses x 20 customers with full coverage."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
DEMO = ROOT / "data" / "demo_small"


def load(kind: str) -> list[dict]:
    return [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted((DEMO / kind).glob("*.yaml"))
    ]


def test_counts_and_ids() -> None:
    businesses = load("businesses")
    customers = load("customers")
    assert len(businesses) == 5
    assert len(customers) == 20
    assert [item["id"] for item in businesses] == [
        f"business_{index:04d}" for index in range(1, 6)
    ]
    assert [item["id"] for item in customers] == [
        f"customer_{index:04d}" for index in range(1, 21)
    ]
    assert len({item["name"] for item in customers}) == 20


def test_customer_menu_keys_are_in_the_business_union() -> None:
    businesses = load("businesses")
    union = set()
    for business in businesses:
        union.update(business["menu_features"])
    for customer in load("customers"):
        assert set(customer["menu_features"]) <= union


def test_each_customer_group_matches_its_base_business() -> None:
    businesses = load("businesses")
    customers = load("customers")
    for index, customer in enumerate(customers):
        base = businesses[index // 4]
        assert set(customer["menu_features"]) <= set(base["menu_features"])
        for amenity in customer["amenity_features"]:
            assert base["amenity_features"][amenity] is True
        assert base["progenitor_customer"] == f"customer_{index // 4 * 4 + 1:04d}"


def test_customer_replicates_are_identical_except_id_and_name() -> None:
    customers = load("customers")
    for group in range(5):
        base = customers[group * 4]
        for copy in customers[group * 4 + 1 : group * 4 + 4]:
            assert copy["request"] == base["request"]
            assert copy["menu_features"] == base["menu_features"]
            assert copy["amenity_features"] == base["amenity_features"]
