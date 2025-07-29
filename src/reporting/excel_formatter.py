"""
Excel Formatting Utilities

Handles Excel file formatting, styles, and layout for tax reports.
Extracted from Taxman class to separate presentation logic.
"""

import dataclasses
import datetime
from typing import Optional, Dict, Any

import xlsxwriter


class ExcelFormats:
    """Container for Excel formatting objects."""
    
    def __init__(self, workbook: xlsxwriter.Workbook, locale: str = "german"):
        self.workbook = workbook
        self.locale = locale
        
        # Date formats
        if locale == "german":
            self.datetime_format = workbook.add_format({"num_format": "dd.mm.yyyy hh:mm;@"})
            self.date_format = workbook.add_format({"num_format": "dd.mm.yyyy;@"})
        else:  # English
            self.datetime_format = workbook.add_format({"num_format": "mm/dd/yyyy hh:mm;@"})
            self.date_format = workbook.add_format({"num_format": "mm/dd/yyyy;@"})
        
        # Number formats
        self.change_format = workbook.add_format({"num_format": "#,##0.00000000"})
        self.fiat_format = workbook.add_format({"num_format": "#,##0.00"})
        
        # Style formats
        self.header_format = workbook.add_format({
            "bold": True,
            "border": 5,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
        })
        
        self.bold_format = workbook.add_format({"bold": True})
        
        # Conditional formats
        self.positive_format = workbook.add_format({"font_color": "green"})
        self.negative_format = workbook.add_format({"font_color": "red"})
    
    def get_format_for_field(self, field: dataclasses.Field) -> Optional[xlsxwriter.format.Format]:
        """Get appropriate format for a dataclass field."""
        if field.type in ("datetime.datetime", "Optional[datetime.datetime]"):
            return self.datetime_format
        if field.type in ("decimal.Decimal", "Optional[decimal.Decimal]"):
            if field.name.endswith("in_fiat"):
                return self.fiat_format
            return self.change_format
        return None
    
    def get_number_format(self, value: Any, field_name: str = "") -> Optional[xlsxwriter.format.Format]:
        """Get format based on value type and field name."""
        if isinstance(value, datetime.datetime):
            return self.datetime_format
        elif isinstance(value, datetime.date):
            return self.date_format
        elif isinstance(value, (int, float)) and field_name.endswith("in_fiat"):
            return self.fiat_format
        elif isinstance(value, (int, float)):
            return self.change_format
        return None


class ExcelWorksheetHelper:
    """Helper class for common Excel worksheet operations."""
    
    def __init__(self, worksheet: xlsxwriter.worksheet.Worksheet, formats: ExcelFormats):
        self.worksheet = worksheet
        self.formats = formats
        self.current_row = 0
    
    def write_header_section(self, title: str, data: Dict[str, Any], start_row: int = None) -> int:
        """Write a header section with title and key-value pairs."""
        if start_row is not None:
            self.current_row = start_row
        
        # Write section title
        self.worksheet.merge_range(
            self.current_row, 0, self.current_row, 1, 
            title, self.formats.header_format
        )
        self.current_row += 1
        
        # Write data rows
        for key, value in data.items():
            format_obj = self.formats.get_number_format(value, key)
            self.worksheet.write_row(self.current_row, 0, [key, value], format_obj)
            self.current_row += 1
        
        self.current_row += 1  # Add spacing
        return self.current_row
    
    def write_table_headers(self, headers: list, start_row: int = None) -> int:
        """Write table headers with proper formatting."""
        if start_row is not None:
            self.current_row = start_row
        
        for col, header in enumerate(headers):
            self.worksheet.write(self.current_row, col, header, self.formats.header_format)
        
        self.current_row += 1
        return self.current_row
    
    def write_data_row(self, data: list, row_formats: list = None) -> int:
        """Write a data row with optional per-column formatting."""
        for col, value in enumerate(data):
            format_obj = None
            if row_formats and col < len(row_formats):
                format_obj = row_formats[col]
            elif hasattr(value, '__class__'):
                format_obj = self.formats.get_number_format(value)
            
            self.worksheet.write(self.current_row, col, value, format_obj)
        
        self.current_row += 1
        return self.current_row
    
    def write_dataclass_table(self, data_objects: list, start_row: int = None) -> int:
        """Write a table from a list of dataclass objects."""
        if not data_objects:
            return self.current_row
        
        if start_row is not None:
            self.current_row = start_row
        
        # Get field information from first object
        first_obj = data_objects[0]
        fields = dataclasses.fields(first_obj)
        
        # Write headers
        headers = [field.name for field in fields]
        self.write_table_headers(headers)
        
        # Write data rows
        for obj in data_objects:
            row_data = []
            row_formats = []
            
            for field in fields:
                value = getattr(obj, field.name)
                row_data.append(value)
                format_obj = self.formats.get_format_for_field(field)
                row_formats.append(format_obj)
            
            self.write_data_row(row_data, row_formats)
        
        self.current_row += 1  # Add spacing
        return self.current_row
    
    def write_title(self, title: str) -> int:
        """Write a main title for the sheet."""
        self.worksheet.merge_range(
            self.current_row, 0, self.current_row, 3,
            title, self.formats.header_format
        )
        self.current_row += 2  # Add extra spacing after title
        return self.current_row
    
    def write_section_header(self, header: str) -> int:
        """Write a section header."""
        self.worksheet.write(self.current_row, 0, header, self.formats.bold_format)
        self.current_row += 1
        return self.current_row
    
    def add_blank_row(self) -> int:
        """Add a blank row for spacing."""
        self.current_row += 1
        return self.current_row
    
    def auto_fit_columns(self, max_width: int = 50):
        """Auto-fit column widths (approximate, as xlsxwriter doesn't support true auto-fit)."""
        # This is a simplified version - real implementation would calculate based on content
        for col in range(20):  # Adjust based on expected number of columns
            self.worksheet.set_column(col, col, min(max_width, 60))  # Increased from 15 to 60 for German text


