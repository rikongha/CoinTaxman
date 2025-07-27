"""
Tax Report Service

Main service that coordinates tax report generation.
Provides a clean interface for the Taxman class to use.
"""

from pathlib import Path
from typing import List, Optional

from .report_generator import ReportData, extract_report_data_from_taxman
from .excel_exporter import GermanExcelExporter, EnglishExcelExporter


class TaxReportService:
    """
    Service for generating tax reports.
    
    This service handles the coordination of report generation,
    replacing the report generation logic that was embedded
    in the Taxman god class.
    """
    
    def __init__(self):
        self.german_exporter = GermanExcelExporter()
        self.english_exporter = EnglishExcelExporter()
    
    def generate_reports_from_taxman(self, taxman_instance) -> List[Path]:
        """
        Generate both German and English reports from Taxman instance.
        
        This method provides backward compatibility during the migration
        from the god class architecture.
        
        Args:
            taxman_instance: Instance of the Taxman class
            
        Returns:
            List of paths to generated report files
        """
        # Extract data from the existing Taxman instance
        report_data = extract_report_data_from_taxman(taxman_instance)
        
        # Generate reports
        german_report = self.german_exporter.generate_report(report_data)
        english_report = self.english_exporter.generate_report(report_data)
        
        return [german_report, english_report]
    
    def generate_german_report(self, report_data: ReportData) -> Path:
        """Generate German Excel report."""
        return self.german_exporter.generate_report(report_data)
    
    def generate_english_report(self, report_data: ReportData) -> Path:
        """Generate English Excel report.""" 
        return self.english_exporter.generate_report(report_data)
    
    def generate_all_reports(self, report_data: ReportData) -> List[Path]:
        """Generate both German and English reports."""
        german_report = self.generate_german_report(report_data)
        english_report = self.generate_english_report(report_data)
        return [german_report, english_report]


# Singleton instance for easy access
_report_service_instance: Optional[TaxReportService] = None


def get_report_service() -> TaxReportService:
    """Get the singleton report service instance."""
    global _report_service_instance
    if _report_service_instance is None:
        _report_service_instance = TaxReportService()
    return _report_service_instance


# Convenience functions for direct usage
def generate_reports_from_taxman(taxman_instance) -> List[Path]:
    """Generate reports from Taxman instance (convenience function)."""
    service = get_report_service()
    return service.generate_reports_from_taxman(taxman_instance)


def generate_german_excel_report(report_data: ReportData) -> Path:
    """Generate German Excel report (convenience function)."""
    service = get_report_service()
    return service.generate_german_report(report_data)


def generate_english_excel_report(report_data: ReportData) -> Path:
    """Generate English Excel report (convenience function)."""
    service = get_report_service()
    return service.generate_english_report(report_data)