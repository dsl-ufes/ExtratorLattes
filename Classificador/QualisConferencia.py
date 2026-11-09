"""Classificador Qualis de trabalhos publicados em eventos."""

from pathlib import Path
import warnings
from typing import Optional

from QualisLens.qualislens.matcher import match, qualis_input_id
from QualisLens.qualislens.qualis_db import QualisDB
from QualisLens.qualislens.overrides import OverrideRepository
from QualisLens.qualislens.matcher import validar_resultado


class QualisConferencia:
    """Integra o QualisLens à interface histórica do ExtratorLattes.

    ``qualis_path`` continua aceitando o TSV legado de 2017-2020 usado nas
    configurações existentes. A base recente distribuída com o QualisLens é
    carregada em conjunto. Também é possível informar explicitamente os dois
    CSVs normalizados.
    """

    def __init__(
        self,
        qualis_path: Optional[str] = None,
        path_2021_2024: Optional[str] = None,
        overrides_path: Optional[str] = None,
    ) -> None:
        argumentos = {}
        if qualis_path:
            caminho_legado = Path(qualis_path).resolve()
            argumentos["path_2017"] = str(caminho_legado)
        if path_2021_2024:
            argumentos["path_2025"] = str(Path(path_2021_2024))
        self._db = QualisDB(**argumentos)
        self._overrides = OverrideRepository(overrides_path) if overrides_path else OverrideRepository()
        self._cache = {}

    def get_match(
        self,
        venue: str,
        ano: Optional[int] = None,
        sigla: Optional[str] = None,
    ) -> dict:
        """Retorna classificação e diagnóstico completo para um evento.

        Quando ``ano`` é omitido, usa a semântica da interface legada: a base
        2017-2020 configurada. O fluxo PPGI sempre informa o ano real.
        """
        if ano is None:
            warnings.warn(
                "get_match/get_estrato sem ano usa a base legada 2017-2020; "
                "informe ano para uma decisão reprodutível",
                DeprecationWarning,
                stacklevel=2,
            )
            ano = 2020
        chave_cache = (venue or "", ano, sigla or "")
        resultado = self._cache.get(chave_cache)
        if resultado is None:
            input_id = qualis_input_id(venue, ano, sigla)
            override = self._overrides.get(input_id)
            if override:
                resultado = {
                    "qualis_input_id": input_id,
                    "qualis_candidatos": "[]",
                    "qualis_score_fuzzy": 0.0,
                    "qualis_score_margem": 0.0,
                    "qualis_score_llm": None,
                    "qualis_llm_motivo": None,
                    "qualis_origem_decisao": "override",
                    "qualis_justificativa": override.justificativa,
                    "qualis_decidido_por": override.decidido_por,
                    "qualis_decidido_em": override.decidido_em,
                    "qualis_politica_versao": override.politica_versao,
                }
                if override.acao == "SEM_CORRESPONDENCIA":
                    resultado.update({"qualis_status": "MANUAL_MISS", "qualis_estrato": None, "qualis_sigla": None, "qualis_nome_oficial": None, "qualis_quadrienio": None, "qualis_evento_id": None, "qualis_registro_id": None, "qualis_obs": "decisão manual: sem correspondência"})
                else:
                    record = self._db.get_by_record_id(override.qualis_registro_id)
                    if record is None:
                        raise ValueError(f"Registro Qualis desconhecido no override: {override.qualis_registro_id}")
                    resultado.update({"qualis_status": "MANUAL_OK", "qualis_estrato": record["estrato"], "qualis_sigla": record["sigla"], "qualis_nome_oficial": record["nome"], "qualis_quadrienio": record["quadrienio"], "qualis_evento_id": record["qualis_evento_id"], "qualis_registro_id": record["qualis_registro_id"], "qualis_obs": "decisão manual: associar"})
                resultado = validar_resultado(resultado)
            else:
                resultado = match(
                    nome_conferencia=venue,
                    ano=ano,
                    sigla_conferencia=sigla,
                    db=self._db,
                )
                resultado.setdefault("qualis_origem_decisao", "automatico")
                resultado.setdefault("qualis_politica_versao", "2")
            self._cache[chave_cache] = resultado
        diagnostico = {
            chave: valor
            for chave, valor in resultado.items()
            if not chave.startswith("_")
        }
        # Chaves curtas formam o contrato público. Prefixos qualis_* ficam por
        # compatibilidade com exportadores já existentes.
        diagnostico.update({
            "estrato": diagnostico["qualis_estrato"],
            "evento_oficial": diagnostico["qualis_nome_oficial"],
            "sigla_oficial": diagnostico["qualis_sigla"],
            "quadrienio": diagnostico["qualis_quadrienio"],
            "metodo": diagnostico["qualis_status"],
            "score_primeiro": diagnostico["qualis_score_fuzzy"],
            "margem_segundo": diagnostico["qualis_score_margem"],
            "candidatos": diagnostico["qualis_candidatos"],
            "motivo": diagnostico["qualis_obs"] or diagnostico["qualis_llm_motivo"],
            "necessita_revisao": diagnostico["qualis_requer_revisao"],
            "qualis_base_paths": dict(self._db.source_paths),
            "qualis_base_hashes": dict(self._db.source_hashes),
        })
        return diagnostico

    def get_estrato(
        self,
        venue: str,
        ano: Optional[int] = None,
        sigla: Optional[str] = None,
    ) -> Optional[str]:
        """Retorna o estrato ou ``None`` quando o caso requer revisão."""
        return self.get_match(venue, ano, sigla).get("qualis_estrato")
