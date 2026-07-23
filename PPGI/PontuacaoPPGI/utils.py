import json
import os
import hashlib
from dataclasses import dataclass

import pandas as pd

from ArquivoInterno.enums.NaturezaTrabalho import NaturezaTrabalho
from ArquivoInterno.enums import NaturezaArtigo
from PontuacaoPPGI.Conference import Conference
from PontuacaoPPGI.Journal import Journal
from PontuacaoPPGI.NotaInfo import NotaInfo
from PontuacaoPPGI.PessoaPPGI import PessoaPPGI
from Deduplicacao import deduplicar_publicacoes, id_ocorrencia, conteudo_fingerprint
from Deduplicacao.core import ler_overrides


@dataclass(frozen=True)
class PreflightResult:
    """Resultado das revisões que impedem a pontuação."""

    revisoes_deduplicacao: tuple
    revisoes_qualis: tuple
    ids_deduplicacao: tuple[str, ...]
    ids_qualis: tuple[str, ...]
    mensagens: tuple[str, ...]
    caminho_revisao_deduplicacao: str
    caminho_revisao_qualis: str

    @property
    def quantidade_deduplicacao(self):
        return len(self.revisoes_deduplicacao)

    @property
    def quantidade_qualis(self):
        return len(self.revisoes_qualis)

    @property
    def pode_pontuar(self):
        return not self.revisoes_deduplicacao and not self.revisoes_qualis


def validar_manifest_deduplicacao(dir_out, ano, overrides_path):
    caminho=os.path.join(dir_out, f'{ano}_deduplicacao_manifest.json')
    if not os.path.isfile(caminho): raise ValueError('deduplicação ausente; execute a Parte 1')
    with open(caminho, encoding='utf-8') as f: manifesto=json.load(f)
    def digest(p):
        with open(p,'rb') as x:return hashlib.sha256(x.read()).hexdigest()
    if manifesto.get('sha256_overrides_deduplicacao') != digest(overrides_path): raise ValueError('overrides alterados; execute a Parte 1')
    for name, expected in manifesto.get('arquivos',{}).items():
        if digest(os.path.join(dir_out,name)) != expected: raise ValueError('saída de deduplicação alterada; execute a Parte 1')
    if manifesto.get('status') != 'SUCESSO': raise ValueError('deduplicação contém revisões; resolva a fila e execute a Parte 1')
    return manifesto


def preflight_pontuacao(ocorrencias_path, overrides_path, nota_info, dir_out, ano):
    """Verifica revisões pendentes antes de calcular qualquer nota.

    As resoluções de deduplicação são aplicadas por ``deduplicar_publicacoes``
    antes de esta função examinar ``resultado.revisoes``.
    """
    linhas = pd.read_csv(ocorrencias_path, dtype=str, keep_default_na=False).to_dict('records')
    review_path=os.path.join(dir_out, f'{ano}_deduplicacao_revisao.csv')
    review_rows=pd.read_csv(review_path, dtype=str, keep_default_na=False).to_dict('records') if os.path.isfile(review_path) else []
    # Part 2 must not calculate identity. The queue published by Part 1 is authoritative.
    anos_por_ocorrencia = {
        linha.get('ocorrencia_id', ''): int(linha['ano'])
        for linha in linhas
        if linha.get('ocorrencia_id') and str(linha.get('ano', '')).strip()
    }

    def revisao_deduplicacao_afeta_nota(revisao):
        ids = tuple(
            ocorrencia_id
            for ocorrencia_id in (
                revisao.get('ocorrencia_a', ''),
                revisao.get('ocorrencia_b', ''),
            )
            if ocorrencia_id
        )
        anos = tuple(
            anos_por_ocorrencia[ocorrencia_id]
            for ocorrencia_id in ids
            if ocorrencia_id in anos_por_ocorrencia
        )
        # Fail closed if a review does not map to the audited occurrence file.
        return not anos or any(nota_info.prod_valida_para_nota(item) for item in anos)

    revisoes_deduplicacao=tuple(
        revisao for revisao in review_rows
        if revisao_deduplicacao_afeta_nota(revisao)
    )
    revisoes_qualis = tuple(
        linha for linha in linhas
        if linha.get('tipo') == 'Conferência'
        and str(linha.get('qualis_requer_revisao', '')).strip().lower() == 'true'
        and nota_info.prod_valida_para_nota(int(linha['ano']))
    )
    ids_deduplicacao = tuple(sorted({x for r in revisoes_deduplicacao for x in (r.get('ocorrencia_a',''),r.get('ocorrencia_b','')) if x}))
    ids_qualis = tuple(sorted(
        linha.get('ocorrencia_id', '')
        for linha in revisoes_qualis
        if linha.get('ocorrencia_id')
    ))
    caminho_revisao_deduplicacao = os.path.join(dir_out, f'{ano}_deduplicacao_revisao.csv')
    caminho_revisao_qualis = os.path.join(dir_out, f'{ano}_qualis_revisao.csv')
    mensagens = []
    if revisoes_deduplicacao:
        mensagens.append(f'{len(revisoes_deduplicacao)} revisão(ões) de deduplicação afetam o intervalo de pontuação.')
    if revisoes_qualis:
        mensagens.append(f'{len(revisoes_qualis)} revisão(ões) Qualis afetam o intervalo de pontuação.')
    return PreflightResult(
        revisoes_deduplicacao=revisoes_deduplicacao,
        revisoes_qualis=revisoes_qualis,
        ids_deduplicacao=ids_deduplicacao,
        ids_qualis=ids_qualis,
        mensagens=tuple(mensagens),
        caminho_revisao_deduplicacao=caminho_revisao_deduplicacao,
        caminho_revisao_qualis=caminho_revisao_qualis,
    )

