"""
Price Service Factory

Creates configured instances of the unified price service with all
necessary dependencies.
"""

import logging
from typing import List, Optional

from interfaces.price_service import PriceService, PriceAPI
from services.price_service_impl import ConsolidatedPriceService, InMemoryPriceCache
from services.repositories import SQLitePriceRepository, ConfigRepositoryImpl
from services.api_adapters import CoinGeckoAPI, CryptoCompareAPI, BinanceAPI, FallbackPriceAPI
from services.usdt_converter import USDTEURConverter

logger = logging.getLogger(__name__)


class PriceServiceFactory:
    """Factory for creating configured price service instances."""
    
    @staticmethod
    def create_production_service(
        coingecko_api_key: Optional[str] = None,
        cryptocompare_api_key: Optional[str] = None,
        binance_api_key: Optional[str] = None,
        binance_secret: Optional[str] = None
    ) -> PriceService:
        """
        Create a production-ready price service with all features enabled.
        
        Args:
            coingecko_api_key: Optional CoinGecko API key for higher rate limits
            cryptocompare_api_key: Optional CryptoCompare API key
            binance_api_key: Optional Binance API key
            binance_secret: Optional Binance secret key
            
        Returns:
            Configured ConsolidatedPriceService
        """
        # Create cache
        cache = InMemoryPriceCache(max_size=10000)
        
        # Create repository
        repository = SQLitePriceRepository()
        
        # Create USDT converter
        usdt_converter = USDTEURConverter()
        
        # Create external APIs in order of preference
        apis: List[PriceAPI] = []
        
        # CoinGecko is primary for historical data
        apis.append(CoinGeckoAPI(api_key=coingecko_api_key))
        
        # CryptoCompare as secondary
        apis.append(CryptoCompareAPI(api_key=cryptocompare_api_key))
        
        # Binance for current prices (if API keys provided)
        if binance_api_key and binance_secret:
            apis.append(BinanceAPI(api_key=binance_api_key, secret_key=binance_secret))
        
        # Wrap in fallback API for robustness
        fallback_api = FallbackPriceAPI(apis)
        
        # Create the unified service
        service = ConsolidatedPriceService(
            cache=cache,
            repository=repository,
            apis=[fallback_api],
            usdt_converter=usdt_converter
        )
        
        logger.info(f"Created production price service with {len(apis)} API sources")
        return service
    
    @staticmethod
    def create_test_service() -> PriceService:
        """
        Create a test service with minimal external dependencies.
        
        Returns:
            Configured ConsolidatedPriceService for testing
        """
        # Use in-memory cache
        cache = InMemoryPriceCache(max_size=1000)
        
        # Use repository (can be mocked in tests)
        repository = SQLitePriceRepository()
        
        # No external APIs for testing
        apis: List[PriceAPI] = []
        
        # USDT converter (can fail gracefully if data not available)
        usdt_converter = USDTEURConverter()
        
        service = ConsolidatedPriceService(
            cache=cache,
            repository=repository,
            apis=apis,
            usdt_converter=usdt_converter
        )
        
        logger.info("Created test price service (no external APIs)")
        return service
    
    @staticmethod
    def create_cache_only_service() -> PriceService:
        """
        Create a service that only uses cache and repository (no external APIs).
        
        This is useful for offline operation or when external APIs should be avoided.
        
        Returns:
            Configured ConsolidatedPriceService without external APIs
        """
        cache = InMemoryPriceCache(max_size=10000)
        repository = SQLitePriceRepository()
        usdt_converter = USDTEURConverter()
        
        service = ConsolidatedPriceService(
            cache=cache,
            repository=repository,
            apis=[],  # No external APIs
            usdt_converter=usdt_converter
        )
        
        logger.info("Created cache-only price service")
        return service


# Convenience function for easy migration
def get_default_price_service() -> PriceService:
    """
    Get the default price service instance.
    
    This function provides a simple way to get a configured price service
    without dealing with the factory complexity.
    
    Returns:
        Default configured PriceService
    """
    return PriceServiceFactory.create_production_service()


# Legacy compatibility functions for gradual migration
def get_price_unified(platform: str, coin: str, currency: str, utc_time) -> Optional[float]:
    """
    Legacy compatibility function.
    
    This allows existing code to gradually migrate to the new unified service
    without requiring immediate changes throughout the codebase.
    """
    from datetime import datetime
    from interfaces.price_service import PriceRequest
    
    service = get_default_price_service()
    
    # Convert datetime if needed
    if hasattr(utc_time, 'date'):
        timestamp = utc_time
    else:
        timestamp = datetime.fromisoformat(str(utc_time))
    
    request = PriceRequest(
        coin=coin,
        currency=currency,
        timestamp=timestamp,
        platform=platform
    )
    
    price = service.get_price(request)
    return float(price.value) if price else None