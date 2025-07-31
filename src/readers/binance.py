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

"""Binance exchange reader implementation."""

import csv
import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import misc
import log_config

if TYPE_CHECKING:
    from book import Book

log = log_config.getLogger(__name__)


def read_binance(book: "Book", file_path: Path, version: int = 1) -> None:
    """Read Binance CSV file.
    
    Args:
        book: Book instance to add operations to
        file_path: Path to Binance CSV file
        version: CSV format version (1 or 2)
    """
    platform = "binance"
    operation_mapping = {
        "Distribution": "Airdrop",
        "Cash Voucher distribution": "Airdrop",
        "Cash Voucher Distribution": "Airdrop",
        "Cashback Voucher": "Airdrop",
        "Rewards Distribution": "Airdrop",
        "Simple Earn Flexible Airdrop": "Airdrop",
        "Airdrop Assets": "Airdrop",
        "Crypto Box": "Airdrop",
        "Launchpool Airdrop": "Airdrop",
        "Megadrop Rewards": "Airdrop",
        #
        "Savings Interest": "CoinLendInterest",
        "Savings purchase": "CoinLend",
        "Savings Principal redemption": "CoinLendEnd",
        "Savings distribution": "CoinLendInterest",
        "Simple Earn Flexible Subscription": "CoinLend",
        "Simple Earn Flexible Redemption": "CoinLendEnd",
        "Simple Earn Flexible Interest": "CoinLendInterest",
        "Simple Earn Locked Subscription": "CoinLend",
        "Simple Earn Locked Redemption": "CoinLendEnd",
        "Simple Earn Locked Rewards": "CoinLendInterest",
        "Savings Distribution": "CoinLendInterest",
        #
        "BNB Vault Rewards": "CoinLendInterest",
        "Launchpool Earnings Withdrawal": "CoinLendInterest",
        #
        "Commission History": "Commission",
        "Commission Fee Shared With You": "Commission",
        "Referrer rebates": "Commission",
        "Referral Kickback": "Commission",
        "Commission Rebate": "Commission",
        # DeFi yield farming
        "Liquid Swap add": "CoinLend",
        "Liquid Swap remove": "CoinLendEnd",
        "Liquid Swap rewards": "CoinLendInterest",
        "Launchpool Interest": "CoinLendInterest",
        "Launchpool Subscription/Redemption": "CoinLend",  # Will be determined by change sign
        #
        "Super BNB Mining": "StakingInterest",
        "POS savings interest": "StakingInterest",
        "POS savings purchase": "Staking",
        "POS savings redemption": "StakingEnd",
        "ETH 2.0 Staking": "Staking",
        "ETH 2.0 Staking Rewards": "StakingInterest",
        "ETH 2.0 Staking Withdrawals": "StakingEnd",
        "Staking Purchase": "Staking",
        "Staking Rewards": "StakingInterest",
        "Staking Redemption": "StakingEnd",
        "DOT Slot Auction Rewards": "StakingInterest",
        "DOT Slot Auction Redemption": "StakingEnd",
        "DOT Slot Auction Staking": "Staking",
        #
        "Fiat Deposit": "Deposit",
        "Fiat Withdraw": "Withdrawal",
        "Withdraw": "Withdrawal",
        #
        "Transaction Buy": "Buy",
        "Transaction Spend": "Sell",
        "Transaction Revenue": "Buy",
        "Transaction Sold": "Sell",
        "Transaction Fee": "Fee",
        "Asset Recovery": "Sell",
        "Asset - Transfer": "Transfer",
        "P2P Trading": "Buy",  # Will be determined by change sign
        "Send": "Withdrawal",
        "Send/Recieve": "Buy",  # Will be determined by change sign
        "Payment": "Buy",  # Will be determined by change sign
        "Token Swap - Distribution": "Airdrop",
        "Token Swap - Redenomination/Rebranding": "Buy",  # Token rebranding
        "HODLer Airdrops Distribution": "Airdrop",
    }

    with open(file_path, encoding="utf8") as f:
        reader = csv.reader(f)

        # Skip header.
        next(reader)

        for rowlist in reader:
            if version == 1:
                _utc_time, account, operation, coin, _change, remark = rowlist
            elif version == 2:
                (
                    _,
                    _utc_time,
                    account,
                    operation,
                    coin,
                    _change,
                    remark,
                ) = rowlist
            else:
                log.error("File version not Supported " + str(file_path))
                raise NotImplementedError

            row = reader.line_num

            # Parse data.
            utc_time = datetime.datetime.strptime(_utc_time, "%Y-%m-%d %H:%M:%S")
            utc_time = utc_time.replace(tzinfo=datetime.timezone.utc)
            change = misc.force_decimal(_change)
            operation = operation_mapping.get(operation, operation)
            if operation in (
                "The Easiest Way to Trade",
                "Small assets exchange BNB",
                "Small Assets Exchange BNB",
                "Transaction Related",
                "Large OTC trading",
                "Sell",
                "Buy",
                "Binance Convert",
                "Send/Recieve",
                "Payment",
                "Token Swap - Redenomination/Rebranding",
            ):
                operation = "Sell" if change < 0 else "Buy"

            if operation == "Liquid Swap add/sell":
                operation = "CoinLendEnd" if change < 0 else "CoinLend"
                
            if operation == "Launchpool Subscription/Redemption":
                operation = "CoinLendEnd" if change < 0 else "CoinLend"

            if operation == "Commission" and account != "Spot":
                # All comissions will be handled the same way.
                # As of now, only Spot Binance Operations are supported,
                # so we have to change the account type to Spot.
                account = "Spot"

            if (
                account in ("Spot", "P2P")
                and operation
                in (
                    "transfer_in",
                    "transfer_out",
                    "Transfer",
                )
                or (
                    account in ("Spot", "Funding")
                    and operation == "Transfer Between Main and Funding Wallet"
                )
                or operation == "Transfer Between Main Account And Mining Account"
                or operation == "Transfer Between Main And Mining Account"
                or operation == "Ledger - Fund Migration"
                or operation == "Transfer Between Futures Contract Accounts"
            ):
                # Ignore transfers
                continue

            change = abs(change)

            # Validate data.
            supported_account_types = ("Spot", "Savings", "Earn", "Funding", "Pool")
            assert account in supported_account_types, (
                f"Other types than {supported_account_types} are currently "
                f"not supported.  Given account type is `{account}`. "
                "Please create an Issue or PR."
            )
            assert operation
            assert coin
            assert change

            if remark:
                # Ignore default remarks
                if remark in (
                    "Withdraw fee is included",
                    "Binance Earn",
                    "Binance Pay",
                    "Binance Launchpool",
                ) or remark.endswith(" to BNB") or remark.startswith("staking project send") or remark.startswith("P2P -") or remark.startswith("Binance Pay -"):
                    remark = ""

                # Do not warn for specific remarks
                elif remark.startswith("Korrekturbuchung."):
                    pass

                # Warn on other binance remarks, becuase all remarks should be some
                # unnecessary default text which we'd like to ignore
                else:
                    log.warning(
                        "I may have missed a remark in %s:%i: `%s`.",
                        file_path,
                        row,
                        remark,
                    )

            book.append_operation(
                operation, utc_time, platform, change, coin, row, file_path, remark
            )


def read_binance_v2(book: "Book", file_path: Path) -> None:
    """Read Binance CSV file version 2.
    
    Args:
        book: Book instance to add operations to
        file_path: Path to Binance CSV file
    """
    read_binance(book=book, file_path=file_path, version=2)