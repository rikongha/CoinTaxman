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

"""Kraken-specific mappings and utilities."""

# Kraken asset mapping for ledger parsing
kraken_asset_map = {
    "XXBT": "BTC",
    "XETH": "ETH",
    "XXRP": "XRP",
    "XLTC": "LTC",
    "XXLM": "XLM",
    "XETC": "ETC",
    "XXMR": "XMR",
    "XREP": "REP",
    "XZEC": "ZEC",
    "ZUSD": "USD",
    "ZEUR": "EUR",
    "ZCAD": "CAD",
    "ZGBP": "GBP",
    "ZJPY": "JPY",
    "ZKRW": "KRW",
    "KFEE": "FEE",
    "EUR.HOLD": "EUR",
}