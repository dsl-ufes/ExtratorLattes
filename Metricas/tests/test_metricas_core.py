import pytest

from Metricas.core import enriquecer_publicacoes
from Metricas.repository import RepositorioMetricasSQLite


class Provider:
    nome = "google_scholar"
    endpoint_versao = "v2"

    def __init__(self, status="RESOLVIDO", valor=2):
        self.status, self.valor, self.chamadas = status, valor, 0

    def resolver_por_doi(self, publicacao, doi):
        self.chamadas += 1
        if self.status != "RESOLVIDO":
            return {"status": self.status}
        return {"status": "RESOLVIDO", "identidade": {"id": "x", "doi": doi, "title": publicacao["titulo"], "year": str(publicacao["ano"]), "type": "journal-article", "issn": []}, "metricas": [{"nome_metrica": "google_scholar.citations", "valor": self.valor, "unidade": "citacoes", "periodo_inicio": "", "periodo_fim": "", "categoria": ""}]}


def pub():
    return {"publicacao_canonica_id": "c1", "titulo": "Um teste", "ano": "2024", "tipo": "Periódico", "doi": "10.1000/teste", "issn": ""}


def test_cache_e_zero_sao_validos(tmp_path):
    repo = RepositorioMetricasSQLite(tmp_path / "m.sqlite"); p = Provider(valor=0)
    assert enriquecer_publicacoes([pub()], [p], repo).metricas[0]["valor"] == 0
    assert enriquecer_publicacoes([pub()], [p], repo).metricas[0]["valor"] == 0
    assert p.chamadas == 1


def test_offline_sem_cache_nao_chama_rede(tmp_path):
    p = Provider(); r = enriquecer_publicacoes([pub()], [p], RepositorioMetricasSQLite(tmp_path / "m.sqlite"), modo="offline")
    assert r.identidades[0]["status"] == "CACHE_AUSENTE" and p.chamadas == 0


def test_falha_nao_vira_zero(tmp_path):
    r = enriquecer_publicacoes([pub()], [Provider("LIMITE_EXCEDIDO")], RepositorioMetricasSQLite(tmp_path / "m.sqlite"))
    assert not r.metricas and r.identidades[0]["status"] == "LIMITE_EXCEDIDO"


def test_snapshot_existente_nao_pode_ser_sobrescrito(tmp_path):
    repo = RepositorioMetricasSQLite(tmp_path / "m.sqlite"); snapshot = repo.criar_snapshot("2", "teste")
    with pytest.raises(ValueError, match="imutáveis"):
        enriquecer_publicacoes([pub()], [Provider()], repo, snapshot_id=snapshot)
