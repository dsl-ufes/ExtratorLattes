"""Metadados de publicações usados pelo fluxo PPGI.

As classes não alteram as interfaces antigas das produções. Elas guardam os
dados necessários para identificar uma ocorrência e para auditar sua origem.
"""
from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class AutorPublicacao:
    nome: str = ""
    nome_citacao: str = ""
    ordem: int = 0
    id_lattes: str = ""
    id_cnpq: str = ""


@dataclass(frozen=True)
class ProvenienciaPublicacao:
    curriculo_id: str = ""
    arquivo_xml: str = ""
    sequencia: int = 0
    elemento_xml: str = ""
    incompleta: bool = False


@dataclass(frozen=True)
class MetadadosPublicacao:
    doi: str = ""
    issn: str = ""
    isbn: str = ""
    volume: str = ""
    fasciculo: str = ""
    pagina_inicial: str = ""
    pagina_final: str = ""
    autores_detalhados: Tuple[AutorPublicacao, ...] = field(default_factory=tuple)
    proveniencia: ProvenienciaPublicacao = field(default_factory=ProvenienciaPublicacao)
