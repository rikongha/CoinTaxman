"""
Tax Rules Interface

Defines the contract for country-specific tax rule implementations.
This enables support for multiple countries while maintaining clean separation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Any, Union
import datetime

import transaction as tr


@dataclass
class TaxContext:
    """Context information needed for tax rule evaluation."""
    tax_year: int
    multi_depot: bool
    country: str
    fiat_currency: str
    
    # Available services (injected)
    balance_manager: Optional[Any] = None
    price_service: Optional[Any] = None
    
    # Transaction context
    current_operation: Optional[tr.Operation] = None
    sold_coins: Optional[List[tr.SoldCoin]] = None
    
    # Additional context
    platform: Optional[str] = None
    timestamp: Optional[datetime.datetime] = None


@dataclass
class TaxResult:
    """Result of tax rule evaluation for an operation."""
    tax_entry: Optional[tr.TaxReportEntry] = None
    is_taxable: bool = False
    taxation_type: Optional[str] = None
    taxable_amount: Optional[Decimal] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


@dataclass
class TaxCategory:
    """Represents a tax category with its rules and metadata."""
    code: str
    name: str
    description: str
    legal_reference: str
    threshold: Optional[Decimal] = None
    allowance: Optional[Decimal] = None
    holding_period_days: Optional[int] = None
    tax_form_mapping: Optional[str] = None


@dataclass
class ComplianceWarning:
    """Warning about potential compliance issues."""
    category: str
    message: str
    operation: Optional[tr.Operation] = None
    severity: str = "warning"  # warning, error, info


class TaxRulesInterface(ABC):
    """
    Abstract interface for country-specific tax rule implementations.
    
    This interface defines the contract that all country-specific tax rules
    must implement, enabling clean separation and future extensibility.
    """
    
    @abstractmethod
    def get_country_code(self) -> str:
        """Get the country code this implementation handles."""
        pass
    
    @abstractmethod
    def get_tax_categories(self) -> Dict[str, TaxCategory]:
        """Get all supported tax categories for this country."""
        pass
    
    @abstractmethod
    def evaluate_operation(self, operation: tr.Operation, context: TaxContext) -> TaxResult:
        """
        Evaluate a single operation for tax implications.
        
        Args:
            operation: The operation to evaluate
            context: Tax evaluation context
            
        Returns:
            Tax result with any applicable tax entries
        """
        pass
    
    @abstractmethod
    def calculate_holding_period_taxation(self, 
                                        buy_date: datetime.datetime, 
                                        sell_date: datetime.datetime) -> bool:
        """
        Determine if a sale is taxable based on holding period rules.
        
        Args:
            buy_date: When the asset was acquired
            sell_date: When the asset was sold
            
        Returns:
            True if the sale is subject to tax, False if exempt
        """
        pass
    
    @abstractmethod
    def classify_income_type(self, operation: tr.Operation, context: TaxContext) -> str:
        """
        Classify an operation into the appropriate tax category.
        
        Args:
            operation: Operation to classify
            context: Tax evaluation context
            
        Returns:
            Tax category code
        """
        pass
    
    @abstractmethod
    def apply_annual_thresholds(self, 
                               entries: List[tr.TaxReportEntry], 
                               context: TaxContext) -> None:
        """
        Apply country-specific annual thresholds and allowances.
        
        This method modifies the tax entries in-place to apply thresholds
        like Germany's €1,000 Freigrenze or income allowances.
        
        Args:
            entries: List of tax report entries to process
            context: Tax evaluation context
        """
        pass
    
    @abstractmethod
    def validate_compliance(self, 
                          operations: List[tr.Operation], 
                          context: TaxContext) -> List[ComplianceWarning]:
        """
        Validate operations for country-specific compliance requirements.
        
        Args:
            operations: All operations to validate
            context: Tax evaluation context
            
        Returns:
            List of compliance warnings or issues
        """
        pass
    
    # Optional methods with default implementations
    
    def get_gift_tax_exemptions(self) -> Dict[str, Decimal]:
        """Get gift tax exemption amounts by relationship."""
        return {}
    
    def get_mining_classification_rules(self) -> Dict[str, Any]:
        """Get rules for classifying mining as commercial vs. private."""
        return {}
    
    def supports_multi_depot(self) -> bool:
        """Check if this country supports multi-depot tracking."""
        return True
    
    def get_required_documentation(self) -> List[str]:
        """Get list of required documentation for tax compliance."""
        return []


class BaseTaxRules(TaxRulesInterface):
    """
    Base implementation providing common functionality.
    
    Country-specific implementations can extend this class to inherit
    common behaviors while overriding country-specific logic.
    """
    
    def __init__(self, country_code: str):
        self._country_code = country_code
        self._tax_categories: Dict[str, TaxCategory] = {}
    
    def get_country_code(self) -> str:
        """Get the country code this implementation handles."""
        return self._country_code
    
    def get_tax_categories(self) -> Dict[str, TaxCategory]:
        """Get all supported tax categories for this country."""
        return self._tax_categories.copy()
    
    def _register_tax_category(self, category: TaxCategory) -> None:
        """Register a tax category with this implementation."""
        self._tax_categories[category.code] = category
    
    def _create_tax_result(self, 
                          is_taxable: bool = False,
                          taxation_type: str = None,
                          taxable_amount: Decimal = None,
                          warnings: List[str] = None) -> TaxResult:
        """Helper to create tax results."""
        return TaxResult(
            is_taxable=is_taxable,
            taxation_type=taxation_type,
            taxable_amount=taxable_amount,
            warnings=warnings or []
        )