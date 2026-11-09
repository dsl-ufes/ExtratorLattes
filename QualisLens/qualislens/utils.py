"""Utilitários compartilhados do pipeline QualisLens."""

import unicodedata


def strip_accents(text: str) -> str:
    """Remove acentos de uma string Unicode via decomposição NFD."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
