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

import datetime
import decimal
import sqlite3
import sys
from inspect import getmembers, isfunction
from pathlib import Path
from typing import Iterator, Optional

import config
import log_config
from database import get_tablenames_from_db, set_price_db

FUNC_PREFIX = "__patch_"
log = log_config.getLogger(__name__)


def get_version(db_path: Path) -> int:
    """Get database version from a database file.

    If the version table is missing, one is created.

    Args:
        db_path (str): Path to database file.

    Raises:
        RuntimeError: The database version is ambiguous.

    Returns:
        int: Version of database file.
    """
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        try:
            cur.execute("SELECT version FROM §version;")
            versions = [int(v[0]) for v in cur.fetchall()]
        except sqlite3.OperationalError as e:
            if str(e) == "no such table: §version":
                # The §version table doesn't exist. Create one.
                update_version(db_path, 0)
                return 0
            else:
                raise e

        if len(versions) == 1:
            version = versions[0]
            return version
        else:
            raise RuntimeError(
                f"The database version of the file `{db_path.name}` is ambigious. "
                f"The table `§version` should have one entry, but has {len(versions)}."
            )


def update_version(db_path: Path, version: int) -> None:
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()

        try:
            cur.execute("DELETE FROM §version;")
        except sqlite3.OperationalError as e:
            if str(e) == "no such table: §version":
                cur.execute("CREATE TABLE §version(version INT);")
            else:
                raise e

        assert isinstance(version, int)
        log.debug(f"Updating version of {db_path} to {version}")
        cur.execute(f"INSERT INTO §version (version) VALUES ({version});")


def create_new_database(db_path: Path) -> None:
    assert not db_path.exists()
    version = get_latest_version()
    update_version(db_path, version)


def get_patch_func_version(func_name: str) -> int:
    assert func_name.startswith(
        FUNC_PREFIX
    ), f"Patch function `{func_name}` should start with {FUNC_PREFIX}."
    len_func_prefix = len(FUNC_PREFIX)
    version_str = func_name[len_func_prefix:]
    version = int(version_str)
    return version


def __patch_001(db_path: Path) -> None:
    """Convert prices from float to string

    Args:
        db_path (Path)
    """
    with sqlite3.connect(db_path) as conn:
        # Clean up any existing temp table first
        conn.execute('DROP TABLE IF EXISTS "sql_temp_table";')
        
        query = "SELECT name,sql FROM sqlite_master WHERE type='table'"
        cur = conn.execute(query)
        tables_to_patch = []
        
        for tablename, sql in cur.fetchall():
            if "price str" not in sql.lower() and not tablename.startswith("§"):
                tables_to_patch.append(tablename)
        
        # Process each table separately to avoid conflicts
        for tablename in tables_to_patch:
            try:
                # Clean up any existing temp table
                conn.execute('DROP TABLE IF EXISTS "sql_temp_table";')
                
                # Create temp table
                conn.execute(
                    """CREATE TABLE "sql_temp_table" (
                    "utc_time" DATETIME PRIMARY KEY,
                    "price"	VARCHAR(255) NOT NULL
                );"""
                )
                
                # Insert data with deduplication (keep latest entry for duplicates)
                conn.execute(
                    f"""INSERT INTO "sql_temp_table" ("utc_time","price")
                SELECT "utc_time", cast("price" as text) FROM "{tablename}"
                GROUP BY "utc_time"
                HAVING MAX(rowid);"""
                )
                
                # Replace original table
                conn.execute(f'DROP TABLE "{tablename}";')
                conn.execute(f'ALTER TABLE "sql_temp_table" RENAME TO "{tablename}";')
                
            except sqlite3.Error as e:
                log.warning(f"Failed to patch table {tablename}: {e}")
                # Clean up temp table if it exists
                conn.execute('DROP TABLE IF EXISTS "sql_temp_table";')
                continue


def __patch_002(db_path: Path) -> None:
    """Group tablenames, so that the symbols are alphanumerical.

    Args:
        db_path (Path)
    """
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        tablenames = get_tablenames_from_db(cur)
        # Iterate over all tables.
        for tablename in tablenames:
            # Skip tables that don't contain "/" separator
            if "/" not in tablename:
                continue
            base_asset, quote_asset = tablename.split("/")

            # Adjust the order, when the symbols aren't ordered alphanumerical.
            if base_asset > quote_asset:

                # Query all prices from the table.
                cur = conn.execute(f"Select utc_time, price FROM `{tablename}`;")

                for _utc_time, _price in list(cur.fetchall()):
                    # Convert the data.
                    # Try non-fractional seconds first, then fractional seconds,
                    # then the same without timezone
                    for dateformat in (
                        "%Y-%m-%d %H:%M:%S%z",
                        "%Y-%m-%d %H:%M:%S.%f%z",
                        "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%d %H:%M:%S.%f",
                    ):
                        try:
                            utc_time = datetime.datetime.strptime(_utc_time, dateformat)
                        except ValueError:
                            continue
                        else:
                            if not dateformat.endswith("%z"):
                                # Add the missing time zone information.
                                utc_time = utc_time.replace(tzinfo=None)
                            break
                    else:
                        raise ValueError(
                            f"Could not parse date `{_utc_time}` "
                            "in table `{tablename}`."
                        )

                    price = decimal.Decimal(_price)
                    set_price_db("", base_asset, quote_asset, utc_time, price, db_path)
                conn.execute(f"DROP TABLE `{tablename}`;")


def __patch_003(db_path: Path) -> None:
    """Patch 001 did not converted the prices from float to varchar previously.
    Run the fixed patch again. So that every user has a correct database with
    prices as strings.

    Args:
        db_path (Path)
    """
    __patch_001(db_path)


def _get_patch_func_names() -> Iterator[str]:
    func_names = (
        f[0]
        for f in getmembers(sys.modules[__name__], isfunction)
        if f[0].startswith(FUNC_PREFIX)
    )
    return func_names


def _get_patch_func_versions() -> Iterator[int]:
    func_names = _get_patch_func_names()
    func_version = map(get_patch_func_version, func_names)
    return func_version


def get_sorted_patch_func_names(current_version: Optional[int] = None) -> list[str]:
    func_names = (
        f
        for f in _get_patch_func_names()
        if current_version is None or get_patch_func_version(f) > current_version
    )
    # Sort patch functions chronological.
    return sorted(func_names, key=get_patch_func_version)


def get_latest_version() -> int:
    func_versions = _get_patch_func_versions()
    return max(func_versions)


def patch_databases() -> None:
    # Check if any database paths exist.
    database_paths = [p for p in Path(config.DATA_PATH).glob("*.db") if p.is_file()]
    if not database_paths:
        return

    # Patch all databases separatly.
    for db_path in database_paths:
        # Read version from database.
        current_version = get_version(db_path)

        patch_func_names = get_sorted_patch_func_names(current_version=current_version)
        if not patch_func_names:
            continue

        # Run the patch functions.
        for patch_func_name in patch_func_names:
            log.info("applying patch %s", patch_func_name.removeprefix(FUNC_PREFIX))
            patch_func = eval(patch_func_name)
            patch_func(db_path)

        # Update version.
        new_version = get_patch_func_version(patch_func_name)
        update_version(db_path, new_version)
