"""
German Tax Summary Calculator

Calculates German tax report summary sections according to German tax law:
- §23 EStG (Private sales transactions)
- §22 Nr. 3 EStG (Income from other services)
- KAP (Capital gains from securities/derivatives)

Based on BlockPit and Koinly reference implementations.
"""

import decimal
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import datetime

import transaction as tr
from .report_generator import ReportData


@dataclass
class GermanTaxSummary:
    """German tax summary according to tax law requirements."""
    
    # §23 EStG - Private sales transactions (Speculative gains)
    paragraph_23_total_gains: decimal.Decimal = decimal.Decimal('0')
    paragraph_23_total_losses: decimal.Decimal = decimal.Decimal('0')
    paragraph_23_net_gain_loss: decimal.Decimal = decimal.Decimal('0')
    paragraph_23_freigrenze: decimal.Decimal = decimal.Decimal('1000.00')
    paragraph_23_taxable_amount: decimal.Decimal = decimal.Decimal('0')
    paragraph_23_transactions_count: int = 0
    paragraph_23_short_term_count: int = 0
    paragraph_23_long_term_count: int = 0
    
    # §22 Nr. 3 EStG - Income from other services (Staking, Lending, Mining, etc.)
    paragraph_22_total_income: decimal.Decimal = decimal.Decimal('0')
    paragraph_22_allowance: decimal.Decimal = decimal.Decimal('256.00')
    paragraph_22_taxable_income: decimal.Decimal = decimal.Decimal('0')
    
    # Breakdown by income type
    paragraph_22_staking: decimal.Decimal = decimal.Decimal('0')
    paragraph_22_lending: decimal.Decimal = decimal.Decimal('0')
    paragraph_22_mining: decimal.Decimal = decimal.Decimal('0')
    paragraph_22_airdrops: decimal.Decimal = decimal.Decimal('0')
    paragraph_22_bounties: decimal.Decimal = decimal.Decimal('0')
    paragraph_22_other: decimal.Decimal = decimal.Decimal('0')
    
    # KAP - Capital gains (Securities/Derivatives not subject to domestic withholding tax)
    kap_domestic_gains: decimal.Decimal = decimal.Decimal('0')
    kap_foreign_gains: decimal.Decimal = decimal.Decimal('0')
    kap_stock_gains: decimal.Decimal = decimal.Decimal('0')
    kap_derivative_gains: decimal.Decimal = decimal.Decimal('0')
    kap_losses_without_stocks: decimal.Decimal = decimal.Decimal('0')
    kap_stock_losses: decimal.Decimal = decimal.Decimal('0')
    kap_derivative_losses: decimal.Decimal = decimal.Decimal('0')
    
    # Transaction costs and fees
    total_fees: decimal.Decimal = decimal.Decimal('0')
    lost_coins: decimal.Decimal = decimal.Decimal('0')
    derivative_fees: decimal.Decimal = decimal.Decimal('0')
    
    # Tax year
    tax_year: int = 2024


