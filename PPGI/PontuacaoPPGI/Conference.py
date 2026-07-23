from ArquivoInterno.Producao import TrabalhoEvento
from ArquivoInterno.enums import ClassificacaoEvento, NaturezaTrabalho


class Conference(TrabalhoEvento):

    def __init__(self, ano: int, pais: str, natureza: NaturezaTrabalho, classificacao: ClassificacaoEvento, titulo: str, venue: str, autores: list, estrato: str, metadados=None):
        super().__init__(ano, pais, natureza, classificacao, titulo, venue, autores, metadados)
        self._estrato = estrato
        self._qualis_match = None

    def by_trabalho_evento(conf: TrabalhoEvento, estrato: str):
        return Conference(conf.get_ano(), conf.get_pais(), conf.get_natureza(), conf.get_classificacao(), conf.get_titulo(), conf.get_venue(), conf.get_autores(), estrato, conf.get_metadados())

    def get_estrato(self):
        return self._estrato
    
    def set_estrato(self, estrato):
        self._estrato = estrato

    def get_qualis_match(self):
        return self._qualis_match

    def set_qualis_match(self, resultado: dict):
        self._qualis_match = resultado
    
