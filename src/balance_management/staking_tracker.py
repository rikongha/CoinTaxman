"""
Staking and Lending Tracker

Tracks coins that are currently staked or lent out to prevent them from 
being sold in FIFO calculations until they are returned.
"""

import datetime
import decimal
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import transaction as tr


@dataclass
class StakedCoin:
    """Represents a coin that is currently staked or lent."""
    operation: tr.Operation  # The original Buy/Deposit operation
    amount: decimal.Decimal
    coin: str
    platform: str
    start_time: datetime.datetime
    stake_type: str  # 'staking' or 'lending'
    
    def __post_init__(self):
        if self.amount <= 0:
            raise ValueError("Staked amount must be positive")


@dataclass 
class StakingContract:
    """Represents an active staking/lending contract."""
    contract_id: str
    coin: str
    platform: str
    total_amount: decimal.Decimal
    start_operation: tr.Operation  # CoinLend or Staking operation
    staked_coins: List[StakedCoin] = field(default_factory=list)
    is_active: bool = True
    
    def add_staked_coin(self, coin: StakedCoin):
        """Add a coin to this staking contract."""
        if coin.coin != self.coin or coin.platform != self.platform:
            raise ValueError("Coin must match contract coin and platform")
        self.staked_coins.append(coin)
    
    def get_total_staked(self) -> decimal.Decimal:
        """Get total amount currently staked in this contract."""
        return sum(sc.amount for sc in self.staked_coins)


