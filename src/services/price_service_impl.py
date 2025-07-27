"""
Unified Price Service Implementation

This consolidates ALL the fragmented price systems:
- price_data.py
- unified_price_system.py
- clean_price_system.py
- enhanced_check_database.py

Into a single, well-tested, maintainable service.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, List
from pathlib import Path

from interfaces.price_service import PriceService, Price, PriceRequest, PriceCache, PriceAPI
from interfaces.repositories import PriceRepository
from services.usdt_converter import USDTEURConverter


logger = logging.getLogger(__name__)


class ConsolidatedPriceService(PriceService):
    """
    Unified price service that replaces all fragmented implementations.
    
    Strategy pattern for different price sources:
    1. Cache (fastest)
    2. Enhanced database  
    3. CSV historical data
    4. USDT conversion
    5. External APIs (slowest)
    """
    
    def __init__(self, 
                 cache: PriceCache,
                 repository: PriceRepository,
                 apis: List[PriceAPI],
                 usdt_converter: Optional[USDTEURConverter] = None):
        self.cache = cache
        self.repository = repository
        self.apis = apis
        self.usdt_converter = usdt_converter
        self.failed_lookups = set()  # Prevent infinite loops
        
        # Symbol mappings for legacy tokens
        self.symbol_mappings = {
            'BCC': 'BCH',    # Bitcoin Cash
            'LUNA': 'LUNC',  # Terra Classic
        }
    
    def get_price(self, request: PriceRequest) -> Optional[Price]:
        """Main price lookup method with clear fallback chain."""
        
        # Normalize the request
        normalized_request = self._normalize_request(request)
        lookup_key = self._get_lookup_key(normalized_request)
        
        # Prevent infinite loops
        if lookup_key in self.failed_lookups:
            return None
        
        try:
            # Strategy 1: Check cache first (fastest)
            if self.cache.exists(normalized_request):
                price = self.cache.get(normalized_request)
                if price and price.value > 0:
                    logger.debug(f"Cache hit: {normalized_request.coin}/{normalized_request.currency}")
                    return price
            
            # Strategy 2: Check repository (database)
            price = self._get_from_repository(normalized_request)
            if price:
                self.cache.set(price)
                return price
            
            # Strategy 3: Try USDT conversion (for EUR requests)
            if normalized_request.currency == 'EUR' and self.usdt_converter:
                price = self._try_usdt_conversion(normalized_request)
                if price:
                    self.cache.set(price)
                    self.repository.save_price(
                        price.coin, price.currency, price.timestamp, 
                        float(price.value), normalized_request.platform or 'consolidated'
                    )
                    return price
            
            # Strategy 4: Try external APIs (slowest)
            price = self._try_external_apis(normalized_request)
            if price:
                self.cache.set(price)
                self.repository.save_price(
                    price.coin, price.currency, price.timestamp,
                    float(price.value), normalized_request.platform or 'api'
                )
                logger.info(f"✅ API success: {price.coin}/{price.currency} = {price.value}")
                return price
            
            # Strategy 5: Historical token handling (for very old/delisted tokens)
            if normalized_request.timestamp.year <= 2018:
                if normalized_request.coin.upper() in ['ETF', 'BCC', 'NPXS', 'RAMP']:
                    # Cache zero price to prevent future lookups
                    zero_price = Price(
                        value=Decimal('0'),
                        coin=normalized_request.coin,
                        currency=normalized_request.currency,
                        timestamp=normalized_request.timestamp,
                        source='historical_delisted'
                    )
                    self.cache.set(zero_price)
                    self.repository.save_price(
                        zero_price.coin, zero_price.currency, zero_price.timestamp,
                        0.0, 'delisted'
                    )
                    logger.info(f"Cached zero price for delisted token: {normalized_request.coin}")
                    return zero_price
            
            # All strategies failed
            self.failed_lookups.add(lookup_key)
            logger.warning(f"Price not found: {normalized_request.coin}/{normalized_request.currency} on {normalized_request.timestamp.date()}")
            return None
            
        except Exception as e:
            logger.error(f"Price lookup error: {e}")
            self.failed_lookups.add(lookup_key)
            return None
    
    def get_prices_batch(self, requests: List[PriceRequest]) -> Dict[PriceRequest, Optional[Price]]:
        """Batch price lookup for efficiency."""
        results = {}
        
        # Group requests by strategy for optimization
        cache_misses = []
        
        for request in requests:
            normalized = self._normalize_request(request)
            if self.cache.exists(normalized):
                results[request] = self.cache.get(normalized)
            else:
                cache_misses.append(request)
        
        # Process cache misses individually (could be optimized further)
        for request in cache_misses:
            results[request] = self.get_price(request)
        
        return results
    
    def cache_price(self, price: Price) -> None:
        """Cache a price."""
        self.cache.set(price)
    
    def is_cached(self, request: PriceRequest) -> bool:
        """Check if price is cached."""
        normalized = self._normalize_request(request)
        return self.cache.exists(normalized)
    
    def _normalize_request(self, request: PriceRequest) -> PriceRequest:
        """Normalize request by applying symbol mappings."""
        normalized_coin = self.symbol_mappings.get(request.coin.upper(), request.coin.upper())
        
        return PriceRequest(
            coin=normalized_coin,
            currency=request.currency.upper(),
            timestamp=request.timestamp,
            platform=request.platform
        )
    
    def _get_lookup_key(self, request: PriceRequest) -> str:
        """Generate unique lookup key."""
        return f"{request.platform}:{request.coin}:{request.currency}:{request.timestamp.date()}"
    
    def _get_from_repository(self, request: PriceRequest) -> Optional[Price]:
        """Get price from repository with date tolerance."""
        platform = request.platform or 'default'
        
        # Try exact timestamp first
        price_value = self.repository.get_price(
            request.coin, request.currency, request.timestamp, platform
        )
        
        if price_value and price_value > 0:
            return Price(
                value=Decimal(str(price_value)),
                coin=request.coin,
                currency=request.currency,
                timestamp=request.timestamp,
                source='database'
            )
        
        # Try with date tolerance (±7 days)
        for days_offset in range(1, 8):
            for direction in [-1, 1]:
                tolerance_date = request.timestamp + timedelta(days=days_offset * direction)
                price_value = self.repository.get_price(
                    request.coin, request.currency, tolerance_date, platform
                )
                
                if price_value and price_value > 0:
                    logger.debug(f"Found price with {days_offset} day tolerance")
                    return Price(
                        value=Decimal(str(price_value)),
                        coin=request.coin,
                        currency=request.currency,
                        timestamp=tolerance_date,
                        source='database_tolerance'
                    )
        
        return None
    
    def _try_usdt_conversion(self, request: PriceRequest) -> Optional[Price]:
        """Try USDT to EUR conversion."""
        if not self.usdt_converter or request.currency != 'EUR':
            return None
        
        try:
            # Get COIN/USDT price first
            usdt_request = PriceRequest(
                coin=request.coin,
                currency='USDT',
                timestamp=request.timestamp,
                platform=request.platform
            )
            
            usdt_price_value = self.repository.get_price(
                usdt_request.coin, usdt_request.currency, 
                usdt_request.timestamp, usdt_request.platform or 'default'
            )
            
            if not usdt_price_value or usdt_price_value <= 0:
                return None
            
            # Convert USDT to EUR
            eur_rate = self.usdt_converter.get_eur_rate(request.timestamp.date())
            if not eur_rate:
                return None
            
            eur_value = Decimal(str(usdt_price_value)) * Decimal(str(eur_rate))
            
            return Price(
                value=eur_value,
                coin=request.coin,
                currency='EUR',
                timestamp=request.timestamp,
                source='usdt_conversion'
            )
            
        except Exception as e:
            logger.debug(f"USDT conversion failed: {e}")
            return None
    
    def _try_external_apis(self, request: PriceRequest) -> Optional[Price]:
        """Try external APIs in order of preference."""
        for api in self.apis:
            try:
                price = api.fetch_price(request)
                if price and price.value > 0:
                    return price
            except Exception as e:
                logger.debug(f"API {api.__class__.__name__} failed: {e}")
                continue
        
        return None


class InMemoryPriceCache(PriceCache):
    """Simple in-memory cache implementation."""
    
    def __init__(self, max_size: int = 10000):
        self.cache: Dict[str, Price] = {}
        self.max_size = max_size
    
    def get(self, request: PriceRequest) -> Optional[Price]:
        key = self._get_key(request)
        return self.cache.get(key)
    
    def set(self, price: Price) -> None:
        if len(self.cache) >= self.max_size:
            # Simple LRU: remove oldest entry
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
        
        key = self._get_key_from_price(price)
        self.cache[key] = price
    
    def exists(self, request: PriceRequest) -> bool:
        key = self._get_key(request)
        return key in self.cache
    
    def _get_key(self, request: PriceRequest) -> str:
        return f"{request.coin}:{request.currency}:{request.timestamp.isoformat()}"
    
    def _get_key_from_price(self, price: Price) -> str:
        return f"{price.coin}:{price.currency}:{price.timestamp.isoformat()}"


