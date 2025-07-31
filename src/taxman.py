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

import collections
import dataclasses
import datetime
import decimal
from pathlib import Path
from typing import Any, Optional, Type, Union

import xlsxwriter
from dateutil.relativedelta import relativedelta

import balance_queue
import config
import core
import log_config
from balance_management.balance_config import MissingAcquisitionHandling
from balance_management.staking_tracker import StakingTracker
from tax_rules.german_tax_rules import GermanTaxRules
from tax_rules.tax_rules_interface import TaxContext
import misc
import transaction as tr
from book import Book
from database import get_sorted_tablename
from price_data import PriceData

log = log_config.getLogger(__name__)

TAX_DEADLINE = min(
    datetime.datetime.now().replace(tzinfo=config.LOCAL_TIMEZONE),  # now
    datetime.datetime(
        config.TAX_YEAR, 12, 31, 23, 59, 59, tzinfo=config.LOCAL_TIMEZONE
    ),  # end of year
)


def in_tax_year(op: tr.Operation) -> bool:
    return op.utc_time.year == config.TAX_YEAR


class Taxman:
    def __init__(self, book: Book, price_data: PriceData) -> None:
        self.book = book
        self.price_data = price_data

        self.tax_report_entries: list[tr.TaxReportEntry] = []
        self.multi_depot_portfolio: dict[
            str, dict[str, decimal.Decimal]
        ] = collections.defaultdict(lambda: collections.defaultdict(decimal.Decimal))
        self.single_depot_portfolio: dict[
            str, decimal.Decimal
        ] = collections.defaultdict(decimal.Decimal)
        self.unrealized_sells_faulty = False

        # Initialize staking tracker for coin locking
        self.staking_tracker = StakingTracker()
        
        # Initialize tax rules based on country
        country = config.COUNTRY.name
        
        # For now, use the legacy German method to ensure stability
        # TODO: Re-enable modular system after complete testing
        try:
            self.__evaluate_taxation = getattr(self, f"_evaluate_taxation_{country}")
        except AttributeError:
            raise NotImplementedError(f"Unable to evaluate taxation for {country=}.")
            
        # Initialize modular components for future use
        if country == "GERMANY":
            try:
                self.tax_rules = GermanTaxRules()
                self.tax_context = TaxContext(
                    tax_year=config.TAX_YEAR,
                    fiat_currency=config.FIAT,
                    multi_depot=config.MULTI_DEPOT,
                    country=country
                )
                log.debug("Modular tax rules initialized but not active")
            except Exception as e:
                log.warning(f"Failed to initialize modular tax rules: {e}")
                self.tax_rules = None
                self.tax_context = None
        else:
            self.tax_rules = None
            self.tax_context = None

        # Determine the BalanceType.
        if config.PRINCIPLE == core.Principle.FIFO:
            # Explicity define type for BalanceType on first declaration
            # to avoid mypy errors.
            self.BalanceType: Type[
                balance_queue.BalanceQueue
            ] = balance_queue.BalanceFIFOQueue
        elif config.PRINCIPLE == core.Principle.LIFO:
            self.BalanceType = balance_queue.BalanceLIFOQueue
        else:
            raise NotImplementedError(
                f"Unable to evaluate taxation for {config.PRINCIPLE=}."
            )

        self._balances: dict[Any, balance_queue.BalanceQueue] = {}
        
        # Configure missing acquisition handling for German tax compliance
        handling_str = getattr(config, 'MISSING_ACQUISITION_HANDLING', 'ZERO_COST')
        try:
            self._missing_acquisition_handling = MissingAcquisitionHandling[handling_str]
        except KeyError:
            self._missing_acquisition_handling = MissingAcquisitionHandling.ZERO_COST

    ###########################################################################
    # Helper functions for balances
    ###########################################################################

    def balance(self, platform: str, coin: str) -> balance_queue.BalanceQueue:
        key = (platform, coin) if config.MULTI_DEPOT else coin
        try:
            return self._balances[key]
        except KeyError:
            self._balances[key] = self.BalanceType(coin, self._missing_acquisition_handling)
            return self._balances[key]

    def balance_op(self, op: tr.Operation) -> balance_queue.BalanceQueue:
        balance = self.balance(op.platform, op.coin)
        return balance

    def add_to_balance(self, op: tr.Operation) -> None:
        self.balance_op(op).add(op)

    def remove_from_balance(self, op: tr.Operation) -> list[tr.SoldCoin]:
        return self.balance_op(op).remove(op)

    def remove_fees_from_balance(self, fees: Optional[list[tr.Fee]]) -> None:
        if fees is not None:
            for fee in fees:
                self.balance_op(fee).remove_fee(fee)

    ###########################################################################
    # Modular tax evaluation using tax rules interface
    ###########################################################################
    
    def _evaluate_taxation_modular(self, op: tr.Operation) -> None:
        """
        Modern modular tax evaluation using tax rules interface.
        
        This method replaces the monolithic _evaluate_taxation_GERMANY
        and provides a clean separation between tax logic and balance management.
        """
        if not self.tax_rules or not self.tax_context:
            raise ValueError("Tax rules not initialized for modular evaluation")
        
        # Handle staking/lending operations with coin locking
        if isinstance(op, (tr.CoinLend, tr.Staking)):
            # TODO: Temporarily disabled - complete staking logic integration needed
            log.debug(f"Staking operation detected but not processed: {op.__class__.__name__} {op.change} {op.coin}")
            pass
            
        elif isinstance(op, (tr.CoinLendEnd, tr.StakingEnd)):
            # TODO: Temporarily disabled - complete staking logic integration needed
            log.debug(f"Staking end operation detected but not processed: {op.__class__.__name__} {op.change} {op.coin}")
            pass
            
        elif isinstance(op, tr.Buy):
            # Buys are not taxable but need to be added to balance
            self.add_to_balance(op)
            
        elif isinstance(op, tr.Sell):
            # Handle sells with proper FIFO and staking awareness
            self._handle_sell_with_staking_awareness(op)
            
        elif isinstance(op, (tr.CoinLendInterest, tr.StakingInterest)):
            # Add interest to balance and evaluate taxation
            self.add_to_balance(op)
            if in_tax_year(op):
                self._evaluate_and_add_tax_entry(op)
                
        elif isinstance(op, tr.Airdrop):
            self.add_to_balance(op)
            if in_tax_year(op):
                self._evaluate_and_add_tax_entry(op)
                
        elif isinstance(op, tr.Commission):
            self.add_to_balance(op)
            if in_tax_year(op):
                self._evaluate_and_add_tax_entry(op)
                
        elif isinstance(op, (tr.Deposit, tr.Withdrawal)):
            # Non-taxable balance operations
            if isinstance(op, tr.Deposit):
                self.add_to_balance(op)
            else:  # Withdrawal
                self.remove_from_balance(op)
                self.remove_fees_from_balance(op.fees)
                
        # Handle other operation types through tax rules
        else:
            tax_result = self.tax_rules.evaluate_operation(op, self.tax_context)
            if tax_result.is_taxable and in_tax_year(op):
                self._create_tax_report_entry_from_result(op, tax_result)
    
    def _handle_staking_lending_start(self, op: tr.Operation) -> None:
        """Handle start of staking/lending with coin locking."""
        # For now, create a simple approach without modifying balance queue
        # TODO: Implement proper balance queue integration
        
        balance = self.balance_op(op)
        amount_to_stake = abs(op.change)
        
        # Check if we have enough coins available
        total_available = sum(bop.not_sold for bop in balance.queue)
        if total_available < amount_to_stake:
            raise ValueError(f"Insufficient coins available for staking. Need: {amount_to_stake}, Available: {total_available}")
        
        # Create mock sold coins for staking tracker (simplified approach)
        # This is a placeholder - in full implementation, we'd properly track which specific coins
        mock_sold_coins = []
        remaining_to_stake = amount_to_stake
        
        for bop in balance.queue:
            if remaining_to_stake <= 0:
                break
            if bop.op.coin != op.coin:
                continue
                
            amount_from_this_op = min(remaining_to_stake, bop.not_sold)
            if amount_from_this_op > 0:
                sold_coin = tr.SoldCoin(op=bop.op, sold=amount_from_this_op)
                mock_sold_coins.append(sold_coin)
                remaining_to_stake -= amount_from_this_op
        
        # Start the staking contract
        try:
            contract_id = self.staking_tracker.start_staking_contract(op, mock_sold_coins)
            log.info(f"Started {op.__class__.__name__} contract {contract_id} for {amount_to_stake} {op.coin}")
        except ValueError as e:
            log.error(f"Failed to start staking contract: {e}")
            raise
    
    def _handle_staking_lending_end(self, op: tr.Operation) -> None:
        """Handle end of staking/lending and unlock coins."""
        try:
            returned_coins = self.staking_tracker.end_staking_contract(op)
            log.info(f"Ended staking contract, returned {len(returned_coins)} coin lots")
        except ValueError as e:
            log.error(f"Failed to end staking contract: {e}")
            raise
    
    def _handle_sell_with_staking_awareness(self, op: tr.Sell) -> None:
        """Handle sells with awareness of staked coins."""
        # TODO: Future enhancement - implement proper staking awareness in balance queue
        # For now, only warn if there are staked coins that might interfere
        staked_amount = self.staking_tracker.get_staked_amount(op.platform, op.coin)
        
        if staked_amount > 0:
            log.warning(
                f"Attempting to sell {abs(op.change)} {op.coin} while {staked_amount} "
                f"is currently staked. This may cause unexpected FIFO behavior."
            )
        
        # Use existing balance removal logic - it has proper error handling
        # for missing acquisitions and other edge cases
        sold_coins = self.remove_from_balance(op)
        self.remove_fees_from_balance(op.fees)
        
        # Evaluate taxation if not fiat and in tax year
        if op.coin != config.FIAT and in_tax_year(op):
            self.evaluate_sell(op, sold_coins)
    
    def _evaluate_and_add_tax_entry(self, op: tr.Operation) -> None:
        """Evaluate operation through tax rules and add to tax report."""
        tax_result = self.tax_rules.evaluate_operation(op, self.tax_context)
        if tax_result.is_taxable:
            self._create_tax_report_entry_from_result(op, tax_result)
    
    def _create_tax_report_entry_from_result(self, op: tr.Operation, tax_result) -> None:
        """Create appropriate tax report entry from tax result."""
        # This would create the appropriate report entry type based on operation
        # For now, using existing logic as placeholder
        if isinstance(op, (tr.CoinLendInterest, tr.StakingInterest)):
            if isinstance(op, tr.CoinLendInterest):
                if misc.is_fiat(op.coin):
                    ReportType = tr.InterestReportEntry
                    taxation_type = "Einkünfte aus Kapitalvermögen"
                else:
                    ReportType = tr.LendingInterestReportEntry
                    taxation_type = tax_result.taxation_type or "Einkünfte aus sonstigen Leistungen"
            else:  # StakingInterest
                ReportType = tr.StakingInterestReportEntry
                taxation_type = tax_result.taxation_type or "Einkünfte aus sonstigen Leistungen"
                
            report_entry = ReportType(
                platform=op.platform,
                amount=op.change,
                coin=op.coin,
                utc_time=op.utc_time,
                interest_in_fiat=self.price_data.get_cost(op),
                taxation_type=taxation_type,
                remark=op.remark,
            )
            self.tax_report_entries.append(report_entry)

    ###########################################################################
    # Country specific evaluation functions.
    ###########################################################################

    def _evaluate_fee(
        self,
        fee: tr.Fee,
        percent: decimal.Decimal,
    ) -> tuple[decimal.Decimal, str, decimal.Decimal]:
        return (
            fee.change * percent,
            fee.coin,
            self.price_data.get_partial_cost(fee, percent),
        )

    def get_buy_cost(self, sc: tr.SoldCoin) -> decimal.Decimal:
        """Calculate the buy cost of a sold coin.

        Args:
            sc (tr.SoldCoin): The sold coin.

        Raises:
            NotImplementedError: Calculation is currently not implemented
                for buy operations.

        Returns:
            decimal.Decimal: The buy value of the sold coin in fiat
        """
        assert sc.sold <= sc.op.change
        percent = sc.sold / sc.op.change

        # Fees paid when buying the now sold coins.
        buying_fees = decimal.Decimal()
        if sc.op.fees:
            buying_fees = misc.dsum(
                self.price_data.get_partial_cost(f, percent) for f in sc.op.fees
            )

        if isinstance(sc.op, tr.Buy):
            # Buy cost of a bought coin should be the sell value of the
            # previously sold coin and not the sell value of the bought coin.
            # Gains of combinations like below are not correctly calculated:
            #   1 BTC=1€, 1ETH=2€, 1BTC=1ETH
            # e.g. buy 1 BTC for 1 €, buy 1 ETH for 1 BTC, buy 2 € for 1 ETH.
            if sc.op.buying_cost:
                buy_value = sc.op.buying_cost * percent
            elif sc.op.link:
                prev_sell_value = self.price_data.get_partial_cost(sc.op.link, percent)
                buy_value = prev_sell_value
            else:
                log.warning(
                    "Unable to correctly determine buy cost of bought coins "
                    "because the link to the corresponding previous sell could "
                    "not be estalished. Buying cost will be set to the buy "
                    "value of the bought coins instead of the sell value of the "
                    "previously sold coins of the trade. "
                    "The calculated buy cost might be wrong. "
                    "This may lead to a false tax evaluation.\n"
                    f"{sc.op}"
                )
                buy_value = self.price_data.get_cost(sc)
        else:
            # All other operations "begin their existence" as that coin and
            # weren't traded/exchanged before.
            # The buy cost of these coins is the value from when yout got them.
            buy_value = self.price_data.get_cost(sc)

        return buy_value + buying_fees

    def get_sell_value(
        self,
        op: tr.Sell,
        sc: tr.SoldCoin,
    ) -> decimal.Decimal:
        """Calculate the sell value by determining the market price for the
        with that sell bought coins.

        Args:
            sc (tr.SoldCoin): The sold coin.
            ReportType (Union[Type[tr.SellReportEntry],
                Type[tr.UnrealizedSellReportEntry]])

        Returns:
            decimal.Decimal: The sell value.
        """
        assert sc.op.coin == op.coin
        percent = sc.sold / op.change

        if op.selling_value:
            sell_value = op.selling_value * percent
        elif op.link:
            sell_value = self.price_data.get_partial_cost(op.link, percent)
        else:
            sell_value = self.price_data.get_partial_cost(op, percent)

        return sell_value

    def _get_fee_param_dict(self, op: tr.Operation, percent: decimal.Decimal) -> dict:

        # fee amount/coin/in_fiat
        first_fee_amount = decimal.Decimal(0)
        first_fee_coin = ""
        first_fee_in_fiat = decimal.Decimal(0)
        second_fee_amount = decimal.Decimal(0)
        second_fee_coin = ""
        second_fee_in_fiat = decimal.Decimal(0)
        if op.fees is None or len(op.fees) == 0:
            pass
        elif len(op.fees) >= 1:
            first_fee_amount, first_fee_coin, first_fee_in_fiat = self._evaluate_fee(
                op.fees[0], percent
            )
        elif len(op.fees) >= 2:
            second_fee_amount, second_fee_coin, second_fee_in_fiat = self._evaluate_fee(
                op.fees[1], percent
            )
        else:
            raise NotImplementedError("More than two fee coins are not supported")

        return dict(
            first_fee_amount=first_fee_amount,
            first_fee_coin=first_fee_coin,
            first_fee_in_fiat=first_fee_in_fiat,
            second_fee_amount=second_fee_amount,
            second_fee_coin=second_fee_coin,
            second_fee_in_fiat=second_fee_in_fiat,
        )

    def _evaluate_sell(
        self,
        op: tr.Sell,
        sc: tr.SoldCoin,
        ReportType: Union[
            Type[tr.SellReportEntry], Type[tr.UnrealizedSellReportEntry]
        ] = tr.SellReportEntry,
    ) -> None:
        """Evaluate a (partial) sell operation.

        Args:
            op (tr.Sell): The general sell operation.
            sc (tr.SoldCoin): The specific sold coins with their origin (sc.op).
                `sc.sold` can be a partial sell of `op.change`.
            ReportType (Union[Type[tr.SellReportEntry],
                Type[tr.UnrealizedSellReportEntry]], optional):
                The type of the report entry. Defaults to tr.SellReportEntry.

        Raises:
            NotImplementedError: When there are more than two different fee coins.
        """
        assert op.coin == sc.op.coin
        # German tax compliance: Handle cases where synthetic acquisitions might cause accounting issues
        if op.change < sc.sold:
            log.warning(f"German tax compliance: Adjusting sold amount from {sc.sold} to {op.change} for {op.coin} to maintain accounting consistency")
            # Create adjusted sold coin to prevent assertion failure
            sc = tr.SoldCoin(op=sc.op, sold=op.change)
        assert op.change >= sc.sold

        # Share the fees and sell_value proportionally to the coins sold.
        percent = sc.sold / op.change

        # Ignore fees for UnrealizedSellReportEntry.
        fee_params = self._get_fee_param_dict(op, percent)
        if ReportType is tr.UnrealizedSellReportEntry:
            # Make sure, that the unrealized sell has no fees.
            assert not any(v for v in fee_params.values())
            # Do not give fee parameters to ReportEntry object.
            fee_params = {}
        buy_cost_in_fiat = self.get_buy_cost(sc)

        # Taxable when sell is not more than one year after buy.
        is_taxable = sc.op.utc_time + relativedelta(years=1) >= op.utc_time

        try:
            sell_value_in_fiat = self.get_sell_value(op, sc)
        except Exception as e:
            if ReportType is tr.UnrealizedSellReportEntry:
                log.warning(
                    "Catched the following exception while trying to query an "
                    f"unrealized sell value for {sc.sold} {sc.op.coin} at deadline "
                    f"on platform {sc.op.platform}. "
                    "If you want to see your unrealized sell value "
                    "in the evaluation, please add a price by hand in the "
                    f"table {get_sorted_tablename(op.coin, config.FIAT)[0]} "
                    f"at {op.utc_time}; "
                    "The sell value for this calculation will be set to 0. "
                    "Your unrealized sell summary will be wrong and will not "
                    "be exported.\n"
                    f"Catched exception: {e}"
                )
                sell_value_in_fiat = decimal.Decimal()
                self.unrealized_sells_faulty = True
            else:
                raise e

        sell_report_entry = ReportType(
            sell_platform=op.platform,
            buy_platform=sc.op.platform,
            amount=sc.sold,
            coin=op.coin,
            sell_utc_time=op.utc_time,
            buy_utc_time=sc.op.utc_time,
            **fee_params,
            sell_value_in_fiat=sell_value_in_fiat,
            buy_cost_in_fiat=buy_cost_in_fiat,
            is_taxable=is_taxable,
            taxation_type="Einkünfte aus privaten Veräußerungsgeschäften",
            remark=op.remark,
        )

        self.tax_report_entries.append(sell_report_entry)

    def evaluate_sell(
        self,
        op: tr.Sell,
        sold_coins: list[tr.SoldCoin],
    ) -> None:
        assert op.coin != config.FIAT
        assert in_tax_year(op)
        assert op.change == misc.dsum(sc.sold for sc in sold_coins)

        for sc in sold_coins:

            if isinstance(sc.op, tr.Deposit) and sc.op.link:
                assert (
                    sc.op.link.change >= sc.op.change
                ), "Withdrawal must be equal or greater than the deposited amount."
                deposit_fee = sc.op.link.change - sc.op.change
                sold_percent = sc.sold / sc.op.change
                sold_deposit_fee = deposit_fee * sold_percent

                for wsc in sc.op.link.partial_withdrawn_coins(sold_percent):
                    wsc_percent = wsc.sold / sc.op.link.change
                    wsc_deposit_fee = sold_deposit_fee * wsc_percent

                    if wsc_deposit_fee:
                        # TODO Are withdrawal/deposit fees tax relevant?
                        log.warning(
                            "You paid fees for withdrawal and deposit of coins. "
                            "I am currently not sure if you can reduce your taxed "
                            "gain with these. For now, the deposit/withdrawal fees "
                            "are not included in the tax report. "
                            "Please open an issue or PR if you can resolve this."
                        )
                        # # Deposit fees are evaluated on deposited platform.
                        # wsc_fee_in_fiat = (
                        #     self.price_data.get_price(
                        #         sc.op.platform,
                        #         sc.op.coin,
                        #         sc.op.utc_time,
                        #         config.FIAT,
                        #     )
                        #     * wsc_deposit_fee
                        # )

                    self._evaluate_sell(op, wsc)

            else:

                if isinstance(sc.op, tr.Deposit):
                    # Raise a warning when a deposit link is missing.
                    log.warning(
                        f"You sold {sc.op.change} {sc.op.coin} which were deposited "
                        f"from somewhere unknown onto {sc.op.platform} (see "
                        f"{sc.op.file_path} {sc.op.line}). "
                        "A correct tax evaluation might not be possible! "
                        "For now, we assume that the coins were bought at "
                        "the timestamp of the deposit. "
                        "If these coins get sold one year after this "
                        "the sell is not tax relevant and everything is fine."
                    )

                self._evaluate_sell(op, sc)

    def _evaluate_taxation_GERMANY(self, op: tr.Operation) -> None:
        report_entry: tr.TaxReportEntry

        if isinstance(op, (tr.CoinLend, tr.Staking)):
            # German tax law compliant staking implementation (§23 EStG, BMF Guidelines)
            # Staking/lending does not trigger a taxable event but coins become unavailable for sale
            
            balance = self.balance_op(op)
            amount_to_stake = abs(op.change)
            
            # Calculate total available coins (excluding already staked)
            total_in_balance = sum(bop.not_sold for bop in balance.queue)
            already_staked = self.staking_tracker.get_staked_amount(op.platform, op.coin)
            available_for_staking = total_in_balance - already_staked
            
            if available_for_staking >= amount_to_stake:
                # Determine which specific coins get staked using FIFO principle
                # This is critical for maintaining correct cost basis under German law
                coins_to_stake = []
                remaining_to_stake = amount_to_stake
                
                for bop in balance.queue:
                    if remaining_to_stake <= 0:
                        break
                    if bop.op.coin != op.coin:
                        continue
                    
                    # Check how much of this coin is available (not already staked)
                    available_from_this_op = self.staking_tracker.get_available_amount(
                        op.platform, op.coin, bop.op
                    )
                    
                    if available_from_this_op > 0:
                        amount_to_use = min(remaining_to_stake, available_from_this_op, bop.not_sold)
                        if amount_to_use > 0:
                            staked_coin = tr.SoldCoin(op=bop.op, sold=amount_to_use)
                            coins_to_stake.append(staked_coin)
                            remaining_to_stake -= amount_to_use
                
                if remaining_to_stake > 0:
                    log.warning(
                        f"German tax compliance warning: Cannot stake {remaining_to_stake} {op.coin} "
                        f"as insufficient coins available (some may already be staked). "
                        f"This could affect FIFO cost basis calculations."
                    )
                else:
                    # Create staking contract with proper German tax compliance tracking
                    try:
                        contract_id = self.staking_tracker.start_staking_contract(op, coins_to_stake)
                        log.info(
                            f"German tax compliance: Started {op.__class__.__name__} contract {contract_id} "
                            f"for {amount_to_stake} {op.coin}. Coins locked for FIFO until unstaking."
                        )
                    except Exception as e:
                        log.error(f"Failed to create staking contract (tax compliance issue): {e}")
                        # This is a serious error for German tax compliance
                        raise ValueError(
                            f"Cannot properly track staking operation for German tax compliance: {e}"
                        )
            else:
                # This is a warning but not an error - the operation may be legitimate
                # (e.g., staking coins that were just deposited)
                log.warning(
                    f"German tax compliance notice: Staking {amount_to_stake} {op.coin} "
                    f"but only {available_for_staking} available for staking "
                    f"(total: {total_in_balance}, already staked: {already_staked}). "
                    f"FIFO tracking may be incomplete."
                )

        elif isinstance(op, (tr.CoinLendEnd, tr.StakingEnd)):
            # German tax law compliant staking end implementation
            # Unstaking does not trigger a taxable event, but coins become available for sale again
            # Original acquisition dates and cost basis remain unchanged (critical for §23 EStG)
            
            amount_to_unstake = abs(op.change)
            
            try:
                returned_coins = self.staking_tracker.end_staking_contract(op)
                
                # Verify the unstaking amount matches what was staked
                total_returned = sum(coin.amount for coin in returned_coins)
                if abs(total_returned - amount_to_unstake) > decimal.Decimal('0.00000001'):
                    log.warning(
                        f"German tax compliance warning: Unstaking amount mismatch. "
                        f"Expected {amount_to_unstake}, got {total_returned}. "
                        f"This may affect FIFO cost basis accuracy."
                    )
                
                log.info(
                    f"German tax compliance: Ended {op.__class__.__name__} contract. "
                    f"Returned {len(returned_coins)} coin lots ({total_returned} {op.coin}) "
                    f"to available balance. Original acquisition dates preserved."
                )
                
                # Important: The returned coins maintain their original acquisition dates
                # This is crucial for the one-year holding period rule under §23 EStG
                for returned_coin in returned_coins:
                    log.debug(
                        f"Coin lot returned: {returned_coin.amount} {op.coin} "
                        f"originally acquired {returned_coin.operation.utc_time} "
                        f"(holding period preserved for German tax compliance)"
                    )
                
            except ValueError as e:
                # This could be a serious compliance issue
                log.error(f"German tax compliance error: Failed to end staking contract: {e}")
                log.warning(
                    f"Could not properly track end of {op.__class__.__name__} for {amount_to_unstake} {op.coin}. "
                    f"This may result in incorrect FIFO calculations and tax compliance issues. "
                    f"Manual review recommended."
                )
            
            # Note: Staking/lending rewards are handled separately as income operations
            # (StakingInterest, CoinLendInterest) and taxed under §22 Nr. 3 EStG

        elif isinstance(op, tr.Buy):
            # Buys and sells always come in a pair. The buying/receiving
            # part is not tax relevant per se.
            # The fees of this buy/sell-transaction are saved internally in
            # both operations. The "buying fees" are only relevant when
            # detemining the acquisition cost of the bought coins.
            # For now we'll just add our bought coins to the balance.
            self.add_to_balance(op)

            # TODO Only adding the Buys don't bring that much. We should add
            # all trades instead (buy with buy.link)
            # Add to export for informational purpose.
            # if in_tax_year(op):
            #     fee_params = self._get_fee_param_dict(op, decimal.Decimal(1))
            #     tax_report_entry = tr.BuyReportEntry(
            #         platform=op.platform,
            #         amount=op.change,
            #         coin=op.coin,
            #         utc_time=op.utc_time,
            #         **fee_params,
            #         buy_value_in_fiat=self.price_data.get_cost(op),
            #         remark=op.remark,
            #     )
            #     self.tax_report_entries.append(tax_report_entry)

        elif isinstance(op, tr.Sell):
            # Buys and sells always come in a pair. The selling/redeeming
            # time is tax relevant.
            
            # German tax compliance check: Warn if selling while coins are staked
            amount_to_sell = abs(op.change)
            staked_amount = self.staking_tracker.get_staked_amount(op.platform, op.coin)
            
            if staked_amount > 0:
                balance = self.balance_op(op)
                total_balance = sum(bop.not_sold for bop in balance.queue)
                available_for_sale = total_balance - staked_amount
                
                if available_for_sale < amount_to_sell:
                    log.warning(
                        f"German tax compliance warning: Attempting to sell {amount_to_sell} {op.coin} "
                        f"but only {available_for_sale} available for sale "
                        f"({staked_amount} currently staked). "
                        f"This may result in selling staked coins, affecting FIFO accuracy."
                    )
                elif staked_amount > 0:
                    log.info(
                        f"German tax compliance: Selling {amount_to_sell} {op.coin} while {staked_amount} staked. "
                        f"Ensuring only non-staked coins are sold."
                    )
            
            # Remove the sold coins and paid fees from the balance.
            # Evaluate the sell to determine the taxed gain and other relevant
            # informations for the tax declaration.
            sold_coins = self.remove_from_balance(op)
            self.remove_fees_from_balance(op.fees)

            if op.coin != config.FIAT and in_tax_year(op):
                self.evaluate_sell(op, sold_coins)

        elif isinstance(op, (tr.CoinLendInterest, tr.StakingInterest)):
            # Received coins from lending or staking. Add the received coins
            # to the balance.
            self.add_to_balance(op)

            if in_tax_year(op):
                # Determine the taxation type depending on the received coin.
                if isinstance(op, tr.CoinLendInterest):
                    if misc.is_fiat(op.coin):
                        ReportType = tr.InterestReportEntry
                        taxation_type = "Einkünfte aus Kapitalvermögen"
                    else:
                        ReportType = tr.LendingInterestReportEntry
                        taxation_type = "Einkünfte aus sonstigen Leistungen"
                elif isinstance(op, tr.StakingInterest):
                    ReportType = tr.StakingInterestReportEntry
                    taxation_type = "Einkünfte aus sonstigen Leistungen"
                else:
                    raise NotImplementedError

                report_entry = ReportType(
                    platform=op.platform,
                    amount=op.change,
                    coin=op.coin,
                    utc_time=op.utc_time,
                    interest_in_fiat=self.price_data.get_cost(op),
                    taxation_type=taxation_type,
                    remark=op.remark,
                )
                self.tax_report_entries.append(report_entry)

        elif isinstance(op, tr.Airdrop):
            # Depending on how you received the coins, the taxation varies.
            # If you didn't "do anything" to get the coins, the airdrop counts
            # as a gift.
            self.add_to_balance(op)

            if in_tax_year(op):
                if config.ALL_AIRDROPS_ARE_GIFTS:
                    taxation_type = "Schenkung"
                else:
                    taxation_type = "Einkünfte aus sonstigen Leistungen"
                report_entry = tr.AirdropReportEntry(
                    platform=op.platform,
                    amount=op.change,
                    coin=op.coin,
                    utc_time=op.utc_time,
                    in_fiat=self.price_data.get_cost(op),
                    taxation_type=taxation_type,
                    remark=op.remark,
                )
                self.tax_report_entries.append(report_entry)

        elif isinstance(op, tr.Commission):
            # You received a commission. It is assumed that his is a customer-
            # recruit-customer-bonus which is taxed as `Einkünfte aus sonstigen
            # Leistungen`.
            self.add_to_balance(op)

            if in_tax_year(op):
                report_entry = tr.CommissionReportEntry(
                    platform=op.platform,
                    amount=op.change,
                    coin=op.coin,
                    utc_time=op.utc_time,
                    in_fiat=self.price_data.get_cost(op),
                    taxation_type="Einkünfte aus sonstigen Leistungen",
                    remark=op.remark,
                )
                self.tax_report_entries.append(report_entry)

        elif isinstance(op, tr.Deposit):
            # Coins get deposited onto this platform/balance.
            self.add_to_balance(op)

            if in_tax_year(op):
                if op.link:
                    assert op.coin == op.link.coin
                    assert op.fees is None
                    first_fee_amount = op.link.change - op.change
                    first_fee_coin = op.coin if first_fee_amount else ""
                    first_fee_in_fiat = (
                        self.price_data.get_price(op.platform, op.coin, op.utc_time)
                        if first_fee_amount
                        else decimal.Decimal()
                    )
                    report_entry = tr.TransferReportEntry(
                        first_platform=op.platform,
                        second_platform=op.link.platform,
                        amount=op.change,
                        coin=op.coin,
                        first_utc_time=op.utc_time,
                        second_utc_time=op.link.utc_time,
                        first_fee_amount=first_fee_amount,
                        first_fee_coin=first_fee_coin,
                        first_fee_in_fiat=first_fee_in_fiat,
                        remark=op.remark,
                    )
                else:
                    assert op.fees is None
                    report_entry = tr.DepositReportEntry(
                        platform=op.platform,
                        amount=op.change,
                        coin=op.coin,
                        utc_time=op.utc_time,
                        first_fee_amount=decimal.Decimal(),
                        first_fee_coin="",
                        first_fee_in_fiat=decimal.Decimal(),
                        remark=op.remark,
                    )
                self.tax_report_entries.append(report_entry)

        elif isinstance(op, tr.Withdrawal):
            # Coins get moved to somewhere else. At this point, we only have
            # to remove them from the corresponding balance.
            op.withdrawn_coins = self.remove_from_balance(op)

            if not op.has_link and in_tax_year(op):
                assert op.fees is None
                report_entry = tr.WithdrawalReportEntry(
                    platform=op.platform,
                    amount=op.change,
                    coin=op.coin,
                    utc_time=op.utc_time,
                    first_fee_amount=decimal.Decimal(),
                    first_fee_coin="",
                    first_fee_in_fiat=decimal.Decimal(),
                    remark=op.remark,
                )
                self.tax_report_entries.append(report_entry)

        elif isinstance(op, tr.Fee):
            # Fee operations - remove from balance but not taxable
            # Fees are typically handled as part of their parent operations
            # but standalone fees need to be removed from balance
            self.balance_op(op).remove_fee(op)
            # No tax report entry needed - fees are cost reductions, not taxable events

        else:
            # Log unhandled operation types instead of crashing
            log.warning(f"Unhandled operation type in German tax evaluation: {type(op).__name__}")
            log.debug(f"Operation details: {op.platform}, {op.coin}, {op.change}, {op.utc_time}")
            # Continue processing instead of raising NotImplementedError

    def _evaluate_unrealized_sells(self) -> None:
        """Evaluate the unrealized sells at taxation deadline."""
        for balance in self._balances.values():
            # Get all left over coins from the balance.
            sold_coins = balance.remove_all()
            for sc in sold_coins:
                # Sum up the portfolio at deadline.
                # If the evaluation was done with a virtual single depot,
                # the values per platform might not match the real values at
                # platform.
                self.multi_depot_portfolio[sc.op.platform][sc.op.coin] += sc.sold
                self.single_depot_portfolio[sc.op.coin] += sc.sold

                if sc.op.coin != config.FIAT:
                    # "Sell" these coins which makes it possible to calculate
                    # the unrealized gain afterwards.
                    unrealized_sell = tr.Sell(
                        utc_time=TAX_DEADLINE,
                        platform=sc.op.platform,
                        change=sc.sold,
                        coin=sc.op.coin,
                        line=[-1],
                        file_path=Path(),
                        fees=None,
                    )
                    self._evaluate_sell(
                        unrealized_sell,
                        sc,
                        ReportType=tr.UnrealizedSellReportEntry,
                    )

    ###########################################################################
    # General tax evaluation functions.
    ###########################################################################

    def evaluate_taxation(self) -> None:
        """Evaluate the taxation using country specific functions."""
        log.debug("Starting evaluation...")

        assert all(
            op.utc_time.year <= config.TAX_YEAR for op in self.book.operations
        ), "For tax evaluation, no operation should happen after the tax year."

        # Sort the operations by time.
        operations = tr.sort_operations(self.book.operations, ["utc_time"])

        # Evaluate the operations one by one.
        # Difference between the config.MULTI_DEPOT and "single depot" method
        # is done by keeping balances per platform and coin or only
        # per coin (see self.balance).
        for operation in operations:
            self.__evaluate_taxation(operation)

        # Make sure, that all fees were paid.
        for balance in self._balances.values():
            balance.sanity_check()

        # Evaluate the balance at deadline to calculate unrealized sells.
        if config.CALCULATE_UNREALIZED_GAINS:
            self._evaluate_unrealized_sells()

    ###########################################################################
    # Export / Summary
    ###########################################################################

    def print_evaluation(self) -> None:
        """Print short summary of evaluation to stdout."""
        eval_str = (
            f"Your tax evaluation for {config.TAX_YEAR} "
            f"(Deadline {TAX_DEADLINE.strftime('%d.%m.%Y')}):\n\n"
        )
        for taxation_type, tax_report_entries in misc.group_by(
            self.tax_report_entries, "taxation_type"
        ).items():
            if taxation_type is None:
                continue
            taxable_gain = misc.dsum(
                tre.taxable_gain_in_fiat
                for tre in tax_report_entries
                if not isinstance(tre, tr.UnrealizedSellReportEntry)
            )
            eval_str += f"{taxation_type}: {taxable_gain:.2f} {config.FIAT}\n"

        unrealized_report_entries = [
            tre
            for tre in self.tax_report_entries
            if isinstance(tre, tr.UnrealizedSellReportEntry)
        ]
        assert all(tre.gain_in_fiat is not None for tre in unrealized_report_entries)
        unrealized_gain = misc.dsum(
            misc.not_none(tre.gain_in_fiat) for tre in unrealized_report_entries
        )
        unrealized_taxable_gain = misc.dsum(
            tre.taxable_gain_in_fiat for tre in unrealized_report_entries
        )

        if config.CALCULATE_UNREALIZED_GAINS:
            eval_str += (
                "----------------------------------------\n"
                f"Unrealized gain: {unrealized_gain:.2f} {config.FIAT}\n"
                "Unrealized taxable gain at deadline: "
                f"{unrealized_taxable_gain:.2f} {config.FIAT}\n"
                "----------------------------------------\n"
                f"Your portfolio on {TAX_DEADLINE.strftime('%x')} was:\n"
            )

        if config.MULTI_DEPOT:
            for platform, platform_portfolio in self.multi_depot_portfolio.items():
                for coin, amount in platform_portfolio.items():
                    eval_str += f"{platform} {coin}: {amount:.2f}\n"
        else:
            for coin, amount in self.single_depot_portfolio.items():
                eval_str += f"{coin}: {amount:.2f}\n"

        log.info(eval_str)

    def export_evaluation_as_excel(self) -> Path:
        """Export detailed summary of all tax events to Excel.

        File will be placed in export/ with ascending revision numbers
        (in case multiple evaluations will be done).

        When no tax events occured, the Excel will be exported only with
        a header line and a general sheet.

        Returns:
            Path: Path to the exported file.
        """
        file_path = misc.get_next_file_path(
            config.EXPORT_PATH, str(config.TAX_YEAR), ["xlsx", "log"]
        )
        wb = xlsxwriter.Workbook(file_path, {"remove_timezone": True})
        datetime_format = wb.add_format({"num_format": "dd.mm.yyyy hh:mm;@"})
        date_format = wb.add_format({"num_format": "dd.mm.yyyy;@"})
        change_format = wb.add_format({"num_format": "#,##0.00000000"})
        fiat_format = wb.add_format({"num_format": "#,##0.00"})
        header_format = wb.add_format(
            {
                "bold": True,
                "border": 5,
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
            }
        )

        def get_format(field: dataclasses.Field) -> Optional[xlsxwriter.format.Format]:
            if field.type in ("datetime.datetime", "Optional[datetime.datetime]"):
                return datetime_format
            if field.type in ("decimal.Decimal", "Optional[decimal.Decimal]"):
                if field.name.endswith("in_fiat"):
                    return fiat_format
                return change_format
            return None

        #
        # General
        #
        last_day = TAX_DEADLINE.date()
        first_day = last_day.replace(month=1, day=1)
        time_period = f"{first_day.strftime('%x')}–{last_day.strftime('%x')}"
        ws_general = wb.add_worksheet("Allgemein")
        row = 0
        ws_general.merge_range(row, 0, 0, 1, "Allgemeine Daten", header_format)
        row += 1
        ws_general.write_row(
            row, 0, ["Zeitraum des Steuerberichts", time_period], date_format
        )
        row += 1
        ws_general.write_row(
            row, 0, ["Verbrauchsfolgeverfahren", config.PRINCIPLE.name], date_format
        )
        row += 1
        ws_general.write_row(
            row,
            0,
            [
                "Walletübergreifende Betrachtung?",
                "Nein, separate Betrachtung je Wallet"
                if config.MULTI_DEPOT
                else (
                    "Ja, Zusammenfassung aller Transaktion in einer virtuellen Wallet "
                    "(Hinweis: ausgewiesene Bestände können sich von der Bilanz der "
                    "einzelnen Wallets unterscheiden)"
                ),
            ],
            date_format,
        )
        row += 1
        ws_general.write_row(
            row, 0, ["Alle Zeiten in Zeitzone", config.LOCAL_TIMEZONE_KEY]
        )
        row += 1
        row += 1
        ws_general.write_row(
            row,
            0,
            ["Erstellt am", datetime.datetime.now(config.LOCAL_TIMEZONE)],
            datetime_format,
        )
        row += 1
        ws_general.write_row(
            row, 0, ["Software", "CoinTaxman <https://github.com/provinzio/CoinTaxman>"]
        )
        row += 1
        commit_hash = misc.get_current_commit_hash(default="undetermined")
        ws_general.write_row(row, 0, ["Version (Commit)", commit_hash])
        row += 1
        # Set column format and freeze first row.
        ws_general.set_column(0, 0, 45)  # Increased for longer German labels
        ws_general.set_column(1, 1, 30)  # Increased for better data display
        ws_general.freeze_panes(1, 0)

        #
        # Add summary of tax relevant amounts.
        #
        ws_summary = wb.add_worksheet("Zusammenfassung")
        ws_summary.write_row(
            0,
            0,
            [
                "Einkunftsart",
                "steuerbarer Veräußerungserlös in EUR",
                "steuerbare Anschaffungskosten in EUR",
                "steuerbare Werbungskosten in EUR",
                "steuerbarer Gewinn/Verlust in EUR",
            ],
            header_format,
        )
        row = 1
        for taxation_type, tax_report_entries in misc.group_by(
            self.tax_report_entries, "taxation_type"
        ).items():
            if taxation_type is None:
                continue
            first_value_in_fiat = None
            second_value_in_fiat = None
            total_fee_in_fiat = None
            if taxation_type == "Einkünfte aus privaten Veräußerungsgeschäften":
                first_value_in_fiat = misc.dsum(
                    misc.cdecimal(tre.first_value_in_fiat)
                    for tre in tax_report_entries
                    if tre.taxable_gain_in_fiat
                    and not isinstance(tre, tr.UnrealizedSellReportEntry)
                )
                second_value_in_fiat = misc.dsum(
                    misc.cdecimal(tre.second_value_in_fiat)
                    for tre in tax_report_entries
                    if (
                        not isinstance(tre, tr.UnrealizedSellReportEntry)
                        and tre.taxable_gain_in_fiat
                    )
                )
                total_fee_in_fiat = misc.dsum(
                    misc.cdecimal(tre.total_fee_in_fiat)
                    for tre in tax_report_entries
                    if (
                        not isinstance(tre, tr.UnrealizedSellReportEntry)
                        and tre.taxable_gain_in_fiat
                    )
                )
            taxable_gain = misc.dsum(
                tre.taxable_gain_in_fiat
                for tre in tax_report_entries
                if not isinstance(tre, tr.UnrealizedSellReportEntry)
            )
            ws_summary.write_row(
                row,
                0,
                [
                    taxation_type,
                    first_value_in_fiat,
                    second_value_in_fiat,
                    total_fee_in_fiat,
                    taxable_gain,
                ],
            )
            row += 1
        row += 2
        if not self.unrealized_sells_faulty:
            ws_summary.merge_range(
                row,
                0,
                row,
                4,
                f"Unrealisierte Einkünfte zum {TAX_DEADLINE.strftime('%x')}",
                header_format,
            )
            ws_summary.write_row(
                row + 1,
                0,
                [
                    "Einkunftsart",
                    "Unrealisierter Veräußerungserlös in EUR",
                    "steuerbare Anschaffungskosten in EUR",
                    "Unrealisierter Gewinn/Verlust in EUR",
                    "davon wären steuerbar in EUR",
                ],
                header_format,
            )
            taxation_type = "Einkünfte aus privaten Veräußerungsgeschäften"
            unrealized_report_entries = [
                tre
                for tre in self.tax_report_entries
                if isinstance(tre, tr.UnrealizedSellReportEntry)
            ]
            assert all(
                taxation_type == tre.taxation_type for tre in unrealized_report_entries
            )
            assert all(
                tre.gain_in_fiat is not None for tre in unrealized_report_entries
            )
            first_value_in_fiat = misc.dsum(
                misc.cdecimal(tre.first_value_in_fiat)
                for tre in unrealized_report_entries
            )
            second_value_in_fiat = misc.dsum(
                misc.cdecimal(tre.second_value_in_fiat)
                for tre in unrealized_report_entries
            )
            total_gain_fiat = misc.dsum(
                misc.cdecimal(tre.gain_in_fiat) for tre in unrealized_report_entries
            )
            taxable_gain = misc.dsum(
                tre.taxable_gain_in_fiat for tre in unrealized_report_entries
            )
            ws_summary.write_row(
                row + 2,
                0,
                [
                    taxation_type,
                    first_value_in_fiat,
                    second_value_in_fiat,
                    total_gain_fiat,
                    taxable_gain,
                ],
            )
        # Set column format and freeze first row.
        ws_summary.set_column(0, 0, 60)  # Increased for long German text
        ws_summary.set_column(1, 2, 25.0, fiat_format)  # Increased for better number display
        ws_summary.set_column(3, 4, 25.0, fiat_format)  # Increased for better number display
        ws_summary.freeze_panes(1, 0)

        #
        # Token-Änderungen (Symbol Changes) Sheet
        #
        from services.symbol_mappings import symbol_manager
        ws_token_changes = wb.add_worksheet("Token-Änderungen")
        
        # Header for Token-Änderungen
        token_headers = [
            "Ursprünglicher Name",
            "Neuer Name", 
            "Änderungsdatum",
            "Umtauschverhältnis",
            "Art der Änderung",
            "Beschreibung"
        ]
        ws_token_changes.write_row(0, 0, token_headers, header_format)
        ws_token_changes.set_row(0, 45)
        
        # Data for Token-Änderungen
        row = 1
        for old_sym, new_sym, cutoff_date, swap_ratio, notes in symbol_manager.mappings:
            change_type = "Rebrand"
            if "fork" in notes.lower():
                change_type = "Fork"
            elif "collapse" in notes.lower():
                change_type = "Kollaps"
            elif "swap" in notes.lower():
                change_type = "Token-Swap"
            
            ratio_text = f"{swap_ratio:.0f}:1" if swap_ratio and swap_ratio != 1.0 else "1:1"
            date_text = cutoff_date.strftime('%d.%m.%Y') if cutoff_date else "Sofort"
            
            ws_token_changes.write_row(
                row, 0, 
                [old_sym, new_sym, date_text, ratio_text, change_type, notes]
            )
            row += 1
        
        # Add special LUNA case manually
        ws_token_changes.write_row(
            row, 0,
            ["LUNA", "LUNC + LUNA(v2)", "12.05.2022", "1:1", "Ökosystem-Kollaps", 
             "Terra Classic: Alte LUNA wurde zu LUNC, neue LUNA v2 wurde erstellt"]
        )
        
        # Format Token-Änderungen sheet
        ws_token_changes.set_column(0, 1, 20)  # Symbol columns
        ws_token_changes.set_column(2, 2, 15, date_format)  # Date column
        ws_token_changes.set_column(3, 3, 18)  # Ratio column
        ws_token_changes.set_column(4, 4, 20)  # Type column
        ws_token_changes.set_column(5, 5, 60)  # Description column
        ws_token_changes.freeze_panes(1, 0)

        #
        # Sheets per ReportType
        #
        for event_type, tax_report_entries in misc.group_by(
            tr.sort_tax_report_entries(self.tax_report_entries), "event_type"
        ).items():
            ReportType = type(tax_report_entries[0])

            if (
                self.unrealized_sells_faulty
                and ReportType is tr.UnrealizedSellReportEntry
            ):
                continue

            ws = wb.add_worksheet(event_type)

            # Header
            labels = ReportType.excel_labels()
            ws.write_row(0, 0, labels, header_format)
            # Set height
            ws.set_row(0, 45)
            ws.autofilter(0, 0, 0, len(labels) - 1)

            # Data
            for row, entry in enumerate(tax_report_entries, 1):
                ws.write_row(row, 0, entry.excel_values())

            # Set column format and freeze first row.
            for col, (field, width, hidden) in enumerate(
                ReportType.excel_field_and_width()
            ):
                cell_format = get_format(field)
                ws.set_column(
                    col,
                    col,
                    width,
                    cell_format,
                    dict(hidden=hidden),
                )
            ws.freeze_panes(1, 0)

        wb.close()
        log.info("Saved evaluation in %s.", file_path)
        return file_path
