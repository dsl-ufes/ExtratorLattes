"""
Pipeline completo QualisLens.

Orquestra as fases:
1. Carga da base Qualis (QualisDB)
2. Leitura do CSV de entrada
3. Para cada linha: pré-processamento → busca exata → fuzzy → LLM (se necessário)
4. Exportação do CSV de saída e da fila de revisão em CSV

Uso:
    python main.py --entrada data/entrada_exemplo.csv
    python main.py --entrada data/lista.csv --modelo mistral:7b
    python main.py --entrada data/lista.csv --modelo llama3.2:3b mistral:7b
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

from .constants import STATUSES_REVISAO
from .exporter import exportar_csv, exportar_fila_revisao, resumo_por_status, COLUNAS_OUTPUT
from .llm_reviewer import revisar
from .matcher import match, validar_resultado
from .qualis_db import get_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("qualislens.main")


def _ler_entrada(caminho: str) -> pd.DataFrame:
    """
    Lê o CSV de entrada validando colunas obrigatórias.

    Parameters
    ----------
    caminho:
        Caminho para o arquivo CSV.

    Returns
    -------
    pd.DataFrame

    Raises
    ------
    SystemExit
        Se colunas obrigatórias estiverem ausentes.
    """
    df = pd.read_csv(caminho, dtype=str)
    obrigatorias = {"titulo_artigo", "nome_conferencia", "ano_publicacao"}
    ausentes = obrigatorias - set(df.columns)
    if ausentes:
        logger.error("Colunas obrigatórias ausentes no CSV: %s", ausentes)
        sys.exit(1)
    logger.info("Entrada lida: %s  (%d artigos)", caminho, len(df))
    return df


def _processar_linha(
    row: pd.Series,
    db,
    modelos: Optional[list[str]] = None,
) -> dict:
    """
    Executa o pipeline completo para uma única linha do DataFrame de entrada.

    Fluxo:
    - Matcher tenta busca exata ou AUTO_FUZZY
    - Se precisar de LLM: chama llm_reviewer (com 1 ou 2 modelos)
    - Mescla resultado do matcher com resultado do LLM (se aplicável)

    Parameters
    ----------
    row:
        Linha do DataFrame de entrada.
    db:
        Instância QualisDB.
    modelos:
        Lista de modelos Ollama a usar. ``None`` desativa a LLM.

    Returns
    -------
    dict
        Dicionário com todas as colunas de saída Qualis.
    """
    nome = str(row.get("nome_conferencia", "") or "")
    sigla = str(row.get("sigla_conferencia", "") or "")
    try:
        ano = int(float(str(row.get("ano_publicacao", 0))))
    except (ValueError, TypeError):
        ano = 0

    sigla = sigla if sigla.strip() else None

    resultado = match(nome, ano, sigla, db)

    # Se o matcher resolveu (EXATO ou AUTO_FUZZY), retornar diretamente
    if not resultado.get("_precisa_llm"):
        return {k: resultado.get(k) for k in COLUNAS_OUTPUT}

    # Sem modelo explícito, preservar a decisão de revisão manual do matcher.
    if not modelos:
        return {k: resultado.get(k) for k in COLUNAS_OUTPUT}

    # Precisa de LLM e o usuário optou por ela.
    candidatos = resultado.get("_candidatos_lista", [])
    score_fuzzy = resultado.get("qualis_score_fuzzy", 0.0)
    nome_original = resultado.get("_pre", {}).get("nome_original", nome)
    titulo = str(row.get("titulo_artigo", "") or "") or None

    llm_resultado = revisar(nome_original, ano, candidatos, score_fuzzy, modelos, titulo_artigo=titulo)

    # Mesclar: campos do matcher (candidatos, score_fuzzy, obs) + campos do LLM
    saida = {k: resultado.get(k) for k in COLUNAS_OUTPUT}
    saida.update({
        "qualis_estrato": llm_resultado["qualis_estrato"],
        "qualis_sigla": llm_resultado["qualis_sigla"],
        "qualis_nome_oficial": llm_resultado["qualis_nome_oficial"],
        "qualis_quadrienio": llm_resultado["qualis_quadrienio"],
        "qualis_score_llm": llm_resultado["qualis_score_llm"],
        "qualis_status": llm_resultado["qualis_status"],
        "qualis_requer_revisao": llm_resultado["qualis_status"] in STATUSES_REVISAO,
        "qualis_llm_motivo": llm_resultado["qualis_llm_motivo"],
        "llm_m1_modelo": llm_resultado.get("llm_m1_modelo"),
        "llm_m1_confianca": llm_resultado.get("llm_m1_confianca"),
        "llm_m1_escolheu": llm_resultado.get("llm_m1_escolheu"),
        "llm_m2_modelo": llm_resultado.get("llm_m2_modelo"),
        "llm_m2_confianca": llm_resultado.get("llm_m2_confianca"),
        "llm_m2_escolheu": llm_resultado.get("llm_m2_escolheu"),
    })
    selecionado = next(
        (candidato for candidato in candidatos
         if candidato.get("sigla") == llm_resultado.get("qualis_sigla")
         and candidato.get("nome") == llm_resultado.get("qualis_nome_oficial")),
        None,
    )
    if selecionado:
        saida["qualis_evento_id"] = selecionado.get("qualis_evento_id")
        saida["qualis_registro_id"] = selecionado.get("qualis_registro_id")
    return validar_resultado(saida)


def executar(
    caminho_entrada: str,
    caminho_saida: Optional[str] = None,
    modelos: Optional[list[str]] = None,
) -> Path:
    """
    Executa o pipeline completo e exporta os resultados.

    Parameters
    ----------
    caminho_entrada:
        Caminho para o CSV de entrada.
    caminho_saida:
        Caminho explícito para o CSV de saída (opcional).
    modelos:
        Lista de modelos Ollama (None → desativado; 2 modelos → dupla verificação).

    Returns
    -------
    Path
        Caminho do CSV de saída.
    """
    if modelos:
        logger.info("Modelos LLM: %s", " + ".join(modelos))
    db = get_db()
    df = _ler_entrada(caminho_entrada)

    resultados: list[dict] = []
    total = len(df)

    for i, (_, row) in enumerate(df.iterrows(), start=1):
        titulo = str(row.get("titulo_artigo", ""))[:60]
        logger.info("[%d/%d] %s", i, total, titulo)
        try:
            r = _processar_linha(row, db, modelos)
        except Exception as exc:  # pragma: no cover
            logger.error("Erro inesperado na linha %d: %s", i, exc, exc_info=True)
            r = {k: None for k in COLUNAS_OUTPUT}
            r["qualis_status"] = "ERRO"
            r["qualis_requer_revisao"] = True
            r["qualis_llm_motivo"] = str(exc)
        resultados.append(r)

    df_resultado = df.copy()
    for col in COLUNAS_OUTPUT:
        df_resultado[col] = [r[col] for r in resultados]

    path_csv = exportar_csv(df_resultado, caminho_entrada, caminho_saida)
    path_revisao = exportar_fila_revisao(df_resultado, str(path_csv))

    resumo = resumo_por_status(df_resultado)
    logger.info("─" * 50)
    logger.info("RESUMO POR STATUS:")
    for status, count in resumo.items():
        logger.info("  %-20s %d", status, count)
    logger.info("─" * 50)
    logger.info("Saída CSV: %s", path_csv)
    logger.info("Fila de revisão: %s", path_revisao)

    return path_csv


def main() -> None:
    """Ponto de entrada da linha de comando."""
    parser = argparse.ArgumentParser(description="QualisLens — associação Qualis para conferências")
    parser.add_argument("--entrada", required=True, help="CSV de entrada")
    parser.add_argument("--saida", default=None, help="CSV de saída (padrão: <entrada>_output.csv)")
    parser.add_argument(
        "--modelo",
        nargs="+",
        default=None,
        metavar="MODELO",
        help=(
            "Modelo(s) Ollama a usar. Exemplos:\n"
            "  --modelo llama3.2:3b\n"
            "  --modelo llama3.2:3b mistral:7b  (dupla verificação)"
        ),
    )
    args = parser.parse_args()

    executar(args.entrada, args.saida, modelos=args.modelo)


if __name__ == "__main__":
    main()
