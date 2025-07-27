"""
Portfolio Management Service

Handles portfolio tracking, position management, and unrealized gains calculation.
Extracted from Taxman class to separate portfolio concerns from tax calculation.
"""

import collections
import decimal
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import datetime

import transaction as tr
from .balance_config import BalanceConfig, DepotMode


@dataclass
class PortfolioPosition:
    """Represents a coin position in the portfolio."""
    platform: str
    coin: str
    amount: decimal.Decimal
    average_cost: Optional[decimal.Decimal] = None
    
    @property
    def value_at_cost(self) -> Optional[decimal.Decimal]:
        """Calculate position value at average cost."""
        if self.average_cost is not None:
            return self.amount * self.average_cost
        return None


@dataclass
class PortfolioSnapshot:
    """Snapshot of portfolio state at a point in time."""
    timestamp: datetime.datetime
    positions: List[PortfolioPosition]
    total_value: Optional[decimal.Decimal] = None
    
    def get_position(self, platform: str, coin: str) -> Optional[PortfolioPosition]:
        """Get specific position by platform and coin."""
        for position in self.positions:
            if position.platform == platform and position.coin == coin:
                return position
        return None


class PortfolioManager:
    """
    Manages portfolio positions and tracks holdings across platforms.
    
    This service handles:
    - Current portfolio positions
    - Multi-depot vs single-depot tracking
    - Portfolio value calculations
    - Position updates from transactions
    """
    
    def __init__(self, config: BalanceConfig):
        self._config = config
        
        # Portfolio tracking based on configuration
        if config.depot_mode == DepotMode.MULTI:
            self._multi_depot_portfolio: Dict[str, Dict[str, decimal.Decimal]] = collections.defaultdict(
                lambda: collections.defaultdict(decimal.Decimal)
            )
        else:
            self._single_depot_portfolio: Dict[str, decimal.Decimal] = collections.defaultdict(decimal.Decimal)
    
    def add_to_portfolio(self, platform: str, coin: str, amount: decimal.Decimal) -> None:
        """Add amount to portfolio position."""
        if self._config.depot_mode == DepotMode.MULTI:
            self._multi_depot_portfolio[platform][coin] += amount
        else:
            self._single_depot_portfolio[coin] += amount
    
    def remove_from_portfolio(self, platform: str, coin: str, amount: decimal.Decimal) -> None:
        """Remove amount from portfolio position."""
        if self._config.depot_mode == DepotMode.MULTI:
            self._multi_depot_portfolio[platform][coin] -= amount
            # Clean up zero positions
            if self._multi_depot_portfolio[platform][coin] == 0:
                del self._multi_depot_portfolio[platform][coin]
        else:
            self._single_depot_portfolio[coin] -= amount
            # Clean up zero positions
            if self._single_depot_portfolio[coin] == 0:
                del self._single_depot_portfolio[coin]
    
    def get_position(self, platform: str, coin: str) -> decimal.Decimal:
        """Get current position amount for platform/coin."""
        if self._config.depot_mode == DepotMode.MULTI:
            return self._multi_depot_portfolio[platform][coin]
        else:
            return self._single_depot_portfolio[coin]
    
    def get_all_positions(self) -> List[PortfolioPosition]:
        """Get all current portfolio positions."""
        positions = []
        
        if self._config.depot_mode == DepotMode.MULTI:
            for platform, coins in self._multi_depot_portfolio.items():
                for coin, amount in coins.items():
                    if amount > 0:
                        positions.append(PortfolioPosition(
                            platform=platform,
                            coin=coin,
                            amount=amount
                        ))
        else:
            for coin, amount in self._single_depot_portfolio.items():
                if amount > 0:
                    positions.append(PortfolioPosition(
                        platform="All",
                        coin=coin,
                        amount=amount
                    ))
        
        return positions
    
    def get_portfolio_summary(self) -> Dict[str, any]:
        """Get portfolio summary statistics."""
        positions = self.get_all_positions()
        
        summary = {
            'total_positions': len(positions),
            'unique_coins': len(set(pos.coin for pos in positions)),
            'depot_mode': self._config.depot_mode.value,
            'positions_by_coin': collections.defaultdict(list)
        }
        
        # Group positions by coin
        for position in positions:
            summary['positions_by_coin'][position.coin].append({
                'platform': position.platform,
                'amount': position.amount
            })
        
        return summary
    
    def create_snapshot(self, timestamp: datetime.datetime = None) -> PortfolioSnapshot:
        """Create a snapshot of current portfolio state."""
        if timestamp is None:
            timestamp = datetime.datetime.now()
        
        positions = self.get_all_positions()
        
        return PortfolioSnapshot(
            timestamp=timestamp,
            positions=positions
        )
    
    def update_from_operation(self, op: tr.Operation) -> None:
        """Update portfolio based on an operation."""
        if isinstance(op, (tr.Buy, tr.Deposit, tr.CoinLendEnd, tr.StakingEnd)):
            # Operations that add coins to portfolio
            self.add_to_portfolio(op.platform, op.coin, op.change)
            
        elif isinstance(op, (tr.Sell, tr.Withdrawal, tr.CoinLendStart, tr.StakingStart)):
            # Operations that remove coins from portfolio
            self.remove_from_portfolio(op.platform, op.coin, op.change)
            
        elif isinstance(op, tr.Fee):
            # Fees remove coins from portfolio
            self.remove_from_portfolio(op.platform, op.coin, op.change)
    
    def validate_portfolio(self) -> List[str]:
        """Validate portfolio state and return any issues."""
        issues = []
        
        for position in self.get_all_positions():
            if position.amount < 0:
                issues.append(f"Negative position: {position.platform}:{position.coin} = {position.amount}")
            
            if position.amount == 0:
                issues.append(f"Zero position should be cleaned up: {position.platform}:{position.coin}")
        
        return issues
    
    # Backward compatibility properties for gradual migration
    @property
    def single_depot_portfolio(self) -> Dict[str, decimal.Decimal]:
        """Backward compatibility: access single depot portfolio."""
        if self._config.depot_mode == DepotMode.SINGLE:
            return dict(self._single_depot_portfolio)
        else:
            # Aggregate multi-depot into single view
            aggregated = collections.defaultdict(decimal.Decimal)
            for platform_coins in self._multi_depot_portfolio.values():
                for coin, amount in platform_coins.items():
                    aggregated[coin] += amount
            return dict(aggregated)
    
    @property 
    def multi_depot_portfolio(self) -> Dict[str, Dict[str, decimal.Decimal]]:
        """Backward compatibility: access multi depot portfolio."""
        if self._config.depot_mode == DepotMode.MULTI:
            # Convert defaultdict to regular dict for external consumption
            return {
                platform: dict(coins) 
                for platform, coins in self._multi_depot_portfolio.items()
            }
        else:
            # Convert single depot to multi-depot view
            return {"All": self.single_depot_portfolio}