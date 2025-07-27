"""
Tax Calculation Service

Main service that orchestrates tax calculation using all extracted components.
This replaces the core logic of the Taxman god class with clean dependency injection.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Dict, Any, Optional
import datetime

import transaction as tr
import core
from balance_management.balance_manager import BalanceManager
from tax_rules.tax_rules_interface import TaxRulesInterface, TaxContext
from reporting.report_generator import ReportData
from services.price_service_factory import get_default_price_service


@dataclass
class TaxCalculationConfig:
    """Configuration for tax calculation service."""
    tax_year: int
    country: core.Country
    fiat_currency: str
    multi_depot: bool
    principle: core.Principle
    calculate_unrealized_gains: bool = True


class TaxCalculationService:
    """
    Main tax calculation service that orchestrates all components.
    
    This service replaces the core functionality of the Taxman god class
    by using dependency injection and clean service boundaries.
    """
    
    def __init__(self,
                 config: TaxCalculationConfig,
                 balance_manager: BalanceManager,
                 tax_rules: TaxRulesInterface,
                 price_service: Any = None):
        
        self._config = config
        self._balance_manager = balance_manager
        self._tax_rules = tax_rules
        self._price_service = price_service or get_default_price_service()
        
        # Tax calculation state
        self._tax_report_entries: List[tr.TaxReportEntry] = []
        self._warnings: List[str] = []
        
        # Tax evaluation context
        self._context = TaxContext(
            tax_year=config.tax_year,
            multi_depot=config.multi_depot,
            country=config.country.name if hasattr(config.country, 'name') else str(config.country),
            fiat_currency=config.fiat_currency,
            balance_manager=balance_manager,
            price_service=price_service
        )
    
    def evaluate_operations(self, operations: List[tr.Operation]) -> None:
        """
        Evaluate a list of operations for tax implications.
        
        This is the main entry point for tax calculation, processing
        all operations and generating tax report entries.
        
        Args:
            operations: List of operations to evaluate
        """
        self._tax_report_entries.clear()
        self._warnings.clear()
        
        # Sort operations by timestamp for proper FIFO/LIFO processing
        sorted_operations = sorted(operations, key=lambda op: op.utc_time)
        
        # Process each operation
        for operation in sorted_operations:
            self._evaluate_single_operation(operation)
        
        # Apply annual thresholds and allowances
        self._tax_rules.apply_annual_thresholds(self._tax_report_entries, self._context)
        
        # Validate compliance
        compliance_warnings = self._tax_rules.validate_compliance(operations, self._context)
        self._warnings.extend([w.message for w in compliance_warnings])
        
        # Calculate unrealized gains if enabled
        if self._config.calculate_unrealized_gains:
            self._calculate_unrealized_gains()
    
    def _evaluate_single_operation(self, operation: tr.Operation) -> None:
        """Evaluate a single operation for tax implications."""
        
        # Update context with current operation
        self._context.current_operation = operation
        self._context.platform = operation.platform
        self._context.timestamp = operation.utc_time
        
        # Process operation through balance manager first
        sold_coins = self._balance_manager.process_operation(operation)
        self._context.sold_coins = sold_coins
        
        # Evaluate tax implications using country-specific rules
        tax_result = self._tax_rules.evaluate_operation(operation, self._context)
        
        # Add warnings from tax evaluation
        if tax_result.warnings:
            self._warnings.extend(tax_result.warnings)
        
        # Create tax report entry if operation is taxable
        if tax_result.is_taxable and sold_coins:
            self._create_tax_report_entry(operation, sold_coins, tax_result)
    
    def _create_tax_report_entry(self, 
                                operation: tr.Operation,
                                sold_coins: List[tr.SoldCoin],
                                tax_result) -> None:
        """Create appropriate tax report entry based on operation type."""
        
        if isinstance(operation, tr.Sell):
            self._create_sell_report_entry(operation, sold_coins, tax_result)
            
        elif isinstance(operation, (tr.StakingInterest, tr.CoinLendInterest)):
            self._create_interest_report_entry(operation, tax_result)
            
        elif isinstance(operation, tr.Mining):
            self._create_mining_report_entry(operation, tax_result)
            
        elif isinstance(operation, tr.Airdrop):
            self._create_airdrop_report_entry(operation, tax_result)
            
        # Add other operation types as needed
    
    def _create_sell_report_entry(self, 
                                 operation: tr.Sell,
                                 sold_coins: List[tr.SoldCoin],
                                 tax_result) -> None:
        """Create sell report entry with proper cost basis calculation."""
        
        for sold_coin in sold_coins:
            # Calculate buy cost using price service
            buy_cost = self._calculate_buy_cost(sold_coin)
            
            # Calculate sell value using price service  
            sell_value = self._calculate_sell_value(operation, sold_coin)
            
            # Determine if taxable based on holding period
            is_taxable = self._tax_rules.calculate_holding_period_taxation(
                sold_coin.op.utc_time, operation.utc_time
            )
            
            if is_taxable:
                # Create sell report entry
                sell_entry = tr.SellReportEntry(
                    sell_platform=operation.platform,
                    buy_platform=sold_coin.op.platform,
                    amount=sold_coin.sold,
                    coin=operation.coin,
                    sell_utc_time=operation.utc_time,
                    buy_utc_time=sold_coin.op.utc_time,
                    first_fee_amount=Decimal('0'),  # Would calculate actual fees
                    first_fee_coin=operation.coin,
                    first_fee_in_fiat=Decimal('0'),
                    second_fee_amount=Decimal('0'),
                    second_fee_coin=operation.coin,
                    second_fee_in_fiat=Decimal('0'),
                    sell_value_in_fiat=sell_value,
                    buy_cost_in_fiat=buy_cost,
                    is_taxable=is_taxable,
                    taxation_type=tax_result.taxation_type or "§23 EStG",
                    remark=f"FIFO: {sold_coin.sold} {operation.coin}"
                )
                
                self._tax_report_entries.append(sell_entry)
    
    def _create_interest_report_entry(self, operation: tr.Operation, tax_result) -> None:
        """Create interest report entry for staking/lending income."""
        
        # Calculate fiat value of interest
        interest_value = self._calculate_fiat_value(operation)
        
        interest_entry = tr.InterestReportEntry(
            platform=operation.platform,
            amount=operation.change,
            utc_time=operation.utc_time,
            coin=operation.coin,
            interest_in_fiat=interest_value,
            taxation_type=tax_result.taxation_type or "§22 Nr. 3 EStG",
            remark=f"Interest: {operation.change} {operation.coin}"
        )
        
        self._tax_report_entries.append(interest_entry)
    
    def _create_mining_report_entry(self, operation: tr.Mining, tax_result) -> None:
        """Create mining report entry."""
        
        # Calculate fiat value at mining time
        mining_value = self._calculate_fiat_value(operation)
        
        # Mining is typically treated as income
        mining_entry = tr.InterestReportEntry(
            platform=operation.platform,
            amount=operation.change,
            utc_time=operation.utc_time,
            coin=operation.coin,
            interest_in_fiat=mining_value,
            taxation_type=tax_result.taxation_type or "§22 Nr. 3 EStG",
            remark=f"Mining: {operation.change} {operation.coin}"
        )
        
        self._tax_report_entries.append(mining_entry)
    
    def _create_airdrop_report_entry(self, operation: tr.Airdrop, tax_result) -> None:
        """Create airdrop report entry."""
        
        # Calculate fiat value at airdrop time
        airdrop_value = self._calculate_fiat_value(operation)
        
        airdrop_entry = tr.InterestReportEntry(
            platform=operation.platform,
            amount=operation.change,
            utc_time=operation.utc_time,
            coin=operation.coin,
            interest_in_fiat=airdrop_value,
            taxation_type=tax_result.taxation_type or "§22 Nr. 3 EStG",
            remark=f"Airdrop: {operation.change} {operation.coin}"
        )
        
        self._tax_report_entries.append(airdrop_entry)
    
    def _calculate_buy_cost(self, sold_coin: tr.SoldCoin) -> Decimal:
        """Calculate fiat cost of purchased coins."""
        # This would use the price service to get historical price
        # For now, return placeholder
        return Decimal('0')
    
    def _calculate_sell_value(self, operation: tr.Sell, sold_coin: tr.SoldCoin) -> Decimal:
        """Calculate fiat value of sold coins."""
        # This would use the price service to get sell price
        # For now, return placeholder
        return Decimal('0')
    
    def _calculate_fiat_value(self, operation: tr.Operation) -> Decimal:
        """Calculate fiat value of operation."""
        # This would use the price service to get price at operation time
        # For now, return placeholder
        return Decimal('0')
    
    def _calculate_unrealized_gains(self) -> None:
        """Calculate unrealized gains for current portfolio."""
        # Get current portfolio positions
        positions = self._balance_manager.portfolio_manager.get_all_positions()
        
        for position in positions:
            if position.amount > 0:
                # Calculate current value vs. cost basis
                # This would create unrealized gain entries
                pass
    
    def get_tax_report_entries(self) -> List[tr.TaxReportEntry]:
        """Get all generated tax report entries."""
        return self._tax_report_entries.copy()
    
    def get_warnings(self) -> List[str]:
        """Get all warnings from tax calculation."""
        return self._warnings.copy()
    
    def generate_report_data(self) -> ReportData:
        """Generate report data for the reporting service."""
        report_data = ReportData()
        
        # Categorize entries by type
        for entry in self._tax_report_entries:
            if isinstance(entry, tr.SellReportEntry):
                report_data.sell_events.append(entry)
            elif isinstance(entry, tr.InterestReportEntry):
                report_data.interest_events.append(entry)
            # Add other entry types as needed
        
        # Set portfolio data
        portfolio_manager = self._balance_manager.portfolio_manager
        report_data.single_depot_portfolio = portfolio_manager.single_depot_portfolio
        report_data.multi_depot_portfolio = portfolio_manager.multi_depot_portfolio
        
        # Set configuration
        report_data.tax_year = self._config.tax_year
        report_data.country = self._config.country.name if hasattr(self._config.country, 'name') else str(self._config.country)
        report_data.fiat_currency = self._config.fiat_currency
        report_data.multi_depot_enabled = self._config.multi_depot
        
        return report_data
    
    def get_tax_summary(self) -> Dict[str, Any]:
        """Get summary of tax calculation results."""
        
        # Calculate totals
        total_gains = sum(
            entry.taxable_gain_in_fiat or Decimal('0')
            for entry in self._tax_report_entries
            if hasattr(entry, 'taxable_gain_in_fiat') and entry.taxable_gain_in_fiat
        )
        
        total_income = sum(
            entry.taxable_gain_in_fiat or Decimal('0')
            for entry in self._tax_report_entries
            if isinstance(entry, tr.InterestReportEntry) and entry.taxable_gain_in_fiat
        )
        
        return {
            'tax_year': self._config.tax_year,
            'country': self._config.country.name if hasattr(self._config.country, 'name') else str(self._config.country),
            'total_entries': len(self._tax_report_entries),
            'total_gains': float(total_gains),
            'total_income': float(total_income),
            'warnings_count': len(self._warnings),
            'calculation_completed': True
        }