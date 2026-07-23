"""Testes unitários para o algoritmo de matching fuzzy (matcher.py)."""

import pytest
from QualisLens.qualislens.matcher import _score_hibrido, _token_level_fuzzy, match
from QualisLens.qualislens.constants import (
    STATUS_AUTO_FUZZY,
    STATUS_EXATO,
    STATUS_REVISAO_MANUAL,
    THRESHOLD_AUTO,
    THRESHOLD_CANDIDATOS_RUINS,
)


class TestTokenLevelFuzzy:
    """Testa a comparação token-a-token com partial_ratio ponderado."""

    def test_identicos(self):
        assert _token_level_fuzzy("sbrc", "sbrc") == 100.0

    def test_query_vazia(self):
        assert _token_level_fuzzy("", "computing") == 0.0

    def test_candidato_vazio(self):
        assert _token_level_fuzzy("computing", "") == 0.0

    def test_ambos_vazios(self):
        assert _token_level_fuzzy("", "") == 0.0

    def test_token_letra_unica_filtrado(self):
        # Tokens com < 2 chars são descartados como ruído
        score = _token_level_fuzzy("a b c", "alpha beta gamma")
        assert score == 0.0

    def test_abreviacao_comp_computing(self):
        # "comp" é prefixo de "computing" → partial_ratio alto
        score = _token_level_fuzzy("comp", "computing")
        assert score > 70.0

    def test_abreviacao_int_international(self):
        score = _token_level_fuzzy("int", "international")
        assert score > 70.0

    def test_abreviacao_conf_conference(self):
        score = _token_level_fuzzy("conf", "conference")
        assert score > 70.0

    def test_multiplos_tokens_abreviados(self):
        # "int conf" vs "international conference"
        score = _token_level_fuzzy("int conf", "international conference")
        assert score > 60.0

    def test_ponderacao_por_comprimento(self):
        # Tokens mais longos têm maior peso
        # "computing" (9 chars) pesa mais do que "net" (3 chars)
        score_longo = _token_level_fuzzy("computing vision", "computing")
        score_curto = _token_level_fuzzy("net vision", "computing")
        # "computing vision" deve ter score maior que "net vision" contra "computing"
        assert score_longo > score_curto

    def test_tokens_completamente_diferentes(self):
        score = _token_level_fuzzy("database systems", "machine learning")
        assert score < 50.0


class TestScoreHibrido:
    """Testa o score composto (token_set + token_sort + fuzzy-token + acrônimo)."""

    def test_nomes_identicos(self):
        score = _score_hibrido("computing", "computing", "", "")
        assert score == 100.0

    def test_reordenacao_de_palavras(self):
        # token_sort_ratio é robusto a reordenação
        score = _score_hibrido("distributed computing", "computing distributed", "", "")
        assert score >= 95.0

    def test_subset_de_tokens(self):
        # token_set_ratio lida bem quando query é subconjunto
        score = _score_hibrido("theory computing", "symposium theory computing", "", "")
        assert score >= 85.0

    def test_acronimo_curto_ignorado(self):
        # Acrônimos com < 3 chars são ignorados
        s1 = _score_hibrido("machine learning", "machine learning", "", "")
        s2 = _score_hibrido("machine learning", "machine learning", "ML", "ML")
        assert s1 == s2

    def test_acronimo_longo_ativo(self):
        # Acrônimos >= 3 chars são usados como sinal secundário
        s_acr = _score_hibrido("aaaa bbbb cccc", "xxxx yyyy zzzz", "ABC", "ABC")
        s_sem = _score_hibrido("aaaa bbbb cccc", "xxxx yyyy zzzz", "", "")
        # Com acrônimo igual o score pode ser maior (ou igual se outros sinais dominam)
        assert s_acr >= s_sem

    def test_completamente_diferente(self):
        score = _score_hibrido("xyz123abc", "database systems", "", "")
        assert score < 50.0

    def test_resultado_entre_zero_e_cem(self):
        for q, c in [
            ("", ""),
            ("sbrc", "sbrc"),
            ("abc def", "xyz uvw"),
            ("int conf comp", "international conference computing"),
        ]:
            score = _score_hibrido(q, c, "", "")
            assert 0.0 <= score <= 100.0, f"score={score} fora de [0,100] para ({q!r}, {c!r})"

    def test_abreviacao_nome_conferencia(self):
        # "ann acm symp theory comp" vs "acm symposium theory computing"
        score = _score_hibrido(
            "ann acm symp theory comp",
            "acm symposium theory computing",
            "",
            "",
        )
        assert score >= 70.0