def config_json(json_path: str):
    config_d = {}
    with open(json_path, 'r') as f:
        json_parsed = json.load(f)

        config_d['ano_inicio_conferencia'] = json_parsed["ano_inicio_conferencia"]

        config_d['ano_fim_conferencia'] = json_parsed['ano_fim_conferencia']

        config_d['ano_inicio_periodico'] = json_parsed["ano_inicio_periodico"]

        config_d['ano_fim_periodico'] = json_parsed['ano_fim_periodico']

        config_d['lista_file'] = json_parsed['arquivo_lista_docentes']

        config_d['curriculo_dir'] = json_parsed['diretorio_curriculos']

        config_d['dir_out'] = json_parsed['diretorio_saida']

        config_d['docente_file'] = json_parsed['arquivo_nota_docente']

        config_d['geral_file'] = json_parsed['arquivo_nota_geral']

        config_d['qualis_j'] = json_parsed['arquivo_qualis_journal']

        config_d['qualis_c'] = json_parsed['arquivo_qualis_conference']

        config_d['nota_info'] = json_parsed['config_pontuacao']
        
        config_d['publicacoes_ocorrencias'] = json_parsed['arquivo_publicacoes_ocorrencias']
        config_d['overrides_deduplicacao'] = json_parsed.get('arquivo_overrides_deduplicacao', 'DadosPPGI/input/publicacoes_deduplicacao_overrides.csv')
        config_d['overrides_qualis'] = json_parsed.get('arquivo_overrides_qualis')


    return config_d

def all_jornal_conferences(docentes: list[PessoaPPGI]):
    journals = []
    conferences = []

    for docente in docentes:
        for prod in docente.get_producoes():
            if isinstance(prod, Journal):
                journals.append(prod)
            elif isinstance(prod, Conference):
                if prod.get_natureza() is not NaturezaTrabalho.COMPLETO:
                    continue
                
                conferences.append(prod)

    return journals, conferences

def create_csv_writer(path, nota_info: NotaInfo):
    csv_file = open(path, 'w')

    min_intervalo = nota_info.get_prod_min_intervalo()
    print(f'Docente;Bolsista de Produtividade (PQ ou DT);Nota Docente;{nota_info.get_prod_min_tag()}({min_intervalo[0]}-{min_intervalo[1]});Regra: B > 0 OU (C >= {nota_info.get_nota_min_value()} E D >= {nota_info.get_prod_min_qtd()})', file=csv_file)

    return csv_file

def _linha_ocorrencia(docente, producao):
    metadados = producao.get_metadados() if hasattr(producao, 'get_metadados') else None
    p = getattr(metadados, 'proveniencia', None)
    autores = getattr(metadados, 'autores_detalhados', ())
    tipo = 'Periódico' if isinstance(producao, Journal) else 'Conferência'
    local = producao.get_revista() if tipo == 'Periódico' else producao.get_venue()
    resultado = producao.get_qualis_match() if isinstance(producao, Conference) else {}
    return {
        'schema_versao': '3', 'Docente': docente.get_nome(), 'tipo': tipo, 'ano': producao.get_ano(),
        'titulo': producao.get_titulo(), 'venue': local, 'revista': local if tipo == 'Periódico' else '',
        'issn': producao.get_issn() if tipo == 'Periódico' else getattr(metadados, 'issn', ''),
        'doi': getattr(metadados, 'doi', ''), 'isbn': getattr(metadados, 'isbn', ''),
        'autores': json.dumps([a.nome_citacao or a.nome for a in autores] or producao.get_autores(), ensure_ascii=False),
        'autores_detalhados': json.dumps([a.__dict__ for a in autores], ensure_ascii=False),
        'curriculo_id': getattr(p, 'curriculo_id', ''), 'arquivo_xml': getattr(p, 'arquivo_xml', ''),
        'sequencia': getattr(p, 'sequencia', ''), 'elemento_xml': getattr(p, 'elemento_xml', ''),
        'proveniencia_incompleta': getattr(p, 'incompleta', False), 'estrato': producao.get_estrato() or '',
        'qualis_status': (resultado or {}).get('qualis_status', ''),
        'qualis_requer_revisao': (resultado or {}).get('qualis_requer_revisao', False),
        'qualis_candidatos': (resultado or {}).get('qualis_candidatos', ''),
        **{campo: (resultado or {}).get(campo, '') for campo in (
            'qualis_input_id', 'qualis_evento_id', 'qualis_registro_id', 'qualis_sigla',
            'qualis_nome_oficial', 'qualis_quadrienio', 'qualis_estrato', 'qualis_origem_decisao',
            'qualis_politica_versao', 'qualis_score_fuzzy', 'qualis_score_margem', 'qualis_obs',
        )},
    }


