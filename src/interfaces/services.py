"""
Service Interfaces

Defines contracts for business services, establishing clear boundaries
between different domains and responsibilities.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Optional, Any
from pathlib import Path

from .price_service import PriceRequest, Price


class TaxCalculationService(ABC):
    """Abstract interface for tax calculation business logic."""
    
    @abstractmethod
    def calculate_annual_tax(self, tax_year: int, transactions: List[Any]) -> Dict[str, Any]:
        """
        Calculate annual tax for given transactions.
        
        Args:
            tax_year: Year to calculate taxes for
            transactions: List of transactions to process
            
        Returns:
            Tax calculation results
        """
        pass
    
    @abstractmethod
    def calculate_unrealized_gains(self, as_of_date: datetime, holdings: Dict[str, Decimal]) -> Dict[str, Any]:
        """
        Calculate unrealized gains for current holdings.
        
        Args:
            as_of_date: Date to calculate unrealized gains as of
            holdings: Current holdings by coin
            
        Returns:
            Unrealized gains calculation
        """
        pass
    
    @abstractmethod
    def apply_tax_rules(self, transactions: List[Any], country: str) -> List[Any]:
        """
        Apply country-specific tax rules to transactions.
        
        Args:
            transactions: Raw transactions
            country: Country code for tax rules
            
        Returns:
            Transactions with tax rules applied
        """
        pass


class TransactionProcessingService(ABC):
    """Abstract interface for transaction processing logic."""
    
    @abstractmethod
    def process_exchange_files(self, exchange: str, files: List[Path]) -> List[Any]:
        """
        Process exchange-specific files into standardized transactions.
        
        Args:
            exchange: Exchange name (binance, kraken, etc.)
            files: List of files to process
            
        Returns:
            Standardized transactions
        """
        pass
    
    @abstractmethod
    def validate_transactions(self, transactions: List[Any]) -> tuple[List[Any], List[str]]:
        """
        Validate transactions and return valid ones with error messages.
        
        Args:
            transactions: Transactions to validate
            
        Returns:
            Tuple of (valid_transactions, error_messages)
        """
        pass
    
    @abstractmethod
    def deduplicate_transactions(self, transactions: List[Any]) -> List[Any]:
        """
        Remove duplicate transactions.
        
        Args:
            transactions: Transactions that may contain duplicates
            
        Returns:
            Deduplicated transactions
        """
        pass


class PortfolioService(ABC):
    """Abstract interface for portfolio management."""
    
    @abstractmethod
    def calculate_current_holdings(self, transactions: List[Any]) -> Dict[str, Decimal]:
        """
        Calculate current holdings from transaction history.
        
        Args:
            transactions: All transactions
            
        Returns:
            Current holdings by coin
        """
        pass
    
    @abstractmethod
    def calculate_cost_basis(self, coin: str, amount: Decimal, transactions: List[Any]) -> Decimal:
        """
        Calculate cost basis for a specific amount of a coin.
        
        Args:
            coin: Coin symbol
            amount: Amount to calculate cost basis for
            transactions: Transaction history
            
        Returns:
            Cost basis in fiat currency
        """
        pass
    
    @abstractmethod
    def get_portfolio_value(self, holdings: Dict[str, Decimal], as_of_date: datetime) -> Decimal:
        """
        Calculate total portfolio value at a specific date.
        
        Args:
            holdings: Current holdings by coin
            as_of_date: Date to value portfolio as of
            
        Returns:
            Total portfolio value in fiat currency
        """
        pass


class ReportingService(ABC):
    """Abstract interface for reporting and export functionality."""
    
    @abstractmethod
    def generate_tax_report(self, tax_data: Dict[str, Any], format: str) -> Path:
        """
        Generate tax report in specified format.
        
        Args:
            tax_data: Tax calculation results
            format: Output format (excel, csv, pdf)
            
        Returns:
            Path to generated report
        """
        pass
    
    @abstractmethod
    def generate_portfolio_report(self, portfolio_data: Dict[str, Any]) -> Path:
        """
        Generate portfolio overview report.
        
        Args:
            portfolio_data: Portfolio analysis results
            
        Returns:
            Path to generated report
        """
        pass
    
    @abstractmethod
    def generate_transaction_report(self, transactions: List[Any]) -> Path:
        """
        Generate detailed transaction report.
        
        Args:
            transactions: Transactions to include in report
            
        Returns:
            Path to generated report
        """
        pass


class ValidationService(ABC):
    """Abstract interface for data validation."""
    
    @abstractmethod
    def validate_price_data(self, price_requests: List[PriceRequest]) -> List[str]:
        """
        Validate price data availability and quality.
        
        Args:
            price_requests: Price requests to validate
            
        Returns:
            List of validation error messages
        """
        pass
    
    @abstractmethod
    def validate_configuration(self) -> List[str]:
        """
        Validate system configuration.
        
        Returns:
            List of configuration error messages
        """
        pass
    
    @abstractmethod
    def validate_file_integrity(self, files: List[Path]) -> Dict[Path, List[str]]:
        """
        Validate integrity of input files.
        
        Args:
            files: Files to validate
            
        Returns:
            Dictionary mapping files to their validation errors
        """
        pass