class ExcelLayoutManager:
    """Manages the overall layout and structure of Excel reports."""
    
    def __init__(self, workbook: xlsxwriter.Workbook, locale: str = "german"):
        self.workbook = workbook
        self.formats = ExcelFormats(workbook, locale)
        self.locale = locale
    
    def get_localized_text(self, key: str) -> str:
        """Get localized text for various report elements."""
        
        texts = {
            "german": {
                "general": "Allgemein",
                "general_data": "Allgemeine Daten", 
                "tax_period": "Zeitraum des Steuerberichts",
                "tax_year": "Steuerjahr",
                "country": "Land",
                "fiat_currency": "Fiat-Währung",
                "multi_depot": "Multi-Depot",
                "total_events": "Anzahl steuerpflichtiger Ereignisse",
                "sell_events": "Verkäufe",
                "interest_events": "Zinsen und Lending", 
                "misc_events": "Sonstige Einkünfte",
                "portfolio_overview": "Portfolio-Übersicht",
                "current_holdings": "Aktuelle Bestände",
                "unrealized_gains": "Unrealisierte Gewinne",
                "summary": "Zusammenfassung",
                "total_gains": "Gesamtgewinne",
                "total_income": "Gesamteinkommen",
                "taxable_amount": "Steuerpflichtiger Betrag"
            },
            "english": {
                "general": "General",
                "general_data": "General Information",
                "tax_period": "Tax Report Period", 
                "tax_year": "Tax Year",
                "country": "Country",
                "fiat_currency": "Fiat Currency",
                "multi_depot": "Multi-Depot",
                "total_events": "Total Taxable Events",
                "sell_events": "Sales",
                "interest_events": "Interest and Lending",
                "misc_events": "Miscellaneous Income", 
                "portfolio_overview": "Portfolio Overview",
                "current_holdings": "Current Holdings",
                "unrealized_gains": "Unrealized Gains",
                "summary": "Summary",
                "total_gains": "Total Gains", 
                "total_income": "Total Income",
                "taxable_amount": "Taxable Amount"
            }
        }
        
        return texts.get(self.locale, texts["german"]).get(key, key)
    
    def create_worksheet(self, name: str) -> ExcelWorksheetHelper:
        """Create a new worksheet with helper."""
        # Translate worksheet name
        localized_name = self.get_localized_text(name.lower())
        worksheet = self.workbook.add_worksheet(localized_name)
        return ExcelWorksheetHelper(worksheet, self.formats)