def gera_publicacoes_ocorrencias_csv(csv_out_path, docentes):
    linhas = []
    for docente in docentes:
        for producao in docente.get_producoes():
            if isinstance(producao, Journal) or (isinstance(producao, Conference) and producao.get_natureza() is NaturezaTrabalho.COMPLETO):
                linhas.append(_linha_ocorrencia(docente, producao))
    # IDs and fingerprints are output metadata.  They are not derived from row order.
    for linha in linhas:
        linha['ocorrencia_id'] = id_ocorrencia(linha)
        linha['conteudo_fingerprint'] = conteudo_fingerprint(linha)
    pd.DataFrame(linhas).to_csv(csv_out_path, index=False, encoding='utf-8-sig')
    return linhas


def _producao_por_linha(linha, canonical_id=''):
    autores = json.loads(linha.get('autores') or '[]')
    ano = int(linha['ano'])
    if linha['tipo'] == 'Periódico':
        producao = Journal(ano, '', linha.get('issn', ''), NaturezaArtigo.COMPLETO, linha.get('titulo', ''), linha.get('revista') or linha.get('venue', ''), autores, linha.get('estrato') or None)
    else:
        producao = Conference(ano, '', NaturezaTrabalho.COMPLETO, None, linha.get('titulo', ''), linha.get('venue', ''), autores, linha.get('estrato') or None)
    producao._publicacao_canonica_id = canonical_id
    return producao


def docentes_por_ocorrencias(csv_path, overrides=()):
    linhas = pd.read_csv(csv_path, dtype=str, keep_default_na=False).to_dict('records')
    for linha in linhas:
        linha['ano'] = int(linha['ano'])
        linha['sequencia'] = int(linha.get('sequencia') or 0)
    resultado = deduplicar_publicacoes(linhas, overrides=overrides)
    linhas_por_id = {resultado.ids_ocorrencia[id(linha)]: linha for linha in linhas}
    docentes = {}
    vistos = set()
    for ocorrencia_id, canonica_id in resultado.canonica_por_ocorrencia.items():
        linha = linhas_por_id[ocorrencia_id]
        chave = (linha['Docente'], canonica_id)
        if chave in vistos: continue
        vistos.add(chave)
        docentes.setdefault(linha['Docente'], PessoaPPGI(linha['Docente'])).insere_producao(_producao_por_linha(linhas_por_id[canonica_id], canonica_id))
    return list(docentes.values()), resultado


def docentes_por_canonicas(canonicas_path, membros_path):
    """Build individual score input from Part 1 output only."""
    canonicas = pd.read_csv(canonicas_path, dtype=str, keep_default_na=False).to_dict('records')
    membros = pd.read_csv(membros_path, dtype=str, keep_default_na=False).to_dict('records')
    by_id = {r['publicacao_canonica_id']: r for r in canonicas}
    docentes, vistos = {}, set()
    for m in membros:
        key=(m['Docente'],m['publicacao_canonica_id'])
        if key in vistos or m['publicacao_canonica_id'] not in by_id: continue
        vistos.add(key); row=by_id[m['publicacao_canonica_id']]
        if str(row.get('bloqueia_pontuacao','')).lower()=='true': raise ValueError('conflito de estrato em publicação canônica')
        docentes.setdefault(m['Docente'], PessoaPPGI(m['Docente'])).insere_producao(_producao_por_linha(row, row['publicacao_canonica_id']))
    return list(docentes.values())


