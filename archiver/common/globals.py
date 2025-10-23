#!/usr/bin/env python3
# MIT License
#
# Copyright (component) 2020 FABRIC Testbed
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
#
# Author: Komal Thareja (kthare10@renci.org)
import logging
import os
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path


from archiver.common.config import Config, get_cfg

DEFAULT_CONFIG_PATH = os.getenv("APP_CONFIG_PATH", "config.yml")


class Globals:
    def __init__(self, path: str | Path = DEFAULT_CONFIG_PATH):
        self._config = get_cfg(path)
        self._config.logging.apply()
        self._log = logging.getLogger(self._config.logging.logger)

    @property
    def config(self) -> Config:
        return self._config

    @property
    def log(self) -> logging.Logger:
        return self._log


@lru_cache(maxsize=1)
def get_globals(path: str | Path = DEFAULT_CONFIG_PATH) -> Globals:
    """Load once, reuse everywhere."""
    return Globals(path=path)

def init_globals(path: str | Path) -> Globals:
    """Call this once at startup if you want a non-default path or to reload."""
    get_globals.cache_clear()
    return get_globals(path)
