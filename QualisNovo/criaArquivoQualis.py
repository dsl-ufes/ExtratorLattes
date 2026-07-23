"""Atualiza a projeção Qualis de periódicos com aliases históricos de ISSN."""

import csv
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd


RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from QualisLens.scripts import atualizar_sucupira


BASE = Path(__file__).resolve().parent
ARQUIVO_QUALIS = RAIZ / "Classificador" / "qualis-unificado.csv"
ARQUIVO_METADATA = RAIZ / "QualisLens" / "base" / "metadata.json"


def _issn(valor):
    texto = str(valor or "").strip().upper().replace(" ", "")
    if len(texto) == 8 and "-" not in texto:
        texto = texto[:4] + "-" + texto[4:]
    return texto if len(texto) == 9 and texto[4] == "-" else ""


def _pares_csv(caminho, primeira, segunda, separador=","):
    tabela = pd.read_csv(caminho, sep=separador, dtype=str).fillna("")
    return [(_issn(a), _issn(b)) for a, b in zip(tabela[primeira], tabela[segunda])]


def _pares_json(diretorio):
    pares = []
    for caminho in sorted(Path(diretorio).glob("*.json")):
        for item in json.loads(caminho.read_text(encoding="utf-8")):
            pares.append((_issn(item.get("issn")), _issn(item.get("e-issn"))))
    return pares


def pares_aliases():
    pares = _pares_csv(BASE / "issn_list_xlsx.csv", "Print-ISSN", "E-ISSN")
    pares += _pares_csv(BASE / "ImpactFactor2024.csv", "ISSN", "EISSN", ";")
    pares += _pares_json(BASE / "ISSNJson")
    return [(a, b) for a, b in pares if a and b and a != b]


def _publicar_csv_atomico(caminho, linhas):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, dir=caminho.parent) as arquivo:
        temporario = Path(arquivo.name)
        escritor = csv.DictWriter(arquivo, fieldnames=("ISSN", "Estrato"), lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(linhas)
    os.replace(temporario, caminho)


def enriquecer_aliases(caminho=ARQUIVO_QUALIS):
    with Path(caminho).open(encoding="utf-8-sig", newline="") as arquivo:
        estratos = {linha["ISSN"]: linha["Estrato"] for linha in csv.DictReader(arquivo)}
    adicionados = 0
    for primeiro, segundo in pares_aliases():
        if primeiro in estratos and segundo not in estratos:
            estratos[segundo] = estratos[primeiro]
            adicionados += 1
        elif segundo in estratos and primeiro not in estratos:
            estratos[primeiro] = estratos[segundo]
            adicionados += 1
    _publicar_csv_atomico(Path(caminho), ({"ISSN": issn, "Estrato": estrato} for issn, estrato in sorted(estratos.items())))
    return adicionados, len(estratos)


def atualizar_metadata(adicionados, quantidade):
    dados = json.loads(ARQUIVO_METADATA.read_text(encoding="utf-8"))
    artefato = dados["artefatos"]["qualis_unificado"]
    artefato["sha256_csv"] = hashlib.sha256(ARQUIVO_QUALIS.read_bytes()).hexdigest()
    artefato["quantidade_registros"] = quantidade
    artefato["aliases_issn"] = {
        "fontes": ["issn_list_xlsx.csv", "ImpactFactor2024.csv", "ISSNJson/*.json"],
        "quantidade_adicionada": adicionados,
    }
    temporario = ARQUIVO_METADATA.with_suffix(".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporario, ARQUIVO_METADATA)


def main(argv=None):
    resultado = atualizar_sucupira.main(argv)
    if resultado:
        return resultado
    adicionados, quantidade = enriquecer_aliases()
    atualizar_metadata(adicionados, quantidade)
    print(f"Aliases de ISSN publicados: {adicionados}; total de periódicos: {quantidade}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
