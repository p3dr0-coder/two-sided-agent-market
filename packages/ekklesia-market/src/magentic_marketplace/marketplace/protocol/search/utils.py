"""Search utils."""

import json
import logging
import math

from magentic_marketplace.platform.database.models import AgentRow

from ...actions import Search, SearchResponse
from ...shared.models import BusinessAgentProfile

logger = logging.getLogger(__name__)


async def convert_agent_rows_to_businesses(
    agent_rows: list[AgentRow],
) -> list[BusinessAgentProfile]:
    """Convert agent rows to BusinessAgentProfile objects."""
    businesses: list[BusinessAgentProfile] = []

    for agent_row in agent_rows:
        try:
            agent = agent_row.data
            business_agent_profile = BusinessAgentProfile.model_validate(
                agent, from_attributes=True
            )
            businesses.append(business_agent_profile)
        except (json.JSONDecodeError, ValueError) as e:
            # Skip invalid business data
            logger.warning(
                f"Failed to validate BusinessAgentProfile {e}", exc_info=True
            )

    return businesses


def paginate_search_response(
    search: Search, businesses: list[BusinessAgentProfile]
) -> SearchResponse:
    """Build a paginated SearchResponse from ranked business profiles."""
    total_possible = len(businesses)
    if search.limit and search.limit > 0:
        start = (search.page - 1) * search.limit
        paginated = businesses[start : start + search.limit]
        total_pages = math.ceil(total_possible / search.limit)
    else:
        paginated = businesses
        total_pages = 1
    return SearchResponse(
        businesses=paginated,
        search_algorithm=search.search_algorithm,
        total_possible_results=total_possible,
        total_pages=total_pages,
    )
