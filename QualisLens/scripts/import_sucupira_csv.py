"""Converte exportação CSV da Sucupira para schema interno QualisLens."""

import argparse
import csv
from pathlib import Path


COLUNAS = ("Sigla", "Nome do evento", "Estrato")


def converter(entrada: Path, saida: Path) -> int:
    with entrada.open(encoding="utf-8-sig", newline="") as origem:
        leitor = csv.DictReader(origem)
        if not set(COLUNAS).issubset(leitor.fieldnames or []):
            raise ValueError(f"CSV deve conter: {', '.join(COLUNAS)}")
        linhas = [{coluna: (linha.get(coluna) or "").strip() for coluna in COLUNAS} for linha in leitor]
    if any(not all(linha.values()) for linha in linhas):
        raise ValueError("CSV contém campos vazios")
    if len({tuple(linha.values()) for linha in linhas}) != len(linhas):
        raise ValueError("CSV contém duplicatas exatas")
    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("w", encoding="utf-8", newline="") as destino:
        escritor = csv.DictWriter(destino, fieldnames=COLUNAS)
        escritor.writeheader()
        escritor.writerows(linhas)
    return len(linhas)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("entrada", type=Path)
    parser.add_argument("saida", type=Path)
    args = parser.parse_args()
    print(converter(args.entrada, args.saida))
