"""
USDT to EUR Converter Implementation

Integrates the existing USDT conversion functionality with the
unified price service architecture.
"""

import csv
import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional, Dict

import config
from date_parser import parse_date_unified

logger = logging.getLogger(__name__)


class USDTEURConverter:
    """USDT to EUR conversion using historical rates."""
    
    def __init__(self):
        self.rates_file = Path(config.DATA_PATH) / "historical-prices" / "investopedia" / "USDTEUR.csv"
        self.rates: Dict[date, float] = {}
        self.available = False
        self._load_rates()
        
    def _load_rates(self):
        """Load USDT/EUR conversion rates."""
        if not self.rates_file.exists():
            logger.warning(f"USDT-EUR rates file not found: {self.rates_file}")
            return
            
        try:
            with open(self.rates_file, 'r') as f:
                reader = csv.DictReader(f)
                for row_num, row in enumerate(reader, 1):
                    try:
                        # Check if row has the expected columns
                        if 'Date' not in row or 'Close' not in row:
                            logger.debug(f"Row {row_num} missing required columns: {list(row.keys())}")
                            continue
                            
                        date_str = row['Date'].strip().strip('"')
                        
                        # Skip empty dates
                        if not date_str:
                            logger.debug(f"Row {row_num} has empty date")
                            continue
                        
                        # Use unified date parser
                        date_obj = parse_date_unified(date_str)
                                
                        if date_obj:
                            rate = float(row['Close'])
                            self.rates[date_obj] = rate
                        else:
                            # Skip logging for non-critical parsing failures
                            continue
                            
                    except (ValueError, KeyError) as e:
                        logger.debug(f"Row {row_num}: Exception parsing row: {e} - Row data: {row}")
                        continue
                        
            self.available = len(self.rates) > 0
            logger.info(f"Loaded {len(self.rates)} USDT/EUR conversion rates")
            
        except Exception as e:
            logger.error(f"Failed to load USDT/EUR rates: {e}")
            
    def get_eur_rate(self, target_date: date) -> Optional[float]:
        """Get USDT/EUR conversion rate for given date."""
        if not self.available:
            return None
            
        # Try exact date first
        if target_date in self.rates:
            return self.rates[target_date]
            
        # Find closest date within 7 days
        closest_date = None
        min_diff = 7
        
        for rate_date in self.rates:
            diff = abs((rate_date - target_date).days)
            if diff <= min_diff:
                min_diff = diff
                closest_date = rate_date
                
        if closest_date:
            logger.debug(f"Using USDT/EUR rate from {closest_date} for {target_date} ({min_diff} days difference)")
            return self.rates[closest_date]
            
        return None
            
    def convert_usdt_to_eur(self, usdt_amount: float, target_date: date) -> Optional[float]:
        """Convert USDT amount to EUR for given date."""
        rate = self.get_eur_rate(target_date)
        if rate:
            return usdt_amount * rate
        return None
    
    def convert_usdt_to_eur_decimal(self, usdt_amount: Decimal, target_date: date) -> Optional[Decimal]:
        """Convert USDT amount to EUR for given date (decimal version)."""
        rate = self.get_eur_rate(target_date)
        if rate:
            return usdt_amount * Decimal(str(rate))
        return None