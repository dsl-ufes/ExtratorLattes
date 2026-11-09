"""QualisLens: associação de nomes de eventos ao Qualis CAPES."""

from .qualislens.matcher import match
from .qualislens.qualis_db import QualisDB

__all__ = ["QualisDB", "match"]
