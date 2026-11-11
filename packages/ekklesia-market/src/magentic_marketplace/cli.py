"""Command-line interface for near-ekklesia."""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from magentic_marketplace.experiments.export_experiment import export_experiment
from magentic_marketplace.experiments.extract_agent_llm_traces import (
    run_extract_traces,
)
from magentic_marketplace.experiments.list_experiments import list_experiments
from magentic_marketplace.experiments.run_analytics import run_analytics
from magentic_marketplace.experiments.run_audit import run_audit
from magentic_marketplace.experiments.run_experiment import run_marketplace_experiment
from magentic_marketplace.experiments.utils import setup_logging
from magentic_marketplace.ui import run_ui_server

DEFAULT_POSTGRES_PORT = 5432
DEFAULT_UI_PORT = 5000


def run_experiment_command(args):
    """Handle the experiment subcommand."""
    setup_logging()
    logger = logging.getLogger(__name__)

    if hasattr(args, "log_level"):
        numeric_level = getattr(logging, args.log_level.upper())
        logging.getLogger().setLevel(numeric_level)

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        logger.error(f"Data directory does not exist: {data_dir}")
        sys.exit(1)

    businesses_dir = data_dir / "businesses"
    customers_dir = data_dir / "customers"
    if not businesses_dir.exists():
        logger.error(f"Businesses directory does not exist: {businesses_dir}")
        sys.exit(1)
    if not customers_dir.exists():
        logger.error(f"Customers directory does not exist: {customers_dir}")
        sys.exit(1)

    env_file = getattr(args, "env_file", ".env")
    did_load_env = load_dotenv(env_file)
    if did_load_env:
        logger.info(f"Loaded environment variables from env file at path: {env_file}")
    else:
        logger.warning(
            f"No environment variables loaded from env file at path: {env_file}"
        )

    database_target = (
        args.db_path
        if args.db_type == "sqlite" and args.db_path
        else (
            f"data/{args.experiment_name}.db"
            if args.db_type == "sqlite" and args.experiment_name
            else (
                args.experiment_name
                if args.db_type == "postgres"
                else "data/<generated-name>.db"
            )
        )
    )
    logger.info(
        "Marketplace Experiment Runner\n"
        "This experiment will:\n"
        f"1. Load businesses from: {businesses_dir}\n"
        f"2. Load customers from: {customers_dir}\n"
        f"3. Use database: {database_target} ({args.db_type})\n"
        "4. Start a marketplace server with the selected protocol\n"
        "5. Register all business and customer agents\n"
        "6. Run the marketplace simulation\n"
    )

    asyncio.run(
        run_marketplace_experiment(
            data_dir=data_dir,
            experiment_name=args.experiment_name,
            search_algorithm=args.search_algorithm,
            search_bandwidth=args.search_bandwidth,
            customer_max_steps=args.customer_max_steps,
            db_type=args.db_type,
            db_path=args.db_path,
            postgres_host=args.postgres_host,
            postgres_port=args.postgres_port,
            postgres_password=args.postgres_password,
            db_pool_min_size=args.db_pool_min_size,
            db_pool_max_size=args.db_pool_max_size,
            server_host=args.server_host,
            server_port=args.server_port,
            override=args.override_db,
            near_settlement=args.near,
            scripted=args.scripted,
            agents_file=args.agents_file,
        )
    )


def run_analysis_command(args):
    """Handle the analytics subcommand."""
    save_to_json = not args.no_save_json
    asyncio.run(
        run_analytics(
            args.database_name,
            args.db_type,
            save_to_json=save_to_json,
            print_results=True,
            fuzzy_match_distance=args.fuzzy_match_distance,
            near=args.near,
        )
    )


def run_extract_traces_command(args):
    """Handle the extract-traces subcommand."""
    asyncio.run(run_extract_traces(args.database_name, args.db_type))


def run_audit_command(args):
    """Handle the audit subcommand."""
    save_to_json = not args.no_save_json
    asyncio.run(run_audit(args.database_name, args.db_type, save_to_json=save_to_json))


def list_experiments_command(args):
    """Handle the list subcommand."""
    asyncio.run(
        list_experiments(
            host=args.postgres_host,
            port=args.postgres_port,
            database=args.postgres_database,
            user=args.postgres_user,
            password=args.postgres_password,
            limit=args.limit,
        )
    )


def run_export_command(args):
    """Handle the export subcommand."""
    asyncio.run(
        export_experiment(
            experiment_name=args.experiment_name,
            output_dir=args.output_dir,
            output_filename=args.output_filename,
            postgres_host=args.postgres_host,
            postgres_port=args.postgres_port,
            postgres_user=args.postgres_user,
            postgres_password=args.postgres_password,
        )
    )


def run_ui_command(args):
    """Handle the UI subcommand to launch the visualizer."""
    run_ui_server(
        database_name=args.database_name,
        db_type=args.db_type,
        postgres_host=args.postgres_host,
        postgres_port=args.postgres_port,
        postgres_password=args.postgres_password,
        ui_port=args.ui_port,
        ui_host=args.ui_host,
    )


