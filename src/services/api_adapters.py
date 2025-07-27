"""
API Adapters for External Price Sources

Concrete implementations of PriceAPI interface for different
external price data sources.
"""

import logging
import requests
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, List, Tuple
from time import sleep

from interfaces.price_service import PriceAPI, Price, PriceRequest

logger = logging.getLogger(__name__)


class CoinGeckoAPI(PriceAPI):
    """CoinGecko API adapter for historical price data."""
    
    def __init__(self, api_key: Optional[str] = None, rate_limit_delay: float = 1.1):
        self.api_key = api_key
        self.base_url = "https://api.coingecko.com/api/v3"
        self.rate_limit_delay = rate_limit_delay
        self.coin_id_map = self._load_coin_id_mapping()
    
    def _load_coin_id_mapping(self) -> Dict[str, str]:
        """Load mapping from coin symbols to CoinGecko IDs."""
        # Common mappings - in production this could be loaded from a file
        return {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'USDT': 'tether',
            'BNB': 'binancecoin',
            'ADA': 'cardano',
            'SOL': 'solana',
            'XRP': 'ripple',
            'DOT': 'polkadot',
            'AVAX': 'avalanche-2',
            'MATIC': 'matic-network',
            'LINK': 'chainlink',
            'UNI': 'uniswap',
            'LTC': 'litecoin',
            'BCH': 'bitcoin-cash',
            'ALGO': 'algorand',
            'ATOM': 'cosmos',
            'VET': 'vechain',
            'FIL': 'filecoin',
            'TRX': 'tron',
            'ETC': 'ethereum-classic',
            'THETA': 'theta-token',
            'LUNC': 'terra-luna'
        }
    
    def fetch_price(self, request: PriceRequest) -> Optional[Price]:
        """Fetch price from CoinGecko API."""
        coin_id = self.coin_id_map.get(request.coin.upper())
        if not coin_id:
            logger.debug(f"No CoinGecko ID mapping for {request.coin}")
            return None
        
        currency = request.currency.lower()
        if currency == 'usdt':
            currency = 'usd'  # CoinGecko uses USD instead of USDT
        
        date_str = request.timestamp.strftime('%d-%m-%Y')
        
        try:
            url = f"{self.base_url}/coins/{coin_id}/history"
            params = {
                'date': date_str,
                'vs_currencies': currency
            }
            
            if self.api_key:
                params['x_cg_demo_api_key'] = self.api_key
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 429:  # Rate limited
                logger.warning("CoinGecko rate limit hit, waiting...")
                sleep(self.rate_limit_delay * 2)
                return None
            
            if response.status_code != 200:
                logger.debug(f"CoinGecko API error {response.status_code} for {request.coin}")
                return None
            
            data = response.json()
            market_data = data.get('market_data', {})
            current_price = market_data.get('current_price', {})
            price_value = current_price.get(currency)
            
            if price_value and price_value > 0:
                sleep(self.rate_limit_delay)  # Respect rate limits
                return Price(
                    value=Decimal(str(price_value)),
                    coin=request.coin.upper(),
                    currency=request.currency.upper(),
                    timestamp=request.timestamp,
                    source='coingecko'
                )
            
            return None
            
        except Exception as e:
            logger.debug(f"CoinGecko API error for {request.coin}: {e}")
            return None
    
    def fetch_prices_batch(self, requests: List[PriceRequest]) -> Dict[PriceRequest, Optional[Price]]:
        """Fetch multiple prices (sequential for rate limiting)."""
        results = {}
        for request in requests:
            results[request] = self.fetch_price(request)
        return results
    
    def get_supported_pairs(self) -> List[Tuple[str, str]]:
        """Get list of supported coin/currency pairs."""
        supported_coins = list(self.coin_id_map.keys())
        supported_currencies = ['USD', 'EUR', 'BTC', 'ETH']
        
        pairs = []
        for coin in supported_coins:
            for currency in supported_currencies:
                pairs.append((coin, currency))
        
        return pairs