class TestMatch:
    """Testa o pipeline de matching completo (sem LLM)."""

    # ── Casos EXATO ─────────────────────────────────────────────────────────────

    def test_exato_por_sigla(self, db):
        result = match("SBRC - Simpósio Brasileiro de Redes de Computadores", 2022, "SBRC", db)
        assert result["qualis_status"] == STATUS_EXATO
        assert result["qualis_estrato"] == "A4"
        assert result["qualis_score_fuzzy"] == 100.0

    def test_exato_por_sigla_icse(self, db):
        result = match("International Conference on Software Engineering", 2023, "ICSE", db)
        assert result["qualis_status"] == STATUS_EXATO
        assert result["qualis_estrato"] == "A1"

    def test_acronimo_isolado_conhecido_resolve(self, db):
        result = match("ICSE 2023", 2023, None, db)
        assert result["qualis_status"] == STATUS_EXATO
        assert result["qualis_sigla"] == "ICSE"

    def test_workshop_nao_casa_com_data_por_sigla_extraida(self, db):
        result = match("Data-Driven Workshop on X", 2023, None, db)
        assert not (result["qualis_status"] == STATUS_EXATO and result["qualis_sigla"] == "DATA")

    def test_parentetico_topico_nao_substitui_nome_por_ai_canadense(self, db):
        result = match("International Conference on Artificial Intelligence (AI) Applications", 2023, None, db)
        assert not (result["qualis_status"] == STATUS_EXATO and result["qualis_sigla"] == "AI")

    def test_exato_por_sigla_aaai(self, db):
        result = match("AAAI Conference on Artificial Intelligence", 2022, "AAAI", db)
        assert result["qualis_status"] == STATUS_EXATO
        assert result["qualis_estrato"] == "A1"

    def test_exato_por_sigla_stoc(self, db):
        result = match("Annual Symposium on Theory of Computing", 2021, "STOC", db)
        assert result["qualis_status"] == STATUS_EXATO
        assert result["qualis_estrato"] == "A1"

    def test_exato_retorna_candidatos_para_rastreabilidade(self, db):
        result = match("SBRC - Simpósio Brasileiro", 2022, "SBRC", db)
        # Candidatos são sempre retornados, mesmo em match exato
        assert result["qualis_candidatos"] is not None
        assert result["_candidatos_lista"] is not None

    def test_exato_sem_llm_necessario(self, db):
        result = match("International Conference on Software Engineering", 2023, "ICSE", db)
        assert not result.get("_precisa_llm", False)
        assert result.get("qualis_llm_motivo") is None

    # ── Casos AUTO_FUZZY ──────────────────────────────────────────────────────

    def test_auto_fuzzy_abreviado_ccgrid(self, db):
        # "Int'l Symp. on Cluster, Cloud and Grid Computing" sem sigla
        result = match("Int'l Symp. on Cluster, Cloud and Grid Computing", 2021, None, db)
        assert result["qualis_status"] == STATUS_AUTO_FUZZY
        assert result["qualis_score_fuzzy"] >= THRESHOLD_AUTO
        assert result["qualis_estrato"] is not None

    def test_auto_fuzzy_abreviado_cbms(self, db):
        result = match("IEEE Int'l Symp. on Computer-Based Medical Systems", 2020, None, db)
        assert result["qualis_status"] == STATUS_AUTO_FUZZY
        assert result["qualis_score_fuzzy"] >= THRESHOLD_AUTO

    def test_auto_fuzzy_score_minimo(self, db):
        # Qualquer AUTO_FUZZY deve ter score >= THRESHOLD_AUTO
        result = match("Int'l Symp. on Cluster, Cloud and Grid Computing", 2021, None, db)
        if result["qualis_status"] == STATUS_AUTO_FUZZY:
            assert result["qualis_score_fuzzy"] >= THRESHOLD_AUTO

    def test_auto_fuzzy_sem_llm_necessario(self, db):
        result = match("Int'l Symp. on Cluster, Cloud and Grid Computing", 2021, None, db)
        assert not result.get("_precisa_llm", False)

    # ── Casos sem decisão automática ─────────────────────────────────────────

    def test_revisao_nome_totalmente_diferente(self, db):
        # Nome sem nenhuma relação com qualquer conferência conhecida
        result = match("zzz xqqq fyyyy 123456789", 2022, None, db)
        assert result["qualis_status"] == STATUS_REVISAO_MANUAL
        assert result["qualis_estrato"] is None
        assert result["qualis_score_fuzzy"] < THRESHOLD_CANDIDATOS_RUINS

    def test_revisao_sem_llm_necessario(self, db):
        # Score muito baixo → não precisa de LLM (candidatos são ruído)
        result = match("zzz xqqq fyyyy 123456789", 2022, None, db)
        assert result.get("_precisa_llm") is False

    # ── Casos FUZZY_PENDENTE (precisa LLM) ───────────────────────────────────

    def test_precisa_llm_score_intermediario(self, db):
        # Scores entre THRESHOLD_CANDIDATOS_RUINS e THRESHOLD_AUTO requerem LLM
        # Este teste verifica o campo _precisa_llm quando aplicável
        result = match("Wksp Embedded Systems Security", 2020, None, db)
        if result.get("_precisa_llm"):
            assert result["qualis_status"] == STATUS_REVISAO_MANUAL
            s = result["qualis_score_fuzzy"]
            assert THRESHOLD_CANDIDATOS_RUINS <= s < THRESHOLD_AUTO
        else:
            # Pode ter resolvido em AUTO_FUZZY ou exigido revisão — também válido
            assert result["qualis_status"] in (STATUS_AUTO_FUZZY, STATUS_REVISAO_MANUAL)

    # ── Campos obrigatórios no retorno ───────────────────────────────────────

    def test_retorno_tem_todos_os_campos(self, db):
        result = match("SBRC", 2022, "SBRC", db)
        campos = [
            "qualis_estrato",
            "qualis_nome_oficial",
            "qualis_quadrienio",
            "qualis_score_fuzzy",
            "qualis_score_llm",
            "qualis_status",
            "qualis_candidatos",
            "qualis_llm_motivo",
            "qualis_obs",
            "_pre",
            "_candidatos_lista",
        ]
        for campo in campos:
            assert campo in result, f"Campo ausente: {campo}"

    # ── Extrapolação de quadriênio ────────────────────────────────────────────

    def test_obs_extrapolado_quando_fora_do_periodo(self, db):
        # VLDB está na base 2017-2020; buscar em 2023 deve extrapolá-la
        result = match("VLDB - Very Large Data Bases", 2023, "VLDB", db)
        if result["qualis_quadrienio"] == "2017-2020":
            assert result["qualis_status"] == STATUS_REVISAO_MANUAL
            assert result["qualis_requer_revisao"] is True
