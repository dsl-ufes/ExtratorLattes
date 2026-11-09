"""
Módulo de exportação dos resultados do pipeline QualisLens.

Responsável por:
- Gerar CSV de saída com sufixo _output (nunca sobrescrever o original)
- Exportar fila de revisão manual em CSV editável
"""

import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from .constants import STATUSES_REVISAO, STATUS_EXATO, STATUS_AUTO_FUZZY

logger = logging.getLogger(__name__)

# Colunas adicionadas ao CSV de saída (produzidas pelo pipeline)
COLUNAS_OUTPUT = [
    "qualis_input_id",
    "qualis_evento_id",
    "qualis_registro_id",
    "qualis_estrato",
    "qualis_status",
    "qualis_requer_revisao",
    "qualis_sigla",
    "qualis_nome_oficial",
    "qualis_quadrienio",
    "qualis_score_fuzzy",
    "qualis_score_margem",
    "qualis_score_llm",
    "llm_m1_modelo",
    "llm_m1_confianca",
    "llm_m1_escolheu",
    "llm_m2_modelo",
    "llm_m2_confianca",
    "llm_m2_escolheu",
    "qualis_candidatos",
    "qualis_llm_motivo",
    "qualis_obs",
    "qualis_origem_decisao",
    "qualis_politica_versao",
    "qualis_justificativa",
    "qualis_decidido_por",
    "qualis_decidido_em",
]


def _formatar_candidatos_legivel(json_str) -> str:
    """
    Converte o JSON de candidatos para texto legível em tabela.

    Exemplo de saída: ``SBRC[A4] 100% | SBSC[A4] 75% | SBCM[A4] 75%``
    Mostra os 3 melhores candidatos; score arredondado para inteiro.
    """
    if not json_str or (isinstance(json_str, float) and pd.isna(json_str)):
        return ""
    try:
        candidatos = json.loads(json_str)
        partes = []
        for c in candidatos[:3]:
            sigla = c.get("sigla", "?")
            estrato = c.get("estrato", "?")
            score = c.get("score", 0)
            partes.append(f"{sigla}[{estrato}] {score:.0f}%")
        return " | ".join(partes)
    except (json.JSONDecodeError, TypeError):
        return str(json_str)


# ── Helpers para colunas derivadas ────────────────────────────────────────────

_STATUSES_AUTOMATICOS = {STATUS_EXATO, STATUS_AUTO_FUZZY}


def _passou_fuzzy(status) -> str:
    """'Sim' se o matching foi automático (sem LLM), 'Não' caso contrário."""
    if not status or (isinstance(status, float) and pd.isna(status)):
        return ""
    return "Sim" if status in _STATUSES_AUTOMATICOS else "Não"


def _confiabilidade(status, llm_confianca, score_fuzzy=0.0, m1_confianca=None, m2_confianca=None) -> str:
    """
    Rótulo de confiabilidade para orientar revisão humana.

    - Matching automático (EXATO/AUTO_FUZZY) → vazio (não precisa de revisão)
    - LLM confianca 'alta'  → 'Alta probabilidade de acerto pela LLM'
    - LLM confianca 'media' → 'Aceitável — vale a revisão'
    - Fuzzy >= 80 E ao menos 1 modelo com confianca 'alta' → 'Aceitável — vale a revisão'
    - Demais casos  → 'Resultado pouco confiável'
    """
    if not status or (isinstance(status, float) and pd.isna(status)):
        return ""
    if status in _STATUSES_AUTOMATICOS:
        return ""
    if llm_confianca == "alta":
        return "Alta probabilidade de acerto pela LLM"
    if llm_confianca == "media":
        return "Aceitável — vale a revisão"
    # Compensar confianca baixa/ausente: fuzzy alto + um modelo confiante
    try:
        fuzzy_alto = float(score_fuzzy) >= 80.0
    except (TypeError, ValueError):
        fuzzy_alto = False
    algum_modelo_alto = m1_confianca == "alta" or m2_confianca == "alta"
    if fuzzy_alto and algum_modelo_alto:
        return "Aceitável — vale a revisão"
    return "Resultado pouco confiável"
COLUNAS_REVISAO = [
    "revisao_escolha",
    "revisao_confirmado",
    "revisao_obs",
]


def _caminho_output(caminho_entrada: str, sufixo: str = "_output") -> Path:
    """
    Gera o caminho do arquivo de saída adicionando sufixo antes da extensão.

    Parameters
    ----------
    caminho_entrada:
        Caminho do arquivo original.
    sufixo:
        Sufixo a adicionar (padrão: ``_output``).

    Returns
    -------
    Path
        Caminho do arquivo de saída.
    """
    p = Path(caminho_entrada)
    return p.parent / f"{p.stem}{sufixo}{p.suffix}"