class BinanceAPI(PriceAPI):
    """Binance API adapter for price data."""
    
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://api.binance.com/api/v3"
    
    def fetch_price(self, request: PriceRequest) -> Optional[Price]:
        """Fetch price from Binance API."""
        # Binance doesn't have direct historical prices without API key
        # This is a simplified implementation for current prices
        try:
            symbol = f"{request.coin.upper()}{request.currency.upper()}"
            url = f"{self.base_url}/ticker/price"
            params = {'symbol': symbol}
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            price_value = data.get('price')
            
            if price_value and float(price_value) > 0:
                return Price(
                    value=Decimal(str(price_value)),
                    coin=request.coin.upper(),
                    currency=request.currency.upper(),
                    timestamp=request.timestamp,
                    source='binance'
                )
            
            return None
            
        except Exception as e:
            logger.debug(f"Binance API error for {request.coin}: {e}")
            return None
    
    def fetch_prices_batch(self, requests: List[PriceRequest]) -> Dict[PriceRequest, Optional[Price]]:
        """Fetch multiple prices."""
        results = {}
        for request in requests:
            results[request] = self.fetch_price(request)
        return results
    
    def get_supported_pairs(self) -> List[Tuple[str, str]]:
        """Get list of supported coin/currency pairs."""
        # This would typically fetch from exchange info endpoint
        # Simplified for now
        return [
            ('BTC', 'USDT'), ('ETH', 'USDT'), ('BNB', 'USDT'),
            ('ADA', 'USDT'), ('SOL', 'USDT'), ('XRP', 'USDT')
        ]


class CryptoCompareAPI(PriceAPI):
    """CryptoCompare API adapter for historical price data."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.base_url = "https://min-api.cryptocompare.com/data"
    
    def fetch_price(self, request: PriceRequest) -> Optional[Price]:
        """Fetch price from CryptoCompare API."""
        try:
            timestamp = int(request.timestamp.timestamp())
            url = f"{self.base_url}/pricehistorical"
            params = {
                'fsym': request.coin.upper(),
                'tsyms': request.currency.upper(),
                'ts': timestamp
            }
            
            if self.api_key:
                params['api_key'] = self.api_key
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            if data.get('Response') == 'Error':
                return None
            
            price_data = data.get(request.coin.upper(), {})
            price_value = price_data.get(request.currency.upper())
            
            if price_value and price_value > 0:
                return Price(
                    value=Decimal(str(price_value)),
                    coin=request.coin.upper(),
                    currency=request.currency.upper(),
                    timestamp=request.timestamp,
                    source='cryptocompare'
                )
            
            return None
            
        except Exception as e:
            logger.debug(f"CryptoCompare API error for {request.coin}: {e}")
            return None
    
    def fetch_prices_batch(self, requests: List[PriceRequest]) -> Dict[PriceRequest, Optional[Price]]:
        """Fetch multiple prices."""
        results = {}
        for request in requests:
            results[request] = self.fetch_price(request)
        return results
    
    def get_supported_pairs(self) -> List[Tuple[str, str]]:
        """Get list of supported coin/currency pairs."""
        # CryptoCompare supports many pairs
        return [
            ('BTC', 'USD'), ('BTC', 'EUR'), ('ETH', 'USD'), ('ETH', 'EUR'),
            ('USDT', 'USD'), ('USDT', 'EUR'), ('BNB', 'USD'), ('ADA', 'USD')
        ]


class FallbackPriceAPI(PriceAPI):
    """Fallback API that tries multiple sources in order."""
    
    def __init__(self, apis: List[PriceAPI]):
        self.apis = apis
    
    def fetch_price(self, request: PriceRequest) -> Optional[Price]:
        """Try each API in order until one succeeds."""
        for api in self.apis:
            try:
                price = api.fetch_price(request)
                if price:
                    return price
            except Exception as e:
                logger.debug(f"API {api.__class__.__name__} failed: {e}")
                continue
        
        return None
    
    def fetch_prices_batch(self, requests: List[PriceRequest]) -> Dict[PriceRequest, Optional[Price]]:
        """Fetch multiple prices using fallback strategy."""
        results = {}
        for request in requests:
            results[request] = self.fetch_price(request)
        return results
    
    def get_supported_pairs(self) -> List[Tuple[str, str]]:
        """Get union of all supported pairs."""
        all_pairs = set()
        for api in self.apis:
            try:
                pairs = api.get_supported_pairs()
                all_pairs.update(pairs)
            except Exception:
                continue
        
        return list(all_pairs)