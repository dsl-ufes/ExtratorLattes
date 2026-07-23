"""
Gera os arquivos entrada_output.csv para todos os fixtures de teste.
Roda sem LLM — apenas busca exata + fuzzy matching.

Uso: python test/generate_outputs.py   (a partir da pasta QualisLens/)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT.parent))

from QualisLens.qualislens.main import executar

LEVELS = ["easy", "mid", "hard"]
SUBFOLDERS = [f"{i:02d}" for i in range(1, 11)]
# Also include the original (root-level) fixtures
ROOT_FIXTURES = [
    ("easy", None),
    ("mid", None),
    ("hard", None),
]

def run_all():
    paths = []
    # numbered subfolders
    for level in LEVELS:
        for sub in SUBFOLDERS:
            entrada = ROOT / "test" / level / sub / "entrada.csv"
            if entrada.exists():
                saida = entrada.parent / "entrada_output.csv"
                paths.append((entrada, saida))
    # root-level fixtures (original)
    for level, _ in ROOT_FIXTURES:
        entrada = ROOT / "test" / level / "entrada.csv"
        if entrada.exists():
            saida = entrada.parent / "entrada_output.csv"
            paths.append((entrada, saida))

    total = len(paths)
    for i, (entrada, saida) in enumerate(paths, 1):
        print(f"[{i}/{total}] {entrada.relative_to(ROOT)} → {saida.name}")
        try:
            executar(str(entrada), str(saida), modelos=None)
        except Exception as e:
            print(f"  ERRO: {e}")

    print(f"\nFeito. {total} arquivos gerados.")

if __name__ == "__main__":
    run_all()
