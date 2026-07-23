"""Enriquecimento auditável de publicações canônicas."""

from .core import POLITICA_METRICAS_V1, enriquecer_publicacoes
from .repository import RepositorioMetricasSQLite

__all__ = ["POLITICA_METRICAS_V1", "RepositorioMetricasSQLite", "enriquecer_publicacoes"]
