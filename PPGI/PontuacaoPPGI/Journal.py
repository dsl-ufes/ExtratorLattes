from ArquivoInterno.Producao import Artigo
from ArquivoInterno.enums import NaturezaArtigo


class Journal(Artigo):
    
    def __init__(self, ano: int, pais: str, issn: str,  natureza: NaturezaArtigo, titulo: str, revista: str, autores: list, estrato: str, metadados=None):
        super().__init__(ano, pais, issn, natureza, titulo, revista, autores, metadados)
        self._estrato = estrato
    
    def by_artigo(artigo: Artigo, estrato: str):
        return Journal(artigo.get_ano(), artigo.get_pais(), artigo.get_issn(), artigo.get_natureza(), artigo.get_titulo(), artigo.get_revista(), artigo.get_autores(), estrato, artigo.get_metadados())

    def get_estrato(self):
        return self._estrato

    def set_estrato(self, estrato):
        self._estrato = estrato
