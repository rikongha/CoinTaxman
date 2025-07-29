"""
Comprehensive Symbol Mappings for Cryptocurrency Forks, Rebrands, and Reissuances

This module handles complex token symbol changes over time, including:
- Hard forks (BCC→BCH)
- Rebrands (LEND→AAVE, NPXS→PUNDIX)
- Ecosystem collapses (LUNA→LUNC, UST→USTC)
- Chain migrations and swaps
"""

from datetime import date
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class SymbolMappingManager:
    """Manages complex cryptocurrency symbol mappings with date context."""
    
    def __init__(self):
        # Format: (old_symbol, new_symbol, cutoff_date, swap_ratio, notes)
        self.mappings = [
            # Bitcoin Cash fork
            ('BCC', 'BCH', None, 1.0, 'Bitcoin Cash - BCC was temporary symbol'),
            ('BCHA', 'BCH', None, 1.0, 'Bitcoin Cash ABC'),
            
            # Aave rebrand (October 3, 2020)
            ('LEND', 'AAVE', date(2020, 10, 3), 100.0, 'LEND became AAVE with 100:1 swap ratio'),
            
            # Pundi X rebrand (March 30, 2021) 
            ('NPXS', 'PUNDIX', date(2021, 3, 30), 1000.0, 'NPXS became PUNDIX with 1000:1 swap ratio'),
            
            # Terra ecosystem collapse (May 12, 2022)
            ('UST', 'USTC', date(2022, 5, 12), 1.0, 'TerraUSD became TerraUSD Classic'),
            
            # Terra LUNA is complex - handled separately
            # Pre-collapse: LUNA (original)
            # Post-collapse: LUNC (Terra Classic) + LUNA (new v2)
            
            # Other potential mappings (add as discovered)
            # ('OLD', 'NEW', date(YYYY, MM, DD), ratio, 'Description'),
        ]
    
    def get_symbol_mapping(self, symbol: str, lookup_date: date) -> Tuple[str, Optional[float]]:
        """
        Get the correct symbol and swap ratio for a given date.
        
        Args:
            symbol: Original symbol to map
            lookup_date: Date of the transaction
            
        Returns:
            Tuple of (mapped_symbol, swap_ratio)
            - mapped_symbol: The symbol to use for price lookup
            - swap_ratio: Price adjustment ratio (None if no adjustment needed)
        """
        symbol = symbol.upper()
        
        # Handle complex LUNA ecosystem
        if symbol == 'LUNA':
            return self._handle_luna_mapping(lookup_date)
        
        # Handle standard mappings
        for old_sym, new_sym, cutoff_date, swap_ratio, notes in self.mappings:
            if symbol == old_sym:
                if cutoff_date is None or lookup_date >= cutoff_date:
                    logger.debug(f"Symbol mapping: {old_sym} → {new_sym} on {lookup_date} ({notes})")
                    return new_sym, swap_ratio
                else:
                    # Before cutoff date, use original symbol
                    return symbol, None
        
        # No mapping needed
        return symbol, None
    
    def _handle_luna_mapping(self, lookup_date: date) -> Tuple[str, Optional[float]]:
        """Handle the complex LUNA/LUNC scenario correctly."""
        terra_rebrand = date(2022, 5, 12)
        
        if lookup_date < terra_rebrand:
            # Pre-rebrand: LUNA transactions should use LUNC historical data
            # (because old LUNA became LUNC after collapse)
            return 'LUNC', None
        else:
            # Post-rebrand: LUNA transactions use new LUNA v2 data
            return 'LUNA', None
    
    def get_all_mapped_symbols(self, symbol: str) -> list[str]:
        """Get all possible symbol variations for comprehensive lookup."""
        symbol = symbol.upper()
        variants = [symbol]
        
        # Add historical variants
        for old_sym, new_sym, _, _, _ in self.mappings:
            if symbol == old_sym and new_sym not in variants:
                variants.append(new_sym)
            elif symbol == new_sym and old_sym not in variants:
                variants.append(old_sym)
        
        # Handle LUNA special case
        if symbol == 'LUNA':
            if 'LUNC' not in variants:
                variants.append('LUNC')
        elif symbol == 'LUNC':
            if 'LUNA' not in variants:
                variants.append('LUNA')
        
        return variants
    
    def validate_historical_data_coverage(self, trading_symbols: list[str], 
                                        historical_symbols: list[str]) -> Dict[str, list[str]]:
        """
        Validate that historical data exists for mapped symbols.
        
        Returns:
            Dict mapping issues to list of affected symbols
        """
        issues = {
            'missing_historical': [],
            'mapping_needed': [],
            'ambiguous': []
        }
        
        for symbol in trading_symbols:
            mapped_symbol, _ = self.get_symbol_mapping(symbol, date.today())
            variants = self.get_all_mapped_symbols(symbol)
            
            # Check if any variant has historical data
            has_historical = any(var.lower() in [h.lower() for h in historical_symbols] 
                               for var in variants)
            
            if not has_historical:
                issues['missing_historical'].append(symbol)
            elif len(variants) > 1:
                issues['mapping_needed'].append(f"{symbol} → {variants}")
        
        return issues


# Global instance
symbol_manager = SymbolMappingManager()