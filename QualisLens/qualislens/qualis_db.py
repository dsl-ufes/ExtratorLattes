"""
Módulo de carga e consulta das bases Qualis para conferências.

Carrega os dois arquivos xlsx (quadriênios 2017-2020 e 2021-2024), normaliza os
campos e expõe a função `buscar` para resolução de um artigo pelo ano de publicação.
"""

import logging
import re
import hashlib
from pathlib import Path
from typing import Optional

from .utils import strip_accents as _strip_accents

import pandas as pd

from .constants import (
    ANO_FIM_ANTIGO,
    ANO_FIM_RECENTE,
    ANO_INICIO_ANTIGO,
    ANO_INICIO_RECENTE,
    PATH_BASE_2017,
    PATH_BASE_2025,
    QUADRIENIO_ANTIGO,
    QUADRIENIO_RECENTE,
)
from .preprocessor import extrair_acronimo, normalizar

logger = logging.getLogger(__name__)

# Colunas padronizadas internamente
_COL_SIGLA = "sigla"
_COL_NOME = "nome"
_COL_ESTRATO = "estrato"
_COL_SIGLA_NORM = "sigla_norm"
_COL_NOME_NORM = "nome_norm"
_COL_QUADRIENIO = "quadrienio"


def _id(*parts: object) -> str:
    """Stable, row-order independent opaque identity."""
    value = "\x1f".join(str(part).strip() for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _normalizar_campo(valor: object) -> str:
    """
    Normaliza um valor de campo para comparação:
    - Converte para string e lowercase
    - Remove acentos
    - Remove pontuação
    - Colapsa espaços

    Parameters
    ----------
    valor:
        Qualquer valor (str, float, NaN…).

    Returns
    -------
    str
        String normalizada, ou string vazia se o valor for nulo.
    """
    if pd.isna(valor):
        return ""
    texto = str(valor).lower().strip()
    texto = _strip_accents(texto)
    texto = re.sub(r"[^\w\s]", " ", texto)   # pontuação → espaço
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def _carregar_csv(path: str, quadrienio: str) -> pd.DataFrame:
    """
    Carrega um CSV Qualis com colunas ``Sigla``, ``Nome do evento``, ``Estrato``.

    Parameters
    ----------
    path:
        Caminho para o arquivo CSV.
    quadrienio:
        Valor a atribuir à coluna ``quadrienio`` (sobrescreve a coluna do CSV
        caso já exista, garantindo consistência).

    Returns
    -------
    pd.DataFrame
        DataFrame com colunas padronizadas + quadrienio.
    """
    arquivo = Path(path)
    if not arquivo.is_file():
        raise FileNotFoundError(f"Base Qualis não encontrada: {arquivo}")

    # As bases novas usam CSV com cabeçalho. O classificador antigo do projeto
    # usa TSV sem cabeçalho; ele contém a mesma estrutura do período 2017-2020
    # e continua aceito para não quebrar configurações existentes. Detecte o
    # TSV antes do parser CSV: nomes de eventos podem conter vírgulas.
    with arquivo.open(encoding="utf-8-sig") as stream:
        primeira_linha = stream.readline()

    def carregar_tsv_legado():
        return pd.read_csv(
            arquivo,
            sep="\t",
            header=None,
            names=["Sigla", "Nome do evento", "Estrato"],
            usecols=[0, 1, 2],
            encoding="utf-8-sig",
        )

    if "\t" in primeira_linha:
        df = carregar_tsv_legado()
    else:
        df = pd.read_csv(arquivo, encoding="utf-8-sig")

    colunas_esperadas = {"Sigla", "Nome do evento", "Estrato"}
    if not colunas_esperadas.issubset(df.columns):
        df = carregar_tsv_legado()

    ausentes = colunas_esperadas - set(df.columns)
    if ausentes:
        raise ValueError(
            f"Base Qualis inválida em {arquivo}: colunas ausentes {sorted(ausentes)}"
        )
    df = df.rename(columns={
        "Sigla": _COL_SIGLA,
        "Nome do evento": _COL_NOME,
        "Estrato": _COL_ESTRATO,
    })
    df[_COL_QUADRIENIO] = quadrienio
    return df[[_COL_SIGLA, _COL_NOME, _COL_ESTRATO, _COL_QUADRIENIO]]


def _carregar_df_2017(path: str) -> pd.DataFrame:
    return _carregar_csv(path, QUADRIENIO_ANTIGO)


def _carregar_df_2025(path: str) -> pd.DataFrame:
    return _carregar_csv(path, QUADRIENIO_RECENTE)


def _resolver_quadrienio(ano: int) -> tuple[str, bool]:
    """
    Determina qual quadriênio usar para um dado ano de publicação.

    Parameters
    ----------
    ano:
        Ano de publicação do artigo.

    Returns
    -------
    tuple[str, bool]
        (quadrienio, extrapolado) — `extrapolado` é True quando o ano
        está fora do intervalo coberto pelas bases.
    """
    if ANO_INICIO_ANTIGO <= ano <= ANO_FIM_ANTIGO:
        return QUADRIENIO_ANTIGO, False
    if ANO_INICIO_RECENTE <= ano <= ANO_FIM_RECENTE:
        return QUADRIENIO_RECENTE, False
    if ano < ANO_INICIO_ANTIGO:
        return QUADRIENIO_ANTIGO, True
    # ano > ANO_FIM_RECENTE
    return QUADRIENIO_RECENTE, True


class QualisDB:
    """
    Base de dados Qualis unificada para conferências.

    Carrega os dois xlsx, normaliza os campos de sigla e nome, e expõe
    a função `buscar` para consulta por sigla ou nome e ano de publicação.
    """

    def __init__(
        self,
        path_2017: str = PATH_BASE_2017,
        path_2025: str = PATH_BASE_2025,
    ) -> None:
        """
        Inicializa e carrega os dois arquivos xlsx.

        Parameters
        ----------
        path_2017:
            Caminho para a base Qualis 2017-2020.
        path_2025:
            Caminho para a base Qualis 2021-2024.
        """
        # data/ está um nível acima de qualislens/
        base_dir = Path(__file__).parent.parent
        p17 = Path(path_2017) if Path(path_2017).is_absolute() else base_dir / path_2017
        p25 = Path(path_2025) if Path(path_2025).is_absolute() else base_dir / path_2025

        df17 = _carregar_df_2017(str(p17))
        df25 = _carregar_df_2025(str(p25))

        self.df: pd.DataFrame = pd.concat([df17, df25], ignore_index=True)

        # Remover linhas completamente vazias
        self.df = self.df.dropna(subset=[_COL_SIGLA, _COL_NOME], how="all")

        # Campos normalizados para busca
        self.df[_COL_SIGLA_NORM] = self.df[_COL_SIGLA].apply(_normalizar_campo)
        self.df[_COL_NOME_NORM] = self.df[_COL_NOME].apply(normalizar)
        self.df["qualis_evento_id"] = self.df.apply(
            lambda row: _id("evento", row[_COL_SIGLA_NORM], row[_COL_NOME_NORM]), axis=1
        )
        self.df["qualis_registro_id"] = self.df.apply(
            lambda row: _id("registro", row["qualis_evento_id"], row[_COL_QUADRIENIO], row[_COL_ESTRATO]), axis=1
        )
        # A hash collision is distinct from a repeated source record.
        for col, payload in (("qualis_evento_id", [_COL_SIGLA_NORM, _COL_NOME_NORM]), ("qualis_registro_id", ["qualis_evento_id", _COL_QUADRIENIO, _COL_ESTRATO])):
            if any(
                len({tuple(map(str, values)) for values in group[payload].itertuples(index=False, name=None)}) > 1
                for _, group in self.df.groupby(col)
            ):
                raise ValueError(f"Colisão de identidade Qualis em {col}")
        self.source_paths = {QUADRIENIO_ANTIGO: str(p17), QUADRIENIO_RECENTE: str(p25)}
        self.source_hashes = {q: hashlib.sha256(Path(path).read_bytes()).hexdigest() for q, path in self.source_paths.items()}

        # Acrônimo pré-computado para matching secundário
        self.df["acronimo"] = self.df[_COL_NOME].apply(
            lambda v: extrair_acronimo(str(v)) if pd.notna(v) else ""
        )

        logger.info(
            "QualisDB carregado: %d registros (%d de 2017-2020, %d de 2021-2024)",
            len(self.df),
            len(df17),
            len(df25),
        )

    def _subset_por_quadrienio(self, quadrienio: str) -> pd.DataFrame:
        """Retorna apenas os registros do quadriênio especificado."""
        return self.df[self.df[_COL_QUADRIENIO] == quadrienio]

    def buscar(
        self,
        sigla_ou_nome: str,
        ano: int,
        por_sigla: bool = True,
    ) -> Optional[dict]:
        """
        Busca exata de um evento pelo campo de sigla ou nome normalizado,
        considerando o quadriênio correto para o ano informado.

        Retorna o primeiro registro encontrado, ou None se não houver match.

        Parameters
        ----------
        sigla_ou_nome:
            Sigla ou nome do evento a buscar (será normalizado internamente).
        ano:
            Ano de publicação do artigo — determina qual quadriênio usar.
        por_sigla:
            Se True, busca pelo campo sigla; se False, busca pelo nome.

        Returns
        -------
        Optional[dict]
            Dicionário com as chaves:
            - sigla, nome, estrato, quadrienio, extrapolado, campo_match
            Retorna None se não encontrado.
        """
        quadrienio, extrapolado = _resolver_quadrienio(ano)
        subset = self._subset_por_quadrienio(quadrienio)
        termo_norm = (
            _normalizar_campo(sigla_ou_nome)
            if por_sigla
            else normalizar(sigla_ou_nome)
        )
        if not termo_norm:
            return None

        campo_busca = _COL_SIGLA_NORM if por_sigla else _COL_NOME_NORM
        mascara = subset[campo_busca] == termo_norm
        resultados = subset[mascara].drop_duplicates(
            subset=[_COL_SIGLA, _COL_NOME, _COL_ESTRATO, _COL_QUADRIENIO]
        )

        if resultados.empty:
            return None

        if len(resultados) > 1:
            # Sigla ambígua — sinalizar para revisão manual
            logger.warning(
                "Sigla/nome ambíguo '%s' retornou %d resultados no quadriênio %s",
                sigla_ou_nome,
                len(resultados),
                quadrienio,
            )

        row = resultados.iloc[0]
        return self._row_dict(row, extrapolado, "sigla" if por_sigla else "nome", len(resultados) > 1)

    def _row_dict(self, row, extrapolado: bool, campo_match: str, ambiguo: bool = False) -> dict:
        return {
            "sigla": row[_COL_SIGLA],
            "nome": row[_COL_NOME],
            "estrato": row[_COL_ESTRATO],
            "quadrienio": row[_COL_QUADRIENIO],
            "extrapolado": extrapolado,
            "campo_match": campo_match,
            "ambiguo": ambiguo,
            "qualis_evento_id": row["qualis_evento_id"],
            "qualis_registro_id": row["qualis_registro_id"],
        }

    def buscar_por_sigla_e_nome(
        self, sigla: Optional[str], nome: Optional[str], ano: int
    ) -> Optional[dict]:
        """
        Tenta busca exata primeiro por sigla, depois por nome normalizado.

        Fluxo:
        1. Busca no quadriênio primário do ano (por sigla, depois por nome).
        2. Se não encontrar, tenta o outro quadriênio como fallback (extrapolado=True).
           Isso cobre conferências que aparecem em apenas um dos quadriênios.

        Parameters
        ----------
        sigla:
            Sigla do evento (pode ser None).
        nome:
            Nome completo do evento (pode ser None).
        ano:
            Ano de publicação.

        Returns
        -------
        Optional[dict]
            Resultado da busca, ou None se não encontrado.
        """
        # 1. Busca no quadriênio primário
        if sigla:
            resultado = self.buscar(sigla, ano, por_sigla=True)
            if resultado:
                return resultado
        if nome:
            resultado = self.buscar(nome, ano, por_sigla=False)
            if resultado:
                return resultado

        # 2. Fallback: tenta o quadriênio alternativo (conferência pode ter sido
        #    classificada apenas em um dos períodos)
        quadrienio_primario, _ = _resolver_quadrienio(ano)
        quadrienio_alternativo = (
            QUADRIENIO_ANTIGO
            if quadrienio_primario == QUADRIENIO_RECENTE
            else QUADRIENIO_RECENTE
        )
        subset_alt = self._subset_por_quadrienio(quadrienio_alternativo)
        for campo_busca, termo in [
            (_COL_SIGLA_NORM, _normalizar_campo(sigla) if sigla else None),
            (_COL_NOME_NORM, normalizar(nome) if nome else None),
        ]:
            if not termo:
                continue
            mascara = subset_alt[campo_busca] == termo
            resultados = subset_alt[mascara].drop_duplicates(
                subset=[_COL_SIGLA, _COL_NOME, _COL_ESTRATO, _COL_QUADRIENIO]
            )
            if not resultados.empty:
                row = resultados.iloc[0]
                logger.info(
                    "buscar_por_sigla_e_nome: fallback cross-quadriênio → '%s' encontrada em %s (ano=%d)",
                    row[_COL_SIGLA],
                    quadrienio_alternativo,
                    ano,
                )
                return self._row_dict(row, True, "sigla" if campo_busca == _COL_SIGLA_NORM else "nome", len(resultados) > 1)

        return None

    def get_subset_quadrienio(self, ano: int) -> pd.DataFrame:
        """
        Retorna o subset do DataFrame para o quadriênio correspondente ao ano.

        Útil para o matcher fuzzy, que opera sobre o subset correto.

        Parameters
        ----------
        ano:
            Ano de publicação.

        Returns
        -------
        pd.DataFrame
            Subset filtrado por quadriênio.
        """
        quadrienio, _ = _resolver_quadrienio(ano)
        return self._subset_por_quadrienio(quadrienio).copy()

    def estrato_em_ambos_quadrienios(self, sigla: str) -> Optional[dict]:
        """
        Verifica se a mesma sigla tem estratos diferentes entre os dois quadriênios.

        Parameters
        ----------
        sigla:
            Sigla do evento.

        Returns
        -------
        Optional[dict]
            Dicionário {quadrienio: estrato} para cada quadriênio onde a sigla
            aparece, ou None se a sigla não estiver em nenhum quadriênio.
        """
        sigla_norm = _normalizar_campo(sigla)
        resultados = self.df[self.df[_COL_SIGLA_NORM] == sigla_norm]
        if resultados.empty:
            return None
        return {
            row[_COL_QUADRIENIO]: row[_COL_ESTRATO]
            for _, row in resultados.iterrows()
        }

    def get_by_event_id(self, qualis_evento_id: str) -> list[dict]:
        return [self._row_dict(row, False, "id") for _, row in self.df[self.df["qualis_evento_id"] == qualis_evento_id].iterrows()]

    def get_by_record_id(self, qualis_registro_id: str) -> Optional[dict]:
        rows = self.df[self.df["qualis_registro_id"] == qualis_registro_id]
        return None if rows.empty else self._row_dict(rows.iloc[0], False, "id")


# ── Instância singleton (carregada uma única vez por processo) ────────────────
_db_instance: Optional[QualisDB] = None


def get_db() -> QualisDB:
    """
    Retorna a instância singleton de QualisDB.

    Na primeira chamada, carrega os xlsx. Chamadas subsequentes reutilizam
    a instância já carregada.

    Returns
    -------
    QualisDB
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = QualisDB()
    return _db_instance
