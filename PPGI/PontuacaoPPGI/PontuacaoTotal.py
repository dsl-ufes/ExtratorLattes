from itertools import combinations
import networkx as nx
import Levenshtein

from ArquivoInterno.enums.NaturezaTrabalho import NaturezaTrabalho
from PontuacaoPPGI.NotaInfo import NotaInfo
import PontuacaoPPGI.Tabela as tb
import PontuacaoPPGI.utils as ppgiu

from PontuacaoPPGI.Journal import Journal

def same_paper_title(str1, str2):
    str1 = str(str1).strip().lower()
    str2 = str(str2).strip().lower()
    if len(str1) == 0 or len(str2) == 0:
        return False
    if len(str1) >= 20 and len(str2) >= 20 and (str1 in str2 or str2 in str1):
        return True
    else:
        if len(str1) >= 10 and len(str2) >= 10 and Levenshtein.distance(str1, str2) <= 5:
            return 1
    return 0

### Verificar depois ###
def conferenceNameSimilarity(str1, str2):
    if len(str1) >= 10 and len(str2) >= 10:
        return Levenshtein.ratio(str1, str2)
    return 0

def samePapers(a, b):
    if a.get_ano() == b.get_ano() and same_paper_title(a.get_titulo(), b.get_titulo()):
        return True
    return False

def deduplicate_papers(papers):
    # A etapa de ocorrências fornece uma identidade canônica. Ela substitui a
    # comparação histórica por título para o agregado PPGI.
    if papers and all(hasattr(paper, '_publicacao_canonica_id') for paper in papers):
        unicos = {}
        for paper in papers:
            unicos.setdefault(paper._publicacao_canonica_id, paper)
        return [unicos[chave] for chave in sorted(unicos)]
    # prepare
    d = {}
    graph = nx.Graph()
    for i, paper in enumerate(papers):
        d[i] = paper
        graph.add_node(i)
        
    error_list = {}

    # creating grap
    for a, b in combinations(d.keys(), 2):
        papera = d[a]
        paperb = d[b]
        if samePapers(papera, paperb):
            # Mesmo paper mas estratos diferentes
            if papera.get_estrato() != paperb.get_estrato():
                if papera.get_titulo() not in error_list:
                    error_list[papera.get_titulo()] = set([papera, paperb])
                else:
                    error_list[papera.get_titulo()].update([papera, paperb])
            graph.add_edge(a, b)
    
    if len(error_list) > 0:
        erro_msg = ''
        erro_msg += "="*21 + " Conflitos encontrados " + "="*21 + "\n"
        erro_msg += "Ao deduplicar os papers, foram encontrados os seguintes conflitos:\n\n"
        
        for titulo_papers in error_list:
            erro_msg += f" - Título: '{titulo_papers}'\n"
            for i, paper in enumerate(error_list[titulo_papers]):    
                tipo = "Periódico" if isinstance(paper, Journal) else "Conferência"
                erro_msg += f"    {i+1} - Tipo: {tipo} | Ano: {paper.get_ano()} | Estrato {i+1}: {paper.get_estrato()}\n"
        
        raise ValueError(erro_msg)
    # getting connected components
    components = nx.connected_components(graph)

    # here
    cleanpapers = []
    for group in components:
        cleanpapers.append(d[min(group)])

    return cleanpapers

def calcula_nota_geral(docentes, nota_info: NotaInfo, csv_path: str):
    journals, conferences = ppgiu.all_jornal_conferences(docentes)

    journals = deduplicate_papers(journals)
    conferences = deduplicate_papers(conferences)

    tabela = tb.Tabela(nota_info.get_prod_min_tag())

    for journal in journals:
        if nota_info.prod_valida_para_nota(journal.get_ano()):
            tabela.add_qtd_by_tag(tb.producao_tag_padrao(journal), 1)
    
    for conference in conferences:
        if nota_info.prod_valida_para_nota(conference.get_ano()):
            if conference.get_natureza() is not NaturezaTrabalho.COMPLETO:
                continue
            tabela.add_qtd_by_tag(tb.producao_tag_padrao(conference), 1)
    
    nota = 0.0
        
    for tag in tabela.get_all_tags():
        nota += tabela.get_qtd_by_tag(tag) * nota_info.valor_qualis(tag)
    
    media = nota / len(docentes)
    media_truncada = nota_info.arrendonda_nota(media)

    df = tabela.get_data_frame()

    df['Nota PPGI'] = [media]
    df['Nota PPGI Truncada'] = [media_truncada]
    df_T = df.T
    df_T.columns = ['Total'] 
    df_T.to_csv(csv_path)
