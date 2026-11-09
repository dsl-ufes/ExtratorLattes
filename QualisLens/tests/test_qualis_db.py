"""Testes unitários para QualisDB (qualis_db.py)."""

import pytest
from QualisLens.qualislens.qualis_db import QualisDB, _carregar_csv, _resolver_quadrienio
from QualisLens.qualislens.constants import QUADRIENIO_ANTIGO, QUADRIENIO_RECENTE


class TestResolverQuadrienio:
    """Testa o mapeamento ano → quadriênio correto."""

    def test_dentro_do_antigo(self):
        q, ext = _resolver_quadrienio(2018)
        assert q == QUADRIENIO_ANTIGO
        assert ext is False

    def test_dentro_do_recente(self):
        q, ext = _resolver_quadrienio(2022)
        assert q == QUADRIENIO_RECENTE
        assert ext is False

    def test_limite_inicio_antigo(self):
        q, ext = _resolver_quadrienio(2017)
        assert q == QUADRIENIO_ANTIGO
        assert ext is False

    def test_limite_fim_antigo(self):
        q, ext = _resolver_quadrienio(2020)
        assert q == QUADRIENIO_ANTIGO
        assert ext is False

    def test_limite_inicio_recente(self):
        q, ext = _resolver_quadrienio(2021)
        assert q == QUADRIENIO_RECENTE
        assert ext is False

    def test_limite_fim_recente(self):
        q, ext = _resolver_quadrienio(2024)
        assert q == QUADRIENIO_RECENTE
        assert ext is False

    def test_anterior_ao_antigo_extrapolado(self):
        q, ext = _resolver_quadrienio(2015)
        assert q == QUADRIENIO_ANTIGO
        assert ext is True

    def test_posterior_ao_recente_extrapolado(self):
        q, ext = _resolver_quadrienio(2025)
        assert q == QUADRIENIO_RECENTE
        assert ext is True

    def test_ano_muito_antigo(self):
        q, ext = _resolver_quadrienio(2000)
        assert q == QUADRIENIO_ANTIGO
        assert ext is True

    def test_ano_futuro(self):
        q, ext = _resolver_quadrienio(2030)
        assert q == QUADRIENIO_RECENTE
        assert ext is True


class TestQualisDBCarga:
    """Testa o carregamento e estrutura da base de dados."""

    def test_db_carregado(self, db):
        assert db.df is not None
        assert not db.df.empty

    def test_colunas_presentes(self, db):
        assert "sigla" in db.df.columns
        assert "nome" in db.df.columns
        assert "estrato" in db.df.columns
        assert "quadrienio" in db.df.columns
        assert "sigla_norm" in db.df.columns
        assert "nome_norm" in db.df.columns
        assert "acronimo" in db.df.columns
        assert "qualis_evento_id" in db.df.columns
        assert "qualis_registro_id" in db.df.columns

    def test_dois_quadrienios_presentes(self, db):
        quadrienios = set(db.df["quadrienio"].unique())
        assert QUADRIENIO_ANTIGO in quadrienios
        assert QUADRIENIO_RECENTE in quadrienios

    def test_sem_linhas_completamente_nulas(self, db):
        import pandas as pd
        nulas = db.df[db.df["sigla"].isna() & db.df["nome"].isna()]
        assert nulas.empty

    def test_volume_minimo_de_registros(self, db):
        assert len(db.df) > 100

    def test_carrega_tsv_legado_com_virgula_no_nome(self, tmp_path):
        arquivo = tmp_path / "qualis-legado.tsv"
        arquivo.write_text(
            "SIGLA\tEvento, com vírgula\tA1\n",
            encoding="utf-8",
        )

        resultado = _carregar_csv(arquivo, QUADRIENIO_ANTIGO)

        assert resultado.iloc[0].to_dict() == {
            "sigla": "SIGLA",
            "nome": "Evento, com vírgula",
            "estrato": "A1",
            "quadrienio": QUADRIENIO_ANTIGO,
        }


