"""Gera a base Qualis de periódicos de todas as áreas (quadriênio 2017-2020).

Esta é a base usada pelo PIIC, cujo edital abrange docentes de todas as áreas.
A base de Computação 2021-2024 (``Classificador/qualis-unificado.csv``) é
gerada por ``criaArquivoQualis.py`` e usada pelo PPGI.

Uso, a partir da raiz do repositório:

    python QualisNovo/criaArquivoQualisTodasAreas.py

Sem argumentos, lê o export de todas as áreas versionado em ``QualisNovo/``.
Um caminho para outro export (mesmas colunas) pode ser passado como argumento.
Para um ISSN avaliado em mais de uma área, mantém o melhor estrato. Depois
adiciona os aliases Print-ISSN/E-ISSN de ``issn_list_xlsx.csv``,
``ImpactFactor2024.csv`` e ``ISSNJson/*.json``.
"""

import json
import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
RAIZ = BASE.parent
ARQUIVO_SAIDA = RAIZ / "Classificador" / "qualis-todas-areas-2017-2020.csv"


def _export_padrao():
    candidatos = sorted(BASE.glob("classifica*todas_as_areas*.csv"))
    if len(candidatos) != 1:
        raise SystemExit(f"Esperado um export de todas as áreas em {BASE}, encontrado(s): {len(candidatos)}")
    return candidatos[0]


def _associar_aliases(estratos, pares):
    """Copia o estrato de um ISSN para o seu par Print/E-ISSN ausente."""
    print_para_e = pares.set_index("Print-ISSN")["E-ISSN"].to_dict()
    e_para_print = pares.set_index("E-ISSN")["Print-ISSN"].to_dict()
    resultado = dict(estratos)
    for issn in list(resultado):
        if issn in print_para_e:
            alias = print_para_e[issn]
        elif issn in e_para_print:
            alias = e_para_print[issn]
        else:
            continue
        resultado.setdefault(alias, resultado[issn])
    return resultado


def _pares_issn_list():
    tabela = pd.read_csv(BASE / "issn_list_xlsx.csv")[["Print-ISSN", "E-ISSN"]].dropna()
    return tabela.map(lambda x: str(x)[:4] + "-" + str(x)[4:] if str(x)[4] != "-" else x)


def _pares_impact_factor():
    tabela = pd.read_csv(BASE / "ImpactFactor2024.csv", sep=";")[["ISSN", "EISSN"]].dropna()
    tabela.columns = ["Print-ISSN", "E-ISSN"]
    return tabela


def _pares_json():
    dados = []
    for caminho in sorted((BASE / "ISSNJson").glob("*.json")):
        dados += json.loads(caminho.read_text(encoding="utf-8"))
    tabela = pd.DataFrame(data=dados)[["issn", "e-issn"]].map(lambda x: None if x == "" else x).dropna()
    # Corrige anomalias como o ISSN 0370-629X do json part-1.
    tabela = tabela.map(lambda x: x[:9] if len(x) > 9 else x)
    tabela.columns = ["Print-ISSN", "E-ISSN"]
    return tabela


def gerar(caminho_export, caminho_saida=ARQUIVO_SAIDA):
    qualis = pd.read_csv(caminho_export).drop(columns=["Área de Avaliação", "Título"])
    estratos = qualis.groupby("ISSN").min()["Estrato"].to_dict()

    # Cada fonte de aliases parte da base original; a ordem do update define
    # a precedência, como no gerador original.
    dados = _associar_aliases(estratos, _pares_issn_list())
    dados.update(_associar_aliases(estratos, _pares_json()))
    dados.update(_associar_aliases(estratos, _pares_impact_factor()))

    saida = pd.DataFrame({"ISSN": list(dados), "Estrato": list(dados.values())})
    saida.to_csv(caminho_saida, header=True, index=False)
    return len(saida)


if __name__ == "__main__":
    export = Path(sys.argv[1]) if len(sys.argv) > 1 else _export_padrao()
    quantidade = gerar(export)
    print(f"{quantidade} ISSNs publicados em {ARQUIVO_SAIDA.relative_to(RAIZ)}")
