"""
Balance Management Service

Main service for managing coin balances, FIFO/LIFO cost basis calculation,
and coordination with portfolio tracking. Extracted from Taxman god class.
"""

import decimal
from typing import Dict, List, Optional, Any, Type
import datetime

import balance_queue
import transaction as tr
from .balance_config import BalanceConfig, BalanceKey, BalancingPrinciple
from .portfolio_manager import PortfolioManager


class BalanceManager:
    """
    Manages coin balances and cost basis calculations.
    
    This service handles:
    - FIFO/LIFO balance queues
    - Cost basis tracking
    - Fee removal from balances
    - Integration with portfolio management
    - Balance validation
    """
    
    def __init__(self, config: BalanceConfig, portfolio_manager: Optional[PortfolioManager] = None):
        self._config = config
        self._portfolio_manager = portfolio_manager or PortfolioManager(config)
        
        # Select appropriate balance queue implementation
        if config.principle == BalancingPrinciple.FIFO:
            self._BalanceType: Type[balance_queue.BalanceQueue] = balance_queue.BalanceFIFOQueue
        else:
            self._BalanceType = balance_queue.BalanceLIFOQueue
        
        # Balance queues indexed by balance key
        self._balances: Dict[BalanceKey, balance_queue.BalanceQueue] = {}
    
    @property
    def portfolio_manager(self) -> PortfolioManager:
        """Access to portfolio manager."""
        return self._portfolio_manager
    
    def get_balance(self, platform: str, coin: str) -> balance_queue.BalanceQueue:
        """Get balance queue for platform/coin combination."""
        key = BalanceKey.create(platform, coin, self._config.depot_mode)
        
        if key not in self._balances:
            self._balances[key] = self._BalanceType(coin)
        
        return self._balances[key]
    
    def get_balance_for_operation(self, op: tr.Operation) -> balance_queue.BalanceQueue:
        """Get balance queue for an operation."""
        return self.get_balance(op.platform, op.coin)
    
    def add_to_balance(self, op: tr.Operation) -> None:
        """
        Add operation to balance queue.
        
        This adds coins to the balance tracking system, updating both
        the balance queue and portfolio positions.
        """
        balance = self.get_balance_for_operation(op)
        balance.add(op)
        
        # Update portfolio
        self._portfolio_manager.add_to_portfolio(op.platform, op.coin, op.change)
    
    def remove_from_balance(self, op: tr.Operation) -> List[tr.SoldCoin]:
        """
        Remove coins from balance queue and return sold coin details.
        
        This handles FIFO/LIFO cost basis calculation by tracking which
        specific purchase operations the sold coins came from.
        
        Returns:
            List of SoldCoin objects tracking the cost basis
        """
        balance = self.get_balance_for_operation(op)
        sold_coins = balance.remove(op)
        
        # Update portfolio
        self._portfolio_manager.remove_from_portfolio(op.platform, op.coin, op.change)
        
        return sold_coins
    
    def remove_fees_from_balance(self, fees: Optional[List[tr.Fee]]) -> None:
        """Remove fees from relevant balance queues."""
        if not fees:
            return
        
        for fee in fees:
            balance = self.get_balance(fee.platform, fee.coin)
            balance.remove(fee)
            
            # Update portfolio
            self._portfolio_manager.remove_from_portfolio(fee.platform, fee.coin, fee.change)
    
    def get_balance_amount(self, platform: str, coin: str) -> decimal.Decimal:
        """Get current balance amount for platform/coin."""
        balance = self.get_balance(platform, coin)
        # Calculate total amount from queue
        total = decimal.Decimal('0')
        for bop in balance.queue:
            total += bop.not_sold
        return total
    
    def get_all_balances(self) -> Dict[BalanceKey, decimal.Decimal]:
        """Get all current balance amounts."""
        result = {}
        for key, balance in self._balances.items():
            total = sum(bop.not_sold for bop in balance.queue)
            if total > 0:
                result[key] = total
        return result
    
    def validate_balances(self) -> List[str]:
        """
        Validate all balances and return any issues found.
        
        Returns:
            List of validation error messages
        """
        issues = []
        
        for key, balance in self._balances.items():
            try:
                balance.sanity_check()
            except Exception as e:
                issues.append(f"Balance validation error for {key}: {e}")
        
        # Also validate portfolio consistency
        portfolio_issues = self._portfolio_manager.validate_portfolio()
        issues.extend(portfolio_issues)
        
        return issues
    
    def get_remaining_coins_summary(self) -> List[Dict[str, Any]]:
        """Get summary of all remaining coins across balances."""
        summary = []
        
        for key, balance in self._balances.items():
            remaining = sum(bop.not_sold for bop in balance.queue)
            if remaining > 0:
                summary.append({
                    'platform': key.platform,
                    'coin': key.coin,
                    'amount': remaining,
                    'balance_key': str(key)
                })
        
        return summary
    
    def process_operation(self, op: tr.Operation) -> Optional[List[tr.SoldCoin]]:
        """
        Process an operation through the balance system.
        
        This is the main entry point for updating balances based on operations.
        It determines whether to add or remove coins and handles the operation appropriately.
        
        Returns:
            List of SoldCoin objects if coins were sold, None otherwise
        """
        if isinstance(op, (tr.Buy, tr.Deposit, tr.CoinLendEnd)):
            # Operations that add coins
            self.add_to_balance(op)
            return None
            
        elif isinstance(op, (tr.Sell, tr.Withdrawal, tr.CoinLend)):
            # Operations that remove coins
            return self.remove_from_balance(op)
            
        elif isinstance(op, tr.Fee):
            # Fees are handled separately
            self.remove_fees_from_balance([op])
            return None
            
        else:
            # Unknown operation type - log but don't process
            return None
    
    def create_balance_snapshot(self, timestamp: datetime.datetime = None) -> Dict[str, Any]:
        """Create a snapshot of current balance state."""
        if timestamp is None:
            timestamp = datetime.datetime.now()
        
        return {
            'timestamp': timestamp,
            'config': {
                'principle': self._config.principle.value,
                'depot_mode': self._config.depot_mode.value,
                'fiat_currency': self._config.fiat_currency
            },
            'balances': {
                str(key): {
                    'amount': sum(bop.not_sold for bop in balance.queue),
                    'queue_length': len(balance.queue) if hasattr(balance, 'queue') else 0
                }
                for key, balance in self._balances.items()
            },
            'portfolio_snapshot': self._portfolio_manager.create_snapshot(timestamp),
            'validation_issues': self.validate_balances()
        }


def create_balance_manager_from_config() -> BalanceManager:
    """Create BalanceManager using global CoinTaxman configuration."""
    from .balance_config import BalanceConfig
    
    config = BalanceConfig.from_global_config()
    portfolio_manager = PortfolioManager(config)
    
    return BalanceManager(config, portfolio_manager)


# Backward compatibility helper functions for gradual migration
def get_balance_manager() -> BalanceManager:
    """Get singleton balance manager instance (for gradual migration)."""
    global _balance_manager_instance
    if '_balance_manager_instance' not in globals():
        _balance_manager_instance = create_balance_manager_from_config()
    return _balance_manager_instance


def extract_balance_data_from_taxman(taxman_instance) -> Dict[str, Any]:
    """
    Extract balance data from existing Taxman instance.
    
    This helper function supports gradual migration by extracting
    balance state from the existing god class.
    """
    return {
        'balances': getattr(taxman_instance, '_balances', {}),
        'single_depot_portfolio': getattr(taxman_instance, 'single_depot_portfolio', {}),
        'multi_depot_portfolio': getattr(taxman_instance, 'multi_depot_portfolio', {}),
        'balance_type': getattr(taxman_instance, 'BalanceType', None)
    }