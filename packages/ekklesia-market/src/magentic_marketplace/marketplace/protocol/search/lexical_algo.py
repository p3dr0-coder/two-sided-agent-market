"""Retrieve and rerank search results using lexical similarity.

The implementation roughly follows what is described here:
https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html.
"""

import re

from ...shared.models import BusinessAgentProfile

_NON_WORD_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def _shingles(text: str, k: int = 4) -> set[str]:
    normalized = _WS_RE.sub(" ", _NON_WORD_RE.sub("", text.lower())).strip()
    padded = f" {normalized} "
    if len(padded) < k:
        padded += " " * (k - len(padded))
    return {padded[i : i + k] for i in range(len(padded) - k + 1)}


def shingle_overlap_score(
    query: str, doc: str, k: int = 4, normalize_length: bool = True
) -> float:
    """Compute the shingle overlap score between two strings.

    Args:
        query (str): The first string.
        doc (str): The second string.
        k (int): The shingle size.
        normalize_length (bool): Whether to normalize the score to the length of the query.

    Returns:
        float: The shingle overlap score between the two strings.

    """
    shingles_query = _shingles(query, k)
    overlap = len(shingles_query & _shingles(doc, k))
    if normalize_length:
        return overlap / len(shingles_query) if shingles_query else 0.0
    return overlap


def lexical_rank(
    query: str,
    businesses: list[BusinessAgentProfile],
    index_name: bool = True,
    index_menu_prices: bool = False,
    index_amenities: bool = False,
) -> list[BusinessAgentProfile]:
    """Rerank search results using lexical similarity.

    Args:
        query: The search query string
        businesses: List of business agent profiles to rank
        index_name (bool): Whether to include the business name in the searchable text.
        index_menu_prices (bool): Whether to include menu item prices in the searchable text.
        index_amenities (bool): Whether to include amenities in the searchable text.

    Returns:
        Ranked list of business agent profiles

    """
    query_shingles = _shingles(query)
    scored = [
        (
            len(
                query_shingles
                & _shingles(
                    business.business.get_searchable_text(
                        index_name=index_name,
                        index_menu_prices=index_menu_prices,
                        index_amenities=index_amenities,
                    )
                )
            ),
            business,
        )
        for business in businesses
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [business for _, business in scored]
