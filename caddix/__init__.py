#!/bin/python3
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :


from psycopg.rows import class_row, dict_row, namedtuple_row, scalar_row, tuple_row

from .base import DatabaseSession, CaddixError, CaddixSessionError
from .config import Configs as Setup
from .pool import PGPool

__title__ = "caddix"
__description__ = "Caddix is a helper library for Python designed to make working with PostgreSQL databases easier, faster, and safer."
__author__ = "Marcus Gros"
__email__ = "marcus-gros@freenet.de"
__copyright__ = "Copyright 2026 Marcus Gros"
__license__ = "MIT"
__version__ = "1.1.0"
__requirements__ = ["psycopg"]
__all__ = [
    "Setup",
    "PGPool",
    "DatabaseSession",
    "CaddixError",
    "CaddixSessionError",
    "dict_row",
    "tuple_row",
    "scalar_row",
    "class_row",
    "namedtuple_row",
]
