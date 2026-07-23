from pathlib import Path

from Metricas.providers import GoogleScholarProvider, parse_google_scholar_html


FIXTURES = Path(__file__).parent / "fixtures"


class Response:
    def __init__(self, text, status_code=200, url="https://scholar.google.com/scholar?q=test"):
        self.text = text
        self.status_code = status_code
        self.url = url
        self.ok = status_code < 400


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def publicacao(doi="10.1000/teste"):
    return {
        "publicacao_canonica_id": "c1",
        "titulo": "Um teste",
        "ano": "2024",
        "tipo": "Periódico",
        "doi": doi,
        "issn": "",
        "autores": '["Alice Silva", "Bruno Costa"]',
    }


def test_parser_extrai_cluster_citacoes_e_evidencia():
    html = (FIXTURES / "google_scholar_results.html").read_text(encoding="utf-8")
    resultados, bloqueado = parse_google_scholar_html(html)
    assert not bloqueado
    assert resultados[0]["id"] == "12345"
    assert resultados[0]["citations"] == 1234
    assert resultados[0]["url_evidencia"].startswith("https://scholar.google.com/scholar?cites=12345")
    assert resultados[0]["url_publicacao"] == "https://example.org/artigo"


def test_provedor_busca_titulo_e_resolve_candidato_compativel():
    html = (FIXTURES / "google_scholar_results.html").read_text(encoding="utf-8")
    session = Session(Response(html))
    provider = GoogleScholarProvider(session=session, sleep=lambda _: None)
    resposta = provider.resolver_por_doi(publicacao(), "10.1000/teste")
    assert resposta["status"] == "RESOLVIDO"
    assert resposta["metricas"][0]["valor"] == 1234
    assert session.calls[0][1]["params"]["q"] == 'intitle:"Um teste"'


def test_resultado_sem_link_de_citacao_representa_zero():
    html = """<div id='gs_res_ccl_mid'><div class='gs_r' data-cid='zero'><div class='gs_ri'>
    <h3 class='gs_rt'><a href='/paper'>Um teste</a></h3>
    <div class='gs_a'>A Silva - Journal of Tests, 2024</div><div class='gs_fl'></div>
    </div></div></div>"""
    provider = GoogleScholarProvider(session=Session(Response(html)), sleep=lambda _: None)
    resposta = provider.resolver_por_doi(publicacao(), "10.1000/teste")
    assert resposta["status"] == "RESOLVIDO"
    assert resposta["metricas"][0]["valor"] == 0


def test_pagina_de_verificacao_nao_e_nao_encontrado():
    resultados, bloqueado = parse_google_scholar_html(
        "<html><form id='gs_captcha_f' action='/sorry/'></form></html>",
        "https://scholar.google.com/sorry/index",
    )
    assert resultados == []
    assert bloqueado


def test_titulo_igual_com_ano_incompativel_nao_resolve():
    html = """<div id='gs_res_ccl_mid'><div class='gs_r' data-cid='antigo'><div class='gs_ri'>
    <h3 class='gs_rt'><a href='/paper'>Um teste</a></h3>
    <div class='gs_a'>A Silva - Journal of Tests, 2023</div><div class='gs_fl'></div>
    </div></div></div>"""
    provider = GoogleScholarProvider(session=Session(Response(html)), sleep=lambda _: None)
    assert provider.resolver_por_doi(publicacao(), "10.1000/teste")["status"] == "NAO_ENCONTRADO"


def test_publicacao_sem_doi_resolve_com_autor_compativel():
    html = (FIXTURES / "google_scholar_results.html").read_text(encoding="utf-8")
    provider = GoogleScholarProvider(session=Session(Response(html)), sleep=lambda _: None)
    assert provider.buscar_candidatos(publicacao(""))["status"] == "RESOLVIDO"


def test_publicacao_sem_doi_nao_resolve_sem_evidencia_adicional():
    html = """<div id='gs_res_ccl_mid'><div class='gs_r' data-cid='sem-autor'><div class='gs_ri'>
    <h3 class='gs_rt'><a href='/paper'>Um teste</a></h3>
    <div class='gs_a'>Autor Diferente - Outro Veículo, 2024</div><div class='gs_fl'></div>
    </div></div></div>"""
    provider = GoogleScholarProvider(session=Session(Response(html)), sleep=lambda _: None)
    assert provider.buscar_candidatos(publicacao(""))["status"] == "NAO_ENCONTRADO"


def test_resultado_parcial_sem_rodape_nao_vira_zero():
    html = """<div id='gs_res_ccl_mid'><div class='gs_r' data-cid='parcial'><div class='gs_ri'>
    <h3 class='gs_rt'><a href='/paper'>Um teste</a></h3>
    <div class='gs_a'>A Silva - Journal of Tests, 2024</div>
    </div></div></div>"""
    provider = GoogleScholarProvider(session=Session(Response(html)), sleep=lambda _: None)
    assert provider.resolver_por_doi(publicacao(), "10.1000/teste")["status"] == "NAO_ENCONTRADO"


def test_provedor_aplica_intervalo_e_jitter_entre_consultas():
    html = (FIXTURES / "google_scholar_results.html").read_text(encoding="utf-8")
    esperas = []
    provider = GoogleScholarProvider(
        session=Session(Response(html)),
        sleep=esperas.append,
        clock=lambda: 0,
        random_uniform=lambda _inicio, _fim: 0.5,
        intervalo_minimo=2.5,
        jitter=1.0,
    )
    provider.resolver_por_doi(publicacao(), "10.1000/teste")
    provider.resolver_por_doi(publicacao(), "10.1000/teste")
    assert esperas == [3.0]


def test_doi_local_nao_dispensa_evidencia_de_autor_ou_veiculo():
    html = """<div id='gs_res_ccl_mid'><div class='gs_r' data-cid='titulo'><div class='gs_ri'>
    <h3 class='gs_rt'><a href='/paper'>Um teste</a></h3>
    <div class='gs_a'>Autor Diferente - Outro Veículo, 2024</div><div class='gs_fl'></div>
    </div></div></div>"""
    provider = GoogleScholarProvider(session=Session(Response(html)), sleep=lambda _: None)
    assert provider.resolver_por_doi(publicacao(), "10.1000/teste")["status"] == "NAO_ENCONTRADO"
