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
from .german_tax_summary import GermanTaxSummaryCalculator


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
            if self.locale == "german":
                self._create_german_tax_summary_sheet(layout_manager, report_data)
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
    
    def _create_german_tax_summary_sheet(self, layout_manager: ExcelLayoutManager, report_data: ReportData):
        """Create German tax summary sheet as first page (German reports only)."""
        # Create worksheet with explicit German name (don't use localization to avoid conflicts)
        worksheet = layout_manager.workbook.add_worksheet("Steuer-Zusammenfassung")
        helper = ExcelWorksheetHelper(worksheet, layout_manager.formats)
        
        # Calculate German tax summary
        calculator = GermanTaxSummaryCalculator()
        summary = calculator.calculate_summary(report_data)
        
        # Debug: Print summary data to understand what we have
        print(f"🔍 German tax summary debug:")
        print(f"  Tax year: {summary.tax_year}")
        print(f"  Sell events: {len(report_data.sell_events)}")
        print(f"  Interest events: {len(report_data.interest_events)}")
        print(f"  Misc events: {len(report_data.misc_events)}")
        print(f"  §23 EStG net: €{summary.paragraph_23_net_gain_loss}")
        print(f"  §22 Nr.3 total: €{summary.paragraph_22_total_income}")
        print(f"  Taxable amount: €{report_data.taxable_amount}")
        
        # Title
        helper.write_title(f"Ermittlung der Besteuerungsgrundlagen aus Gewinnen und Verlusten\naus dem Handel mit Kryptowährungen {summary.tax_year}")
        
        # §23 EStG Section - Private Sales Transactions
        helper.write_section_header("Ermittlung der sonstigen Einkünfte aus privaten Veräußerungsgeschäften nach § 23 EStG in EUR")
        
        paragraph_23_data = {
            "Summe Veräußerungsgewinn /-verlust": f"{summary.paragraph_23_net_gain_loss:.2f}",
            "Freigrenze": f"{summary.paragraph_23_freigrenze:.2f}",
            "Steuerrelevanter Veräußerungsgewinn /-verlust": f"{summary.paragraph_23_taxable_amount:.2f}",
            "Sonstige Einkünfte aus privaten Veräußerungsgeschäften im Sinne des § 23 EStG": "",
            "- einzutragen in Anlage SO - Zeile 54 -": f"{summary.paragraph_23_taxable_amount:.2f}"
        }
        
        for key, value in paragraph_23_data.items():
            helper.write_data_row([key, value])
        
        helper.add_blank_row()
        
        # §22 Nr. 3 EStG Section - Income from Other Services
        helper.write_section_header("Ermittlung der sonstigen Einkünfte nach § 22 Nr. 3 EStG in EUR")
        
        paragraph_22_data = {
            "Summe sonstige Einkünfte": f"{summary.paragraph_22_total_income:.2f}",
            "Freigrenze": f"{summary.paragraph_22_allowance:.2f}",
            "Steuerrelevante sonstige Einkünfte": f"{summary.paragraph_22_taxable_income:.2f}",
            "Sonstige Einkünfte im Sinne des § 22 Nr. 3 EStG": "",
            "- einzutragen in Anlage SO - Zeile 11 -": f"{summary.paragraph_22_taxable_income:.2f}"
        }
        
        for key, value in paragraph_22_data.items():
            helper.write_data_row([key, value])
        
        helper.add_blank_row()
        
        # KAP Section - Capital Gains
        helper.write_section_header("Ermittlung der Kapitalerträge, die nicht dem inländischen Steuerabzug unterlegen haben")
        
        kap_data = {
            "Inländische Kapitalerträge": f"{summary.kap_domestic_gains:.2f}",
            "- einzutragen in Anlage KAP - Zeile 18 -": "",
            "Ausländische Kapitalerträge": f"{summary.kap_foreign_gains:.2f}",
            "- einzutragen in Anlage KAP - Zeile 19 -": "",
            "In den Zeilen 18 und 19 enthaltene Gewinne aus Aktienveräußerungen": f"{summary.kap_stock_gains:.2f}",
            "- einzutragen in Anlage KAP - Zeile 20 -": "",
            "In den Zeilen 18 und 19 enthaltene Einkünfte aus Gewinne aus Termingeschäften": f"{summary.kap_derivative_gains:.2f}",
            "- einzutragen in Anlage KAP - Zeile 21 -": "",
            "In den Zeilen 18 und 19 enthaltene Verluste ohne Verluste aus der Veräußerung von Aktien": f"{summary.kap_losses_without_stocks:.2f}",
            "- einzutragen in Anlage KAP - Zeile 22 -": "",
            "In den Zeilen 18 und 19 enthaltene Verluste aus der Veräußerung von Aktien": f"{summary.kap_stock_losses:.2f}",
            "- einzutragen in Anlage KAP - Zeile 23 -": "",
            "Verluste aus Termingeschäften": f"{summary.kap_derivative_losses:.2f}",
            "- einzutragen in Anlage KAP - Zeile 24 -": ""
        }
        
        for key, value in kap_data.items():
            helper.write_data_row([key, value])
        
        helper.add_blank_row()
        
        # Fees and Costs Section
        helper.write_section_header("Nicht abgezogene Gesamt-Transaktionswerte in EUR")
        
        fees_data = {
            "Fee": f"{summary.total_fees:.2f}",
            "Lost": f"{summary.lost_coins:.2f}",
            "Derivative Fee": f"{summary.derivative_fees:.2f}"
        }
        
        for key, value in fees_data.items():
            helper.write_data_row([key, value])
        
        helper.add_blank_row()
        
        # §22 Nr. 3 EStG Breakdown Section
        helper.write_section_header(f"Ermittlung der Besteuerungsgrundlagen von steuerrelevanten Zuflüssen\nim Zusammenhang mit Kryptowährungen {summary.tax_year}")
        helper.write_data_row(["- Anlage zu den Einkünften aus sonstigen Leistungen -", ""])
        helper.add_blank_row()
        
        helper.write_section_header("Zuflüsse im Zusammenhang mit Kryptowährungen in EUR")
        
        income_breakdown = {
            "Lending": f"{summary.paragraph_22_lending:.2f}",
            "Staking": f"{summary.paragraph_22_staking:.2f}",
            "Masternodes": "0.00",  # Not separately tracked yet
            "Mining (nicht gewerblich)": f"{summary.paragraph_22_mining:.2f}",
            "Bounties": f"{summary.paragraph_22_bounties:.2f}",
            "Income": f"{summary.paragraph_22_other:.2f}",
            "Summe sonstige Einkünfte": f"{summary.paragraph_22_total_income:.2f}"
        }
        
        for key, value in income_breakdown.items():
            helper.write_data_row([key, value])
        
        helper.auto_fit_columns()
    
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