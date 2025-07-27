"""
Price Service Interface

Defines the contract for price lookup services, eliminating the current
fragmentation across multiple price systems.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    """Value object for price information."""
    value: Decimal
    coin: str
    currency: str
    timestamp: datetime
    source: str
    
    def __post_init__(self):
        if self.value < 0:
            raise ValueError("Price cannot be negative")
        if not self.coin or not self.currency:
            raise ValueError("Coin and currency must be specified")


@dataclass(frozen=True)
class PriceRequest:
    """Value object for price lookup requests."""
    coin: str
    currency: str
    timestamp: datetime
    platform: Optional[str] = None
    
    def __post_init__(self):
        if not self.coin or not self.currency:
            raise ValueError("Coin and currency must be specified")


class PriceService(ABC):
    """
    Abstract interface for price lookup services.
    
    This replaces the fragmented price systems:
    - price_data.py
    - unified_price_system.py  
    - clean_price_system.py
    - enhanced_check_database.py
    """
    
    @abstractmethod
    def get_price(self, request: PriceRequest) -> Optional[Price]:
        """
        Get price for a specific coin/currency pair at a given timestamp.
        
        Args:
            request: Price lookup request
            
        Returns:
            Price if found, None if not available
        """
        pass
    
    @abstractmethod
    def get_prices_batch(self, requests: List[PriceRequest]) -> Dict[PriceRequest, Optional[Price]]:
        """
        Get multiple prices in a single call for efficiency.
        
        Args:
            requests: List of price lookup requests
            
        Returns:
            Dictionary mapping requests to prices (None if not found)
        """
        pass
    
    @abstractmethod
    def cache_price(self, price: Price) -> None:
        """
        Cache a price for future lookups.
        
        Args:
            price: Price to cache
        """
        pass
    
    @abstractmethod
    def is_cached(self, request: PriceRequest) -> bool:
        """
        Check if a price is available in cache.
        
        Args:
            request: Price lookup request
            
        Returns:
            True if price is cached, False otherwise
        """
        pass


class PriceCache(ABC):
    """Abstract interface for price caching."""
    
    @abstractmethod
    def get(self, request: PriceRequest) -> Optional[Price]:
        """Get cached price."""
        pass
    
    @abstractmethod
    def set(self, price: Price) -> None:
        """Cache a price."""
        pass
    
    @abstractmethod
    def exists(self, request: PriceRequest) -> bool:
        """Check if price exists in cache."""
        pass


class PriceAPI(ABC):
    """Abstract interface for external price APIs."""
    
    @abstractmethod
    def fetch_price(self, request: PriceRequest) -> Optional[Price]:
        """Fetch price from external API."""
        pass
    
    @abstractmethod
    def fetch_prices_batch(self, requests: List[PriceRequest]) -> Dict[PriceRequest, Optional[Price]]:
        """Fetch multiple prices from external API."""
        pass
    
    @abstractmethod
    def get_supported_pairs(self) -> List[Tuple[str, str]]:
        """Get list of supported coin/currency pairs."""
        pass