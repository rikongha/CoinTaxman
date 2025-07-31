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

"""Bybit exchange reader implementation."""

import csv
import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import misc

if TYPE_CHECKING:
    from book import Book


def read_bybit(book: "Book", file_path: Path) -> None:
    """Read Bybit AssetChangeDetails CSV file.
    
    Args:
        book: Book instance to add operations to
        file_path: Path to Bybit CSV file
    """
    platform = "bybit"
    
    # Operation mapping from Bybit type to CoinTaxman operation
    operation_mapping = {
        "Earn": "StakingInterest",
        "Deposit": "Deposit", 
        "Withdrawal": "Withdrawal",
        "Fiat": "Sell",  # P2P sales/purchases treated as sells
        "Trading": "Buy",  # Will be determined by positive/negative QTY
        "Transfer": "Deposit",  # Internal transfers
        "Bonus": "Airdrop",
        "Commission": "Commission",
        "Fee": "Fee",
    }
    
    with open(file_path, encoding="utf8") as f:
        reader = csv.reader(f)
        
        # Skip UID header line
        first_line = next(reader)
        if not first_line[0].startswith("UID:"):
            # Rewind if this isn't a UID line
            f.seek(0)
        
        # Read actual headers
        headers = next(reader)
        expected_headers = ["Uid", "Date & Time(UTC)", "Coin", "QTY", "Type", "Account Balance", "Description"]
        
        if headers != expected_headers:
            raise ValueError(f"Unexpected Bybit CSV format. Expected {expected_headers}, got {headers}")
        
        for columns in reader:
            if len(columns) != 7:
                continue
                
            uid, _utc_time, coin, _qty, operation_type, _balance, description = columns
            row = reader.line_num
            
            # Parse data
            utc_time = datetime.datetime.strptime(_utc_time, "%Y-%m-%d %H:%M:%S")
            utc_time = utc_time.replace(tzinfo=datetime.timezone.utc)
            
            qty = misc.force_decimal(_qty)
            
            # Skip zero quantity operations
            if qty == 0:
                continue
            
            # Handle special cases based on quantity sign before mapping
            if operation_type == "Earn":
                # Positive = staking reward (taxable income)
                # Negative = unstaking (getting staked coins back, not taxable)
                if qty > 0:
                    operation = "StakingInterest"
                else:
                    # Negative Earn = unstaking, treat as deposit (getting your coins back)
                    operation = "Deposit"
            elif operation_type == "Trading":
                # For trading operations, determine buy/sell from quantity sign
                operation = "Buy" if qty > 0 else "Sell"
            else:
                # Map other operation types normally
                operation = operation_mapping.get(operation_type)
                if not operation:
                    # Handle unknown operation types
                    if qty > 0:
                        operation = "Buy"
                    else:
                        operation = "Sell"
            
            # Use absolute quantity
            qty = abs(qty)
            
            # Clean up description for remark
            remark = description.strip() if description and description.strip() else None
            if remark in ("", "-"):
                remark = None
            
            # Validate data
            assert operation
            assert coin
            assert qty > 0
            
            # Add operation to book
            book.append_operation(
                operation, utc_time, platform, qty, coin, row, file_path, remark=remark
            )


def read_bybit_uta(book: "Book", file_path: Path) -> None:
    """Read Bybit UTA (Unified Trading Account) CSV file.
    
    Args:
        book: Book instance to add operations to  
        file_path: Path to Bybit UTA CSV file
    """
    import csv
    import datetime
    import misc
    
    platform = "bybit"
    
    with open(file_path, encoding="utf8") as f:
        reader = csv.reader(f)
        
        # Skip UID header line if present
        first_line = next(reader)
        if not first_line[0].startswith("UID:"):
            # Rewind if this isn't a UID line
            f.seek(0)
        
        # Read actual headers
        headers = next(reader)
        expected_headers = ["Uid", "Currency", "Contract", "Type", "Direction", "Quantity", "Position", "Filled Price", "Funding", "Fee Paid", "Cash Flow", "Change", "Wallet Balance", "Action", "Time(UTC)"]
        
        if headers != expected_headers:
            raise ValueError(f"Unexpected Bybit UTA CSV format. Expected {expected_headers}, got {headers}")
        
        for columns in reader:
            if len(columns) != 15:
                continue
                
            (uid, currency, contract, operation_type, direction, quantity, 
             position, filled_price, funding, fee_paid, cash_flow, change, 
             wallet_balance, action, _utc_time) = columns
            row = reader.line_num
            
            # Parse data
            utc_time = datetime.datetime.strptime(_utc_time, "%Y-%m-%d %H:%M:%S")
            utc_time = utc_time.replace(tzinfo=datetime.timezone.utc)
            
            # Use change for quantity (wallet balance change)
            qty = misc.force_decimal(change)
            
            # Skip zero quantity operations
            if qty == 0:
                continue
            
            # Map operation based on action and type
            operation = None
            if action == "Transfer":
                operation = "Deposit" if qty > 0 else "Withdrawal"
            elif operation_type == "TRADE":
                operation = "Buy" if qty > 0 else "Sell"
            elif operation_type == "FUNDING":
                operation = "Fee" if qty < 0 else "Commission"
            else:
                # Default mapping
                operation = "Buy" if qty > 0 else "Sell"
            
            # Use absolute quantity
            qty = abs(qty)
            
            # Validate data
            assert operation
            assert currency
            assert qty > 0
            
            # Add operation to book
            book.append_operation(
                operation, utc_time, platform, qty, currency, row, file_path
            )


def read_bybit_withdraw_deposit(book: "Book", file_path: Path) -> None:
    """Read Bybit withdrawal/deposit specific CSV file.
    
    Args:
        book: Book instance to add operations to
        file_path: Path to Bybit withdraw/deposit CSV file  
    """
    # Specific withdraw/deposit format, implement if needed
    # For now, delegate to regular Bybit reader
    read_bybit(book, file_path)