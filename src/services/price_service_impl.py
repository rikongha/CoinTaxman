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
from services.missing_coins_tracker import get_missing_coins_tracker


logger = logging.getLogger(__name__)


class ConsolidatedPriceService(PriceService):
    """
    Unified price service that replaces all fragmented implementations.
    
    Strategy pattern for different price sources:
    1. Cache (fastest)
    2. Enhanced database  
    3. CSV historical data
    4. Direct exchange APIs
    5. Exchange APIs with USDT conversion (for EUR requests)
    6. Database USDT conversion
    7. CryptoCompare API
    8. Missing coins tracking (slowest)
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
        
        # Symbol mappings for legacy tokens, rebrands, and forks
        self.symbol_mappings = {
            # Bitcoin Cash fork
            'BCC': 'BCH',
            
            # Terra ecosystem collapse
            'LUNA': 'LUNC',      # Terra Classic
            'UST': 'USTC',       # TerraUSD Classic
            
            # Aave rebrand
            'LEND': 'AAVE',      # Lend Token became Aave
            
            # Other symbol changes and mappings
            'BETH': 'BETH',      # Binance Ethereum (keep as is)
            'TRX': 'TRX',        # TRON (keep as is)
            
            # Additional historical mappings
            'NPXS': 'PUNDIX',    # Pundi X rebrand
            'RAMP': 'RAMP',      # Keep as is
            'ETF': 'ETF',        # Keep as is (if exists)
        }
    
    def get_price(self, request: PriceRequest) -> Optional[Price]:
        """Main price lookup method with optimized fallback chain."""
        
        # Get swap ratio before normalization
        original_coin = request.coin.upper()
        date = request.timestamp.date()
        from services.symbol_mappings import symbol_manager
        mapped_symbol, swap_ratio = symbol_manager.get_symbol_mapping(original_coin, date)
        
        # Normalize the request
        normalized_request = self._normalize_request(request)
        lookup_key = self._get_lookup_key(normalized_request)
        
        # Prevent infinite loops
        if lookup_key in self.failed_lookups:
            return None
        
        try:
            # Strategy 1: Check in-memory cache first (fastest)
            if self.cache.exists(normalized_request):
                price = self.cache.get(normalized_request)
                if price and price.value > 0:
                    logger.debug(f"✅ Cache hit: {normalized_request.coin}/{normalized_request.currency} from cache")
                    # Apply swap ratio adjustment if needed
                    adjusted_price = self._apply_swap_ratio_adjustment(price, original_coin, swap_ratio)
                    return adjusted_price
            
            # Strategy 2: Check legacy databases (existing cached data)
            price = self._get_from_repository(normalized_request)
            if price:
                self.cache.set(price)
                # Apply swap ratio adjustment if needed
                adjusted_price = self._apply_swap_ratio_adjustment(price, original_coin, swap_ratio)
                return adjusted_price
            
            # Strategy 2.5: Check historical CSV files (coingecko data)
            price = self._get_from_historical_csv(normalized_request)
            if price:
                self.cache.set(price)
                self.repository.save_price(
                    price.coin, price.currency, price.timestamp,
                    float(price.value), normalized_request.platform or 'historical_csv'
                )
                logger.info(f"✅ Historical CSV success: {price.coin}/{price.currency} = {price.value}")
                return price
            
            # Strategy 3: Try direct exchange APIs (Binance, Kraken, etc.)
            price = self._try_external_apis(normalized_request)
            if price:
                self.cache.set(price)
                self.repository.save_price(
                    price.coin, price.currency, price.timestamp,
                    float(price.value), normalized_request.platform or 'exchange_api'
                )
                logger.info(f"✅ Exchange API success: {price.coin}/{price.currency} = {price.value}")
                return price
            
            # Strategy 3.5: For EUR requests, check USDT pairs on exchanges and calculate EUR manually
            if normalized_request.currency == 'EUR' and self.usdt_converter:
                price = self._try_exchange_usdt_to_eur_conversion(normalized_request)
                if price:
                    self.cache.set(price)
                    self.repository.save_price(
                        price.coin, price.currency, price.timestamp,
                        float(price.value), normalized_request.platform or 'exchange_usdt_to_eur'
                    )
                    logger.info(f"✅ Exchange USDT→EUR conversion: {price.coin}/{price.currency} = {price.value}")
                    return price
            
            # Strategy 4: Try USDT conversion from database (using historical rates)
            if normalized_request.currency == 'EUR' and self.usdt_converter:
                price = self._try_usdt_conversion(normalized_request)
                if price:
                    self.cache.set(price)
                    self.repository.save_price(
                        price.coin, price.currency, price.timestamp, 
                        float(price.value), normalized_request.platform or 'usdt_conversion'
                    )
                    return price
            
            # Strategy 5: Try CryptoCompare API (for critical missing prices)
            price = self._try_cryptocompare_api(normalized_request)
            if price:
                self.cache.set(price)
                self.repository.save_price(
                    price.coin, price.currency, price.timestamp,
                    float(price.value), normalized_request.platform or 'cryptocompare'
                )
                logger.info(f"✅ CryptoCompare success: {price.coin}/{price.currency} = {price.value}")
                return price
            
            # Strategy 6: Historical token handling (for very old/delisted tokens)
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
            
            # All strategies failed - track for manual sourcing
            self.failed_lookups.add(lookup_key)
            self._track_missing_coin(normalized_request, "All lookup strategies exhausted")
            return None
            
        except Exception as e:
            logger.error(f"Price lookup error: {e}")
            self.failed_lookups.add(lookup_key)
            self._track_missing_coin(normalized_request, f"Error: {e}")
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
        """Normalize request by applying complex symbol mappings with date context."""
        coin = request.coin.upper()
        date = request.timestamp.date()
        
        # Apply date-conditional symbol mappings
        normalized_coin = self._apply_symbol_mapping(coin, date)
        
        return PriceRequest(
            coin=normalized_coin,
            currency=request.currency.upper(),
            timestamp=request.timestamp,
            platform=request.platform
        )
    
    def _apply_symbol_mapping(self, coin: str, date) -> str:
        """Apply comprehensive symbol mappings using the symbol manager."""
        from services.symbol_mappings import symbol_manager
        
        mapped_symbol, swap_ratio = symbol_manager.get_symbol_mapping(coin, date)
        
        # Store swap ratio for potential price adjustments
        # (Currently not implemented but could be used for ratio adjustments)
        if swap_ratio and swap_ratio != 1.0:
            logger.debug(f"Symbol {coin} has swap ratio {swap_ratio} - price adjustment may be needed")
        
        return mapped_symbol
    
    def _apply_swap_ratio_adjustment(self, price: Price, original_coin: str, swap_ratio: Optional[float]) -> Price:
        """Apply swap ratio adjustment for token conversions like LEND→AAVE."""
        if not swap_ratio or swap_ratio == 1.0:
            return price
        
        # For token swaps, the old token is worth 1/ratio of the new token
        # E.g., 100 LEND = 1 AAVE, so 1 LEND = 1/100 AAVE price
        adjusted_value = price.value / Decimal(str(swap_ratio))
        
        logger.debug(f"🔄 Swap ratio adjustment: {original_coin} price adjusted by 1/{swap_ratio} = {adjusted_value}")
        
        return Price(
            value=adjusted_value,
            coin=original_coin,  # Keep original coin symbol
            currency=price.currency,
            timestamp=price.timestamp,
            source=f"{price.source}_swap_adjusted"
        )
    
    def _get_lookup_key(self, request: PriceRequest) -> str:
        """Generate unique lookup key."""
        return f"{request.platform}:{request.coin}:{request.currency}:{request.timestamp.date()}"
    
    def _get_from_repository(self, request: PriceRequest) -> Optional[Price]:
        """Get price from repository with date tolerance and cross-platform fallback."""
        platform = request.platform or 'default'
        
        # Try exact timestamp first with specific platform
        price_value = self.repository.get_price(
            request.coin, request.currency, request.timestamp, platform
        )
        
        if price_value and price_value > 0:
            return Price(
                value=Decimal(str(price_value)),
                coin=request.coin,
                currency=request.currency,
                timestamp=request.timestamp,
                source=f'database_{platform}'
            )
        
        # Strategy 2.1: Try any platform for the same coin/currency/date
        if platform != 'default':
            price_value = self.repository.get_price(
                request.coin, request.currency, request.timestamp, 'default'
            )
            
            if price_value and price_value > 0:
                logger.debug(f"✅ Cross-platform fallback: {request.coin}/{request.currency} from default instead of {platform}")
                return Price(
                    value=Decimal(str(price_value)),
                    coin=request.coin,
                    currency=request.currency,
                    timestamp=request.timestamp,
                    source='database_cross_platform'
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
            # Direct USDT/EUR conversion using historical rates
            if request.coin.upper() == 'USDT':
                eur_rate = self.usdt_converter.get_eur_rate(request.timestamp.date())
                if eur_rate and eur_rate > 0:
                    return Price(
                        value=Decimal(str(eur_rate)),
                        coin=request.coin,
                        currency='EUR',
                        timestamp=request.timestamp,
                        source='usdt_converter_direct'
                    )
            
            # Indirect conversion: Get COIN/USDT price first, then convert to EUR
            usdt_request = PriceRequest(
                coin=request.coin,
                currency='USDT',
                timestamp=request.timestamp,
                platform=request.platform
            )
            
            # Try to get USDT price from multiple sources
            usdt_price_value = None
            
            # 1. Try repository first
            usdt_price_value = self.repository.get_price(
                usdt_request.coin, usdt_request.currency, 
                usdt_request.timestamp, usdt_request.platform or 'default'
            )
            
            # 2. If not found in repository, try external APIs for USDT pair
            if not usdt_price_value or usdt_price_value <= 0:
                logger.debug(f"No USDT price in repository, trying APIs for {request.coin}/USDT")
                for api in self.apis:
                    try:
                        usdt_price = api.fetch_price(usdt_request)
                        if usdt_price and usdt_price.value > 0:
                            usdt_price_value = float(usdt_price.value)
                            logger.debug(f"Found {request.coin}/USDT = {usdt_price_value} via {api.__class__.__name__}")
                            
                            # Cache the USDT price for future use
                            self.cache.set(usdt_price)
                            self.repository.save_price(
                                usdt_price.coin, usdt_price.currency, usdt_price.timestamp,
                                usdt_price_value, request.platform or 'exchange_api_usdt'
                            )
                            break
                    except Exception as e:
                        logger.debug(f"API {api.__class__.__name__} failed for USDT conversion: {e}")
                        continue
            
            if not usdt_price_value or usdt_price_value <= 0:
                logger.debug(f"No USDT price found for {request.coin} from any source")
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
    
    def _try_exchange_usdt_to_eur_conversion(self, request: PriceRequest) -> Optional[Price]:
        """
        When EUR pair is missing, check if USDT pair exists on exchanges and calculate EUR manually.
        
        Process: COIN/EUR missing → Find COIN/USDT on exchange → Use USDTEUR file → Calculate COIN/EUR
        """
        if not self.usdt_converter or request.currency != 'EUR':
            return None
        
        try:
            # Create USDT request for the same platform/exchange
            usdt_request = PriceRequest(
                coin=request.coin,
                currency='USDT',
                timestamp=request.timestamp,
                platform=request.platform  # Same exchange that's missing EUR pair
            )
            
            logger.debug(f"💱 {request.coin}/EUR missing, checking {request.coin}/USDT on {request.platform}")
            
            # Try exchange APIs to find USDT pair
            for api in self.apis:
                try:
                    usdt_price = api.fetch_price(usdt_request)
                    if usdt_price and usdt_price.value > 0:
                        # Get USDT/EUR rate from historical file
                        eur_rate = self.usdt_converter.get_eur_rate(request.timestamp.date())
                        if not eur_rate or eur_rate <= 0:
                            logger.debug(f"❌ No USDT/EUR rate for {request.timestamp.date()}")
                            continue
                        
                        # Calculate: COIN/EUR = COIN/USDT * USDT/EUR
                        eur_value = usdt_price.value * Decimal(str(eur_rate))
                        
                        logger.info(f"✅ Manual calculation: {request.coin}/USDT = {usdt_price.value} * USDT/EUR = {eur_rate} → {request.coin}/EUR = {eur_value}")
                        
                        # Cache both prices for efficiency
                        self.cache.set(usdt_price)
                        self.repository.save_price(
                            usdt_price.coin, usdt_price.currency, usdt_price.timestamp,
                            float(usdt_price.value), request.platform or 'exchange_usdt'
                        )
                        
                        return Price(
                            value=eur_value,
                            coin=request.coin,
                            currency='EUR',
                            timestamp=request.timestamp,
                            source=f'calculated_from_usdt_via_{api.__class__.__name__}'
                        )
                        
                except Exception as e:
                    logger.debug(f"❌ {api.__class__.__name__} failed for {request.coin}/USDT: {e}")
                    continue
            
            logger.debug(f"❌ No {request.coin}/USDT found on any exchange for manual EUR calculation")
            return None
            
        except Exception as e:
            logger.error(f"Exchange USDT→EUR conversion failed: {e}")
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
    
    def _get_from_historical_csv(self, request: PriceRequest) -> Optional[Price]:
        """Get price from historical CSV files (coingecko data)."""
        try:
            import csv
            from pathlib import Path
            import config
            
            # Map currency to file suffix
            currency_map = {
                'EUR': 'usd',  # We'll convert USD to EUR later
                'USD': 'usd'
            }
            
            file_suffix = currency_map.get(request.currency.upper())
            if not file_suffix:
                return None
            
            # Look for CSV file
            csv_file = Path(config.DATA_PATH) / "historical-prices" / "coingecko" / f"{request.coin.lower()}-{file_suffix}-max.csv"
            
            if not csv_file.exists():
                logger.debug(f"Historical CSV not found: {csv_file}")
                return None
            
            target_date = request.timestamp.date()
            closest_price = None
            min_days_diff = float('inf')
            
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        # Parse date from "2021-05-10 00:00:00 UTC" format
                        date_str = row['snapped_at'].split(' ')[0]  # Get just the date part
                        csv_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                        
                        days_diff = abs((csv_date - target_date).days)
                        
                        # Find closest date within 7 days
                        if days_diff <= 7 and days_diff < min_days_diff:
                            price_value = float(row['price'])
                            if price_value > 0:
                                closest_price = price_value
                                min_days_diff = days_diff
                                
                    except (ValueError, KeyError) as e:
                        continue
            
            if closest_price:
                # Convert USD to EUR if needed
                if request.currency.upper() == 'EUR' and file_suffix == 'usd':
                    # Use USDT converter as USD/EUR approximation
                    if self.usdt_converter:
                        eur_rate = self.usdt_converter.get_eur_rate(target_date)
                        if eur_rate:
                            closest_price = closest_price * eur_rate
                        else:
                            logger.debug(f"No USD/EUR conversion rate for {target_date}")
                            return None
                
                logger.debug(f"Found historical CSV price: {request.coin}/{request.currency} = {closest_price}")
                
                return Price(
                    value=Decimal(str(closest_price)),
                    coin=request.coin,
                    currency=request.currency,
                    timestamp=request.timestamp,
                    source='historical_csv'
                )
            
            return None
            
        except Exception as e:
            logger.debug(f"Historical CSV lookup failed for {request.coin}/{request.currency}: {e}")
            return None
    
    def _try_cryptocompare_api(self, request: PriceRequest) -> Optional[Price]:
        """Try CryptoCompare API for historical price data."""
        try:
            import requests
            
            # CryptoCompare historical daily price endpoint
            url = "https://min-api.cryptocompare.com/data/v2/histoday"
            
            # Convert timestamp to UNIX timestamp
            unix_timestamp = int(request.timestamp.timestamp())
            
            params = {
                'fsym': request.coin.upper(),
                'tsym': request.currency.upper(),
                'limit': 1,
                'toTs': unix_timestamp,
                'api_key': None  # Free tier - no API key needed initially
            }
            
            logger.debug(f"Trying CryptoCompare for {request.coin}/{request.currency} on {request.timestamp.date()}")
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('Response') == 'Success' and data.get('Data', {}).get('Data'):
                price_data = data['Data']['Data'][0]
                close_price = price_data.get('close', 0)
                
                if close_price > 0:
                    return Price(
                        value=Decimal(str(close_price)),
                        coin=request.coin,
                        currency=request.currency,
                        timestamp=request.timestamp,
                        source='cryptocompare'
                    )
            
            logger.debug(f"CryptoCompare: No valid price data for {request.coin}/{request.currency}")
            return None
            
        except Exception as e:
            logger.debug(f"CryptoCompare API failed for {request.coin}/{request.currency}: {e}")
            return None
    
    def _track_missing_coin(self, request: PriceRequest, reason: str, critical: bool = False):
        """Track missing coin for manual sourcing."""
        tracker = get_missing_coins_tracker()
        tracker.add_missing_coin(
            coin=request.coin,
            currency=request.currency,
            timestamp=request.timestamp,
            platform=request.platform or 'unknown',
            reason=reason,
            critical=critical
        )


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


