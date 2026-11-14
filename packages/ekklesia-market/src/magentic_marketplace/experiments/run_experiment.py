#!/usr/bin/env python3
"""Run marketplace experiments using YAML configuration files."""

import asyncio
import socket
import time
from datetime import datetime
from pathlib import Path

from magentic_marketplace.experiments.utils import (
    load_businesses_from_yaml,
    load_customers_from_yaml,
)
from magentic_marketplace.marketplace.agents import BusinessAgent, CustomerAgent
from magentic_marketplace.marketplace.protocol.protocol import SimpleMarketplaceProtocol
from magentic_marketplace.platform.client import MarketplaceClient
from magentic_marketplace.platform.database import (
    connect_to_postgresql_database,
    connect_to_sqlite_database,
)
from magentic_marketplace.platform.launcher import AgentLauncher, MarketplaceLauncher


async def _wait_for_agent_count(
    base_url: str, expected: int, *, timeout: float = 60.0
) -> None:
    """Poll the served agent list until the business registrations land."""
    deadline = time.monotonic() + timeout
    count = 0
    while time.monotonic() < deadline:
        async with MarketplaceClient(base_url) as client:
            response = await client.agents.list(offset=0, limit=200)
        count = len(response.items)
        if count >= expected:
            return
        await asyncio.sleep(0.1)
    raise TimeoutError(f"only {count} agents registered")


async def _wait_for_settlements(
    near_client, expected: int, *, timeout: float = 60.0
) -> None:
    """Poll ``get_trade_count`` until every expected settlement landed."""
    deadline = time.monotonic() + timeout
    count = await near_client.get_trade_count()
    while count < expected and time.monotonic() < deadline:
        await asyncio.sleep(0.2)
        count = await near_client.get_trade_count()
    if count < expected:
        raise TimeoutError(f"only {count}/{expected} settlements landed")


async def run_marketplace_experiment(
    data_dir: str | Path,
    experiment_name: str | None = None,
    search_algorithm: str = "simple",
    search_bandwidth: int = 10,
    customer_max_steps: int | None = None,
    db_type: str = "sqlite",
    db_path: str | None = None,
    postgres_host: str = "localhost",
    postgres_port: int = 5432,
    postgres_password: str = "postgres",
    db_pool_min_size: int = 2,
    db_pool_max_size: int = 10,
    server_host: str = "127.0.0.1",
    server_port: int = 0,
    override: bool = False,
    near_settlement: bool = False,
    scripted: bool = False,
    agents_file: str | None = None,
):
    """Run a marketplace experiment using YAML configuration files."""
    if db_type not in {"sqlite", "postgres"}:
        raise ValueError(f"unsupported db_type: {db_type}")
    if scripted and not near_settlement:
        raise ValueError("--scripted requires --near")

    data_dir = Path(data_dir)
    businesses_dir = data_dir / "businesses"
    customers_dir = data_dir / "customers"

    print(f"Loading data from: {data_dir}")
    businesses = load_businesses_from_yaml(businesses_dir)
    customers = load_customers_from_yaml(customers_dir)

    print(f"Loaded {len(customers)} customers and {len(businesses)} businesses")

    if experiment_name is None:
        experiment_name = f"marketplace_{len(customers)}_{len(businesses)}_{int(datetime.now().timestamp() * 1000)}"

    sqlite_path = Path(db_path) if db_path else Path("data") / f"{experiment_name}.db"

    def database_factory():
        if db_type == "sqlite":
            if override and sqlite_path.exists():
                sqlite_path.unlink()
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            return connect_to_sqlite_database(str(sqlite_path))
        return connect_to_postgresql_database(
            schema=experiment_name,
            host=postgres_host,
            port=postgres_port,
            password=postgres_password,
            min_size=db_pool_min_size,
            max_size=db_pool_max_size,
            mode="override" if override else "create_new",
        )

    # Auto-assign port if set to 0
    if server_port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((server_host, 0))
            server_port = s.getsockname()[1]
        print(f"Auto-assigned server port: {server_port}")

    near_client = None
    if near_settlement:
        from magentic_marketplace.near import NearClient, NearSettlementProtocol

        near_client = NearClient(
            agents_file=agents_file,
            experiment_name=experiment_name,
        )
        protocol = NearSettlementProtocol(near_client)
    else:
        protocol = SimpleMarketplaceProtocol()

    marketplace_launcher = MarketplaceLauncher(
        protocol=protocol,
        database_factory=database_factory,
        host=server_host,
        port=server_port,
        server_log_level="warning",
        experiment_name=experiment_name,
    )

    print(f"Using protocol: {marketplace_launcher.protocol.__class__.__name__}")

    try:
        async with marketplace_launcher:
            logger = await marketplace_launcher.create_logger("marketplace_experiment")
            logger.info(
                f"Marketplace experiment started:\nbusinesses={len(businesses)}\ncustomers={len(customers)}\ndata_dir={data_dir}\nexperiment_name:{experiment_name}\ndb_type={db_type}",
            )

            if scripted:
                from magentic_marketplace.marketplace.agents.scripted_business import (
                    DeterministicBusinessAgent,
                )
                from magentic_marketplace.marketplace.agents.scripted_customer import (
                    DeterministicCustomerAgent,
                )

                business_agents = [
                    DeterministicBusinessAgent(
                        business, marketplace_launcher.server_url, near_client
                    )
                    for business in businesses
                ]
                customer_agents = [
                    DeterministicCustomerAgent(
                        customer,
                        marketplace_launcher.server_url,
                        search_bandwidth=max(search_bandwidth, 50),
                        max_steps=min(customer_max_steps or 60, 60),
                    )
                    for customer in customers
                ]

                business_tasks = [
                    asyncio.create_task(agent.run()) for agent in business_agents
                ]
                try:
                    await _wait_for_agent_count(
                        marketplace_launcher.server_url, len(business_agents)
                    )
                    for customer_agent in customer_agents:
                        await customer_agent.run()
                    if near_client is not None:
                        await _wait_for_settlements(near_client, len(customer_agents))
                finally:
                    for business_agent in business_agents:
                        business_agent.shutdown()
                    await asyncio.gather(*business_tasks, return_exceptions=True)
            else:
                business_agents = [
                    BusinessAgent(business, marketplace_launcher.server_url)
                    for business in businesses
                ]
                customer_agents = [
                    CustomerAgent(
                        customer,
                        marketplace_launcher.server_url,
                        search_algorithm=search_algorithm,
                        search_bandwidth=search_bandwidth,
                        max_steps=customer_max_steps,
                    )
                    for customer in customers
                ]

                async with AgentLauncher(
                    marketplace_launcher.server_url
                ) as agent_launcher:
                    try:
                        await agent_launcher.run_agents_with_dependencies(
                            primary_agents=customer_agents,
                            dependent_agents=business_agents,
                        )
                    except KeyboardInterrupt:
                        logger.warning("Simulation interrupted by user")
    finally:
        if near_client is not None:
            await near_client.close()

    print(
        "\nRun analytics with: near-ekklesia analyze "
        f"{sqlite_path if db_type == 'sqlite' else experiment_name} "
        f"--db-type {db_type}" + (" --near" if near_settlement else "")
    )
