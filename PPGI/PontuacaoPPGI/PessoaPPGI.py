from ArquivoInterno import Producao
from ArquivoInterno.CurriculoXML import CurriculoXML
from Classificador.Qualis import Qualis
from Classificador.QualisConferencia import QualisConferencia
from PontuacaoPPGI.Conference import Conference
from PontuacaoPPGI.Journal import Journal

class PessoaPPGI():

    def __init__(self, nome: str):
        self._nome = nome
        self._producoes = []
    
    def get_nome(self):
        return self._nome
    
    def get_producoes(self):
        return self._producoes
    
    def carrega_producoes_by_lattes(self, caminho: str, ano_inicio_c: int, ano_fim_c: int, ano_inicio_p: int, ano_fim_p: int, get_nome = False):
        parse = CurriculoXML(caminho)

        if get_nome:
            self._nome = parse.get_nome()
        self._producoes += [Journal.by_artigo(x, None) for x in parse.get_artigo(ano_inicio_p, ano_fim_p)]
        self._producoes += [Conference.by_trabalho_evento(x, None) for x in parse.get_trabalho_evento(ano_inicio_c, ano_fim_c)]

    def atualiza_estratos(self, qualis_journal: Qualis, qualis_conference: QualisConferencia):
        for prod in self._producoes:
            if isinstance(prod, Journal):
                prod.set_estrato(qualis_journal.get_estrato(prod.get_issn()))
            elif isinstance(prod, Conference):
                resultado = qualis_conference.get_match(
                    prod.get_venue(),
                    prod.get_ano(),
                )
                prod.set_qualis_match(resultado)
                prod.set_estrato(resultado["qualis_estrato"])

    def insere_producao(self, producao: Producao):
        self._producoes.append(producao)
