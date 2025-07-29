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

"""Date parsing utilities for CoinTaxman."""

import datetime
from typing import Union


def parse_date_unified(date_string: str) -> datetime.datetime:
    """
    Unified date parser that handles multiple date formats commonly found
    in exchange exports and user input.
    
    Args:
        date_string: Date string to parse
        
    Returns:
        datetime object with UTC timezone
        
    Raises:
        ValueError: If date format is not recognized
    """
    # Handle empty or None input
    if not date_string or not isinstance(date_string, str):
        raise ValueError("Date string cannot be empty or None")
    
    date_string = date_string.strip()
    
    # Common date formats found in exchange exports
    formats = [
        "%Y-%m-%d %H:%M:%S",           # 2023-01-15 14:30:25
        "%Y-%m-%dT%H:%M:%SZ",          # 2023-01-15T14:30:25Z
        "%Y-%m-%d %H:%M:%S UTC",       # 2023-01-15 14:30:25 UTC
        "%Y-%m-%d",                    # 2023-01-15
        "%m/%d/%Y %H:%M:%S",           # 01/15/2023 14:30:25
        "%m/%d/%Y",                    # 01/15/2023
        "%d.%m.%Y %H:%M:%S",           # 15.01.2023 14:30:25
        "%d.%m.%Y",                    # 15.01.2023
        "%Y-%m-%dT%H:%M:%S.%fZ",       # 2023-01-15T14:30:25.123456Z
        "%Y-%m-%dT%H:%M:%S.%f",        # 2023-01-15T14:30:25.123456
        "%b %d, %Y",                   # Jan 28, 2013
        "%B %d, %Y",                   # January 28, 2013
    ]
    
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(date_string, fmt)
            # Ensure UTC timezone
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except ValueError:
            continue
    
    # If no format matches, raise error with helpful message
    raise ValueError(
        f"Unable to parse date '{date_string}'. "
        f"Supported formats include: YYYY-MM-DD HH:MM:SS, "
        f"YYYY-MM-DDTHH:MM:SSZ, MM/DD/YYYY, DD.MM.YYYY, etc."
    )