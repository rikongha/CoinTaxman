"""
German Tax Rules Implementation

Implements German cryptocurrency tax law according to:
- §23 EStG (Private sales transactions)
- §22 Nr. 3 EStG (Income from other services)  
- BMF Guidelines (Federal Ministry of Finance)
"""

import decimal
import datetime
from typing import Dict, List, Optional, Any
from dateutil.relativedelta import relativedelta

import transaction as tr
import core
from .tax_rules_interface import (
    TaxRulesInterface, TaxContext, TaxResult, TaxCategory, 
    ComplianceWarning, BaseTaxRules
)


class GermanTaxRules(BaseTaxRules):
    """
    German cryptocurrency tax rules implementation.
    
    Implements German tax law for cryptocurrency transactions including:
    - One-year holding period rule (§23 EStG)
    - Income from staking/lending (§22 Nr. 3 EStG)
    - Annual thresholds and allowances
    - BMF compliance requirements
    """
    
    # German tax law constants
    ANNUAL_GAIN_THRESHOLD = decimal.Decimal('1000.00')  # €1,000 Freigrenze (2024+)
    INCOME_ALLOWANCE = decimal.Decimal('256.00')        # §22 Nr. 3 EStG allowance
    HOLDING_PERIOD_DAYS = 365                           # One year for §23 EStG
    
    # Gift tax exemption amounts (per year)
    GIFT_TAX_EXEMPTIONS = {
        'spouse': decimal.Decimal('500000'),      # €500,000
        'child': decimal.Decimal('400000'),       # €400,000  
        'grandchild': decimal.Decimal('200000'),  # €200,000
        'other': decimal.Decimal('20000')         # €20,000
    }
    
    def __init__(self):
        super().__init__("DE")
        self._register_german_tax_categories()
    
    def _register_german_tax_categories(self):
        """Register German tax categories."""
        
        # §23 EStG - Private sales transactions
        self._register_tax_category(TaxCategory(
            code="§23 EStG",
            name="Private Veräußerungsgeschäfte",
            description="Private sales transactions (speculative gains)",
            legal_reference="§23 Einkommensteuergesetz",
            threshold=self.ANNUAL_GAIN_THRESHOLD,
            holding_period_days=self.HOLDING_PERIOD_DAYS,
            tax_form_mapping="Anlage SO lines 41-47, 54-55"
        ))
        
        # §22 Nr. 3 EStG - Income from other services
        self._register_tax_category(TaxCategory(
            code="§22 Nr. 3 EStG", 
            name="Einkünfte aus sonstigen Leistungen",
            description="Income from other services (staking, lending)",
            legal_reference="§22 Nr. 3 Einkommensteuergesetz",
            allowance=self.INCOME_ALLOWANCE,
            tax_form_mapping="Anlage SO lines 10-16"
        ))
        
        # Gifts (tax-free for giver)
        self._register_tax_category(TaxCategory(
            code="Schenkung",
            name="Schenkung",
            description="Gifts (tax-free for giver under German gift tax law)",
            legal_reference="Schenkungsteuergesetz",
            tax_form_mapping="Not taxable for giver"
        ))
    
    def evaluate_operation(self, operation: tr.Operation, context: TaxContext) -> TaxResult:
        """Main German tax evaluation logic."""
        
        # Store operation in context for nested calls
        context.current_operation = operation
        
        if isinstance(operation, (tr.CoinLend, tr.Staking)):
            return self._evaluate_staking_lending_start(operation, context)
            
        elif isinstance(operation, (tr.CoinLendEnd, tr.StakingEnd)):
            return self._evaluate_staking_lending_end(operation, context)
            
        elif isinstance(operation, tr.Sell):
            return self._evaluate_sell(operation, context)
            
        elif isinstance(operation, (tr.StakingInterest, tr.CoinLendInterest)):
            return self._evaluate_income(operation, context)
            
        elif isinstance(operation, tr.Airdrop):
            return self._evaluate_airdrop(operation, context)
            
        elif isinstance(operation, tr.Mining):
            return self._evaluate_mining(operation, context)
            
        elif isinstance(operation, tr.Gift):
            return self._evaluate_gift(operation, context)
            
        elif isinstance(operation, tr.HardFork):
            return self._evaluate_hard_fork(operation, context)
            
        elif isinstance(operation, (tr.Buy, tr.Deposit, tr.Withdrawal)):
            # Non-taxable operations
            return self._create_tax_result(is_taxable=False)
            
        else:
            # Unknown operation type
            return self._create_tax_result(
                is_taxable=False,
                warnings=[f"Unknown operation type: {type(operation).__name__}"]
            )
    
    def calculate_holding_period_taxation(self, 
                                        buy_date: datetime.datetime, 
                                        sell_date: datetime.datetime) -> bool:
        """German one-year holding period rule (§23 EStG)."""
        return buy_date + relativedelta(years=1) > sell_date
    
    def classify_income_type(self, operation: tr.Operation, context: TaxContext) -> str:
        """Classify operation into German tax category."""
        
        if isinstance(operation, tr.Sell):
            return "§23 EStG"
            
        elif isinstance(operation, (tr.StakingInterest, tr.CoinLendInterest)):
            return "§22 Nr. 3 EStG"
            
        elif isinstance(operation, tr.Gift):
            return "Schenkung"
            
        elif isinstance(operation, tr.Mining):
            # Would need additional logic to determine commercial vs. private
            return "§22 Nr. 3 EStG"  # Default for private mining
            
        elif isinstance(operation, tr.Airdrop):
            # Classification depends on whether service was performed
            return "§22 Nr. 3 EStG"  # Default
            
        else:
            return "Unknown"
    
    def apply_annual_thresholds(self, 
                               entries: List[tr.TaxReportEntry], 
                               context: TaxContext) -> None:
        """Apply German annual thresholds and allowances."""
        
        # Apply €1,000 Freigrenze for §23 EStG gains
        self._apply_annual_gain_threshold(entries, context)
        
        # Apply €256 income allowance for §22 Nr. 3 EStG
        self._apply_income_allowance(entries, context)
    
    def _apply_annual_gain_threshold(self, 
                                   entries: List[tr.TaxReportEntry], 
                                   context: TaxContext) -> None:
        """Apply German €1,000 Freigrenze (all-or-nothing threshold)."""
        
        # Calculate total gains from §23 EStG transactions
        total_gains = decimal.Decimal('0')
        speculative_entries = []
        
        for entry in entries:
            if (hasattr(entry, 'taxation_type') and 
                entry.taxation_type == "§23 EStG" and
                hasattr(entry, 'taxable_gain_in_fiat') and
                entry.taxable_gain_in_fiat is not None):
                
                total_gains += entry.taxable_gain_in_fiat
                speculative_entries.append(entry)
        
        # Apply all-or-nothing rule
        if total_gains <= self.ANNUAL_GAIN_THRESHOLD:
            # All gains are tax-free
            for entry in speculative_entries:
                if hasattr(entry, '_mark_tax_free'):
                    entry._mark_tax_free("Under €1,000 Freigrenze")
    
    def _apply_income_allowance(self, 
                              entries: List[tr.TaxReportEntry], 
                              context: TaxContext) -> None:
        """Apply German €256 income allowance for §22 Nr. 3 EStG."""
        
        # Calculate total income from §22 Nr. 3 EStG
        total_income = decimal.Decimal('0')
        income_entries = []
        
        for entry in entries:
            if (hasattr(entry, 'taxation_type') and 
                entry.taxation_type == "§22 Nr. 3 EStG" and
                hasattr(entry, 'taxable_gain_in_fiat') and
                entry.taxable_gain_in_fiat is not None):
                
                total_income += entry.taxable_gain_in_fiat
                income_entries.append(entry)
        
        # Apply allowance proportionally if total income exceeds allowance
        if total_income > self.INCOME_ALLOWANCE:
            remaining_allowance = self.INCOME_ALLOWANCE
            
            for entry in income_entries:
                if remaining_allowance > 0 and hasattr(entry, 'apply_income_allowance'):
                    allowance_for_entry = min(remaining_allowance, entry.taxable_gain_in_fiat)
                    entry.apply_income_allowance(allowance_for_entry)
                    remaining_allowance -= allowance_for_entry
    
    def validate_compliance(self, 
                          operations: List[tr.Operation], 
                          context: TaxContext) -> List[ComplianceWarning]:
        """Validate German BMF compliance requirements."""
        warnings = []
        
        # Check for wallet-by-wallet tracking requirement
        if not context.multi_depot:
            warnings.append(ComplianceWarning(
                category="BMF Compliance",
                message="German BMF guidelines require separate tracking of each wallet/platform",
                severity="warning"
            ))
        
        # Check for FIFO principle compliance
        # (This would need access to configuration)
        
        # Check for proper documentation
        # (This would need more detailed analysis)
        
        return warnings
    
    def get_gift_tax_exemptions(self) -> Dict[str, decimal.Decimal]:
        """Get German gift tax exemption amounts by relationship."""
        return self.GIFT_TAX_EXEMPTIONS.copy()
    
    def supports_multi_depot(self) -> bool:
        """German BMF guidelines recommend multi-depot tracking."""
        return True
    
    def get_required_documentation(self) -> List[str]:
        """Get required documentation for German tax compliance."""
        return [
            "Transaction records with timestamps",
            "Wallet addresses and platform documentation", 
            "Price documentation at transaction time",
            "Holding period calculations",
            "FIFO cost basis tracking",
            "Separate records for each wallet/platform (BMF guideline)"
        ]
    
    # Private helper methods for specific operation types
    
    def _evaluate_sell(self, operation: tr.Sell, context: TaxContext) -> TaxResult:
        """Evaluate sell operation under German tax law."""
        # This would contain the detailed sell evaluation logic
        # from the current _evaluate_taxation_GERMANY method
        return self._create_tax_result(
            is_taxable=True,
            taxation_type="§23 EStG"
        )
    
    def _evaluate_income(self, operation: tr.Operation, context: TaxContext) -> TaxResult:
        """Evaluate income operations (staking, lending interest)."""
        return self._create_tax_result(
            is_taxable=True,
            taxation_type="§22 Nr. 3 EStG"
        )
    
    def _evaluate_staking_lending_start(self, operation: tr.Operation, context: TaxContext) -> TaxResult:
        """Evaluate start of staking/lending (non-taxable tracking)."""
        return self._create_tax_result(is_taxable=False)
    
    def _evaluate_staking_lending_end(self, operation: tr.Operation, context: TaxContext) -> TaxResult:
        """Evaluate end of staking/lending (non-taxable tracking)."""
        return self._create_tax_result(is_taxable=False)
    
    def _evaluate_airdrop(self, operation: tr.Airdrop, context: TaxContext) -> TaxResult:
        """Evaluate airdrop under German tax law."""
        # Classification logic based on service performed
        return self._create_tax_result(
            is_taxable=True,
            taxation_type="§22 Nr. 3 EStG"
        )
    
    def _evaluate_mining(self, operation: tr.Mining, context: TaxContext) -> TaxResult:
        """Evaluate mining under German tax law."""
        # Would include commercial vs. private classification
        return self._create_tax_result(
            is_taxable=True,
            taxation_type="§22 Nr. 3 EStG"
        )
    
    def _evaluate_gift(self, operation: tr.Gift, context: TaxContext) -> TaxResult:
        """Evaluate gift under German tax law (tax-free for giver)."""
        return self._create_tax_result(
            is_taxable=False,
            taxation_type="Schenkung"
        )
    
    def _evaluate_hard_fork(self, operation: tr.HardFork, context: TaxContext) -> TaxResult:
        """Evaluate hard fork under German tax law."""
        # Cost basis allocation logic
        return self._create_tax_result(is_taxable=False)