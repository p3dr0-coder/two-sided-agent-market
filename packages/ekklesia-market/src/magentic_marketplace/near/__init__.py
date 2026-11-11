"""Native-NEAR settlement adapter for the marketplace simulation."""

from .adapter import NearSettlementProtocol
from .client import NearClient
from .events import NearAnalyticsFeed

__all__ = ["NearAnalyticsFeed", "NearClient", "NearSettlementProtocol"]
