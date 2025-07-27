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

import logging
from logging import getLogger, shutdown  # noqa: F401

from config import LOG_LEVEL, TMP_LOG_FILEPATH

log = getLogger(None)
log.setLevel(LOG_LEVEL)

# Entferne die handler des basic loggers.
for handler in log.handlers:
    log.removeHandler(handler)

# Handler
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
fh = logging.FileHandler(TMP_LOG_FILEPATH, "w")
fh.setLevel(logging.DEBUG)  # Log all debug info to file for comprehensive debugging

# Formatter
formatter = logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s")

handlers: list[logging.Handler] = [ch, fh]
for handler in handlers:
    handler.setFormatter(formatter)
    log.addHandler(handler)

# Disable urllib debug messages
getLogger("urllib3").propagate = False
