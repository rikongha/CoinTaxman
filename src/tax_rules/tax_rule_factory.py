"""
Tax Rule Factory

Creates appropriate tax rule implementations based on country configuration.
Provides a clean way to instantiate country-specific tax logic.
"""

from typing import Dict, Type

import core
from .tax_rules_interface import TaxRulesInterface
from .german_tax_rules import GermanTaxRules


class TaxRuleFactory:
    """
    Factory for creating country-specific tax rule implementations.
    
    This factory encapsulates the creation logic and makes it easy to
    add support for new countries without modifying existing code.
    """
    
    # Registry of supported countries and their implementations
    _IMPLEMENTATIONS: Dict[core.Country, Type[TaxRulesInterface]] = {
        core.Country.GERMANY: GermanTaxRules,
    }
    
    @classmethod
    def create_tax_rules(cls, country: core.Country) -> TaxRulesInterface:
        """
        Create tax rules implementation for the specified country.
        
        Args:
            country: Country to create tax rules for
            
        Returns:
            Tax rules implementation for the country
            
        Raises:
            NotImplementedError: If the country is not supported
        """
        if country not in cls._IMPLEMENTATIONS:
            raise NotImplementedError(
                f"Tax rules for {country.name} are not implemented. "
                f"Supported countries: {[c.name for c in cls._IMPLEMENTATIONS.keys()]}"
            )
        
        implementation_class = cls._IMPLEMENTATIONS[country]
        return implementation_class()
    
    @classmethod
    def get_supported_countries(cls) -> list[core.Country]:
        """Get list of supported countries."""
        return list(cls._IMPLEMENTATIONS.keys())
    
    @classmethod
    def register_implementation(cls, 
                              country: core.Country, 
                              implementation: Type[TaxRulesInterface]) -> None:
        """
        Register a new tax rules implementation for a country.
        
        This allows for dynamic registration of new country implementations
        without modifying the factory code.
        
        Args:
            country: Country to register implementation for
            implementation: Tax rules implementation class
        """
        cls._IMPLEMENTATIONS[country] = implementation
    
    @classmethod
    def is_country_supported(cls, country: core.Country) -> bool:
        """Check if a country is supported."""
        return country in cls._IMPLEMENTATIONS


def create_tax_rules_from_config() -> TaxRulesInterface:
    """
    Create tax rules using the global configuration.
    
    Convenience function that reads the country from config and
    creates the appropriate tax rules implementation.
    
    Returns:
        Tax rules implementation for the configured country
    """
    import config
    return TaxRuleFactory.create_tax_rules(config.COUNTRY)


# Backward compatibility function for gradual migration
def get_tax_rules() -> TaxRulesInterface:
    """Get singleton tax rules instance (for gradual migration)."""
    global _tax_rules_instance
    if '_tax_rules_instance' not in globals():
        _tax_rules_instance = create_tax_rules_from_config()
    return _tax_rules_instance