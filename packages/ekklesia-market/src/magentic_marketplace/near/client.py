"""Async near-kit client for the ekklesia settlement contract.

Signing calls append a compact record to the experiment transaction log because
NEAR RPC has no list-transactions-by-account query. Those records are the input
for the EVENT_JSON analytics feed.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from near import Amount, AsyncNear, KeyPairSigner, parse_key

YOCTO_PER_NEAR = 10**24
CENTS_PER_NEAR = 100_000
YOCTO_PER_USD_CENT = YOCTO_PER_NEAR // CENTS_PER_NEAR
PROPOSAL_TTL_NS = 300_000_000_000
AGENT_REGISTRATION_DEPOSIT_YOCTO = 100_000_000_000_000_000_000_000  # 0.1 NEAR
BUSINESS_REGISTRATION_DEPOSIT_YOCTO = 500_000_000_000_000_000_000_000  # 0.5 NEAR
GAS_100_TGAS = "100 Tgas"
EVENT_STANDARD = "ekklesia-market"


def to_cents(value: Any) -> int:
    """Convert a YAML/JSON dollar value to integer cents without float drift.

    ``int(419.15 * 100)`` truncates to ``41914``; ``Decimal(str(419.15)) * 100``
    is exactly ``41915``. Non-integral cent values are rejected because the
    contract enforces exact cents.
    """
    if isinstance(value, bool):
        raise TypeError("boolean is not a price")
    scaled = Decimal(str(value)) * 100
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError(f"price {value!r} is not an exact number of cents")
    return int(integral)


def total_cents(items: Iterable[Any]) -> int:
    """Sum ``quantity * unit_price`` for proposal items, in exact cents."""
    total = 0
    for item in items:
        if isinstance(item, Mapping):
            unit_price = item["unit_price"]
            quantity = item.get("quantity", 1)
        else:
            unit_price = item.unit_price
            quantity = item.quantity
        total += to_cents(unit_price) * int(quantity)
    return total


def expiry_ns(value: Any, block_timestamp_ns: int) -> int:
    """Convert an origin ``expiry_time`` string to nanoseconds.

    A missing value uses the contract's five-minute default. Naive datetimes are
    treated as UTC because the origin emits timezone-aware ISO strings.
    """
    if value is None or value == "":
        return block_timestamp_ns + PROPOSAL_TTL_NS
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp() * 1_000_000_000)


class NearClient:
    """Root-signed client plus per-agent signers loaded from ``agents.json``."""

    def __init__(
        self,
        contract_id: str | None = None,
        *,
        network: str | None = None,
        rpc_url: str | None = None,
        signer: Any | None = None,
        agents_file: str | Path | None = None,
        tx_log_path: str | Path | None = None,
        experiment_name: str | None = None,
        client: AsyncNear | None = None,
    ):
        """Create a client from environment values unless explicit values win."""
        self.contract_id = contract_id or os.environ.get("MARKET_CONTRACT_ID", "")
        if not self.contract_id:
            raise ValueError("MARKET_CONTRACT_ID is not set")
        self.network = network or os.environ.get("NEAR_NETWORK", "sandbox")
        self.rpc_url = rpc_url or os.environ.get("NEAR_RPC_URL") or None
        self.agents_file = Path(
            agents_file or os.environ.get("NEAR_AGENTS_FILE", ".sandbox/agents.json")
        )
        if tx_log_path is not None:
            self.tx_log_path = Path(tx_log_path)
        elif experiment_name:
            self.tx_log_path = Path("data") / f"{experiment_name}-tx.jsonl"
        else:
            self.tx_log_path = Path(".sandbox/tx.jsonl")

        self._agents: dict[str, dict[str, Any]] | None = None
        self._signers: dict[str, KeyPairSigner] = {}

        if client is not None:
            self._client = client
        else:
            if signer is None and self.network == "sandbox":
                from near.testing import sandbox_signer

                signer = sandbox_signer()
            self._client = AsyncNear(
                network=self.network,
                rpc_url=self.rpc_url,
                signer=signer,
            )

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    @property
    def root_account_id(self) -> str:
        """The signing account of the root client."""
        account_id = getattr(self._client.signer, "account_id", None)
        if not account_id:
            raise RuntimeError("near client has no root signer")
        return str(account_id)

    def signer_for(self, sim_agent_id: str) -> KeyPairSigner:
        """Load and cache the sub-account signer for a simulation agent."""
        if sim_agent_id not in self._signers:
            entry = self._agents_by_sim_id().get(sim_agent_id)
            if entry is None:
                raise KeyError(
                    f"no on-chain signer for simulation agent {sim_agent_id!r}"
                )
            account_id = str(entry["account_id"])
            self._signers[sim_agent_id] = KeyPairSigner(
                account_id, parse_key(str(entry["secret_key"]))
            )
        return self._signers[sim_agent_id]

    def account_for(self, sim_agent_id: str) -> str:
        """Map a simulation agent id (``business_0001``) to its sub-account."""
        entry = self._agents_by_sim_id().get(sim_agent_id)
        if entry is None:
            raise KeyError(f"no on-chain account for simulation agent {sim_agent_id!r}")
        return str(entry["account_id"])

    def _client_for(self, account_id: str) -> AsyncNear:
        if account_id == self.root_account_id:
            return self._client
        agents = self._agents_by_sim_id()
        for sim_id, entry in agents.items():
            if str(entry["account_id"]) == account_id:
                return self._client.with_signer(self.signer_for(sim_id))
        raise KeyError(f"no signer for account {account_id!r}")

    def _agents_by_sim_id(self) -> dict[str, dict[str, Any]]:
        if self._agents is None:
            if not self.agents_file.exists():
                raise FileNotFoundError(
                    f"agents file not found: {self.agents_file}; run "
                    "python -m magentic_marketplace.near.bootstrap first"
                )
            document = json.loads(self.agents_file.read_text(encoding="utf-8"))
            merged: dict[str, dict[str, Any]] = {}
            for group in ("businesses", "customers"):
                entries = document.get(group, {})
                if isinstance(entries, dict):
                    merged.update(entries)
            self._agents = merged
        return self._agents


    def _note_tx(self, method: str, account_id: str, result: Any) -> None:
        tx_hash = getattr(result, "transaction_hash", None)
        if not tx_hash:
            raise RuntimeError(f"{method} returned no transaction hash")
        record = {
            "method": method,
            "account": account_id,
            "tx_hash": tx_hash,
            "ts": datetime.now(UTC).isoformat(),
        }
        self.tx_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.tx_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")

    async def _call(
        self,
        method: str,
        args: dict[str, Any],
        *,
        account_id: str | None = None,
        deposit_yocto: int = 0,
        gas: str = GAS_100_TGAS,
    ) -> Any:
        signer_account = account_id or self.root_account_id
        client = self._client_for(signer_account)
        result = await client.call(
            self.contract_id,
            method,
            args,
            gas=gas,
            deposit=Amount(deposit_yocto),
        )
        self._note_tx(method, signer_account, result)
        return result

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def register_agent(
        self,
        agent_name: str,
        profile: Mapping[str, Any],
        public_key: str,
        *,
        deposit_yocto: int = AGENT_REGISTRATION_DEPOSIT_YOCTO,
        account_id: str | None = None,
    ) -> str:
        """Create and register a sub-account; return the full account id."""
        await self._call(
            "register_agent",
            {
                "agent_name": agent_name,
                "profile": dict(profile),
                "public_key": public_key,
            },
            account_id=account_id,
            deposit_yocto=deposit_yocto,
        )
        return self.account_for_name(agent_name)

    def account_for_name(self, agent_name: str) -> str:
        """Derive the sub-account id without a network read."""
        return f"{agent_name}.{self.contract_id}"

    async def post_proposal(
        self,
        proposal_id: str,
        business_sim_id: str,
        customer_sim_id: str,
        items: Sequence[Any],
        total_price_cents: int,
        expiry_ns_value: int,
    ) -> Any:
        """Sign ``post_proposal`` as the business sub-account."""
        encoded_items = []
        for item in items:
            if isinstance(item, Mapping):
                name = item["item_name"]
                quantity = int(item.get("quantity", 1))
                unit_price = item["unit_price"]
            else:
                name = item.item_name
                quantity = int(item.quantity)
                unit_price = item.unit_price
            encoded_items.append(
                {
                    "item_name": str(name),
                    "quantity": quantity,
                    "unit_price": str(to_cents(unit_price)),
                }
            )
        return await self._call(
            "post_proposal",
            {
                "proposal_id": str(proposal_id),
                "customer": self.account_for(customer_sim_id),
                "items": encoded_items,
                "total_price": str(int(total_price_cents)),
                "expiry": str(int(expiry_ns_value)),
            },
            account_id=self.account_for(business_sim_id),
        )

    async def accept_proposal(self, proposal_id: str, customer_sim_id: str) -> Any:
        """Escrow exactly ``total_price * YOCTO_PER_USD_CENT`` as the customer."""
        proposal = await self.get_proposal(proposal_id)
        if proposal is None:
            raise ValueError(f"proposal {proposal_id!r} does not exist on-chain")
        total = int(proposal["total_price"])
        return await self._call(
            "accept_proposal",
            {"proposal_id": str(proposal_id)},
            account_id=self.account_for(customer_sim_id),
            deposit_yocto=total * YOCTO_PER_USD_CENT,
        )

    async def settle(self, proposal_id: str, business_sim_id: str) -> Any:
        """Sign ``settle`` as the business sub-account after delivery."""
        return await self._call(
            "settle",
            {"proposal_id": str(proposal_id)},
            account_id=self.account_for(business_sim_id),
        )

    async def refund(self, proposal_id: str, caller_account_id: str | None = None) -> Any:
        """Permissionless refund; the caller pays gas and escrow returns to the customer."""
        return await self._call(
            "refund",
            {"proposal_id": str(proposal_id)},
            account_id=caller_account_id,
        )

    # ------------------------------------------------------------------
    # Views and time
    # ------------------------------------------------------------------

    async def get_welfare(self) -> dict[str, Any]:
        return await self._client.view(self.contract_id, "get_welfare")

    async def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        return await self._client.view(
            self.contract_id, "get_proposal", {"proposal_id": str(proposal_id)}
        )

    async def get_agent(self, account_id: str) -> dict[str, Any] | None:
        return await self._client.view(
            self.contract_id, "get_agent", {"agent_id": str(account_id)}
        )

    async def get_trade_count(self) -> int:
        return int(await self._client.view(self.contract_id, "get_trade_count"))

    async def block_timestamp_ns(self) -> int:
        block = await self._client.rpc("block", {"finality": "final"})
        return int(block["header"]["timestamp"])

    async def block_height(self) -> int:
        block = await self._client.rpc("block", {"finality": "final"})
        return int(block["header"]["height"])

    async def fast_forward(self, blocks: int, *, timeout: float = 30.0) -> None:
        """Advance a Docker sandbox by blocks and wait until the head moves."""
        if blocks < 1:
            raise ValueError("blocks must be >= 1")
        start = await self.block_height()
        await self._client.rpc("sandbox_fast_forward", {"delta_height": int(blocks)})
        deadline = time.monotonic() + timeout + blocks * 0.05
        while time.monotonic() < deadline:
            if await self.block_height() >= start + blocks:
                return
            await asyncio.sleep(0.05)
        raise TimeoutError(f"sandbox did not advance {blocks} blocks")

    # ------------------------------------------------------------------
    # Transaction log and events
    # ------------------------------------------------------------------

    def tx_records(self) -> list[dict[str, Any]]:
        """Read the experiment transaction log (oldest first)."""
        if not self.tx_log_path.exists():
            return []
        records = []
        for line in self.tx_log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records

    async def fetch_events(self) -> list[dict[str, Any]]:
        """Fetch statuses for logged transactions and parse EVENT_JSON logs."""
        records = []
        for record in self.tx_records():
            result = await self._client.transaction_status(
                str(record["tx_hash"]),
                sender_id=str(record["account"]),
                wait_until="FINAL",
            )
            gas = 0
            if result.transaction_outcome is not None:
                gas += int(result.transaction_outcome.gas_burnt)
            gas += sum(int(receipt.gas_burnt) for receipt in result.receipts_outcome)
            events = []
            for log in result.logs:
                if not log.startswith("EVENT_JSON:"):
                    continue
                event = json.loads(log[len("EVENT_JSON:") :])
                if event.get("standard") != EVENT_STANDARD:
                    continue
                events.append(event)
            records.append(
                {
                    "method": record["method"],
                    "account": record["account"],
                    "tx_hash": record["tx_hash"],
                    "total_gas_burnt": gas,
                    "events": events,
                }
            )
        return records
