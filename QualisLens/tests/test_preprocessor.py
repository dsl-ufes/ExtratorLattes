"""Testes unitários para o módulo de pré-processamento (preprocessor.py)."""

import pytest
from QualisLens.qualislens.preprocessor import (
    extrair_acronimo,
    extrair_siglas_candidatas,
    extrair_siglas_fortes,
    normalizar,
    preprocessar_linha,
    separar_sigla_nome,
)


class TestNormalizar:
    def test_string_vazia(self):
        assert normalizar("") == ""

    def test_none_retorna_vazio(self):
        assert normalizar(None) == ""

    def test_converte_para_lowercase(self):
        assert normalizar("SBRC") == "sbrc"

    def test_remove_acentos(self):
        assert normalizar("Ciência") == "ciencia"
        assert normalizar("Inteligência") == "inteligencia"

    def test_traduz_tipo_de_evento(self):
        assert normalizar("Simpósio") == "symposium"
        assert normalizar("Simpósio") == normalizar("Symposium")

    def test_remove_stopword_on(self):
        result = normalizar("International Conference on Software Engineering")
        assert "on" not in result.split()
        assert "international" in result
        assert "conference" in result
        assert "software" in result
        assert "engineering" in result

    def test_remove_multiplas_stopwords(self):
        # "of", "the", "and" são stopwords
        result = normalizar("Journal of the Computer and Information Science")
        tokens = result.split()
        assert "of" not in tokens
        assert "the" not in tokens
        assert "and" not in tokens

    def test_remove_pontuacao(self):
        result = normalizar("IEEE/ACM Conference")
        assert "/" not in result
        assert "ieee" in result
        assert "acm" in result

    def test_remove_apostrofo(self):
        result = normalizar("Int'l Conference")
        assert "'" not in result

    def test_colapsa_espacos_extras(self):
        result = normalizar("  hello   world  ")
        assert "  " not in result
        assert result == result.strip()

    def test_nome_completo_conferencia(self):
        result = normalizar("International Conference on Software Engineering")
        assert result == "international conference software engineering"

    def test_nome_com_acentos_portugues(self):
        result = normalizar("Simpósio Brasileiro de Redes")
        assert result == "symposium brasileiro de redes"

    def test_separadores_viram_espaco(self):
        result = normalizar("IEEE/ACM International Conference")
        assert "/" not in result
        assert "ieee" in result
        assert "acm" in result
        assert "international" in result

    def test_hifens_e_pontuacao(self):
        result = normalizar("Comp.-Aided Design")
        assert "-" not in result
        assert "." not in result

    def test_sigla_normalizada(self):
        result = normalizar("SBRC")
        assert result == "sbrc"


class TestSepararSiglaNome:
    def test_formato_sigla_hifen_nome(self):
        sigla, nome = separar_sigla_nome("SBRC - Simpósio Brasileiro de Redes")
        assert sigla == "SBRC"
        assert nome == "Simpósio Brasileiro de Redes"

    def test_formato_sigla_dois_pontos_nome(self):
        sigla, nome = separar_sigla_nome("ICSE: International Conference on Software Engineering")
        assert sigla == "ICSE"
        assert nome == "International Conference on Software Engineering"

    def test_sem_sigla_retorna_none(self):
        sigla, nome = separar_sigla_nome("International Conference on Software Engineering")
        assert sigla is None
        assert nome == "International Conference on Software Engineering"

    def test_string_vazia(self):
        sigla, nome = separar_sigla_nome("")
        assert sigla is None
        assert nome == ""

    def test_none_retorna_none(self):
        sigla, nome = separar_sigla_nome(None)
        assert sigla is None

    def test_sigla_minima_dois_chars(self):
        sigla, nome = separar_sigla_nome("AB - Anything")
        assert sigla == "AB"
        assert nome == "Anything"

    def test_sigla_maxima_oito_chars(self):
        sigla, nome = separar_sigla_nome("ABCDEFGH - Anything")
        assert sigla == "ABCDEFGH"

    def test_sigla_nove_chars_captura(self):
        sigla, nome = separar_sigla_nome("ABCDEFGHI - Anything")
        assert sigla == "ABCDEFGHI"

    def test_sigla_com_digitos(self):
        sigla, nome = separar_sigla_nome("IEEE3 - Conference")
        assert sigla == "IEEE3"

    def test_nome_preservado_com_pontuacao(self):
        sigla, nome = separar_sigla_nome("VLDB - Very Large Data Bases")
        assert sigla == "VLDB"
        assert nome == "Very Large Data Bases"

    def test_espaco_variavel_ao_redor_separador(self):
        sigla1, nome1 = separar_sigla_nome("SBRC-Simpósio Brasileiro")
        sigla2, nome2 = separar_sigla_nome("SBRC  -  Simpósio Brasileiro")
        assert sigla1 == sigla2 == "SBRC"
        assert nome1 == nome2 == "Simpósio Brasileiro"


