"""
Taxman Integration Helper

Provides integration functions to gradually migrate from the Taxman god class
to the new clean architecture using the tax calculation service.
"""

from pathlib import Path
from typing import List, Any

import transaction as tr
from reporting.tax_report_service import TaxReportService
from .tax_service_factory import create_tax_service


class TaxmanMigrationAdapter:
    """
    Adapter that provides the same interface as Taxman but uses the new architecture.
    
    This allows gradual migration by replacing Taxman internals while
    maintaining the same external interface.
    """
    
    def __init__(self):
        # Create new architecture services
        self.tax_service = create_tax_service()
        self.report_service = TaxReportService()
        
        # Maintain compatibility properties
        self._operations: List[tr.Operation] = []
        self._tax_calculated = False
    
    def add_operation(self, operation: tr.Operation) -> None:
        """Add operation for tax calculation (compatibility method)."""
        self._operations.append(operation)
        self._tax_calculated = False
    
    def add_operations(self, operations: List[tr.Operation]) -> None:
        """Add multiple operations for tax calculation."""
        self._operations.extend(operations)
        self._tax_calculated = False
    
    def evaluate_taxation(self) -> None:
        """
        Evaluate taxation for all operations.
        
        This replaces the main evaluation logic from the Taxman class
        using the new clean architecture.
        """
        if not self._operations:
            return
        
        # Use new tax calculation service
        self.tax_service.evaluate_operations(self._operations)
        self._tax_calculated = True
    
    def export_evaluation_as_excel(self) -> Path:
        """
        Export tax evaluation to Excel (compatibility method).
        
        Returns:
            Path to exported German Excel file
        """
        if not self._tax_calculated:
            self.evaluate_taxation()
        
        # Generate report data
        report_data = self.tax_service.generate_report_data()
        
        # Use new reporting service
        return self.report_service.generate_german_report(report_data)
    
    def export_evaluation_as_excel_english(self) -> Path:
        """
        Export tax evaluation to English Excel (compatibility method).
        
        Returns:
            Path to exported English Excel file
        """
        if not self._tax_calculated:
            self.evaluate_taxation()
        
        # Generate report data
        report_data = self.tax_service.generate_report_data()
        
        # Use new reporting service
        return self.report_service.generate_english_report(report_data)
    
    # Compatibility properties for accessing results
    
    @property
    def tax_report_entries(self) -> List[tr.TaxReportEntry]:
        """Get tax report entries (compatibility property)."""
        if not self._tax_calculated:
            return []
        return self.tax_service.get_tax_report_entries()
    
    @property
    def sell_events(self) -> List[tr.SellReportEntry]:
        """Get sell events (compatibility property)."""
        return [entry for entry in self.tax_report_entries 
                if isinstance(entry, tr.SellReportEntry)]
    
    @property
    def interest_events(self) -> List[tr.InterestReportEntry]:
        """Get interest events (compatibility property)."""
        return [entry for entry in self.tax_report_entries
                if isinstance(entry, tr.InterestReportEntry)]
    
    @property
    def single_depot_portfolio(self) -> dict:
        """Get single depot portfolio (compatibility property)."""
        return self.tax_service._balance_manager.portfolio_manager.single_depot_portfolio
    
    @property
    def multi_depot_portfolio(self) -> dict:
        """Get multi depot portfolio (compatibility property)."""
        return self.tax_service._balance_manager.portfolio_manager.multi_depot_portfolio
    
    def get_tax_summary(self) -> dict:
        """Get tax calculation summary."""
        if not self._tax_calculated:
            self.evaluate_taxation()
        return self.tax_service.get_tax_summary()
    
    def get_warnings(self) -> List[str]:
        """Get calculation warnings."""
        if not self._tax_calculated:
            return []
        return self.tax_service.get_warnings()


def create_modern_taxman() -> TaxmanMigrationAdapter:
    """
    Create a modern Taxman using the new architecture.
    
    This function provides a drop-in replacement for the old Taxman class
    that uses the new clean architecture under the hood.
    
    Returns:
        TaxmanMigrationAdapter that behaves like the old Taxman
    """
    return TaxmanMigrationAdapter()


def migrate_existing_taxman(legacy_taxman: Any) -> TaxmanMigrationAdapter:
    """
    Migrate an existing Taxman instance to the new architecture.
    
    This function extracts data from an existing Taxman instance and
    recreates it using the new architecture.
    
    Args:
        legacy_taxman: Existing Taxman instance
        
    Returns:
        New TaxmanMigrationAdapter with migrated data
    """
    modern_taxman = TaxmanMigrationAdapter()
    
    # Extract operations from legacy taxman
    # (This would need to be implemented based on how operations are stored)
    
    # Extract balance state
    # (This would need to be implemented based on balance storage)
    
    # Extract configuration
    # (This would need to be implemented based on config access)
    
    return modern_taxman


# Direct replacement functions for existing code
def calculate_taxes(operations: List[tr.Operation]) -> dict:
    """
    Direct tax calculation function (modern interface).
    
    This provides a simple functional interface for tax calculation
    without needing to create service instances.
    
    Args:
        operations: List of operations to calculate taxes for
        
    Returns:
        Dictionary with tax calculation results
    """
    tax_service = create_tax_service()
    tax_service.evaluate_operations(operations)
    
    return {
        'entries': tax_service.get_tax_report_entries(),
        'summary': tax_service.get_tax_summary(),
        'warnings': tax_service.get_warnings(),
        'report_data': tax_service.generate_report_data()
    }


def generate_tax_reports(operations: List[tr.Operation]) -> List[Path]:
    """
    Generate both German and English tax reports.
    
    Args:
        operations: List of operations to calculate taxes for
        
    Returns:
        List of paths to generated report files
    """
    # Calculate taxes
    tax_service = create_tax_service()
    tax_service.evaluate_operations(operations)
    
    # Generate reports
    report_service = TaxReportService()
    report_data = tax_service.generate_report_data()
    
    return report_service.generate_all_reports(report_data)