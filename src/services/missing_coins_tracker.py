"""
Missing Coins Tracker

Tracks coins for which historical price data could not be found,
creating a file for manual sourcing of historical data.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Set, Dict, List
from dataclasses import dataclass

import config

logger = logging.getLogger(__name__)


@dataclass
class MissingCoinEntry:
    """Represents a missing coin price entry."""
    coin: str
    currency: str
    timestamp: datetime
    platform: str
    reason: str = "No historical data available"
    critical: bool = False  # Whether this affects tax calculations


class MissingCoinsTracker:
    """Tracks missing coin prices for manual sourcing."""
    
    def __init__(self, output_file: Path = None):
        self.output_file = output_file or (Path(config.DATA_PATH) / "missing_coins.csv")
        self.missing_entries: Dict[str, MissingCoinEntry] = {}
        self.session_missing: Set[str] = set()  # Avoid duplicate logs in same session
        
    def add_missing_coin(self, coin: str, currency: str, timestamp: datetime, 
                        platform: str, reason: str = "No historical data available",
                        critical: bool = False):
        """Add a missing coin entry."""
        # Create unique key to avoid duplicates
        key = f"{coin.upper()}/{currency.upper()}@{timestamp.date()}@{platform}"
        
        # Skip if already logged in this session
        if key in self.session_missing:
            return
            
        self.session_missing.add(key)
        
        entry = MissingCoinEntry(
            coin=coin.upper(),
            currency=currency.upper(), 
            timestamp=timestamp,
            platform=platform,
            reason=reason,
            critical=critical
        )
        
        self.missing_entries[key] = entry
        
        if critical:
            logger.error(f"🚨 CRITICAL missing price: {coin.upper()}/{currency.upper()} on {timestamp.date()} ({platform}) - AFFECTS TAX CALCULATION!")
        else:
            logger.info(f"📝 Missing price data: {coin.upper()}/{currency.upper()} on {timestamp.date()} ({platform})")
        
    def export_missing_coins(self):
        """Export missing coins to CSV file."""
        if not self.missing_entries:
            logger.info("No missing coins to export")
            return
            
        # Ensure directory exists
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Read existing entries to avoid duplicates
        existing_keys = set()
        if self.output_file.exists():
            try:
                with open(self.output_file, 'r', newline='') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        key = f"{row['Coin']}/{row['Currency']}@{row['Date']}@{row['Platform']}"
                        existing_keys.add(key)
            except Exception as e:
                logger.debug(f"Could not read existing missing coins file: {e}")
        
        # Write new entries
        new_entries = []
        for key, entry in self.missing_entries.items():
            if key not in existing_keys:
                new_entries.append(entry)
        
        if not new_entries:
            logger.info("No new missing coins to add")
            return
            
        # Append new entries to file
        mode = 'a' if self.output_file.exists() else 'w'
        with open(self.output_file, mode, newline='') as f:
            fieldnames = ['Coin', 'Currency', 'Date', 'Time', 'Platform', 'Reason', 'Critical', 'Status']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            # Write header if new file
            if mode == 'w':
                writer.writeheader()
            
            # Sort entries with critical ones first
            sorted_entries = sorted(new_entries, key=lambda e: (not e.critical, e.timestamp))
            
            # Write entries
            for entry in sorted_entries:
                writer.writerow({
                    'Coin': entry.coin,
                    'Currency': entry.currency,
                    'Date': entry.timestamp.date().isoformat(),
                    'Time': entry.timestamp.time().isoformat(),
                    'Platform': entry.platform,
                    'Reason': entry.reason,
                    'Critical': 'YES' if entry.critical else 'NO',
                    'Status': 'MISSING'
                })
        
        logger.info(f"📄 Exported {len(new_entries)} missing coins to {self.output_file}")
        
    def get_missing_summary(self) -> Dict[str, int]:
        """Get summary statistics of missing coins."""
        if not self.missing_entries:
            return {}
            
        summary = {}
        for entry in self.missing_entries.values():
            coin_key = f"{entry.coin}/{entry.currency}"
            summary[coin_key] = summary.get(coin_key, 0) + 1
            
        return summary
        
    def print_summary(self):
        """Print summary of missing coins."""
        if not self.missing_entries:
            logger.info("✅ No missing coins found")
            return
            
        critical_count = sum(1 for entry in self.missing_entries.values() if entry.critical)
        total_count = len(self.missing_entries)
        non_critical_count = total_count - critical_count
        
        logger.info("📊 Missing Coins Summary:")
        if critical_count > 0:
            logger.error(f"🚨 CRITICAL: {critical_count} missing prices that affect tax calculations!")
        if non_critical_count > 0:
            logger.info(f"📝 Non-critical: {non_critical_count} missing prices")
        
        # Group by coin pair
        coin_summary = {}
        for entry in self.missing_entries.values():
            coin_pair = f"{entry.coin}/{entry.currency}"
            if coin_pair not in coin_summary:
                coin_summary[coin_pair] = {'critical': 0, 'total': 0}
            coin_summary[coin_pair]['total'] += 1
            if entry.critical:
                coin_summary[coin_pair]['critical'] += 1
        
        for coin_pair, counts in sorted(coin_summary.items()):
            if counts['critical'] > 0:
                logger.warning(f"  🚨 {coin_pair}: {counts['critical']} CRITICAL + {counts['total'] - counts['critical']} other")
            else:
                logger.info(f"  📝 {coin_pair}: {counts['total']} missing prices")
        
        logger.info(f"📄 Missing coins exported to {self.output_file}")


# Global tracker instance
_global_tracker = None

def get_missing_coins_tracker() -> MissingCoinsTracker:
    """Get the global missing coins tracker instance."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = MissingCoinsTracker()
    return _global_tracker