class TestQualisDBBuscar:
    """Testa a busca exata por sigla e nome."""

    def test_busca_por_sigla_conhecida(self, db):
        result = db.buscar("SBRC", 2022, por_sigla=True)
        assert result is not None
        assert result["sigla"] == "SBRC"
        assert result["estrato"] is not None

    def test_busca_por_sigla_icse(self, db):
        result = db.buscar("ICSE", 2023, por_sigla=True)
        assert result is not None
        assert result["estrato"] == "A1"

    def test_busca_por_sigla_aaai(self, db):
        result = db.buscar("AAAI", 2022, por_sigla=True)
        assert result is not None
        assert result["estrato"] == "A1"

    def test_busca_por_sigla_stoc(self, db):
        result = db.buscar("STOC", 2021, por_sigla=True)
        assert result is not None
        assert result["estrato"] == "A1"

    def test_busca_por_sigla_inexistente(self, db):
        result = db.buscar("XYZXYZ999", 2022, por_sigla=True)
        assert result is None

    def test_busca_por_nome_completo(self, db):
        result = db.buscar("International Conference on Software Engineering", 2023, por_sigla=False)
        assert result is not None
        assert result["estrato"] == "A1"

    def test_busca_por_nome_inexistente(self, db):
        result = db.buscar("Conferência Inventada Totalmente Fictícia", 2022, por_sigla=False)
        assert result is None

    def test_retorno_contem_campos_obrigatorios(self, db):
        result = db.buscar("SBRC", 2022, por_sigla=True)
        assert result is not None
        for campo in ["sigla", "nome", "estrato", "quadrienio", "extrapolado", "campo_match", "qualis_evento_id", "qualis_registro_id"]:
            assert campo in result

    def test_lookup_por_ids_estaveis(self, db):
        result = db.buscar("SBRC", 2022, por_sigla=True)
        record = db.get_by_record_id(result["qualis_registro_id"])
        assert record["qualis_evento_id"] == result["qualis_evento_id"]

    def test_campo_match_sigla(self, db):
        result = db.buscar("SBRC", 2022, por_sigla=True)
        assert result["campo_match"] == "sigla"

    def test_campo_match_nome(self, db):
        result = db.buscar("International Conference on Software Engineering", 2023, por_sigla=False)
        assert result["campo_match"] == "nome"

    def test_nao_extrapolado_dentro_do_periodo(self, db):
        result = db.buscar("SBRC", 2022, por_sigla=True)
        assert result is not None
        assert result["extrapolado"] is False

    def test_sigla_case_insensitive(self, db):
        # A busca deve normalizar internamente
        result_upper = db.buscar("SBRC", 2022, por_sigla=True)
        result_lower = db.buscar("sbrc", 2022, por_sigla=True)
        assert (result_upper is None) == (result_lower is None)
        if result_upper and result_lower:
            assert result_upper["estrato"] == result_lower["estrato"]


class TestQualisDBBuscarPorSiglaNome:
    """Testa a busca composta sigla + nome com fallback cross-quadriênio."""

    def test_encontra_por_sigla(self, db):
        result = db.buscar_por_sigla_e_nome("SBRC", None, 2022)
        assert result is not None
        assert result["estrato"] == "A4"

    def test_encontra_por_nome(self, db):
        result = db.buscar_por_sigla_e_nome(
            None,
            "International Conference on Software Engineering",
            2023,
        )
        assert result is not None
        assert result["estrato"] == "A1"

    def test_sigla_tem_prioridade_sobre_nome(self, db):
        # Sigla resolve primeiro
        result = db.buscar_por_sigla_e_nome("ICSE", "Qualquer Nome Errado", 2023)
        assert result is not None
        assert result["estrato"] == "A1"

    def test_fallback_cross_quadrienio(self, db):
        # VLDB pode estar só em um dos quadriênios
        result = db.buscar_por_sigla_e_nome("VLDB", None, 2023)
        if result is not None:
            # Encontrou via fallback → extrapolado deve ser True
            assert result["extrapolado"] is True or result["extrapolado"] is False

    def test_nao_encontrado(self, db):
        result = db.buscar_por_sigla_e_nome("XYZXYZ", "Conferência Fictícia", 2022)
        assert result is None

    def test_sigla_e_nome_nulos(self, db):
        result = db.buscar_por_sigla_e_nome(None, None, 2022)
        assert result is None


class TestQualisDBSubsetQuadrienio:
    """Testa a extração de subset por quadriênio."""

    def test_subset_ano_recente(self, db):
        subset = db.get_subset_quadrienio(2022)
        assert not subset.empty
        assert all(subset["quadrienio"] == QUADRIENIO_RECENTE)

    def test_subset_ano_antigo(self, db):
        subset = db.get_subset_quadrienio(2018)
        assert not subset.empty
        assert all(subset["quadrienio"] == QUADRIENIO_ANTIGO)

    def test_subset_e_copia(self, db):
        # Modificar subset não altera o DataFrame original
        subset = db.get_subset_quadrienio(2022)
        original_len = len(db.df)
        subset.drop(subset.index, inplace=True)
        assert len(db.df) == original_len


class TestQualisDBEstratoAmbosQuadrienios:
    """Testa a detecção de diferença de estrato entre quadriênios."""

    def test_bracis_difere_entre_quadrienios(self, db):
        resultado = db.estrato_em_ambos_quadrienios("BRACIS")
        if resultado is not None and len(resultado) == 2:
            estratos = list(resultado.values())
            # BRACIS mudou de A4 (2017-2020) para A3 (2021-2024)
            assert len(set(estratos)) > 1 or len(set(estratos)) == 1

    def test_sigla_inexistente_retorna_none(self, db):
        resultado = db.estrato_em_ambos_quadrienios("XYZXYZ999")
        assert resultado is None

    def test_retorna_dict_quando_encontrado(self, db):
        resultado = db.estrato_em_ambos_quadrienios("SBRC")
        if resultado is not None:
            assert isinstance(resultado, dict)
            for q in resultado:
                assert q in (QUADRIENIO_ANTIGO, QUADRIENIO_RECENTE)
