"""
Excel Export Service

Handles the creation of Excel tax reports from evaluation data.
Extracted from Taxman class to separate export logic from tax calculation.
"""

import datetime
from pathlib import Path
from typing import Dict, Any

import xlsxwriter

import config
import misc
from .report_generator import ReportGenerator, ReportData, TaxReportSummary
from .excel_formatter import ExcelLayoutManager, ExcelWorksheetHelper


class ExcelReportExporter(ReportGenerator):
    """Excel implementation of tax report generator."""
    
    def __init__(self, locale: str = "german"):
        self.locale = locale
    
    def generate_report(self, report_data: ReportData) -> Path:
        """Generate Excel tax report from evaluation data."""
        
        # Determine file path
        if self.locale == "english":
            file_path = misc.get_next_file_path(
                config.EXPORT_PATH, f"{report_data.tax_year}_english", ["xlsx", "log"]
            )
        else:
            file_path = misc.get_next_file_path(
                config.EXPORT_PATH, str(report_data.tax_year), ["xlsx", "log"]
            )
        
        # Create workbook
        workbook = xlsxwriter.Workbook(file_path, {"remove_timezone": True})
        layout_manager = ExcelLayoutManager(workbook, self.locale)
        
        try:
            # Create report sections
            self._create_general_sheet(layout_manager, report_data)
            self._create_sell_events_sheet(layout_manager, report_data)
            self._create_interest_events_sheet(layout_manager, report_data)
            self._create_misc_events_sheet(layout_manager, report_data)
            self._create_transfer_events_sheet(layout_manager, report_data)
            self._create_portfolio_sheet(layout_manager, report_data)
            self._create_unrealized_gains_sheet(layout_manager, report_data)
            
        finally:
            workbook.close()
        
        return file_path
    
    def _create_general_sheet(self, layout_manager: ExcelLayoutManager, report_data: ReportData):
        """Create the general information sheet."""
        helper = layout_manager.create_worksheet("general")
        
        # Tax period information
        last_day = datetime.datetime(report_data.tax_year, 12, 31).date()
        first_day = last_day.replace(month=1, day=1)
        time_period = f"{first_day.strftime('%x')}–{last_day.strftime('%x')}"
        
        general_data = {
            layout_manager.get_localized_text("tax_period"): time_period,
            layout_manager.get_localized_text("tax_year"): report_data.tax_year,
            layout_manager.get_localized_text("country"): report_data.country,
            layout_manager.get_localized_text("fiat_currency"): report_data.fiat_currency,
            layout_manager.get_localized_text("multi_depot"): "Ja" if report_data.multi_depot_enabled else "Nein"
        }
        
        helper.write_header_section(
            layout_manager.get_localized_text("general_data"), 
            general_data
        )
        
        # Event summary
        summary = TaxReportSummary(report_data).calculate_summary()
        
        event_summary = {
            layout_manager.get_localized_text("sell_events"): summary['sell_events_count'],
            layout_manager.get_localized_text("interest_events"): summary['interest_events_count'], 
            layout_manager.get_localized_text("misc_events"): summary['misc_events_count']
        }
        
        helper.write_header_section(
            layout_manager.get_localized_text("total_events"),
            event_summary
        )
        
        # Financial summary
        financial_summary = {
            layout_manager.get_localized_text("total_gains"): summary['total_sell_gains'],
            layout_manager.get_localized_text("total_income"): summary['total_income'],
            layout_manager.get_localized_text("taxable_amount"): report_data.taxable_amount
        }
        
        helper.write_header_section(
            layout_manager.get_localized_text("summary"),
            financial_summary
        )
    
    def _create_sell_events_sheet(self, layout_manager: ExcelLayoutManager, report_data: ReportData):
        """Create the sell events sheet."""
        if not report_data.sell_events:
            return
        
        helper = layout_manager.create_worksheet("sell_events")
        
        # Filter out None values for taxable events
        taxable_sell_events = [
            event for event in report_data.sell_events 
            if event.taxable_gain_in_fiat is not None
        ]
        
        if taxable_sell_events:
            helper.write_dataclass_table(taxable_sell_events)
        
        helper.auto_fit_columns()
    
    def _create_interest_events_sheet(self, layout_manager: ExcelLayoutManager, report_data: ReportData):
        """Create the interest/lending events sheet."""
        if not report_data.interest_events:
            return
        
        helper = layout_manager.create_worksheet("interest_events")
        helper.write_dataclass_table(report_data.interest_events)
        helper.auto_fit_columns()
    
    def _create_misc_events_sheet(self, layout_manager: ExcelLayoutManager, report_data: ReportData):
        """Create the miscellaneous events sheet."""
        if not report_data.misc_events:
            return
        
        helper = layout_manager.create_worksheet("misc_events")
        helper.write_dataclass_table(report_data.misc_events)
        helper.auto_fit_columns()
    
    def _create_transfer_events_sheet(self, layout_manager: ExcelLayoutManager, report_data: ReportData):
        """Create the transfer events sheet."""
        if not report_data.transfer_events:
            return
        
        helper = layout_manager.create_worksheet("transfer_events")
        helper.write_dataclass_table(report_data.transfer_events)
        helper.auto_fit_columns()
    
    def _create_portfolio_sheet(self, layout_manager: ExcelLayoutManager, report_data: ReportData):
        """Create the portfolio overview sheet."""
        helper = layout_manager.create_worksheet("portfolio_overview")
        
        # Current holdings
        if report_data.single_depot_portfolio:
            holdings_data = [
                [layout_manager.get_localized_text("current_holdings"), ""]
            ]
            
            for coin, amount in report_data.single_depot_portfolio.items():
                holdings_data.append([coin, amount])
            
            helper.write_table_headers([layout_manager.get_localized_text("current_holdings"), "Amount"])
            
            for coin, amount in report_data.single_depot_portfolio.items():
                helper.write_data_row([coin, amount])
        
        helper.auto_fit_columns()
    
    def _create_unrealized_gains_sheet(self, layout_manager: ExcelLayoutManager, report_data: ReportData):
        """Create the unrealized gains sheet."""
        if not report_data.unrealized_events:
            return
        
        helper = layout_manager.create_worksheet("unrealized_gains")
        helper.write_dataclass_table(report_data.unrealized_events)
        helper.auto_fit_columns()


class GermanExcelExporter(ExcelReportExporter):
    """German localized Excel exporter."""
    
    def __init__(self):
        super().__init__(locale="german")


class EnglishExcelExporter(ExcelReportExporter):
    """English localized Excel exporter."""
    
    def __init__(self):
        super().__init__(locale="english")


# Factory functions for backward compatibility
def create_german_excel_report(report_data: ReportData) -> Path:
    """Create German Excel report (backward compatibility)."""
    exporter = GermanExcelExporter()
    return exporter.generate_report(report_data)


def create_english_excel_report(report_data: ReportData) -> Path:
    """Create English Excel report (backward compatibility)."""
    exporter = EnglishExcelExporter()
    return exporter.generate_report(report_data)