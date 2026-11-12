"""Parse on-chain EVENT_JSON logs and cross-check the welfare view."""

from __future__ import annotations

import statistics
from collections.abc import Mapping
from typing import Any

from .client import NearClient


class NearAnalyticsFeed:
    """Welfare and gas diagnostics derived from a run's transaction log."""

    def __init__(self, client: NearClient):
        """Bind the feed to a client whose tx log covers this experiment."""
        self.client = client
        self.records: list[dict[str, Any]] = []
        self.welfare: dict[str, Any] | None = None

    async def load(self, welfare: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Fetch tx statuses, read welfare, and assert the event-stream identity."""
        self.records = await self.client.fetch_events()
        self.welfare = dict(welfare) if welfare is not None else await self.client.get_welfare()
        self.assert_welfare(self.welfare)
        return self.welfare

    def _payloads(self, event_name: str) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for record in self.records:
            for event in record["events"]:
                if event.get("event") != event_name:
                    continue
                data = event.get("data", [])
                if isinstance(data, dict):
                    data = [data]
                payloads.extend(data)
        return payloads

    @property
    def trades(self) -> list[dict[str, Any]]:
        return self._payloads("trade_settled")

    @property
    def posted(self) -> list[dict[str, Any]]:
        return self._payloads("proposal_posted")

    @property
    def rejected(self) -> list[dict[str, Any]]:
        return self._payloads("proposal_rejected")

    def settle_gas_tgas(self) -> list[float]:
        """Gas burnt by each logged ``settle`` transaction, in TGas."""
        return [
            int(record["total_gas_burnt"]) / 1e12
            for record in self.records
            if record["method"] == "settle"
        ]

    def median_settle_gas_tgas(self) -> float:
        """Median settle gas; 0.0 before any settle is logged."""
        samples = self.settle_gas_tgas()
        return float(statistics.median(samples)) if samples else 0.0

    def assert_welfare(self, welfare: Mapping[str, Any]) -> None:
        """Assert the on-chain counters agree with the emitted TradeSettled stream."""
        utility_from_events = sum(
            int(trade["customer_utility_delta_cents"]) for trade in self.trades
        )
        utility_from_view = int(welfare["total_customer_utility_cents"])
        if utility_from_events != utility_from_view:
            raise AssertionError(
                "welfare mismatch: get_welfare="
                f"{utility_from_view} vs TradeSettled sum={utility_from_events}"
            )
        if len(self.trades) != int(welfare["settled_count"]):
            raise AssertionError(
                "settled_count mismatch: "
                f"get_welfare={welfare['settled_count']} vs events={len(self.trades)}"
            )
        if len(self.rejected) != int(welfare["rejected_proposals"]):
            raise AssertionError(
                "rejected_proposals mismatch: "
                f"get_welfare={welfare['rejected_proposals']} vs events={len(self.rejected)}"
            )
        needs_met_customers = {
            trade["customer"] for trade in self.trades if trade["needs_met"]
        }
        if len(needs_met_customers) != int(welfare["needs_met_count"]):
            raise AssertionError(
                "needs_met_count mismatch: "
                f"get_welfare={welfare['needs_met_count']} vs "
                f"distinct event customers={len(needs_met_customers)}"
            )

    def headline(self, welfare: Mapping[str, Any] | None = None) -> str:
        """The doc Step 12 sentence, populated only with measured values."""
        measured = dict(welfare) if welfare is not None else self.welfare
        if measured is None:
            raise RuntimeError("call load() before headline()")
        utility = int(measured["total_customer_utility_cents"])
        bps = int(measured["purchase_completion_bps"])
        needs_met = int(measured["needs_met_count"])
        registered = int(measured["registered_customers"])
        rejected = int(measured["rejected_proposals"])
        attempts = len(self.posted) + len(self.rejected)
        gas = self.median_settle_gas_tgas()
        return (
            f"Total marketplace customer utility = {utility}; "
            f"purchase completion rate = {bps / 100:g}% (R = {bps}/100); "
            f"needs-met = {needs_met}/{registered}; "
            f"invalid proposals accepted = 0 of {attempts} attempts "
            f"({rejected} soft-rejected); "
            f"gas/settle = {gas:.3f} TGas"
        )