def exportar_csv(
    df_resultado: pd.DataFrame,
    caminho_entrada: str,
    caminho_saida: Optional[str] = None,
) -> Path:
    """
    Exporta o DataFrame de resultados como CSV.

    Nunca sobrescreve o arquivo original — gera novo arquivo com sufixo ``_output``.

    Parameters
    ----------
    df_resultado:
        DataFrame com todas as colunas originais mais as colunas Qualis.
    caminho_entrada:
        Caminho do CSV original (usado para gerar nome do arquivo de saída).
    caminho_saida:
        Caminho explícito de saída (opcional — se None, usa sufixo _output).

    Returns
    -------
    Path
        Caminho do arquivo gerado.
    """
    destino = Path(caminho_saida) if caminho_saida else _caminho_output(caminho_entrada)
    df_saida = df_resultado.copy()

    # Candidatos: JSON → texto legível
    if "qualis_candidatos" in df_saida.columns:
        df_saida["qualis_candidatos"] = df_saida["qualis_candidatos"].apply(_formatar_candidatos_legivel)

    # Colunas derivadas para orientar análise
    df_saida["passou_fuzzy"] = df_saida["qualis_status"].apply(_passou_fuzzy)
    df_saida["confiabilidade"] = df_saida.apply(
        lambda r: _confiabilidade(
            r["qualis_status"],
            r.get("qualis_score_llm"),
            r.get("qualis_score_fuzzy", 0.0),
            r.get("llm_m1_confianca"),
            r.get("llm_m2_confianca"),
        ), axis=1
    )

    # Reordenar colunas: entrada → resultado → diagnóstico → detalhe LLM → obs
    _ordem_qualis = [
        "qualis_estrato",
        "qualis_sigla",
        "qualis_nome_oficial",
        "qualis_quadrienio",
        "passou_fuzzy",
        "qualis_score_fuzzy",
        "qualis_score_margem",
        "qualis_status",
        "qualis_requer_revisao",
        "confiabilidade",
        "qualis_score_llm",
        "llm_m1_modelo",
        "llm_m1_confianca",
        "llm_m1_escolheu",
        "llm_m2_modelo",
        "llm_m2_confianca",
        "llm_m2_escolheu",
        "qualis_candidatos",
        "qualis_llm_motivo",
        "qualis_obs",
    ]
    _set_qualis = set(_ordem_qualis)
    colunas_entrada = [c for c in df_saida.columns if c not in _set_qualis]
    colunas_presentes = [c for c in _ordem_qualis if c in df_saida.columns]
    df_saida = df_saida[colunas_entrada + colunas_presentes]

    df_saida.to_csv(destino, index=False, encoding="utf-8-sig")
    logger.info("CSV de saída exportado: %s  (%d linhas)", destino, len(df_saida))
    return destino


def exportar_fila_revisao(
    df_resultado: pd.DataFrame,
    caminho_entrada: str,
    caminho_saida: Optional[str] = None,
) -> Path:
    """
    Exporta em CSV a fila de revisão manual.

    Filtra apenas os registros com status que requerem revisão humana
    (LLM_MISS, LLM_LOW_OK, LLM_LOW_MISS) e adiciona colunas vazias
    para o revisor preencher.

    Parameters
    ----------
    df_resultado:
        DataFrame completo de resultados.
    caminho_entrada:
        Caminho do arquivo de entrada (usado para nomear o arquivo de revisão).
    caminho_saida:
        Caminho explícito (opcional).

    Returns
    -------
    Path
        Caminho do arquivo CSV gerado.
    """
    p = Path(caminho_entrada)
    destino = (
        Path(caminho_saida)
        if caminho_saida
        else p.parent / f"{p.stem}_revisao.csv"
    )

    fila = df_resultado[
        df_resultado["qualis_requer_revisao"].astype(str).str.lower().eq("true")
        | df_resultado["qualis_status"].isin(STATUSES_REVISAO + ["ERRO"])
    ].copy()

    # A decision applies to one reported input, not to every occurrence.
    if "qualis_input_id" in fila.columns and not fila.empty:
        agg = {column: "first" for column in fila.columns if column != "qualis_input_id"}
        for column in ("titulo_artigo", "Docente", "docente", "ocorrencia_id"):
            if column in fila.columns:
                agg[column] = lambda values: " | ".join(sorted({str(v) for v in values if str(v)}))
        fila = fila.groupby("qualis_input_id", dropna=False, as_index=False).agg(agg)

    for col in COLUNAS_REVISAO:
        fila[col] = ""

    if "qualis_candidatos" in fila.columns:
        fila["qualis_candidatos"] = fila["qualis_candidatos"].apply(_formatar_candidatos_legivel)

    if fila.empty:
        logger.info("Nenhum registro na fila de revisão — arquivo não gerado.")
        # Gera arquivo vazio mesmo assim para consistência
        fila_vazia = pd.DataFrame(columns=list(df_resultado.columns) + COLUNAS_REVISAO)
        fila_vazia.to_csv(destino, index=False, encoding="utf-8-sig")
    else:
        fila.to_csv(destino, index=False, encoding="utf-8-sig")

    logger.info(
        "Fila de revisão exportada: %s  (%d registros para revisar)",
        destino,
        len(fila),
    )
    return destino


def resumo_por_status(df_resultado: pd.DataFrame) -> dict[str, int]:
    """
    Retorna contagem de registros por status.

    Parameters
    ----------
    df_resultado:
        DataFrame com coluna ``qualis_status``.

    Returns
    -------
    dict[str, int]
        Mapeamento {status: contagem}, ordenado por contagem desc.
    """
    if df_resultado.empty or "qualis_status" not in df_resultado.columns:
        return {}
    contagem = df_resultado["qualis_status"].value_counts().to_dict()
    return dict(sorted(contagem.items(), key=lambda x: x[1], reverse=True))