def main():
    """Run main CLI."""
    parser = argparse.ArgumentParser(
        prog="near-ekklesia",
        description=(
            "near-ekklesia - agent market simulation with native-NEAR escrow, "
            "scoped per-agent keys, and EVENT_JSON welfare metrics"
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command", help="Available commands", required=True
    )

    experiment_parser = subparsers.add_parser(
        "run", help="Run a marketplace experiment using YAML configuration files"
    )
    experiment_parser.set_defaults(func=run_experiment_command)

    experiment_parser.add_argument(
        "data_dir",
        type=str,
        help="Path to the data directory containing businesses/ and customers/ subdirectories",
    )
    experiment_parser.add_argument(
        "--search-algorithm",
        type=str,
        default="lexical",
        help="Search algorithm for customer agents (default: lexical)",
    )
    experiment_parser.add_argument(
        "--search-bandwidth",
        type=int,
        default=10,
        help="Search bandwidth for customer agents (default: 10)",
    )
    experiment_parser.add_argument(
        "--customer-max-steps",
        type=int,
        default=100,
        help="Maximum number of steps a customer agent can take before stopping.",
    )
    experiment_parser.add_argument(
        "--experiment-name",
        default=None,
        help=(
            "Experiment name; used as the SQLite file stem "
            "(data/<name>.db) or the Postgres schema name"
        ),
    )
    experiment_parser.add_argument(
        "--db-type",
        choices=["sqlite", "postgres"],
        default="sqlite",
        help="Database backend (default: sqlite)",
    )
    experiment_parser.add_argument(
        "--db-path",
        default=None,
        help=(
            "SQLite database path (default: data/<experiment_name>.db); "
            "ignored for Postgres"
        ),
    )
    experiment_parser.add_argument(
        "--near",
        action="store_true",
        help="Settle OrderProposal/Payment messages with the NEAR contract",
    )
    experiment_parser.add_argument(
        "--scripted",
        action="store_true",
        help="Use the deterministic no-LLM agents (requires --near)",
    )
    experiment_parser.add_argument(
        "--agents-file",
        default=None,
        help="Path to the bootstrap agents.json (default: NEAR_AGENTS_FILE)",
    )
    experiment_parser.add_argument(
        "--env-file",
        default=".env",
        help=".env file with environment variables to load.",
    )
    experiment_parser.add_argument(
        "--postgres-host",
        default=os.environ.get("POSTGRES_HOST", "localhost"),
        help="PostgreSQL host (default: POSTGRES_HOST env var or localhost)",
    )
    experiment_parser.add_argument(
        "--postgres-port",
        type=int,
        default=int(os.environ.get("POSTGRES_PORT", DEFAULT_POSTGRES_PORT)),
        help=f"PostgreSQL port (default: POSTGRES_PORT env var or {DEFAULT_POSTGRES_PORT})",
    )
    experiment_parser.add_argument(
        "--postgres-password",
        default=os.environ.get("POSTGRES_PASSWORD", "postgres"),
        help="PostgreSQL password (default: POSTGRES_PASSWORD env var or postgres)",
    )
    experiment_parser.add_argument(
        "--db-pool-min-size",
        type=int,
        default=2,
        help="Minimum connections in PostgreSQL pool (default: 2)",
    )
    experiment_parser.add_argument(
        "--db-pool-max-size",
        type=int,
        default=10,
        help="Maximum connections in PostgreSQL pool (default: 10)",
    )
    experiment_parser.add_argument(
        "--server-host",
        default="127.0.0.1",
        help="FastAPI server host (default: 127.0.0.1)",
    )
    experiment_parser.add_argument(
        "--server-port",
        type=int,
        default=0,
        help="FastAPI server port (default: auto-assign)",
    )
    experiment_parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )
    experiment_parser.add_argument(
        "--override-db",
        action="store_true",
        help="Unlink an existing SQLite file or override an existing Postgres schema.",
    )

    analytics_parser = subparsers.add_parser(
        "analyze", help="Analyze marketplace simulation data"
    )
    analytics_parser.set_defaults(func=run_analysis_command)
    analytics_parser.add_argument(
        "database_name", help="Path to the SQLite database file or Postgres schema name"
    )
    analytics_parser.add_argument(
        "--db-type",
        choices=["sqlite", "postgres"],
        default="postgres",
        help="Type of database to use (default: postgres)",
    )
    analytics_parser.add_argument(
        "--no-save-json",
        action="store_true",
        help="Disable saving analytics to JSON file",
    )
    analytics_parser.add_argument(
        "--fuzzy-match-distance",
        type=int,
        default=0,
        help="Maximum Levenshtein distance for fuzzy item name matching (default: 0)",
    )
    analytics_parser.add_argument(
        "--near",
        action="store_true",
        help="Cross-check get_welfare and EVENT_JSON logs; print the headline",
    )

    extract_traces_parser = subparsers.add_parser(
        "extract-traces",
        help="Extract LLM traces from marketplace simulation and save to markdown files",
    )
    extract_traces_parser.set_defaults(func=run_extract_traces_command)
    extract_traces_parser.add_argument(
        "database_name", help="Postgres schema name or path to the SQLite database file"
    )
    extract_traces_parser.add_argument(
        "--db-type",
        choices=["sqlite", "postgres"],
        default="postgres",
        help="Type of database to use (default: postgres)",
    )

    audit_parser = subparsers.add_parser(
        "audit",
        help="Audit marketplace simulation to verify customers received all proposals",
    )
    audit_parser.set_defaults(func=run_audit_command)
    audit_parser.add_argument(
        "database_name", help="Postgres schema name or path to the SQLite database file"
    )
    audit_parser.add_argument(
        "--db-type",
        choices=["sqlite", "postgres"],
        default="postgres",
        help="Type of database to use (default: postgres)",
    )
    audit_parser.add_argument(
        "--no-save-json",
        action="store_true",
        help="Disable saving audit results to JSON file",
    )

    export_parser = subparsers.add_parser(
        "export",
        help="Export a PostgreSQL experiment to SQLite database file",
    )
    export_parser.set_defaults(func=run_export_command)
    export_parser.add_argument(
        "experiment_name",
        help="Name of the experiment (PostgreSQL schema name)",
    )
    export_parser.add_argument(
        "-o",
        "--output-dir",
        help="Output directory for the SQLite database file (default: current directory)",
        default=None,
    )
    export_parser.add_argument(
        "-f",
        "--output-filename",
        help="Output filename for the SQLite database (default: <experiment_name>.db)",
        default=None,
    )
    export_parser.add_argument(
        "--postgres-host",
        default=os.environ.get("POSTGRES_HOST", "localhost"),
        help="PostgreSQL host (default: POSTGRES_HOST env var or localhost)",
    )
    export_parser.add_argument(
        "--postgres-port",
        type=int,
        default=int(os.environ.get("POSTGRES_PORT", "5432")),
        help="PostgreSQL port (default: POSTGRES_PORT env var or 5432)",
    )
    export_parser.add_argument(
        "--postgres-user",
        default=os.environ.get("POSTGRES_USER", "postgres"),
        help="PostgreSQL user (default: POSTGRES_USER env var or postgres)",
    )
    export_parser.add_argument(
        "--postgres-password",
        default=os.environ.get("POSTGRES_PASSWORD", "postgres"),
        help="PostgreSQL password (default: POSTGRES_PASSWORD env var or postgres)",
    )

    list_experiments_parser = subparsers.add_parser(
        "list",
        help="List all marketplace experiments stored in PostgreSQL",
    )
    list_experiments_parser.set_defaults(func=list_experiments_command)
    list_experiments_parser.add_argument(
        "--postgres-host",
        default=os.environ.get("POSTGRES_HOST", "localhost"),
        help="PostgreSQL host (default: POSTGRES_HOST env var or localhost)",
    )
    list_experiments_parser.add_argument(
        "--postgres-port",
        type=int,
        default=int(os.environ.get("POSTGRES_PORT", "5432")),
        help="PostgreSQL port (default: POSTGRES_PORT env var or 5432)",
    )
    list_experiments_parser.add_argument(
        "--postgres-database",
        default=os.environ.get("POSTGRES_DB", "marketplace"),
        help="PostgreSQL database name (default: POSTGRES_DB env var or marketplace)",
    )
    list_experiments_parser.add_argument(
        "--postgres-user",
        default=os.environ.get("POSTGRES_USER", "postgres"),
        help="PostgreSQL user (default: POSTGRES_USER env var or postgres)",
    )
    list_experiments_parser.add_argument(
        "--postgres-password",
        default=os.environ.get("POSTGRES_PASSWORD", "postgres"),
        help="PostgreSQL password (default: POSTGRES_PASSWORD env var or postgres)",
    )
    list_experiments_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of experiments to display",
    )

    ui_parser = subparsers.add_parser(
        "ui", help="Launch interactive visualizer for marketplace data"
    )
    ui_parser.set_defaults(func=run_ui_command)
    ui_parser.add_argument(
        "database_name",
        help="Postgres schema name or path to the SQLite database file",
    )
    ui_parser.add_argument(
        "--db-type",
        choices=["sqlite", "postgres"],
        default="postgres",
        help="Type of database to use (default: postgres)",
    )
    ui_parser.add_argument(
        "--postgres-host",
        default="localhost",
        help="PostgreSQL host (default: localhost)",
    )
    ui_parser.add_argument(
        "--postgres-port",
        type=int,
        default=DEFAULT_POSTGRES_PORT,
        help=f"PostgreSQL port (default: {DEFAULT_POSTGRES_PORT})",
    )
    ui_parser.add_argument(
        "--postgres-password",
        default="postgres",
        help="PostgreSQL password (default: postgres)",
    )
    ui_parser.add_argument(
        "--ui-host",
        default="localhost",
        help="UI server host (default: localhost)",
    )
    ui_parser.add_argument(
        "--ui-port",
        type=int,
        default=DEFAULT_UI_PORT,
        help=f"Port for ui server(default: {DEFAULT_UI_PORT})",
    )

    args = parser.parse_args()

    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nExecution interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
