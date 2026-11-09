"""Validated, versioned manual identity decisions for future snapshots."""
from __future__ import annotations
import csv
import hashlib
from Deduplicacao.core import normalizar_doi

PROVEDORES = {'crossref', 'google_scholar', 'scopus'}

def hash_arquivo(caminho):
    with open(caminho, 'rb') as arquivo: return hashlib.sha256(arquivo.read()).hexdigest()

def carregar_overrides(caminho, fingerprints):
    """Return decisions keyed by (canonical id, provider), or raise ValueError."""
    decisoes = {}
    with open(caminho, newline='', encoding='utf-8-sig') as arquivo:
        for linha in csv.DictReader(arquivo):
            chave = (linha.get('publicacao_canonica_id',''), linha.get('provedor',''))
            acao = linha.get('acao','')
            if linha.get('schema_versao') != '1' or chave[1] not in PROVEDORES or acao not in {'ASSOCIAR','SEM_CORRESPONDENCIA'}:
                raise ValueError('override de métrica inválido')
            if not linha.get('justificativa','').strip() or fingerprints.get(chave[0]) != linha.get('conteudo_fingerprint'):
                raise ValueError('override de métrica obsoleto ou sem justificativa')
            if acao == 'ASSOCIAR' and not linha.get('identificador_externo','').strip():
                raise ValueError('override ASSOCIAR sem identificador')
            if chave in decisoes and decisoes[chave] != linha:
                raise ValueError('overrides contraditórios')
            decisoes[chave] = linha
    return decisoes
