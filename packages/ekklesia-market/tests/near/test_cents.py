"""Every demo YAML price must convert to exact integer cents."""

from decimal import Decimal
from pathlib import Path

import yaml

from magentic_marketplace.near.client import to_cents, total_cents

ROOT = Path(__file__).resolve().parents[4]
DEMO = ROOT / "data" / "demo_small"


def demo_files() -> list[Path]:
    """The 25 demo YAML files (5 businesses + 20 customers)."""
    return sorted((DEMO / "businesses").glob("*.yaml")) + sorted(
        (DEMO / "customers").glob("*.yaml")
    )


def test_twenty_five_demo_yaml_files() -> None:
    files = demo_files()
    assert len(files) == 25
    priced = 0
    for path in files:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for value in document["menu_features"].values():
            expected = int(Decimal(str(value)) * 100)
            assert to_cents(value) == expected
            assert to_cents(str(value)) == expected
            priced += 1
    assert priced > 25


def test_float_bug_value_is_exact() -> None:
    assert to_cents(419.15) == 41_915
    # int(419.15 * 100) is platform-dependent (41914 or 41915); exactness is
    # why the adapter uses Decimal(str(value)) instead.
    assert to_cents("154.45") == 15_445


def test_cents_reject() -> None:
    try:
        to_cents(419.155)
    except ValueError:
        pass
    else:
        raise AssertionError("non-integral cents must be rejected")


def test_total_cents_uses_quantity() -> None:
    items = [
        {"unit_price": 419.15, "quantity": 1},
        {"unit_price": "154.45", "quantity": 2},
    ]
    assert total_cents(items) == 41_915 + 2 * 15_445
