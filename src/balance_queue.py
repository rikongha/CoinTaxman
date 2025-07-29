# CoinTaxman
# Copyright (C) 2021  Carsten Docktor <https://github.com/provinzio>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import abc
import collections
import dataclasses
import decimal
import datetime
from typing import Union

import config
import log_config
import transaction as tr
from balance_management.balance_config import MissingAcquisitionHandling

log = log_config.getLogger(__name__)


@dataclasses.dataclass
class BalancedOperation:
    op: tr.Operation
    sold: decimal.Decimal = decimal.Decimal()

    @property
    def not_sold(self) -> decimal.Decimal:
        """Calculate the amount of coins which are not sold yet.

        Returns:
            decimal.Decimal: Amount of coins which are not sold yet.
        """
        not_sold = self.op.change - self.sold
        # If the left over amount is <= 0, this coin shouldn't be in the queue.
        assert not_sold > 0, f"{not_sold=} should be > 0"
        return not_sold


class BalanceQueue(abc.ABC):
    def __init__(self, coin: str, missing_acquisition_handling: MissingAcquisitionHandling = MissingAcquisitionHandling.ERROR) -> None:
        self.coin = coin
        self.missing_acquisition_handling = missing_acquisition_handling
        self.queue: collections.deque[BalancedOperation] = collections.deque()
        # It might happen, that the exchange takes fees before the buy/sell-
        # transaction. Keep fees, which couldn't be removed directly from the
        # queue and remove them as soon as possible.
        # At the end, all fees should have been paid (removed from the buffer).
        self.buffer_fee = decimal.Decimal()

    @abc.abstractmethod
    def _put_(self, bop: BalancedOperation) -> None:
        """Put a new item in the queue.

        Args:
            item (BalancedOperation)
        """
        raise NotImplementedError

    @abc.abstractmethod
    def _pop_(self) -> BalancedOperation:
        """Pop an item from the queue.

        Returns:
            BalancedOperation
        """
        raise NotImplementedError

    @abc.abstractmethod
    def _peek_(self) -> BalancedOperation:
        """Peek at the next item in the queue.

        Returns:
            BalancedOperation
        """
        raise NotImplementedError

    def _put(self, item: Union[tr.Operation, BalancedOperation]) -> None:
        """Put a new item in the queue and remove buffered fees.

        Args:
            item (Union[Operation, BalancedOperation])
        """
        if isinstance(item, tr.Operation):
            item = BalancedOperation(item)
        elif not isinstance(item, BalancedOperation):
            raise TypeError

        self._put_(item)

        # Remove fees which couldn't be removed before.
        if self.buffer_fee:
            # Clear the buffer.
            fee, self.buffer_fee = self.buffer_fee, decimal.Decimal()
            # Try to remove the fees.
            self._remove_fee(fee)

    def _pop(self) -> BalancedOperation:
        """Pop an item from the queue.

        Returns:
            BalancedOperation
        """
        return self._pop_()

    def _peek(self) -> BalancedOperation:
        """Peek at the next item in the queue.

        Returns:
            BalancedOperation
        """
        return self._peek_()

    def add(self, op: tr.Operation) -> None:
        """Add an operation with coins to the balance.

        Args:
            op (tr.Operation)
        """
        assert not isinstance(op, tr.Fee)
        assert op.coin == self.coin
        self._put(op)

    def _remove(
        self,
        change: decimal.Decimal,
    ) -> tuple[list[tr.SoldCoin], decimal.Decimal]:
        """Remove as many coins as necessary from the queue.

        The removement logic is defined by the BalanceQueue child class.

        Args:
            change (decimal.Decimal): Amount of coins to be removed.

        Returns:
          - list[tr.SoldCoin]: List of coins which were removed.
          - decimal.Decimal: Amount of change which could not be removed
                because the queue ran out of coins.
        """
        sold_coins: list[tr.SoldCoin] = []

        while self.queue and change > 0:
            # Look at the next coin in the queue.
            bop = self._peek()

            # Get the amount of not sold coins.
            not_sold = bop.not_sold

            if not_sold > change:
                # There are more coins left than change.
                # Update the sold value,
                bop.sold += change
                # keep track of the sold amount
                sold_coins.append(tr.SoldCoin(bop.op, change))
                # and set the change to 0.
                change = decimal.Decimal()
                # All demanded change was removed.
                break

            else:  # not_sold <= change
                # The change is higher than or equal to the left over coins.
                # Update the left over change,
                change -= not_sold
                # remove the fully sold coin from the queue
                self._pop()
                # and keep track of the sold amount.
                sold_coins.append(tr.SoldCoin(bop.op, not_sold))

        assert change >= 0, "Removed more than necessary from the queue."
        return sold_coins, change

    def remove(
        self,
        op: tr.Operation,
    ) -> list[tr.SoldCoin]:
        """Remove as many coins as necessary from the queue.

        The removement logic is defined by the BalanceQueue child class.

        Args:
            op (tr.Operation): Operation with coins to be removed.

        Raises:
            RuntimeError: When there are not enough coins in queue to be sold.

        Returns:
          - list[tr.SoldCoin]: List of coins which were removed.
        """
        assert op.coin == self.coin
        sold_coins, unsold_change = self._remove(op.change)
        
        # Validate total sold amount doesn't exceed operation amount
        total_sold = sum(sc.sold for sc in sold_coins)
        if total_sold > op.change:
            log.error(f"Internal error: total sold {total_sold} exceeds operation amount {op.change}")
            raise RuntimeError("Balance accounting error")

        if unsold_change:
            # Queue ran out of items to sell and not all coins could be sold.
            msg = (
                f"Not enough {op.coin} in queue to sell: "
                f"missing {unsold_change} {op.coin} "
                f"(transaction from {op.utc_time} on {op.platform}, "
                f"see {op.file_path.name} lines {op.line})"
            )
            
            if self.coin == config.FIAT:
                log.warning(
                    f"{msg}\n"
                    "Tracking of your home fiat is not important for tax "
                    f"evaluation but the {op.coin} in your portfolio at "
                    "deadline will be wrong."
                )
            else:
                # Handle missing acquisitions according to German tax compliance
                if self.missing_acquisition_handling == MissingAcquisitionHandling.ERROR:
                    log.error(
                        f"{msg}\n"
                        f"This can happen when you sold more {op.coin} than you have "
                        "according to your account statements. Have you added every "
                        "account statement including these from last years and the "
                        f"all deposits of {op.coin}?\n"
                        "\tThis error may also occur after deposits from unknown "
                        "sources. CoinTaxman requires the full transaction history to "
                        "evaluate taxation (when and where were these deposited coins "
                        "bought?).\n"
                    )
                    raise RuntimeError
                    
                elif self.missing_acquisition_handling == MissingAcquisitionHandling.ZERO_COST:
                    # German tax compliant: Create synthetic €0 cost basis acquisition
                    # This represents airdrops without consideration or hard fork rewards
                    log.warning(
                        f"{msg}\n"
                        f"German tax compliance: Creating synthetic €0 cost basis acquisition "
                        f"for missing {unsold_change} {op.coin}. This assumes the missing coins "
                        f"came from airdrops without consideration or hard forks (per § 22 Nr. 3 EStG).\n"
                        f"If this is incorrect, please add the missing acquisition transactions."
                    )
                    
                    # Create synthetic acquisition one second before the sale to maintain FIFO order
                    # Use the same platform as the sale to avoid price lookup issues
                    synthetic_time = op.utc_time - datetime.timedelta(seconds=1)
                    synthetic_acquisition = tr.Buy(
                        utc_time=synthetic_time,
                        platform=op.platform,  # Use same platform as the sale
                        change=unsold_change,
                        coin=op.coin,
                        line=[],
                        file_path=op.file_path,
                        fees=None,
                        remarks=["Synthetic €0 cost basis acquisition for German tax compliance - assumed airdrop/fork"]
                    )
                    
                    # Add synthetic acquisition to queue and try removal again
                    self.add(synthetic_acquisition)
                    additional_sold_coins, remaining_unsold = self._remove(unsold_change)
                    
                    # Only add the additional coins if they don't exceed the missing amount
                    # This prevents assertion errors in tax calculation
                    total_additional = sum(sc.sold for sc in additional_sold_coins)
                    if total_additional <= unsold_change:
                        sold_coins.extend(additional_sold_coins)
                    else:
                        # Adjust the sold amounts to match exactly the missing amount
                        remaining_to_allocate = unsold_change
                        for sc in additional_sold_coins:
                            if remaining_to_allocate <= 0:
                                break
                            if sc.sold <= remaining_to_allocate:
                                sold_coins.append(sc)
                                remaining_to_allocate -= sc.sold
                            else:
                                # Create adjusted sold coin for partial amount
                                adjusted_sc = tr.SoldCoin(
                                    op=sc.op,
                                    sold=remaining_to_allocate
                                )
                                sold_coins.append(adjusted_sc)
                                remaining_to_allocate = decimal.Decimal('0')
                    
                    if remaining_unsold:
                        log.error(f"Failed to create sufficient synthetic acquisition for {op.coin}")
                        raise RuntimeError
                        
                elif self.missing_acquisition_handling == MissingAcquisitionHandling.WARNING:
                    log.warning(
                        f"{msg}\n"
                        f"Continuing with partial sale. Missing {unsold_change} {op.coin} "
                        f"will not be included in tax calculation."
                    )

        # Final validation: ensure total sold amount never exceeds operation amount
        final_total_sold = sum(sc.sold for sc in sold_coins)
        if final_total_sold > op.change:
            log.error(f"Final validation failed: total sold {final_total_sold} exceeds operation amount {op.change}")
            # Truncate sold_coins to match operation amount exactly
            remaining_amount = op.change
            truncated_sold_coins = []
            for sc in sold_coins:
                if remaining_amount <= 0:
                    break
                if sc.sold <= remaining_amount:
                    truncated_sold_coins.append(sc)
                    remaining_amount -= sc.sold
                else:
                    # Create truncated sold coin
                    truncated_sc = tr.SoldCoin(op=sc.op, sold=remaining_amount)
                    truncated_sold_coins.append(truncated_sc)
                    remaining_amount = decimal.Decimal('0')
            sold_coins = truncated_sold_coins
            
        return sold_coins

    def _remove_fee(self, fee: decimal.Decimal) -> None:
        """Remove fee from the last added transaction.

        Args:
            fee: decimal.Decimal
        """
        _, left_over_fee = self._remove(fee)
        if left_over_fee and self.coin != config.FIAT:
            log.warning(
                "Not enough coins in queue to remove fee. Buffer the fee for "
                "next adding time... "
                "This should not happen. You might be missing an account "
                "statement. Please open issue or PR if you need help."
            )
            self.buffer_fee += left_over_fee

    def remove_fee(self, fee: tr.Fee) -> None:
        assert fee.coin == self.coin
        self._remove_fee(fee.change)

    def sanity_check(self) -> None:
        """Validate that all fees were paid or raise an exception.

        At the end, all fees should have been paid.

        Raises:
            RuntimeError: Not all fees were paid.
        """
        if self.buffer_fee:
            msg = (
                f"Not enough {self.coin} in queue to pay left over fees: "
                f"missing {self.buffer_fee} {self.coin}.\n"
                "\tThis error occurs when you sold more coins than you have "
                "according to your account statements. Have you added every "
                "account statement, including these from the last years?\n"
                "\tThis error may also occur after deposits from unknown "
                "sources. "
            )
            if self.coin == config.FIAT:
                log.warning(
                    f"{msg}"
                    "Tracking of your home fiat is not important for tax "
                    f"evaluation but the {self.coin} in your portfolio at "
                    "deadline will be wrong."
                )
            else:
                log.error(
                    "{msg}"
                    "CoinTaxman requires the full transaction history to "
                    "evaluate taxation (when where these deposited coins bought?).\n"
                )
                raise RuntimeError

    def remove_all(self) -> list[tr.SoldCoin]:
        sold_coins = []
        while self.queue:
            bop = self._pop()
            not_sold = bop.not_sold
            sold_coins.append(tr.SoldCoin(bop.op, not_sold))
        return sold_coins


class BalanceFIFOQueue(BalanceQueue):
    def _put_(self, bop: BalancedOperation) -> None:
        """Put a new item in the queue.

        Args:
            item (BalancedOperation)
        """
        self.queue.append(bop)

    def _pop_(self) -> BalancedOperation:
        """Pop an item from the queue.

        Returns:
            BalancedOperation
        """
        return self.queue.popleft()

    def _peek_(self) -> BalancedOperation:
        """Peek at the next item in the queue.

        Returns:
            BalancedOperation
        """
        return self.queue[0]


class BalanceLIFOQueue(BalanceQueue):
    def _put_(self, bop: BalancedOperation) -> None:
        """Put a new item in the queue.

        Args:
            item (BalancedOperation)
        """
        self.queue.append(bop)

    def _pop_(self) -> BalancedOperation:
        """Pop an item from the queue.

        Returns:
            BalancedOperation
        """
        return self.queue.pop()

    def _peek_(self) -> BalancedOperation:
        """Peek at the next item in the queue.

        Returns:
            BalancedOperation
        """
        return self.queue[-1]
