"""Testes da atualização auditável das bases oficiais da Sucupira."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
from pathlib import Path

import pytest
import requests
from openpyxl import Workbook

from Classificador.Qualis import Qualis
from QualisLens.scripts import atualizar_sucupira as sucupira


REPO_ROOT = Path(__file__).resolve().parents[2]


def _xlsx(
    cabecalho: tuple[str, ...],
    linhas: list[tuple[object, ...]],
    *,
    dimensao_a1: bool = False,
) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(cabecalho)
    for linha in linhas:
        worksheet.append(linha)
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    conteudo = buffer.getvalue()
    if not dimensao_a1:
        return conteudo

    origem = zipfile.ZipFile(io.BytesIO(conteudo))
    destino_buffer = io.BytesIO()
    with origem, zipfile.ZipFile(destino_buffer, "w") as destino:
        for item in origem.infolist():
            dados = origem.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                dados = re.sub(
                    br'<dimension ref="[^"]+"',
                    b'<dimension ref="A1"',
                    dados,
                    count=1,
                )
            destino.writestr(item, dados)
    return destino_buffer.getvalue()


def _issn(numero: int) -> str:
    base = f"{numero:07d}"
    soma = sum(int(digito) * peso for digito, peso in zip(base, range(8, 1, -1)))
    verificador = (11 - soma % 11) % 11
    final = "X" if verificador == 10 else str(verificador)
    return f"{base[:4]}-{base[4:]}{final}"


def _eventos_validos() -> bytes:
    return _xlsx(
        sucupira.COLUNAS_EVENTOS,
        [
            ("ZZZ", "  Evento   Z  ", "b4"),
            ("AAA", "Evento Á", "A1"),
        ],
    )


def _periodicos_validos(*, dimensao_a1: bool = False) -> bytes:
    return _xlsx(
        sucupira.COLUNAS_PERIODICOS,
        [
            (_issn(20), "Revista Z", "c"),
            (_issn(10), " Revista   A ", "A2"),
        ],
        dimensao_a1=dimensao_a1,
    )


class _Resposta:
    def __init__(
        self,
        *,
        status: int = 200,
        text: str = "",
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        url: str = "https://sucupira.example/pagina",
    ) -> None:
        self.status_code = status
        self.text = text
        self.content = content if content is not None else text.encode()
        self.headers = headers or {}
        self.url = url
        self.reason = "erro" if status >= 400 else "ok"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            resposta = requests.Response()
            resposta.status_code = self.status_code
            resposta.url = self.url
            raise requests.HTTPError(response=resposta)


class _Sessao:
    def __init__(self, respostas: list[object]) -> None:
        self.respostas = list(respostas)
        self.headers: dict[str, str] = {}
        self.chamadas: list[tuple[str, str, dict[str, object]]] = []

    def request(self, method: str, url: str, **kwargs: object) -> _Resposta:
        self.chamadas.append((method, url, kwargs))
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        assert isinstance(resposta, _Resposta)
        return resposta


def _form_jsf(
    *,
    viewstate: str,
    evento_selecionado: bool,
    area_selecionada: bool,
    incluir_resultado: bool = False,
) -> str:
    evento_selected = ' selected="selected"' if evento_selecionado else ""
    area_selected = ' selected="selected"' if area_selecionada else ""
    resultado = ""
    if incluir_resultado:
        resultado = """
        <table><tr><td>COMPUTAÇÃO</td><td>
          <a href="#" onclick="mojarra.jsfcljs(document.getElementById('form'),
            {'comando-download-dinamico':'comando-download-dinamico'},'');return false">
            <img alt="Arquivo de classificações" src="/xls.gif"/>
          </a>
        </td></tr></table>
        """
    return f"""
    <form id="form" action="/acao-dinamica" method="post">
      <input type="hidden" name="form" value="form"/>
      <select name="form:evento" id="form:evento">
        <option value="0">-- SELECIONE --</option>
        <option value="codigo-periodo-dinamico"{evento_selected}>
          {sucupira.OPCAO_PERIODICOS}
        </option>
      </select>
      <div class="input-group">
        <input type="checkbox" name="check-area-dinamico"
          {'checked="checked"' if area_selecionada else ''}/>
        <select name="form:area" id="form:area">
          <option value="0">-- SELECIONE --</option>
          <option value="codigo-area-dinamico"{area_selected}>COMPUTAÇÃO</option>
        </select>
      </div>
      <a id="adicionar-area-dinamico" href="#"
        onclick="mojarra.ab(this,event,'action','form:area','painel-areas');return false">
      </a>
      <input type="submit" name="consultar-dinamico" value="Consultar"/>
      <input type="hidden" name="javax.faces.ViewState" value="{viewstate}"/>
      {resultado}
    </form>
    """


def _ajax(updates: dict[str, str]) -> str:
    blocos = "".join(
        f'<update id="{nome}"><![CDATA[{valor}]]></update>'
        for nome, valor in updates.items()
    )
    return f"<?xml version='1.0'?><partial-response><changes>{blocos}</changes></partial-response>"


def test_cliente_jsf_resolve_descricoes_ajax_viewstate_e_download():
    inicial = _form_jsf(
        viewstate="VS-1",
        evento_selecionado=False,
        area_selecionada=False,
    )
    atualizado = _form_jsf(
        viewstate="ignorado",
        evento_selecionado=True,
        area_selecionada=False,
    )
    resultado = _form_jsf(
        viewstate="VS-4",
        evento_selecionado=True,
        area_selecionada=True,
        incluir_resultado=True,
    )
    arquivo = _periodicos_validos()
    sessao = _Sessao(
        [
            _Resposta(text=inicial),
            _Resposta(
                text=_ajax(
                    {
                        "form": atualizado,
                        "javax.faces.ViewState": "VS-2",
                    }
                )
            ),
            _Resposta(
                text=_ajax(
                    {
                        "painel-areas": "<span><b>COMPUTAÇÃO</b></span>",
                        "javax.faces.ViewState": "VS-3",
                    }
                )
            ),
            _Resposta(text=resultado),
            _Resposta(
                content=arquivo,
                headers={
                    "Content-Type": (
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    "Content-Disposition": 'attachment; filename="oficial.xlsx"',
                },
            ),
        ]
    )
    client = sucupira.SucupiraClient(
        session=sessao,  # type: ignore[arg-type]
        sleep=lambda _: None,
    )

    download = client.baixar(sucupira.FONTES["periodicos"], "COMPUTAÇÃO")

    assert download.conteudo == arquivo
    assert download.nome_original == "oficial.xlsx"
    assert download.opcao_selecionada == sucupira.OPCAO_PERIODICOS
    evento_ajax = sessao.chamadas[1][2]["data"]
    assert evento_ajax["form:evento"] == "codigo-periodo-dinamico"
    area_ajax = sessao.chamadas[2][2]["data"]
    assert "adicionar-area-dinamico" in area_ajax["javax.faces.partial.execute"]
    consulta = sessao.chamadas[3][2]["data"]
    assert consulta["form:area"] == "codigo-area-dinamico"
    download_post = sessao.chamadas[4][2]["data"]
    assert download_post["comando-download-dinamico"] == (
        "comando-download-dinamico"
    )


def test_retry_ocorre_somente_para_timeout_429_e_5xx():
    sucesso = _Resposta(text="ok")
    sessao = _Sessao(
        [
            requests.Timeout("lento"),
            _Resposta(status=429),
            _Resposta(status=503),
            sucesso,
        ]
    )
    client = sucupira.SucupiraClient(
        session=sessao,  # type: ignore[arg-type]
        tentativas=4,
        sleep=lambda _: None,
    )

    assert client._request("GET", "https://example.test") is sucesso
    assert len(sessao.chamadas) == 4

    sem_retry = _Sessao([_Resposta(status=400), sucesso])
    client = sucupira.SucupiraClient(
        session=sem_retry,  # type: ignore[arg-type]
        sleep=lambda _: None,
    )
    with pytest.raises(sucupira.ImportacaoError, match="sem retry"):
        client._request("GET", "https://example.test")
    assert len(sem_retry.chamadas) == 1


def test_xlsx_valido_eventos_e_periodicos_com_dimensao_oficial_incorreta():
    eventos = sucupira.normalizar_eventos(_eventos_validos(), minimo=1)
    periodicos = sucupira.normalizar_periodicos(
        _periodicos_validos(dimensao_a1=True),
        minimo=1,
    )

    assert eventos.contagem_antes == eventos.contagem_depois == 2
    assert [linha["Sigla"] for linha in eventos.linhas] == ["AAA", "ZZZ"]
    assert periodicos.contagem_antes == periodicos.contagem_depois == 2
    assert [linha["ISSN"] for linha in periodicos.linhas] == [
        _issn(10),
        _issn(20),
    ]


@pytest.mark.parametrize(
    "cabecalho",
    [
        ("Sigla", "Nome do evento"),
        ("Sigla", "Nome do evento", "Estrato", "Área"),
        (" Sigla", "Nome do evento", "Estrato"),
    ],
)
def test_rejeita_coluna_ausente_ou_inesperada(cabecalho):
    arquivo = _xlsx(cabecalho, [tuple("x" for _ in cabecalho)])
    with pytest.raises(sucupira.ImportacaoError, match="Colunas"):
        sucupira.normalizar_eventos(arquivo, minimo=1)


@pytest.mark.parametrize(
    ("area", "quadrienio"),
    [
        ("ENGENHARIAS IV", "2021-2024"),
        ("COMPUTAÇÃO", "2017-2020"),
    ],
)
def test_rejeita_area_ou_periodo_incorreto(area, quadrienio):
    with pytest.raises(sucupira.ImportacaoError, match="não suportad"):
        sucupira.validar_alvo(area, quadrienio)


def test_rejeita_html_no_lugar_do_xlsx():
    resposta = _Resposta(
        text="<html>erro</html>",
        headers={"Content-Type": "text/html"},
    )
    with pytest.raises(sucupira.ImportacaoError, match="Content-Type"):
        sucupira.validar_resposta_xlsx(resposta)  # type: ignore[arg-type]


def test_rejeita_contagem_abaixo_do_minimo():
    with pytest.raises(sucupira.ImportacaoError, match="abaixo do mínimo"):
        sucupira.normalizar_eventos(_eventos_validos(), minimo=3)


def test_rejeita_campo_vazio_e_estrato_invalido():
    vazio = _xlsx(
        sucupira.COLUNAS_EVENTOS,
        [("ABC", "", "A1")],
    )
    with pytest.raises(sucupira.ImportacaoError, match="campos vazios"):
        sucupira.normalizar_eventos(vazio, minimo=1)

    estrato = _xlsx(
        sucupira.COLUNAS_EVENTOS,
        [("ABC", "Evento", "B5")],
    )
    with pytest.raises(sucupira.ImportacaoError, match="Estrato inválido"):
        sucupira.normalizar_eventos(estrato, minimo=1)


def test_rejeita_issn_invalido():
    arquivo = _xlsx(
        sucupira.COLUNAS_PERIODICOS,
        [("1234-5678", "Revista", "A1")],
    )
    with pytest.raises(sucupira.ImportacaoError, match="ISSN inválido"):
        sucupira.normalizar_periodicos(arquivo, minimo=1)


def test_rejeita_duplicata_exata():
    arquivo = _xlsx(
        sucupira.COLUNAS_EVENTOS,
        [
            ("ABC", "Evento", "A1"),
            ("ABC", "Evento", "A1"),
        ],
    )
    with pytest.raises(sucupira.ImportacaoError, match="Duplicata exata"):
        sucupira.normalizar_eventos(arquivo, minimo=1)


def test_rejeita_identidade_com_estratos_conflitantes():
    issn = _issn(30)
    arquivo = _xlsx(
        sucupira.COLUNAS_PERIODICOS,
        [
            (issn, "Revista A", "A1"),
            (issn, "Revista B", "A2"),
        ],
    )
    with pytest.raises(sucupira.ImportacaoError, match="conflitantes"):
        sucupira.normalizar_periodicos(arquivo, minimo=1)


def _escrever_entradas(tmp_path: Path) -> tuple[Path, Path]:
    entradas = tmp_path / "entradas"
    entradas.mkdir()
    eventos = entradas / "eventos.xlsx"
    periodicos = entradas / "periodicos.xlsx"
    eventos.write_bytes(_eventos_validos())
    periodicos.write_bytes(_periodicos_validos(dimensao_a1=True))
    return eventos, periodicos


def _artefatos(root: Path) -> list[Path]:
    return [
        root
        / "QualisLens/base/originais/"
        "sucupira_eventos_computacao_2021_2024.xlsx",
        root
        / "QualisLens/base/originais/"
        "sucupira_periodicos_computacao_2021_2024.xlsx",
        root / "QualisLens/base/qualis_2021_2024.csv",
        root / "Classificador/base/qualis_periodicos_2021_2024.csv",
        root / "Classificador/qualis-unificado.csv",
        root / "QualisLens/base/metadata.json",
    ]


def test_offline_tem_hashes_e_csvs_deterministicos_e_parte1_compativel(tmp_path):
    eventos, periodicos = _escrever_entradas(tmp_path)
    roots = [tmp_path / "repo-a", tmp_path / "repo-b"]
    metadados = []
    for root in roots:
        metadados.append(
            sucupira.executar_importacao(
                offline=True,
                eventos_xlsx=eventos,
                periodicos_xlsx=periodicos,
                repo_root=root,
                gerado_em_utc="2026-01-02T03:04:05Z",
                min_eventos=1,
                min_periodicos=1,
            )
        )

    for relativo in [
        "QualisLens/base/qualis_2021_2024.csv",
        "Classificador/base/qualis_periodicos_2021_2024.csv",
        "Classificador/qualis-unificado.csv",
        "QualisLens/base/metadata.json",
    ]:
        assert (roots[0] / relativo).read_bytes() == (roots[1] / relativo).read_bytes()
    assert metadados[0] == metadados[1]

    metadata = json.loads((roots[0] / "QualisLens/base/metadata.json").read_text())
    eventos_csv = roots[0] / "QualisLens/base/qualis_2021_2024.csv"
    periodicos_csv = (
        roots[0] / "Classificador/base/qualis_periodicos_2021_2024.csv"
    )
    projecao = roots[0] / "Classificador/qualis-unificado.csv"
    assert eventos_csv.read_text(encoding="utf-8").splitlines()[0] == (
        "Sigla,Nome do evento,Estrato,quadrienio"
    )
    assert periodicos_csv.read_text(encoding="utf-8").splitlines()[0] == (
        "ISSN,Título,Estrato,quadrienio"
    )
    assert projecao.read_text(encoding="utf-8").splitlines()[0] == "ISSN,Estrato"
    assert metadata["fontes"]["eventos"]["sha256_csv"] == hashlib.sha256(
        eventos_csv.read_bytes()
    ).hexdigest()
    assert metadata["fontes"]["periodicos"]["sha256_csv"] == hashlib.sha256(
        periodicos_csv.read_bytes()
    ).hexdigest()
    assert metadata["artefatos"]["qualis_unificado"]["sha256_csv"] == (
        hashlib.sha256(projecao.read_bytes()).hexdigest()
    )
    assert metadata["area"] == "COMPUTAÇÃO"
    assert metadata["quadrienio"] == "2021-2024"
    assert metadata["gerado_em_utc"] == "2026-01-02T03:04:05Z"
    assert metadata["politica_importacao_versao"] == "1"
    assert metadata["fontes"]["eventos"]["url"] == sucupira.URL_EVENTOS
    assert metadata["fontes"]["periodicos"]["url"] == sucupira.URL_PERIODICOS
    assert metadata["fontes"]["eventos"]["opcao_selecionada"] == (
        sucupira.OPCAO_EVENTOS
    )
    assert metadata["fontes"]["periodicos"]["opcao_selecionada"] == (
        sucupira.OPCAO_PERIODICOS
    )
    assert metadata["fontes"]["eventos"]["sha256_xlsx"] == hashlib.sha256(
        eventos.read_bytes()
    ).hexdigest()
    assert metadata["fontes"]["periodicos"]["sha256_xlsx"] == hashlib.sha256(
        periodicos.read_bytes()
    ).hexdigest()

    classificador = Qualis(str(projecao))
    assert classificador.get_estrato(_issn(10)) == "A2"


def test_artefatos_publicados_batem_com_os_hashes_do_metadata():
    metadata = json.loads(
        (REPO_ROOT / "QualisLens/base/metadata.json").read_text(encoding="utf-8")
    )
    arquivos = [
        (
            metadata["fontes"]["eventos"]["arquivo_original"],
            metadata["fontes"]["eventos"]["sha256_xlsx"],
        ),
        (
            metadata["fontes"]["eventos"]["arquivo_csv"],
            metadata["fontes"]["eventos"]["sha256_csv"],
        ),
        (
            metadata["fontes"]["periodicos"]["arquivo_original"],
            metadata["fontes"]["periodicos"]["sha256_xlsx"],
        ),
        (
            metadata["fontes"]["periodicos"]["arquivo_csv"],
            metadata["fontes"]["periodicos"]["sha256_csv"],
        ),
        (
            metadata["artefatos"]["qualis_unificado"]["arquivo"],
            metadata["artefatos"]["qualis_unificado"]["sha256_csv"],
        ),
    ]
    for relativo, hash_esperado in arquivos:
        assert hashlib.sha256((REPO_ROOT / relativo).read_bytes()).hexdigest() == (
            hash_esperado
        )


def test_parte1_carrega_a_projecao_oficial_publicada():
    classificador = Qualis(str(REPO_ROOT / "Classificador/qualis-unificado.csv"))

    assert len(classificador.qualis_dict) >= sucupira.MIN_PERIODICOS
    assert classificador.get_estrato("00010782") == "A1"
    assert classificador.get_estrato("0001-0782") == "A1"


def test_falha_antes_da_publicacao_preserva_todas_as_bases(tmp_path):
    root = tmp_path / "repo"
    for artefato in _artefatos(root):
        artefato.parent.mkdir(parents=True, exist_ok=True)
        artefato.write_bytes(b"base-anterior")
    eventos, _ = _escrever_entradas(tmp_path)
    periodicos_invalidos = tmp_path / "periodicos-invalidos.xlsx"
    periodicos_invalidos.write_bytes(
        _xlsx(
            sucupira.COLUNAS_PERIODICOS,
            [("1234-5678", "Revista inválida", "A1")],
        )
    )

    with pytest.raises(sucupira.ImportacaoError):
        sucupira.executar_importacao(
            offline=True,
            eventos_xlsx=eventos,
            periodicos_xlsx=periodicos_invalidos,
            repo_root=root,
            min_eventos=1,
            min_periodicos=1,
        )

    assert all(artefato.read_bytes() == b"base-anterior" for artefato in _artefatos(root))


def test_falha_durante_publicacao_restaura_os_artefatos(monkeypatch, tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    origem_a = staging / "nova-a"
    origem_b = staging / "nova-b"
    origem_a.write_bytes(b"nova-a")
    origem_b.write_bytes(b"nova-b")
    destino_a = tmp_path / "destino-a"
    destino_b = tmp_path / "destino-b"
    destino_a.write_bytes(b"anterior-a")
    destino_b.write_bytes(b"anterior-b")

    replace_real = os.replace
    falhou = False

    def replace_com_falha(origem, destino):
        nonlocal falhou
        if Path(origem) == origem_b and not falhou:
            falhou = True
            raise OSError("falha simulada")
        replace_real(origem, destino)

    monkeypatch.setattr(sucupira.os, "replace", replace_com_falha)

    with pytest.raises(sucupira.ImportacaoError, match="publicação atômica"):
        sucupira._publicar_atomicamente(
            [(origem_a, destino_a), (origem_b, destino_b)],
            staging,
        )

    assert destino_a.read_bytes() == b"anterior-a"
    assert destino_b.read_bytes() == b"anterior-b"


@pytest.mark.online
@pytest.mark.skipif(
    os.environ.get("QUALIS_SUCUPIRA_ONLINE") != "1",
    reason="Defina QUALIS_SUCUPIRA_ONLINE=1 para acessar a rede.",
)
def test_smoke_online_opcional():
    client = sucupira.SucupiraClient()
    eventos_download = client.baixar(sucupira.FONTES["eventos"], "COMPUTAÇÃO")
    periodicos_download = client.baixar(
        sucupira.FONTES["periodicos"],
        "COMPUTAÇÃO",
    )

    eventos = sucupira.normalizar_eventos(eventos_download.conteudo)
    periodicos = sucupira.normalizar_periodicos(periodicos_download.conteudo)

    assert eventos.contagem_depois >= sucupira.MIN_EVENTOS
    assert periodicos.contagem_depois >= sucupira.MIN_PERIODICOS
