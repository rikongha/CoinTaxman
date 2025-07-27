"""
Balance Management Configuration

Defines configuration classes and enums for balance tracking behavior.
Extracted from global config dependencies to enable dependency injection.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class BalancingPrinciple(Enum):
    """Cost basis calculation method."""
    FIFO = "FIFO"  # First In, First Out
    LIFO = "LIFO"  # Last In, First Out


class DepotMode(Enum):
    """Portfolio tracking mode."""
    SINGLE = "SINGLE"  # Track all platforms together
    MULTI = "MULTI"   # Track each platform separately


@dataclass(frozen=True)
class BalanceKey:
    """Key for identifying unique balance queues."""
    platform: Optional[str]
    coin: str
    
    @classmethod
    def create(cls, platform: str, coin: str, depot_mode: DepotMode) -> 'BalanceKey':
        """Create balance key based on depot mode."""
        return cls(
            platform=platform if depot_mode == DepotMode.MULTI else None,
            coin=coin.upper()
        )
    
    def __str__(self) -> str:
        if self.platform:
            return f"{self.platform}:{self.coin}"
        return self.coin


@dataclass
class BalanceConfig:
    """Configuration for balance management."""
    principle: BalancingPrinciple
    depot_mode: DepotMode
    fiat_currency: str
    
    @classmethod
    def from_global_config(cls) -> 'BalanceConfig':
        """Create config from global CoinTaxman configuration."""
        import config
        import core
        
        # Map global config to enum values
        principle_map = {
            core.Principle.FIFO: BalancingPrinciple.FIFO,
            core.Principle.LIFO: BalancingPrinciple.LIFO
        }
        
        return cls(
            principle=principle_map.get(config.PRINCIPLE, BalancingPrinciple.FIFO),
            depot_mode=DepotMode.MULTI if getattr(config, 'MULTI_DEPOT', False) else DepotMode.SINGLE,
            fiat_currency=getattr(config, 'FIAT_CURRENCY', 'EUR')
        )