import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "PPGI"))
sys.path.insert(0, str(ROOT))

from ArquivoInterno.enums import NaturezaTrabalho
from PontuacaoPPGI.Conference import Conference
from PontuacaoPPGI.PessoaPPGI import PessoaPPGI
from PontuacaoPPGI.utils import gera_qualis_revisao_csv, gera_recredenciamento_csv


def test_ppgi_exports_recredenciamento_and_qualis_review(tmp_path):
    docente = PessoaPPGI("Docente de teste")
    conferencia = Conference(2023, "", NaturezaTrabalho.COMPLETO, None, "Artigo ambíguo", "International Conference", [], None)
    conferencia.set_qualis_match({
        "qualis_estrato": None,
        "qualis_requer_revisao": True,
        "qualis_status": "REVISAO_MANUAL",
        "qualis_candidatos": '[{"sigla":"ICSE","score":70}]',
        "qualis_score_fuzzy": 70.0,
        "qualis_score_margem": 2.0,
        "qualis_obs": "nome_generico",
        "qualis_llm_motivo": None,
    })
    docente.insere_producao(conferencia)

    recredenciamento = tmp_path / "recredenciamento.csv"
    revisao = tmp_path / "qualis_revisao.csv"
    gera_recredenciamento_csv(recredenciamento, [docente])
    gera_qualis_revisao_csv(revisao, [docente])

    assert pd.read_csv(recredenciamento).loc[0, "Qualis"] == "Qualis não identificado"
    fila = pd.read_csv(revisao)
    assert fila.loc[0, "Docente"] == "Docente de teste"
    assert fila.loc[0, "Motivo"] == "nome_generico"
