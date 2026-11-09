"""Implementação do pipeline QualisLens."""

from .matcher import match
from .qualis_db import QualisDB

__all__ = ["QualisDB", "match"]
