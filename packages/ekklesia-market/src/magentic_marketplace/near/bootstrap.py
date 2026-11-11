"""Deploy the market and register the 5x20 demo agents.

Sandbox mode starts from a fresh Docker sandbox and creates ``ekklesia.sandbox``
as a sub-account of the sandbox root. Testnet mode uses ``NEAR_ACCOUNT_ID`` and
``NEAR_PRIVATE_KEY`` from the environment and expects an existing, funded
``ekklesia.testnet`` (pass ``--deploy`` to upload the WASM again).

The generated ``.sandbox/agents.json`` contains sub-account secret keys, is
written with mode 0600, and is gitignored.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from near import (
    Amount,
    AsyncNear,
    KeyPairSigner,
    add_full_access_key,
    create_account,
    deploy_contract,
    generate_key,
    parse_key,
    transfer,
)
from near.testing import sandbox_signer

from .client import (
    AGENT_REGISTRATION_DEPOSIT_YOCTO,
    BUSINESS_REGISTRATION_DEPOSIT_YOCTO,
    YOCTO_PER_USD_CENT,
    NearClient,
    to_cents,
)

ROOT = Path(__file__).resolve().parents[5]
GAS_FUND_YOCTO = 200_000_000_000_000_000_000_000  # 0.2 NEAR
CONTRACT_FUNDING_YOCTO = 10_000_000_000_000_000_000_000_000  # 10 NEAR


def _root_signer(network: str) -> KeyPairSigner:
    if network == "sandbox":
        return sandbox_signer()
    account_id = os.environ.get("NEAR_ACCOUNT_ID")
    private_key = os.environ.get("NEAR_PRIVATE_KEY")
    if not account_id or not private_key:
        raise SystemExit(
            "testnet bootstrap needs NEAR_ACCOUNT_ID and NEAR_PRIVATE_KEY "
            "(or use --network sandbox)"
        )
    return KeyPairSigner(account_id, parse_key(private_key))


def _load_documents(data_dir: Path, kind: str) -> list[dict[str, Any]]:
    files = sorted((data_dir / kind).glob("*.yaml"))
    if not files:
        raise FileNotFoundError(f"no YAML files under {data_dir / kind}")
    return [yaml.safe_load(path.read_text(encoding="utf-8")) for path in files]


def _business_profile(business: MappingLike, payout_account: str) -> dict[str, Any]:
    return {
        "role": "Business",
        "menu": [
            [str(name), str(to_cents(price))]
            for name, price in business["menu_features"].items()
        ],
        "amenities": [
            str(name)
            for name, offered in business["amenity_features"].items()
            if offered
        ],
        "requested_total_cents": "0",
        "payout_account": payout_account,
    }


def _customer_profile(customer: MappingLike, account_id: str) -> dict[str, Any]:
    menu = [
        [str(name), str(to_cents(price))]
        for name, price in customer["menu_features"].items()
    ]
    requested_total = sum(int(price) for _, price in menu)
    return {
        "role": "Customer",
        "menu": menu,
        "amenities": [str(name) for name in customer["amenity_features"]],
        "requested_total_cents": str(requested_total),
        "payout_account": account_id,
    }


MappingLike = dict[str, Any]


def _locate_wasm(explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    elif os.environ.get("MARKET_WASM"):
        candidates.append(Path(os.environ["MARKET_WASM"]))
    candidates.extend(
        [
            ROOT / "target/near/ekklesia_market/ekklesia_market.wasm",
            ROOT / "target/wasm32-unknown-unknown/release/ekklesia_market.wasm",
        ]
    )
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    raise FileNotFoundError(
        "contract WASM not found; run scripts/setup_local.sh or pass --wasm"
    )


async def bootstrap(args: argparse.Namespace) -> None:
    """Deploy/verify the contract and register the demo market participants."""
    network = args.network
    contract_id = args.contract_id or (
        "ekklesia.sandbox" if network == "sandbox" else "ekklesia.testnet"
    )
    rpc_url = args.rpc_url or (
        "http://127.0.0.1:3030" if network == "sandbox" else None
    )
    root_signer = _root_signer(network)
    root = AsyncNear(network=network, rpc_url=rpc_url, signer=root_signer)
    root_account = root_signer.account_id
    payout_account = args.payout_account or os.environ.get(
        "NEAR_PAYOUT_ACCOUNT", root_account
    )

    data_dir = Path(args.data_dir)
    businesses = _load_documents(data_dir, "businesses")
    customers = _load_documents(data_dir, "customers")
    if len(businesses) != 5 or len(customers) != 20:
        raise SystemExit(
            f"expected 5 businesses and 20 customers, got {len(businesses)} and "
            f"{len(customers)}; run scripts/fixtures.sh"
        )

    deploy = args.deploy
    if deploy is None:
        deploy = network == "sandbox"

    try:
        if deploy:
            wasm = _locate_wasm(args.wasm)
            print(f"Deploying {wasm} to {contract_id}")
            if network == "sandbox":
                await root.send_transaction(
                    contract_id,
                    actions=[
                        create_account(),
                        transfer(Amount(CONTRACT_FUNDING_YOCTO)),
                        add_full_access_key(root_signer.public_key),
                        deploy_contract(wasm.read_bytes()),
                    ],
                    wait_until="FINAL",
                )
            else:
                await root.send_transaction(
                    contract_id,
                    actions=[deploy_contract(wasm.read_bytes())],
                    wait_until="FINAL",
                )
            if not args.no_init:
                await root.call(
                    contract_id,
                    "new",
                    {"fee_bps": int(args.fee_bps)},
                    gas="100 Tgas",
                    wait_until="FINAL",
                )

        client = NearClient(
            contract_id=contract_id,
            network=network,
            rpc_url=rpc_url,
            signer=root_signer,
            agents_file=args.agents_file,
            experiment_name=None,
            tx_log_path=".sandbox/bootstrap-tx.jsonl",
            client=root,
        )

        document: dict[str, Any] = {
            "contract_id": contract_id,
            "network": network,
            "rpc_url": rpc_url or "",
            "root_account": root_account,
            "payout_account": payout_account,
            "generated_at": datetime.now(UTC).isoformat(),
            "businesses": {},
            "customers": {},
        }

        for index, business in enumerate(businesses, start=1):
            agent_name = f"b{index}"
            key = generate_key()
            profile = _business_profile(business, payout_account)
            account_id = await client.register_agent(
                agent_name,
                profile,
                str(key.public_key),
                deposit_yocto=BUSINESS_REGISTRATION_DEPOSIT_YOCTO,
            )
            document["businesses"][str(business["id"])] = {
                "sim_id": str(business["id"]),
                "account_id": account_id,
                "secret_key": str(key.secret_key),
                "public_key": str(key.public_key),
                "role": "Business",
                "profile": profile,
            }

        for index, customer in enumerate(customers, start=1):
            agent_name = f"c{index}"
            key = generate_key()
            account_id = client.account_for_name(agent_name)
            profile = _customer_profile(customer, account_id)
            account_id = await client.register_agent(
                agent_name,
                profile,
                str(key.public_key),
                deposit_yocto=AGENT_REGISTRATION_DEPOSIT_YOCTO,
            )
            document["customers"][str(customer["id"])] = {
                "sim_id": str(customer["id"]),
                "account_id": account_id,
                "secret_key": str(key.secret_key),
                "public_key": str(key.public_key),
                "role": "Customer",
                "profile": profile,
            }

        for entry in document["businesses"].values():
            await root.send(
                entry["account_id"],
                Amount(GAS_FUND_YOCTO),
                wait_until="FINAL",
            )
        for entry in document["customers"].values():
            escrow = int(entry["profile"]["requested_total_cents"]) * YOCTO_PER_USD_CENT
            await root.send(
                entry["account_id"],
                Amount(escrow + GAS_FUND_YOCTO),
                wait_until="FINAL",
            )

        agents_path = Path(args.agents_file)
        agents_path.parent.mkdir(parents=True, exist_ok=True)
        agents_path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        agents_path.chmod(0o600)

        env_path = Path(".sandbox/env.sh")
        env_path.write_text(
            "\n".join(
                [
                    f"export MARKET_CONTRACT_ID={contract_id}",
                    f"export NEAR_NETWORK={network}",
                    f"export NEAR_RPC_URL={rpc_url or ''}",
                    f"export NEAR_AGENTS_FILE={agents_path.as_posix()}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        env_path.chmod(0o600)

        welfare = await client.get_welfare()
        print(
            "Registered "
            f"{len(document['businesses'])} businesses and "
            f"{len(document['customers'])} customers "
            f"(registered_customers={welfare['registered_customers']})"
        )
        print(f"export MARKET_CONTRACT_ID={contract_id}")
        print(f"export NEAR_NETWORK={network}")
        print(f"export NEAR_RPC_URL={rpc_url or ''}")
        print(f"export NEAR_AGENTS_FILE={agents_path.as_posix()}")
    finally:
        await root.aclose()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="python -m magentic_marketplace.near.bootstrap",
        description="Deploy the ekklesia market and register demo agents",
    )
    parser.add_argument(
        "--network",
        default=os.environ.get("NEAR_NETWORK", "sandbox"),
        choices=["sandbox", "testnet", "mainnet"],
    )
    parser.add_argument("--rpc-url", default=os.environ.get("NEAR_RPC_URL") or None)
    parser.add_argument("--contract-id", default=os.environ.get("MARKET_CONTRACT_ID"))
    parser.add_argument("--payout-account", default=None)
    parser.add_argument("--data-dir", default="data/demo_small")
    parser.add_argument("--wasm", default=None)
    parser.add_argument("--agents-file", default=".sandbox/agents.json")
    parser.add_argument("--fee-bps", type=int, default=0)
    parser.add_argument("--deploy", dest="deploy", action="store_true", default=None)
    parser.add_argument("--no-deploy", dest="deploy", action="store_false")
    parser.add_argument("--no-init", action="store_true")
    asyncio.run(bootstrap(parser.parse_args()))


if __name__ == "__main__":
    main()
