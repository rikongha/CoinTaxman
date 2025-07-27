"""
Repository Interfaces

Defines contracts for data access, eliminating direct database coupling
throughout the codebase.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

# Import domain entities (we'll need to create these)
# from domain.entities import Transaction, Operation, Portfolio


class TransactionRepository(ABC):
    """Abstract interface for transaction data access."""
    
    @abstractmethod
    def save_transactions(self, transactions: List[Any]) -> None:
        """Save a list of transactions."""
        pass
    
    @abstractmethod
    def find_by_platform(self, platform: str) -> List[Any]:
        """Find all transactions for a specific platform."""
        pass
    
    @abstractmethod
    def find_by_date_range(self, start_date: datetime, end_date: datetime) -> List[Any]:
        """Find transactions within a date range."""
        pass
    
    @abstractmethod
    def find_by_coin(self, coin: str) -> List[Any]:
        """Find all transactions for a specific coin."""
        pass
    
    @abstractmethod
    def count_by_platform(self, platform: str) -> int:
        """Count transactions for a platform."""
        pass


class PriceRepository(ABC):
    """Abstract interface for price data access."""
    
    @abstractmethod
    def save_price(self, coin: str, currency: str, timestamp: datetime, 
                  price: float, platform: str) -> None:
        """Save a single price entry."""
        pass
    
    @abstractmethod
    def get_price(self, coin: str, currency: str, timestamp: datetime, 
                 platform: str) -> Optional[float]:
        """Get a specific price."""
        pass
    
    @abstractmethod
    def get_prices_for_coin(self, coin: str, currency: str, 
                           start_date: datetime, end_date: datetime) -> Dict[datetime, float]:
        """Get all prices for a coin within date range."""
        pass
    
    @abstractmethod
    def has_price(self, coin: str, currency: str, timestamp: datetime, 
                 platform: str) -> bool:
        """Check if price exists."""
        pass
    
    @abstractmethod
    def get_zero_prices(self, platform: str) -> List[Dict[str, Any]]:
        """Get all zero/missing price entries for analysis."""
        pass


class FileRepository(ABC):
    """Abstract interface for file operations."""
    
    @abstractmethod
    def read_csv_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Read and parse a CSV file."""
        pass
    
    @abstractmethod
    def write_csv_file(self, file_path: Path, data: List[Dict[str, Any]]) -> None:
        """Write data to CSV file."""
        pass
    
    @abstractmethod
    def get_files_by_pattern(self, directory: Path, pattern: str) -> List[Path]:
        """Get files matching a pattern."""
        pass
    
    @abstractmethod
    def file_exists(self, file_path: Path) -> bool:
        """Check if file exists."""
        pass


class ConfigRepository(ABC):
    """Abstract interface for configuration access."""
    
    @abstractmethod
    def get_tax_year(self) -> int:
        """Get configured tax year."""
        pass
    
    @abstractmethod
    def get_country(self) -> str:
        """Get configured country."""
        pass
    
    @abstractmethod
    def get_fiat_currency(self) -> str:
        """Get configured fiat currency."""
        pass
    
    @abstractmethod
    def is_multi_depot_enabled(self) -> bool:
        """Check if multi-depot mode is enabled."""
        pass
    
    @abstractmethod
    def get_data_path(self) -> Path:
        """Get configured data directory path."""
        pass
    
    @abstractmethod
    def get_export_path(self) -> Path:
        """Get configured export directory path."""
        pass


class ExportRepository(ABC):
    """Abstract interface for export operations."""
    
    @abstractmethod
    def export_to_excel(self, data: Dict[str, Any], file_path: Path) -> None:
        """Export data to Excel file."""
        pass
    
    @abstractmethod
    def export_to_csv(self, data: List[Dict[str, Any]], file_path: Path) -> None:
        """Export data to CSV file."""
        pass
    
    @abstractmethod
    def export_to_json(self, data: Dict[str, Any], file_path: Path) -> None:
        """Export data to JSON file."""
        pass