class TestExtrairAcronimo:
    def test_acronimo_basico(self):
        # ICCV: International Conference Computer Vision
        assert extrair_acronimo("International Conference on Computer Vision") == "ICCV"

    def test_ignora_stopwords(self):
        # "on", "of" são stopwords
        resultado = extrair_acronimo("Symposium on Theory of Computing")
        assert "O" not in resultado  # "on"
        assert "O" not in resultado  # "of"

    def test_ignora_organizadora(self):
        # "acm", "ieee" são stopwords de acrônimo
        resultado = extrair_acronimo("ACM Symposium on Theory of Computing")
        assert resultado.startswith("S")  # começa com Symposium

    def test_string_vazia(self):
        assert extrair_acronimo("") == ""

    def test_none_retorna_vazio(self):
        assert extrair_acronimo(None) == ""

    def test_maiusculas_na_saida(self):
        resultado = extrair_acronimo("International Conference on Software Engineering")
        assert resultado == resultado.upper()

    def test_icse(self):
        # ICSE: International Conference Software Engineering (sem "on")
        resultado = extrair_acronimo("International Conference on Software Engineering")
        assert resultado == "ICSE"

    def test_aaai(self):
        resultado = extrair_acronimo("AAAI Conference on Artificial Intelligence")
        # "aaai" está em STOPWORDS_ACR? Não - apenas ieee, acm, springer, elsevier
        # então "aaai" NÃO é filtrado
        assert "A" in resultado  # "aaai" contribui com A

    def test_acronimo_sem_stopwords(self):
        resultado = extrair_acronimo("Data Compression Conference")
        assert resultado == "DCC"


class TestPreprocessarLinha:
    def test_com_sigla_entrada(self):
        result = preprocessar_linha("International Conference on Software Engineering", "ICSE")
        assert result["sigla_original"] == "ICSE"
        assert result["sigla_norm"] == "icse"
        assert result["nome_original"] == "International Conference on Software Engineering"
        assert "on" not in result["nome_norm"].split()

    def test_sigla_extraida_do_nome(self):
        result = preprocessar_linha("SBRC - Simpósio Brasileiro de Redes")
        assert result["sigla_original"] == "SBRC"
        assert result["sigla_norm"] == "sbrc"
        assert result["nome_original"] == "Simpósio Brasileiro de Redes"

    def test_sigla_entrada_tem_prioridade(self):
        # sigla_entrada deve prevalecer sobre sigla extraída do nome
        result = preprocessar_linha("SBRC - Simpósio Brasileiro", "SBRC2024")
        assert result["sigla_original"] == "SBRC2024"

    def test_sem_sigla(self):
        result = preprocessar_linha("International Conference on Software Engineering")
        assert result["sigla_original"] is None
        assert result["sigla_norm"] is None

    def test_sigla_entrada_vazia_ignorada(self):
        result = preprocessar_linha("SBRC - Simpósio Brasileiro", "")
        # sigla_entrada vazia → usa a extraída do nome
        assert result["sigla_original"] == "SBRC"

    def test_nome_norm_sem_acentos(self):
        result = preprocessar_linha("Simpósio Brasileiro de Redes")
        assert "symposium" in result["nome_norm"]
        assert "ó" not in result["nome_norm"]

    def test_sigla_norm_lowercase(self):
        result = preprocessar_linha("Qualquer Nome", "AAAI")
        assert result["sigla_norm"] == "aaai"
