import csv

from Metricas.reports import exportar
from Metricas.repository import RepositorioMetricasSQLite


def test_ranking_scholar_e_docente_nao_repete_vinculo(tmp_path):
    repo = RepositorioMetricasSQLite(tmp_path / "m.sqlite")
    snapshot = repo.criar_snapshot("1", "teste")
    repo.salvar_metricas([
        {"snapshot_id": snapshot, "publicacao_canonica_id": "c1", "provedor": "google_scholar", "nome_metrica": "google_scholar.citations", "valor": 5, "unidade": "citacoes", "periodo_inicio": "", "periodo_fim": "", "categoria": "", "papel_provedor": "PRIMARIO", "fallback_acionado_por": ""},
        {"snapshot_id": snapshot, "publicacao_canonica_id": "c2", "provedor": "google_scholar", "nome_metrica": "google_scholar.citations", "valor": 10, "unidade": "citacoes", "periodo_inicio": "", "periodo_fim": "", "categoria": "", "papel_provedor": "PRIMARIO", "fallback_acionado_por": ""},
    ])
    repo.finalizar_snapshot(snapshot, "CONCLUIDO")
    ocorrencias = [
        {"ocorrencia_id": "variante", "publicacao_canonica_id": "c1", "Docente": "A", "titulo": "Título variante", "ano": "2024", "tipo": "Periódico", "venue": "J"},
        {"ocorrencia_id": "c1", "publicacao_canonica_id": "c1", "Docente": "A", "titulo": "Primeiro", "ano": "2024", "tipo": "Periódico", "venue": "J"},
        {"publicacao_canonica_id": "c2", "Docente": "B", "titulo": "Segundo", "ano": "2024", "tipo": "Conferência", "venue": "C"},
    ]
    exportar(repo, snapshot, tmp_path, "2024", ocorrencias)
    with open(tmp_path / "2024_metricas_ranking.csv", encoding="utf-8-sig", newline="") as arquivo:
        ranking = list(csv.DictReader(arquivo))
    with open(tmp_path / "2024_metricas_docentes.csv", encoding="utf-8-sig", newline="") as arquivo:
        docentes = list(csv.DictReader(arquivo))
    assert len(ranking) == 2
    assert [x["ranking_na_fonte"] for x in ranking] == ["1", "2"]
    assert next(x for x in ranking if x["publicacao_canonica_id"] == "c1")["titulo"] == "Primeiro"
    assert len(docentes) == 2