def gera_deduplicacao_csvs(dir_out, prefixo, resultado):
    linhas = []
    for item in resultado.ocorrencias:
        item_id = resultado.ids_ocorrencia[id(item)]
        linha = dict(item) if isinstance(item, dict) else {}
        linha.update({'ocorrencia_id': item_id, 'publicacao_canonica_id': resultado.canonica_por_ocorrencia[item_id]})
        linhas.append(linha)
    colunas_ocorrencias = sorted(set(k for x in linhas for k in x) | {'ocorrencia_id','publicacao_canonica_id','conteudo_fingerprint'})
    pd.DataFrame(linhas, columns=colunas_ocorrencias).to_csv(os.path.join(dir_out, prefixo + '_publicacoes_ocorrencias.csv'), index=False, encoding='utf-8-sig')
    pd.DataFrame(resultado.publicacoes_unicas).to_csv(os.path.join(dir_out, prefixo + '_publicacoes_unicas.csv'), index=False, encoding='utf-8-sig')
    pd.DataFrame(resultado.membros, columns=['publicacao_canonica_id','ocorrencia_id','Docente']).to_csv(os.path.join(dir_out, prefixo + '_publicacoes_membros.csv'), index=False, encoding='utf-8-sig')
    colunas_decisao = ['ocorrencia_a', 'ocorrencia_b', 'decisao', 'motivo', 'score_titulo']
    pd.DataFrame([d.__dict__ for d in resultado.decisoes], columns=colunas_decisao).to_csv(os.path.join(dir_out, prefixo + '_deduplicacao_decisoes.csv'), index=False, encoding='utf-8-sig')
    pd.DataFrame([d.__dict__ for d in resultado.revisoes], columns=colunas_decisao).to_csv(os.path.join(dir_out, prefixo + '_deduplicacao_revisao.csv'), index=False, encoding='utf-8-sig')


# Compatibilidade de biblioteca para consumidores antigos. As etapas PPGI não
# usam esta função e não aceitam este formato como entrada.
def gera_recredenciamento_csv(csv_out_path, docentes):
    linhas = []
    for docente in docentes:
        for producao in docente.get_producoes():
            if isinstance(producao, Journal):
                linhas.append({'Docente': docente.get_nome(), 'Tipo': 'Periódico', 'Qualis': producao.get_estrato() or 'Qualis não identificado', 'Ano': producao.get_ano(), 'Local': producao.get_revista(), 'Título': producao.get_titulo()})
            elif isinstance(producao, Conference) and producao.get_natureza() is NaturezaTrabalho.COMPLETO:
                linhas.append({'Docente': docente.get_nome(), 'Tipo': 'Conferência', 'Qualis': producao.get_estrato() or 'Qualis não identificado', 'Ano': producao.get_ano(), 'Local': producao.get_venue(), 'Título': producao.get_titulo()})
    pd.DataFrame(linhas, columns=['Docente', 'Tipo', 'Qualis', 'Ano', 'Local', 'Título']).to_csv(csv_out_path, index=False)


def gera_qualis_revisao_csv(csv_out_path: str, docentes: list[PessoaPPGI]):
    """Exporta diagnósticos de conferências sem decisão automática."""
    linhas = []
    for docente in docentes:
        for producao in docente.get_producoes():
            if not isinstance(producao, Conference):
                continue
            resultado = producao.get_qualis_match() or {}
            if not resultado.get("qualis_requer_revisao"):
                continue
            linhas.append({
                "Docente": docente.get_nome(),
                "Título": producao.get_titulo(),
                "Ano": producao.get_ano(),
                "Evento informado": producao.get_venue(),
                "Status": resultado.get("qualis_status"),
                "Candidatos": resultado.get("qualis_candidatos"),
                "Score primeiro": resultado.get("qualis_score_fuzzy"),
                "Margem segundo": resultado.get("qualis_score_margem"),
                "Motivo": resultado.get("qualis_obs") or resultado.get("qualis_llm_motivo"),
                "qualis_input_id": resultado.get("qualis_input_id"),
                "Sigla informada": resultado.get("sigla_original", ""),
                "Candidatos JSON": resultado.get("qualis_candidatos"),
                "Ação": "",
                "qualis_registro_id selecionado": "",
                "Justificativa": "",
            })
    colunas = ["qualis_input_id", "Docente", "Título", "Ano", "Evento informado", "Sigla informada", "Status", "Candidatos", "Candidatos JSON", "Score primeiro", "Margem segundo", "Motivo", "Ação", "qualis_registro_id selecionado", "Justificativa"]
    fila = pd.DataFrame(linhas, columns=colunas)
    if not fila.empty:
        agrupamento = {coluna: "first" for coluna in colunas if coluna != "qualis_input_id"}
        agrupamento["Docente"] = lambda valores: " | ".join(sorted(set(valores)))
        agrupamento["Título"] = lambda valores: " | ".join(sorted(set(valores)))
        fila = fila.groupby("qualis_input_id", dropna=False, as_index=False).agg(agrupamento)
    fila.to_csv(csv_out_path, index=False, encoding="utf-8-sig")