class GermanTaxSummaryCalculator:
    """Calculator for German tax summary sections."""
    
    def __init__(self):
        self.FREIGRENZE_23 = decimal.Decimal('1000.00')  # €1,000 threshold for §23 EStG
        self.ALLOWANCE_22 = decimal.Decimal('256.00')    # €256 allowance for §22 Nr. 3 EStG
        self.HOLDING_PERIOD_DAYS = 365                   # One year holding period
    
    def calculate_summary(self, report_data: ReportData) -> GermanTaxSummary:
        """Calculate comprehensive German tax summary from report data."""
        
        summary = GermanTaxSummary()
        summary.tax_year = report_data.tax_year
        
        # Calculate §23 EStG (Private sales transactions)
        self._calculate_paragraph_23(summary, report_data)
        
        # Calculate §22 Nr. 3 EStG (Income from other services)
        self._calculate_paragraph_22(summary, report_data)
        
        # Calculate KAP (Capital gains from securities/derivatives)
        self._calculate_kap_section(summary, report_data)
        
        # Calculate fees and costs
        self._calculate_fees_and_costs(summary, report_data)
        
        return summary
    
    def _calculate_paragraph_23(self, summary: GermanTaxSummary, report_data: ReportData):
        """Calculate §23 EStG private sales transactions summary."""
        
        total_gains = decimal.Decimal('0')
        total_losses = decimal.Decimal('0')
        short_term_count = 0
        long_term_count = 0
        
        for event in report_data.sell_events:
            if not hasattr(event, 'taxable_gain_in_fiat') or event.taxable_gain_in_fiat is None:
                continue
                
            gain_loss = decimal.Decimal(str(event.taxable_gain_in_fiat))
            
            # Determine if short-term (< 1 year) or long-term
            is_short_term = self._is_short_term_transaction(event)
            
            if is_short_term:
                short_term_count += 1
                if gain_loss > 0:
                    total_gains += gain_loss
                else:
                    total_losses += abs(gain_loss)
            else:
                long_term_count += 1
                # Long-term gains are generally tax-free in Germany
        
        net_gain_loss = total_gains - total_losses
        
        # Apply Freigrenze (all-or-nothing threshold)
        if net_gain_loss <= self.FREIGRENZE_23:
            taxable_amount = decimal.Decimal('0')  # All tax-free under threshold
        else:
            taxable_amount = net_gain_loss  # All taxable if above threshold
        
        # Update summary
        summary.paragraph_23_total_gains = total_gains
        summary.paragraph_23_total_losses = total_losses
        summary.paragraph_23_net_gain_loss = net_gain_loss
        summary.paragraph_23_taxable_amount = taxable_amount
        summary.paragraph_23_transactions_count = len(report_data.sell_events)
        summary.paragraph_23_short_term_count = short_term_count
        summary.paragraph_23_long_term_count = long_term_count
    
    def _calculate_paragraph_22(self, summary: GermanTaxSummary, report_data: ReportData):
        """Calculate §22 Nr. 3 EStG income from other services summary."""
        
        total_income = decimal.Decimal('0')
        staking_income = decimal.Decimal('0')
        lending_income = decimal.Decimal('0')
        mining_income = decimal.Decimal('0')
        airdrop_income = decimal.Decimal('0')
        bounty_income = decimal.Decimal('0')
        other_income = decimal.Decimal('0')
        
        # Process interest events (staking, lending)
        for event in report_data.interest_events:
            if not hasattr(event, 'taxable_gain_in_fiat') or event.taxable_gain_in_fiat is None:
                continue
            
            # Only include if actually taxable
            if not getattr(event, 'is_taxable', True):
                continue
                
            income = decimal.Decimal(str(event.taxable_gain_in_fiat))
            total_income += income
            
            # Categorize by event type
            event_type = getattr(event, 'event_type', '').lower()
            if 'staking' in event_type:
                staking_income += income
            elif 'lending' in event_type or 'lend' in event_type:
                lending_income += income
            else:
                other_income += income
        
        # Process misc events (mining, airdrops, bounties)
        for event in report_data.misc_events:
            if not hasattr(event, 'taxable_gain_in_fiat') or event.taxable_gain_in_fiat is None:
                continue
            
            # Only include if actually taxable
            if not getattr(event, 'is_taxable', True):
                continue
                
            income = decimal.Decimal(str(event.taxable_gain_in_fiat))
            total_income += income
            
            # Categorize by event type
            event_type = getattr(event, 'event_type', '').lower()
            if 'mining' in event_type:
                mining_income += income
            elif 'airdrop' in event_type:
                airdrop_income += income
            elif 'bounty' in event_type:
                bounty_income += income
            else:
                other_income += income
        
        # Apply allowance
        taxable_income = max(decimal.Decimal('0'), total_income - self.ALLOWANCE_22)
        
        # Update summary
        summary.paragraph_22_total_income = total_income
        summary.paragraph_22_taxable_income = taxable_income
        summary.paragraph_22_staking = staking_income
        summary.paragraph_22_lending = lending_income
        summary.paragraph_22_mining = mining_income
        summary.paragraph_22_airdrops = airdrop_income
        summary.paragraph_22_bounties = bounty_income
        summary.paragraph_22_other = other_income
    
    def _calculate_kap_section(self, summary: GermanTaxSummary, report_data: ReportData):
        """Calculate KAP section for securities and derivatives."""
        
        # Note: Most cryptocurrency transactions fall under §23 EStG, not KAP
        # KAP would apply to crypto ETFs, structured products, or derivatives
        # For now, initialize to zero unless specific derivative transactions are found
        
        domestic_gains = decimal.Decimal('0')
        foreign_gains = decimal.Decimal('0')
        stock_gains = decimal.Decimal('0')
        derivative_gains = decimal.Decimal('0')
        losses_without_stocks = decimal.Decimal('0')
        stock_losses = decimal.Decimal('0')
        derivative_losses = decimal.Decimal('0')
        
        # Check for derivative or structured product transactions
        for event in report_data.sell_events:
            # This would need platform-specific logic to identify derivatives
            platform = getattr(event, 'platform', '').lower()
            coin = getattr(event, 'coin', '').upper()
            
            # Example: Check for known derivative products
            if ('future' in platform or 'margin' in platform or 
                'cfd' in platform or coin.endswith('PERP')):
                
                if hasattr(event, 'taxable_gain_in_fiat') and event.taxable_gain_in_fiat is not None:
                    gain_loss = decimal.Decimal(str(event.taxable_gain_in_fiat))
                    
                    # Classify as domestic or foreign based on platform
                    if self._is_domestic_platform(platform):
                        domestic_gains += max(decimal.Decimal('0'), gain_loss)
                        if gain_loss < 0:
                            derivative_losses += abs(gain_loss)
                    else:
                        foreign_gains += max(decimal.Decimal('0'), gain_loss)
                        if gain_loss < 0:
                            derivative_losses += abs(gain_loss)
                    
                    derivative_gains += max(decimal.Decimal('0'), gain_loss)
        
        # Update summary
        summary.kap_domestic_gains = domestic_gains
        summary.kap_foreign_gains = foreign_gains
        summary.kap_stock_gains = stock_gains
        summary.kap_derivative_gains = derivative_gains
        summary.kap_losses_without_stocks = losses_without_stocks
        summary.kap_stock_losses = stock_losses
        summary.kap_derivative_losses = derivative_losses
    
    def _calculate_fees_and_costs(self, summary: GermanTaxSummary, report_data: ReportData):
        """Calculate transaction fees and costs that may be deductible."""
        
        total_fees = decimal.Decimal('0')
        lost_coins = decimal.Decimal('0')
        derivative_fees = decimal.Decimal('0')
        
        # Extract fees from all transaction types
        all_events = (
            report_data.sell_events + 
            report_data.interest_events + 
            report_data.misc_events + 
            report_data.transfer_events
        )
        
        for event in all_events:
            # Standard transaction fees
            if hasattr(event, 'fee_in_fiat') and event.fee_in_fiat is not None:
                fee = decimal.Decimal(str(event.fee_in_fiat))
                total_fees += fee
                
                # Categorize fees
                event_type = getattr(event, 'event_type', '').lower()
                platform = getattr(event, 'platform', '').lower()
                
                if ('future' in event_type or 'margin' in event_type or 
                    'derivative' in platform):
                    derivative_fees += fee
            
            # Lost or burned coins
            if hasattr(event, 'lost_amount') and event.lost_amount is not None:
                lost_value = decimal.Decimal(str(event.lost_amount))
                lost_coins += lost_value
        
        # Update summary
        summary.total_fees = total_fees
        summary.lost_coins = lost_coins
        summary.derivative_fees = derivative_fees
    
    def _is_short_term_transaction(self, sell_event) -> bool:
        """Determine if transaction is short-term (< 1 year holding period)."""
        
        if not hasattr(sell_event, 'buy_timestamp') or not hasattr(sell_event, 'sell_timestamp'):
            return True  # Conservative assumption
        
        buy_date = sell_event.buy_timestamp
        sell_date = sell_event.sell_timestamp
        
        if isinstance(buy_date, str):
            buy_date = datetime.fromisoformat(buy_date.replace('Z', '+00:00'))
        if isinstance(sell_date, str):
            sell_date = datetime.fromisoformat(sell_date.replace('Z', '+00:00'))
        
        holding_days = (sell_date - buy_date).days
        return holding_days < self.HOLDING_PERIOD_DAYS
    
    def _is_domestic_platform(self, platform: str) -> bool:
        """Determine if platform is considered domestic German platform."""
        
        # German or EU-based platforms
        domestic_platforms = [
            'bison', 'bitcoin.de', 'bitpanda', 'coinbase', 'kraken'
        ]
        
        return any(domestic in platform.lower() for domestic in domestic_platforms)
    
    def format_for_tax_forms(self, summary: GermanTaxSummary) -> Dict[str, Any]:
        """Format summary for German tax form entries."""
        
        return {
            # Anlage SO - Sonstige Einkünfte
            'anlage_so': {
                # §22 Nr. 3 EStG entries (lines 10-16)
                'line_11': float(summary.paragraph_22_taxable_income),  # Taxable income from other services
                
                # §23 EStG entries (lines 41-47, 54-55)
                'line_54': float(summary.paragraph_23_taxable_amount),  # Taxable speculative gains
            },
            
            # Anlage KAP - Kapitalerträge
            'anlage_kap': {
                'line_18': float(summary.kap_domestic_gains),           # Domestic capital gains
                'line_19': float(summary.kap_foreign_gains),           # Foreign capital gains
                'line_20': float(summary.kap_stock_gains),             # Stock gains
                'line_21': float(summary.kap_derivative_gains),        # Derivative gains
                'line_22': float(summary.kap_losses_without_stocks),   # Losses without stocks
                'line_23': float(summary.kap_stock_losses),            # Stock losses
                'line_24': float(summary.kap_derivative_losses),       # Derivative losses
            },
            
            # Summary totals
            'summary_totals': {
                'paragraph_23_net': float(summary.paragraph_23_net_gain_loss),
                'paragraph_22_total': float(summary.paragraph_22_total_income),
                'total_fees': float(summary.total_fees),
                'tax_year': summary.tax_year
            }
        }


def create_german_tax_summary(report_data: ReportData) -> GermanTaxSummary:
    """Create German tax summary from report data (convenience function)."""
    calculator = GermanTaxSummaryCalculator()
    return calculator.calculate_summary(report_data)