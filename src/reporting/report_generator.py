"""
Tax Report Generation Service

Handles the creation of tax reports from evaluation data.
Extracted from the Taxman god class to follow single responsibility principle.
"""

import dataclasses
import datetime
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Any, Optional

import transaction as tr


class ReportData:
    """Container for tax evaluation data needed for reports."""
    
    def __init__(self):
        self.sell_events: List[tr.SellReportEntry] = []
        self.interest_events: List[tr.InterestReportEntry] = []
        self.transfer_events: List[tr.TransferReportEntry] = []
        self.misc_events: List[tr.MiscReportEntry] = []
        self.unrealized_events: List[tr.UnrealizedSellReportEntry] = []
        
        # Summary data
        self.taxable_amount: float = 0.0
        self.total_gains: float = 0.0
        self.total_losses: float = 0.0
        self.total_income: float = 0.0
        self.tax_year: int = 0
        
        # Portfolio data
        self.single_depot_portfolio: Dict[str, float] = {}
        self.multi_depot_portfolio: Dict[str, Dict[str, float]] = {}
        
        # Configuration
        self.country: str = "GERMANY"
        self.fiat_currency: str = "EUR"
        self.multi_depot_enabled: bool = False


class ReportGenerator(ABC):
    """Abstract interface for tax report generation."""
    
    @abstractmethod
    def generate_report(self, report_data: ReportData) -> Path:
        """
        Generate a tax report from evaluation data.
        
        Args:
            report_data: Container with all tax evaluation data
            
        Returns:
            Path to the generated report file
        """
        pass


class TaxReportSummary:
    """Summary statistics for tax reporting."""
    
    def __init__(self, report_data: ReportData):
        self.report_data = report_data
        
    def calculate_summary(self) -> Dict[str, Any]:
        """Calculate summary statistics from report data."""
        
        # Calculate totals from events
        total_sell_gains = sum(
            float(event.taxable_gain_in_fiat or 0) 
            for event in self.report_data.sell_events
            if hasattr(event, 'taxable_gain_in_fiat') and event.taxable_gain_in_fiat is not None
        )
        
        total_interest_income = sum(
            float(event.taxable_gain_in_fiat or 0)
            for event in self.report_data.interest_events
            if hasattr(event, 'taxable_gain_in_fiat') and event.taxable_gain_in_fiat is not None
        )
        
        total_misc_income = sum(
            float(event.taxable_gain_in_fiat or 0)
            for event in self.report_data.misc_events  
            if hasattr(event, 'taxable_gain_in_fiat') and event.taxable_gain_in_fiat is not None
        )
        
        # Calculate portfolio value
        portfolio_value = sum(self.report_data.single_depot_portfolio.values())
        
        # Calculate unrealized gains
        total_unrealized = sum(
            float(event.taxable_gain_in_fiat or 0)
            for event in self.report_data.unrealized_events
            if hasattr(event, 'taxable_gain_in_fiat') and event.taxable_gain_in_fiat is not None
        )
        
        return {
            'sell_events_count': len(self.report_data.sell_events),
            'interest_events_count': len(self.report_data.interest_events),
            'misc_events_count': len(self.report_data.misc_events),
            'total_sell_gains': total_sell_gains,
            'total_interest_income': total_interest_income,
            'total_misc_income': total_misc_income,
            'total_income': total_interest_income + total_misc_income,
            'portfolio_value': portfolio_value,
            'total_unrealized_gains': total_unrealized,
            'tax_year': self.report_data.tax_year,
            'country': self.report_data.country,
            'fiat_currency': self.report_data.fiat_currency
        }


def extract_report_data_from_taxman(taxman_instance) -> ReportData:
    """
    Extract report data from existing Taxman instance.
    
    This function allows gradual migration by extracting data from
    the existing god class structure.
    
    Args:
        taxman_instance: Instance of the Taxman class
        
    Returns:
        ReportData container with extracted information
    """
    report_data = ReportData()
    
    # Extract tax events
    report_data.sell_events = getattr(taxman_instance, 'sell_events', [])
    report_data.interest_events = getattr(taxman_instance, 'interest_events', [])
    report_data.transfer_events = getattr(taxman_instance, 'transfer_events', [])
    report_data.misc_events = getattr(taxman_instance, 'misc_events', [])
    report_data.unrealized_events = getattr(taxman_instance, 'unrealized_events', [])
    
    # Extract summary data
    report_data.taxable_amount = getattr(taxman_instance, 'taxable_amount', 0.0)
    report_data.total_gains = getattr(taxman_instance, 'total_gains', 0.0)
    report_data.total_losses = getattr(taxman_instance, 'total_losses', 0.0)
    report_data.total_income = getattr(taxman_instance, 'total_income', 0.0)
    
    # Extract portfolio data
    report_data.single_depot_portfolio = getattr(taxman_instance, 'single_depot_portfolio', {})
    report_data.multi_depot_portfolio = getattr(taxman_instance, 'multi_depot_portfolio', {})
    
    # Extract configuration
    import config
    report_data.tax_year = config.TAX_YEAR
    report_data.country = config.COUNTRY.name if hasattr(config.COUNTRY, 'name') else str(config.COUNTRY)
    report_data.fiat_currency = getattr(config, 'FIAT_CURRENCY', 'EUR')
    report_data.multi_depot_enabled = getattr(config, 'MULTI_DEPOT', False)
    
    return report_data