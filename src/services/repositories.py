"""
Repository Implementations

Concrete implementations of the repository interfaces that handle
data access for the unified price service.
"""

import logging
import sqlite3
from datetime import datetime
from typing import Optional, Dict, List, Any
from pathlib import Path

from interfaces.repositories import PriceRepository, ConfigRepository
import config

logger = logging.getLogger(__name__)


class SQLitePriceRepository(PriceRepository):
    """SQLite implementation of price repository."""
    
    def __init__(self, db_path: Optional[Path] = None):
        # Default to a general price database in the data path
        self.db_path = db_path or (Path(config.DATA_PATH) / "unified_prices.db")
        self._ensure_table_exists()
    
    def _ensure_table_exists(self):
        """Ensure the price table exists."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS price_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        platform TEXT NOT NULL,
                        coin TEXT NOT NULL,
                        currency TEXT NOT NULL,
                        utc_time TEXT NOT NULL,
                        price REAL NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(platform, coin, currency, utc_time)
                    )
                """)
                
                # Create index for faster lookups
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_price_lookup 
                    ON price_data(platform, coin, currency, utc_time)
                """)
                
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to create price table: {e}")
    
    def save_price(self, coin: str, currency: str, timestamp: datetime, 
                  price: float, platform: str) -> None:
        """Save a single price entry."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO price_data 
                    (platform, coin, currency, utc_time, price)
                    VALUES (?, ?, ?, ?, ?)
                """, (platform, coin.upper(), currency.upper(), 
                      timestamp.isoformat(), price))
                conn.commit()
                logger.debug(f"Saved price: {coin}/{currency} = {price} on {platform}")
        except Exception as e:
            logger.error(f"Failed to save price {coin}/{currency}: {e}")
    
    def get_price(self, coin: str, currency: str, timestamp: datetime, 
                 platform: str) -> Optional[float]:
        """Get a specific price."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT price FROM price_data 
                    WHERE platform = ? AND coin = ? AND currency = ? AND utc_time = ?
                """, (platform, coin.upper(), currency.upper(), timestamp.isoformat()))
                
                result = cursor.fetchone()
                if result:
                    return float(result[0])
                return None
        except Exception as e:
            logger.error(f"Failed to get price {coin}/{currency}: {e}")
            return None
    
    def get_prices_for_coin(self, coin: str, currency: str, 
                           start_date: datetime, end_date: datetime) -> Dict[datetime, float]:
        """Get all prices for a coin within date range."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT utc_time, price FROM price_data 
                    WHERE coin = ? AND currency = ? 
                    AND utc_time BETWEEN ? AND ?
                    ORDER BY utc_time
                """, (coin.upper(), currency.upper(), 
                      start_date.isoformat(), end_date.isoformat()))
                
                results = {}
                for row in cursor.fetchall():
                    timestamp = datetime.fromisoformat(row[0])
                    price = float(row[1])
                    results[timestamp] = price
                
                return results
        except Exception as e:
            logger.error(f"Failed to get prices for {coin}/{currency}: {e}")
            return {}
    
    def has_price(self, coin: str, currency: str, timestamp: datetime, 
                 platform: str) -> bool:
        """Check if price exists."""
        return self.get_price(coin, currency, timestamp, platform) is not None
    
    def get_zero_prices(self, platform: str) -> List[Dict[str, Any]]:
        """Get all zero/missing price entries for analysis."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT platform, coin, currency, utc_time, price 
                    FROM price_data 
                    WHERE platform = ? AND (price = 0 OR price IS NULL)
                    ORDER BY utc_time
                """, (platform,))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'platform': row[0],
                        'coin': row[1],
                        'currency': row[2],
                        'timestamp': datetime.fromisoformat(row[3]),
                        'price': row[4]
                    })
                
                return results
        except Exception as e:
            logger.error(f"Failed to get zero prices for {platform}: {e}")
            return []


class ConfigRepositoryImpl(ConfigRepository):
    """Implementation of configuration repository using config module."""
    
    def get_tax_year(self) -> int:
        """Get configured tax year."""
        return getattr(config, 'TAX_YEAR', datetime.now().year)
    
    def get_country(self) -> str:
        """Get configured country."""
        return getattr(config, 'COUNTRY', 'DE')
    
    def get_fiat_currency(self) -> str:
        """Get configured fiat currency."""
        return getattr(config, 'FIAT_CURRENCY', 'EUR')
    
    def is_multi_depot_enabled(self) -> bool:
        """Check if multi-depot mode is enabled."""
        return getattr(config, 'CONSIDER_DEPOT', False)
    
    def get_data_path(self) -> Path:
        """Get configured data directory path."""
        return Path(getattr(config, 'DATA_PATH', 'data'))
    
    def get_export_path(self) -> Path:
        """Get configured export directory path."""
        return Path(getattr(config, 'EXPORT_PATH', 'export'))


# Legacy database integration helper
def get_price_db(platform: str, coin: str, currency: str, utc_time: datetime) -> Optional[float]:
    """
    Legacy helper function for gradual migration.
    
    This provides backward compatibility while we migrate existing code
    to use the repository pattern.
    """
    repo = SQLitePriceRepository()
    return repo.get_price(coin, currency, utc_time, platform)


def set_price_db(platform: str, coin: str, currency: str, utc_time: datetime, price: float) -> None:
    """
    Legacy helper function for gradual migration.
    
    This provides backward compatibility while we migrate existing code
    to use the repository pattern.
    """
    repo = SQLitePriceRepository()
    repo.save_price(coin, currency, utc_time, price, platform)