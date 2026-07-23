"""Corpus rotulado manualmente. Não use generate_outputs.py como oráculo."""

import csv
from pathlib import Path

import pandas as pd
import pytest

from QualisLens.qualislens.constants import STATUS_AUTO_FUZZY, STATUS_EXATO, STATUS_REVISAO_MANUAL
from QualisLens.qualislens.matcher import match
from QualisLens.qualislens.main import _processar_linha
from Classificador.QualisConferencia import QualisConferencia


CORPUS = Path(__file__).parent / "data" / "gold_corpus.csv"


def _casos():
    with CORPUS.open(encoding="utf-8") as arquivo:
        return list(csv.DictReader(arquivo))


@pytest.mark.parametrize("caso", _casos(), ids=lambda caso: caso["id"])
def test_corpus_gold(caso, db):
    resultado = match(caso["venue"], int(caso["ano"]), caso["sigla"] or None, db)
    candidatos = resultado["_candidatos_lista"]
    siglas = {str(c["sigla"]).upper() for c in candidatos}
    esperado = caso["esperado"]

    if caso["decisao"] == "exato":
        assert resultado["qualis_status"] == STATUS_EXATO
        assert resultado["qualis_estrato"] == esperado
    elif caso["decisao"] == "topo_ou_revisao":
        # Caso difícil: candidato certo deve estar disponível; só aceite auto
        # quando ele for exatamente o candidato rotulado.
        assert caso["sigla_esperada"] in siglas
        if resultado["qualis_status"] in (STATUS_EXATO, STATUS_AUTO_FUZZY):
            assert resultado["qualis_sigla"] == caso["sigla_esperada"]
            assert resultado["qualis_estrato"] == esperado
        else:
            assert resultado["qualis_status"] == STATUS_REVISAO_MANUAL
    else:
        assert resultado["qualis_status"] == STATUS_REVISAO_MANUAL
        assert resultado["qualis_estrato"] is None


def test_auto_fuzzy_has_no_contradictory_distinctive_term(db):
    resultado = match("Congresso Brasileiro de Engenharia Mecânica", 2022, None, db)
    assert resultado["qualis_status"] == STATUS_REVISAO_MANUAL
    assert "biomed" not in (resultado.get("qualis_sigla") or "").lower()


def test_default_flow_never_calls_ollama(monkeypatch, db):
    def falha(*args, **kwargs):
        raise AssertionError("HTTP/Ollama called without --modelo")

    monkeypatch.setattr("QualisLens.qualislens.llm_reviewer._chamar_ollama", falha)
    resultado = _processar_linha(pd.Series({
        "titulo_artigo": "Teste sem rede",
        "nome_conferencia": "evento desconhecido sem correspondencia",
        "ano_publicacao": "2022",
    }), db, modelos=None)
    assert resultado["qualis_status"] == STATUS_REVISAO_MANUAL


def test_legacy_api_returns_auditable_contract():
    resultado = QualisConferencia().get_match("International Conference on Software Engineering", 2023, "ICSE")
    assert {"estrato", "evento_oficial", "sigla_oficial", "quadrienio", "metodo", "score_primeiro", "margem_segundo", "candidatos", "motivo", "necessita_revisao"} <= set(resultado)
    assert resultado["estrato"] == "A1"


def test_override_applies_when_venue_embeds_extractable_sigla(tmp_path):
    """Regressão: o qualis_input_id reportado na fila de revisão precisa ser
    o mesmo usado na busca de override, mesmo quando o texto do evento
    contém um token que o pré-processador extrai como sigla (ex.: "SC24:
    Workshops of ..."). Antes da correção, o ID reportado usava a sigla
    extraída e o ID de busca usava a sigla bruta (None aqui), então um
    override escrito com o ID visto pelo humano nunca era encontrado.
    """
    venue = "SC24: Workshops of the International Conference for High Performance Computing, Networking, Storage and Analysis"
    ano = 2024

    sem_override = QualisConferencia()
    resultado_inicial = sem_override.get_match(venue, ano)
    input_id = resultado_inicial["qualis_input_id"]
    assert resultado_inicial["necessita_revisao"] is True

    overrides_path = tmp_path / "qualis_overrides.csv"
    with overrides_path.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow([
            "schema_versao", "qualis_input_id", "acao", "qualis_registro_id",
            "justificativa", "decidido_por", "decidido_em", "politica_versao",
        ])
        escritor.writerow([
            "1", input_id, "SEM_CORRESPONDENCIA", "",
            "evento nao consta na base local", "teste", "2026-01-01T00:00:00-03:00", "2",
        ])

    com_override = QualisConferencia(overrides_path=str(overrides_path))
    resultado_final = com_override.get_match(venue, ano)

    assert resultado_final["metodo"] == "MANUAL_MISS"
    assert resultado_final["necessita_revisao"] is False