class StakingTracker:
    """
    Tracks staked and lent coins to prevent them from being sold.
    
    This is critical for accurate FIFO calculations under German tax law,
    as staked/lent coins should not be available for selling until returned.
    """
    
    def __init__(self):
        # Platform -> Coin -> List of active contracts
        self._active_contracts: Dict[str, Dict[str, List[StakingContract]]] = defaultdict(lambda: defaultdict(list))
        
        # Track contract IDs to prevent duplicates
        self._contract_counter = 0
        
        # Cache for performance
        self._staked_amounts_cache: Optional[Dict[Tuple[str, str], decimal.Decimal]] = None
        
    def _generate_contract_id(self, operation: tr.Operation) -> str:
        """Generate a unique contract ID."""
        self._contract_counter += 1
        return f"{operation.platform}_{operation.coin}_{operation.utc_time.isoformat()}_{self._contract_counter}"
    
    def _invalidate_cache(self):
        """Invalidate the staked amounts cache."""
        self._staked_amounts_cache = None
    
    def start_staking_contract(self, 
                             start_operation: tr.Operation,
                             available_coins: List[tr.SoldCoin]) -> str:
        """
        Start a new staking/lending contract.
        
        Args:
            start_operation: The CoinLend or Staking operation
            available_coins: List of coins available to be staked (from FIFO)
            
        Returns:
            Contract ID
        """
        if not isinstance(start_operation, (tr.CoinLend, tr.Staking)):
            raise ValueError("Operation must be CoinLend or Staking")
            
        # Generate contract ID
        contract_id = self._generate_contract_id(start_operation)
        
        # Determine stake type
        stake_type = 'lending' if isinstance(start_operation, tr.CoinLend) else 'staking'
        
        # Create contract
        contract = StakingContract(
            contract_id=contract_id,
            coin=start_operation.coin,
            platform=start_operation.platform,
            total_amount=abs(start_operation.change),
            start_operation=start_operation
        )
        
        # Allocate coins to this contract using FIFO
        remaining_to_stake = abs(start_operation.change)
        
        for sold_coin in available_coins:
            if remaining_to_stake <= 0:
                break
                
            if sold_coin.op.coin != start_operation.coin:
                continue
                
            # Take as much as needed from this coin
            amount_to_stake = min(remaining_to_stake, sold_coin.sold)
            
            if amount_to_stake > 0:
                staked_coin = StakedCoin(
                    operation=sold_coin.op,
                    amount=amount_to_stake,
                    coin=start_operation.coin,
                    platform=start_operation.platform,
                    start_time=start_operation.utc_time,
                    stake_type=stake_type
                )
                
                contract.add_staked_coin(staked_coin)
                remaining_to_stake -= amount_to_stake
        
        if remaining_to_stake > 0:
            raise ValueError(f"Insufficient coins available for staking. Missing: {remaining_to_stake}")
        
        # Store contract
        self._active_contracts[start_operation.platform][start_operation.coin].append(contract)
        self._invalidate_cache()
        
        return contract_id
    
    def end_staking_contract(self, 
                           end_operation: tr.Operation,
                           contract_id: Optional[str] = None) -> List[StakedCoin]:
        """
        End a staking/lending contract and return the staked coins.
        
        Args:
            end_operation: The CoinLendEnd or StakingEnd operation
            contract_id: Specific contract to end (if None, uses FIFO)
            
        Returns:
            List of coins that were returned from staking
        """
        if not isinstance(end_operation, (tr.CoinLendEnd, tr.StakingEnd)):
            raise ValueError("Operation must be CoinLendEnd or StakingEnd")
        
        platform_contracts = self._active_contracts[end_operation.platform][end_operation.coin]
        
        if not platform_contracts:
            raise ValueError(f"No active staking contracts found for {end_operation.coin} on {end_operation.platform}")
        
        # Find contract to end
        contract_to_end = None
        if contract_id:
            # Find specific contract
            for contract in platform_contracts:
                if contract.contract_id == contract_id:
                    contract_to_end = contract
                    break
            if not contract_to_end:
                raise ValueError(f"Contract {contract_id} not found")
        else:
            # Use FIFO - end oldest contract first
            contract_to_end = min(platform_contracts, key=lambda c: c.start_operation.utc_time)
        
        # Verify amounts match (within reasonable tolerance)
        end_amount = abs(end_operation.change)
        staked_amount = contract_to_end.get_total_staked()
        
        if abs(end_amount - staked_amount) > decimal.Decimal('0.00000001'):
            raise ValueError(f"End amount {end_amount} doesn't match staked amount {staked_amount}")
        
        # Mark contract as ended and get returned coins
        contract_to_end.is_active = False
        returned_coins = contract_to_end.staked_coins.copy()
        
        # Remove from active contracts
        platform_contracts.remove(contract_to_end)
        self._invalidate_cache()
        
        return returned_coins
    
    def get_staked_amount(self, platform: str, coin: str) -> decimal.Decimal:
        """Get total amount of coin currently staked on platform."""
        if self._staked_amounts_cache is None:
            self._rebuild_cache()
        
        return self._staked_amounts_cache.get((platform, coin), decimal.Decimal('0'))
    
    def _rebuild_cache(self):
        """Rebuild the staked amounts cache."""
        cache = {}
        
        for platform, coin_contracts in self._active_contracts.items():
            for coin, contracts in coin_contracts.items():
                total_staked = sum(
                    contract.get_total_staked() 
                    for contract in contracts 
                    if contract.is_active
                )
                if total_staked > 0:
                    cache[(platform, coin)] = total_staked
        
        self._staked_amounts_cache = cache
    
    def is_coin_staked(self, platform: str, coin: str, operation: tr.Operation) -> bool:
        """Check if a specific coin purchase is currently staked."""
        for contracts in self._active_contracts[platform][coin]:
            if not contracts.is_active:
                continue
            for staked_coin in contracts.staked_coins:
                if staked_coin.operation == operation:
                    return True
        return False
    
    def get_available_amount(self, platform: str, coin: str, operation: tr.Operation) -> decimal.Decimal:
        """Get how much of a specific coin purchase is available (not staked)."""
        total_in_operation = abs(operation.change)
        
        staked_amount = decimal.Decimal('0')
        for contracts in self._active_contracts[platform][coin]:
            if not contracts.is_active:
                continue
            for staked_coin in contracts.staked_coins:
                if staked_coin.operation == operation:
                    staked_amount += staked_coin.amount
        
        return max(decimal.Decimal('0'), total_in_operation - staked_amount)
    
    def get_active_contracts(self, platform: Optional[str] = None, coin: Optional[str] = None) -> List[StakingContract]:
        """Get list of active staking contracts, optionally filtered."""
        contracts = []
        
        for plat, coin_contracts in self._active_contracts.items():
            if platform and plat != platform:
                continue
            for c, contract_list in coin_contracts.items():
                if coin and c != coin:
                    continue
                contracts.extend([contract for contract in contract_list if contract.is_active])
        
        return contracts
    
    def get_staking_summary(self) -> Dict[str, Dict[str, decimal.Decimal]]:
        """Get summary of all active staking by platform and coin."""
        summary = defaultdict(lambda: defaultdict(decimal.Decimal))
        
        for platform, coin_contracts in self._active_contracts.items():
            for coin, contracts in coin_contracts.items():
                total = sum(
                    contract.get_total_staked() 
                    for contract in contracts 
                    if contract.is_active
                )
                if total > 0:
                    summary[platform][coin] = total
        
        return dict(summary)

    def clear_ended_contracts(self):
        """Clean up ended contracts to save memory."""
        for platform in list(self._active_contracts.keys()):
            for coin in list(self._active_contracts[platform].keys()):
                # Keep only active contracts
                self._active_contracts[platform][coin] = [
                    contract for contract in self._active_contracts[platform][coin]
                    if contract.is_active
                ]
                # Remove empty coin entries
                if not self._active_contracts[platform][coin]:
                    del self._active_contracts[platform][coin]
            # Remove empty platform entries
            if not self._active_contracts[platform]:
                del self._active_contracts[platform]
        
        self._invalidate_cache()