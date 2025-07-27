"""
Tax Service Factory

Creates fully configured tax calculation services with all dependencies.
This replaces the monolithic Taxman class construction with clean dependency injection.
"""

import core
from balance_management.balance_manager import create_balance_manager_from_config
from tax_rules.tax_rule_factory import create_tax_rules_from_config
from services.price_service_factory import get_default_price_service
from .tax_calculation_service import TaxCalculationService, TaxCalculationConfig


class TaxServiceFactory:
    """
    Factory for creating fully configured tax calculation services.
    
    This factory encapsulates all the complexity of setting up the various
    services and ensures they are properly configured and connected.
    """
    
    @staticmethod
    def create_from_config() -> TaxCalculationService:
        """
        Create tax calculation service using global configuration.
        
        This is the main factory method that reads the global configuration
        and creates a fully configured tax calculation service.
        
        Returns:
            Configured TaxCalculationService ready for use
        """
        import config
        
        # Create configuration
        tax_config = TaxCalculationConfig(
            tax_year=config.TAX_YEAR,
            country=config.COUNTRY,
            fiat_currency=getattr(config, 'FIAT_CURRENCY', 'EUR'),
            multi_depot=getattr(config, 'MULTI_DEPOT', False),
            principle=config.PRINCIPLE,
            calculate_unrealized_gains=getattr(config, 'CALCULATE_UNREALIZED_GAINS', True)
        )
        
        # Create service dependencies
        balance_manager = create_balance_manager_from_config()
        tax_rules = create_tax_rules_from_config()
        price_service = get_default_price_service()
        
        # Create the tax calculation service
        return TaxCalculationService(
            config=tax_config,
            balance_manager=balance_manager,
            tax_rules=tax_rules,
            price_service=price_service
        )
    
    @staticmethod
    def create_custom(tax_year: int,
                     country: core.Country,
                     fiat_currency: str = "EUR",
                     multi_depot: bool = False,
                     principle: core.Principle = core.Principle.FIFO) -> TaxCalculationService:
        """
        Create tax calculation service with custom configuration.
        
        This method allows creating a tax service with specific parameters
        without relying on global configuration.
        
        Args:
            tax_year: Year to calculate taxes for
            country: Country tax rules to use
            fiat_currency: Base fiat currency
            multi_depot: Whether to track platforms separately
            principle: FIFO or LIFO cost basis
            
        Returns:
            Configured TaxCalculationService
        """
        from balance_management.balance_config import BalanceConfig, BalancingPrinciple, DepotMode
        from balance_management.balance_manager import BalanceManager
        from balance_management.portfolio_manager import PortfolioManager
        from tax_rules.tax_rule_factory import TaxRuleFactory
        
        # Create custom configuration
        tax_config = TaxCalculationConfig(
            tax_year=tax_year,
            country=country,
            fiat_currency=fiat_currency,
            multi_depot=multi_depot,
            principle=principle,
            calculate_unrealized_gains=True
        )
        
        # Create balance configuration
        balance_config = BalanceConfig(
            principle=BalancingPrinciple.FIFO if principle == core.Principle.FIFO else BalancingPrinciple.LIFO,
            depot_mode=DepotMode.MULTI if multi_depot else DepotMode.SINGLE,
            fiat_currency=fiat_currency
        )
        
        # Create services
        portfolio_manager = PortfolioManager(balance_config)
        balance_manager = BalanceManager(balance_config, portfolio_manager)
        tax_rules = TaxRuleFactory.create_tax_rules(country)
        price_service = get_default_price_service()
        
        return TaxCalculationService(
            config=tax_config,
            balance_manager=balance_manager,
            tax_rules=tax_rules,
            price_service=price_service
        )


def create_tax_service() -> TaxCalculationService:
    """
    Convenience function to create tax service from configuration.
    
    This provides a simple way to get a configured tax service
    without dealing with factory complexity.
    
    Returns:
        Configured TaxCalculationService
    """
    return TaxServiceFactory.create_from_config()


# Singleton instance for gradual migration
_tax_service_instance = None


def get_tax_service() -> TaxCalculationService:
    """Get singleton tax service instance (for gradual migration)."""
    global _tax_service_instance
    if _tax_service_instance is None:
        _tax_service_instance = create_tax_service()
    return _tax_service_instance