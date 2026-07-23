"""Deduplicação auditável de publicações do PPGI."""
from .core import POLITICA_V1, POLITICA_V2, ResultadoDeduplicacao, deduplicar_publicacoes, id_ocorrencia, conteudo_fingerprint

__all__ = ["POLITICA_V1", "POLITICA_V2", "ResultadoDeduplicacao", "deduplicar_publicacoes", "id_ocorrencia", "conteudo_fingerprint"]
