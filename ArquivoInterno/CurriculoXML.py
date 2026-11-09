import xml.etree.ElementTree as ET
import ArquivoInterno.Producao as prod
from pathlib import Path
from ArquivoInterno.Publicacao import AutorPublicacao, MetadadosPublicacao, ProvenienciaPublicacao

class CurriculoXML():
    def __init__(self, caminho_xml: str):
        self._root = ET.parse(caminho_xml)
        self._caminho_xml = str(caminho_xml)
        dados = self._root.find("DADOS-GERAIS")
        # The Lattes identifier belongs to CURRICULO-VITAE.  A filename is not
        # provenance and must never become an identity.
        self._curriculo_id = self._root.getroot().attrib.get("NUMERO-IDENTIFICADOR", "") or (dados.attrib.get("NUMERO-IDENTIFICADOR", "") if dados is not None else "")
        if not self._curriculo_id:
            raise ValueError("CURRICULO-VITAE sem NUMERO-IDENTIFICADOR")

    @staticmethod
    def _atributo(elemento, nome):
        return elemento.attrib.get(nome, "") if elemento is not None else ""

    def _autores(self, item):
        autores = []
        for ordem, autor in enumerate(item.iter("AUTORES"), 1):
            autores.append(AutorPublicacao(
                nome=self._atributo(autor, "NOME-COMPLETO-DO-AUTOR"),
                nome_citacao=self._atributo(autor, "NOME-PARA-CITACAO"),
                ordem=ordem,
                id_lattes=self._atributo(autor, "NRO-ID-CNPQ") or self._atributo(autor, "NUMERO-IDENTIFICADOR"),
                id_cnpq=self._atributo(autor, "ID-CNPQ"),
            ))
        return autores

    def _metadados(self, item, detalhe, maisdetalhe, sequencia, elemento):
        autores = tuple(self._autores(item))
        return MetadadosPublicacao(
            doi=self._atributo(maisdetalhe, "DOI") or self._atributo(detalhe, "DOI"),
            issn=self._atributo(maisdetalhe, "ISSN"),
            isbn=self._atributo(maisdetalhe, "ISBN"),
            volume=self._atributo(maisdetalhe, "VOLUME"),
            fasciculo=self._atributo(maisdetalhe, "FASCICULO"),
            pagina_inicial=self._atributo(maisdetalhe, "PAGINA-INICIAL"),
            pagina_final=self._atributo(maisdetalhe, "PAGINA-FINAL"),
            autores_detalhados=autores,
            proveniencia=ProvenienciaPublicacao(self._curriculo_id, self._caminho_xml, sequencia, elemento, not bool(sequencia)),
        )

    def get_nome(self):
        dadosgerais  = self._root.find("DADOS-GERAIS")

        if not dadosgerais.attrib["NOME-COMPLETO"]:
            print("Falta nome")

        return dadosgerais.attrib["NOME-COMPLETO"]
    
    def get_nivel_academico(self):
        niveis = ("GRADUACAO", "MESTRADO", "DOUTORADO")

        ano_conclusao = 10000
        nivel        = -1
        maiornivel   = -1
        for n in niveis:
            nivel += 1
            for item in self._root.iter(n):
                if item.attrib['ANO-DE-CONCLUSAO']:
                    maiornivel = nivel
                    ano_conclusao = _parse_ano(item.attrib['ANO-DE-CONCLUSAO'])

        return ano_conclusao, niveis[maiornivel]

    def get_livro(self, ano_inicio: int, ano_fim: int):
        all_livros = []

        for item in self._root.iter("LIVRO-PUBLICADO-OU-ORGANIZADO"):
            for detalhe in item.iter("DADOS-BASICOS-DO-LIVRO"):
                ano  = _parse_ano(detalhe.attrib['ANO'])
                pais = detalhe.attrib['PAIS-DE-PUBLICACAO']
                tipo = detalhe.attrib['TIPO']
                if tipo == "LIVRO_PUBLICADO":
                    for maisdetalhe in item.iter("DETALHAMENTO-DO-LIVRO"):
                        isbn = maisdetalhe.attrib['ISBN']
                    if ano >= ano_inicio and ano <= ano_fim:
                        all_livros.append(prod.Livro(ano, pais, isbn))

        return all_livros
    
    def get_capitulo_livro(self, ano_inicio: int, ano_fim: int):
        all_capitulos = []

        for item in self._root.iter("CAPITULO-DE-LIVRO-PUBLICADO"):
            for detalhe in item.iter("DADOS-BASICOS-DO-CAPITULO"):
                ano  = _parse_ano(detalhe.attrib['ANO'])
                pais = detalhe.attrib['PAIS-DE-PUBLICACAO']
                for maisdetalhe in item.iter("DETALHAMENTO-DO-CAPITULO"):
                    isbn = maisdetalhe.attrib['ISBN']
                if ano >= ano_inicio and ano <= ano_fim:
                    all_capitulos.append(prod.CapituloLivro(ano, pais, isbn))
        
        return all_capitulos
    
    def get_artigo(self, ano_inicio: int, ano_fim: int):
        all_artigos = []

        for item in self._root.iter("ARTIGO-PUBLICADO"):
            detalhe = next(iter(item.iter("DADOS-BASICOS-DO-ARTIGO")), None)
            maisdetalhe = next(iter(item.iter("DETALHAMENTO-DO-ARTIGO")), None)
            if detalhe is None:
                continue
            ano = _parse_ano(self._atributo(detalhe, 'ANO-DO-ARTIGO'))
            natureza = self._atributo(detalhe, 'NATUREZA')
            pais = self._atributo(detalhe, 'PAIS-DE-PUBLICACAO') or self._atributo(maisdetalhe, 'LOCAL-DE-PUBLICACAO')
            titulo = self._atributo(detalhe, 'TITULO-DO-ARTIGO')
            issn = self._atributo(maisdetalhe, 'ISSN')
            revista = self._atributo(maisdetalhe, 'TITULO-DO-PERIODICO-OU-REVISTA')
            if ano >= ano_inicio and ano <= ano_fim:
                metadados = self._metadados(item, detalhe, maisdetalhe, self._atributo(item, "SEQUENCIA-PRODUCAO"), "ARTIGO-PUBLICADO")
                autores = [a.nome_citacao or a.nome for a in metadados.autores_detalhados]
                all_artigos.append(prod.Artigo(ano, pais, issn, prod.NaturezaArtigo.by_tag(natureza), titulo, revista, autores, metadados))

        return all_artigos


    def get_organizacao_livro(self, ano_inicio: int, ano_fim: int):
        all_organizacao = []
        
        for item in self._root.iter("LIVRO-PUBLICADO-OU-ORGANIZADO"):
            for detalhe in item.iter("DADOS-BASICOS-DO-LIVRO"):
                ano  = _parse_ano(detalhe.attrib['ANO'])
                pais = ""
                isbn = ""
                if "PAIS" in detalhe.attrib:
                    pais = detalhe.attrib['PAIS']
                tipo = detalhe.attrib['TIPO']
                if tipo == "LIVRO_ORGANIZADO_OU_EDICAO":
                    natureza = detalhe.attrib['NATUREZA']
                    for maisdetalhe in item.iter("DETALHAMENTO-DO-LIVRO"):
                        isbn = maisdetalhe.attrib['ISBN']
                    if ano >= ano_inicio and ano <= ano_fim:
                        all_organizacao.append(prod.OrganizacaoLivro(ano, pais, isbn, prod.NaturezaLivro.by_tag(natureza)))
        
        return all_organizacao

    def get_traducao(self, ano_inicio: int, ano_fim: int):
        all_traducoes = []

        for item in self._root.iter("TRADUCAO"):
            for detalhe in item.iter("DADOS-BASICOS-DA-TRADUCAO"):
                ano  = _parse_ano(detalhe.attrib['ANO'])
                pais = detalhe.attrib['PAIS-DE-PUBLICACAO']
                natureza = detalhe.attrib['NATUREZA']
                for maisdetalhe in item.iter("DETALHAMENTO-DA-TRADUCAO"):
                    issn_isbn = maisdetalhe.attrib['ISSN-ISBN']
                    if ano >= ano_inicio and ano <= ano_fim:
                        all_traducoes.append(prod.Traducao(ano, pais,issn_isbn, prod.NaturezaTraducao(natureza)))
        
        return all_traducoes

    def get_trabalho_evento(self, ano_inicio: int, ano_fim: int):
        all_trabalhos = []

        for item in self._root.iter("TRABALHO-EM-EVENTOS"):
            detalhe = next(iter(item.iter("DADOS-BASICOS-DO-TRABALHO")), None)
            maisdetalhe = next(iter(item.iter("DETALHAMENTO-DO-TRABALHO")), None)
            if detalhe is None:
                continue
            ano = _parse_ano(self._atributo(detalhe, 'ANO-DO-TRABALHO'))
            pais = self._atributo(detalhe, 'PAIS-DO-EVENTO')
            natureza = self._atributo(detalhe, 'NATUREZA')
            titulo = self._atributo(detalhe, 'TITULO-DO-TRABALHO')
            classificacao = self._atributo(maisdetalhe, "CLASSIFICACAO-DO-EVENTO") or "NACIONAL"
            venue = self._atributo(maisdetalhe, 'NOME-DO-EVENTO').strip()
            if ano >= ano_inicio and ano <= ano_fim:
                metadados = self._metadados(item, detalhe, maisdetalhe, self._atributo(item, "SEQUENCIA-PRODUCAO"), "TRABALHO-EM-EVENTOS")
                autores = [a.nome_citacao or a.nome for a in metadados.autores_detalhados]
                all_trabalhos.append(prod.TrabalhoEvento(ano, pais, prod.NaturezaTrabalho.by_tag(natureza), prod.ClassificacaoEvento.by_tag(classificacao), titulo, venue, autores, metadados))
            
        return all_trabalhos
    
    def get_organizacao_evento(self, ano_inicio: int, ano_fim: int):
        all_eventos = []

        for item in self._root.iter("ORGANIZACAO-DE-EVENTO"):
            
            for detalhe in item.iter("DADOS-BASICOS-DA-ORGANIZACAO-DE-EVENTO"):
                ano  = _parse_ano(detalhe.attrib['ANO'])
                pais = detalhe.attrib['PAIS']
                tipo = detalhe.attrib['TIPO']

                if ano >= ano_inicio and ano <= ano_fim:
                    all_eventos.append(prod.OrganizacaoEvento(ano, pais, prod.TipoEvento.by_tag(tipo)))
            
        return all_eventos
    
    def get_programa_radio_tv(self, ano_inicio: int, ano_fim: int):
        all_programa = []

        for item in self._root.iter("PROGRAMA-DE-RADIO-OU-TV"):
            
            for detalhe in item.iter("DADOS-BASICOS-DO-PROGRAMA-DE-RADIO-OU-TV"):
                ano  = _parse_ano(detalhe.attrib['ANO'])
                pais = detalhe.attrib['PAIS']
                natureza = detalhe.attrib['NATUREZA']

                if ano >= ano_inicio and ano <= ano_fim:
                    all_programa.append(prod.ProgramaRadioTV(ano, pais, prod.NaturezaPrograma.by_tag(natureza)))
            
        return all_programa

    def get_artistica_cultural(self, ano_inicio: int, ano_fim: int):
        all_artistica_cultural = []

        # Dicionário que mapeia todas as tags contidas na tag "PRODUCAO-ARTISTICA-CULTURAL" para suas respectivas 
        # preposições o que ajuda a completar a tag "DADOS-BASICOS-PREPOSICAO-TIPOOBRA"
        tiposproducaoartistica = {"APRESENTACAO-DE-OBRA-ARTISTICA": "DA", "APRESENTACAO-EM-RADIO-OU-TV": "DA", 
                                  "ARRANJO-MUSICAL": "DO", "COMPOSICAO-MUSICAL": "DA", "CURSO-DE-CURTA-DURACAO": "DO", 
                                  "OBRA-DE-ARTES-VISUAIS": "DA", "OUTRA-PRODUCAO-ARTISTICA-CULTURAL": "DE", 
                                  "SONOPLASTIA": "DE", "ARTES-CENICAS": "DE", "ARTES-VISUAIS": "DE", 
                                  "MUSICA": "DA"}

        for tipo in tiposproducaoartistica:
            for item in self._root.iter(tipo):
                for detalhe in item.iter("DADOS-BASICOS-%s-%s"%(tiposproducaoartistica[tipo], tipo)):
                    ano  = _parse_ano(detalhe.attrib['ANO'])
                    pais     = detalhe.attrib['PAIS']
                    if ano >= ano_inicio and ano <= ano_fim:
                        if tipo == "ARTES-CENICAS":
                            all_artistica_cultural.append(prod.ArtesCenicas(ano, pais))
                            continue
                        if tipo == "ARTES-VISUAIS":
                            all_artistica_cultural.append(prod.ArtesVisuais(ano, pais))
                            continue
                        if tipo == "MUSICA":
                            all_artistica_cultural.append(prod.Musica(ano, pais))
                            continue
                        all_artistica_cultural.append(prod.ArtisticaCultural(ano, pais))
        
        return all_artistica_cultural

    def get_registro_patente(self, ano_inicio: int, ano_fim: int):
        all_patentes = []

        for item in self._root.iter("REGISTRO-OU-PATENTE"):
            pais = ""
            if 'DATA-DE-CONCESSAO' in item.attrib:
                if item.attrib['DATA-DE-CONCESSAO'] != "":
                    data = item.attrib['DATA-DE-CONCESSAO']
                    ano = _parse_ano(data[4:])
                    if ano >= ano_inicio and ano <= ano_fim:
                        all_patentes.append(prod.RegistroPatente(ano, pais))
                        continue
            if 'DATA-PEDIDO-DE-DEPOSITO' in item.attrib:
                if item.attrib['DATA-PEDIDO-DE-DEPOSITO'] != "":
                    data = item.attrib['DATA-PEDIDO-DE-DEPOSITO']
                    ano = _parse_ano(data[4:])
                    if ano >= ano_inicio and ano <= ano_fim:
                        all_patentes.append(prod.RegistroPatente(ano, pais))
                        continue
        
        return all_patentes

    def _get_orientacao_mestrado(self, ano_inicio: int, ano_fim: int):
        orientacoes = []

        tipo_md = "MESTRADO"

        tipoitem = "ORIENTACOES-CONCLUIDAS-PARA-%s"%tipo_md
        dadosbasicos = "DADOS-BASICOS-DE-ORIENTACOES-CONCLUIDAS-PARA-%s"%tipo_md
        detalhamento = "DETALHAMENTO-DE-ORIENTACOES-CONCLUIDAS-PARA-%s"%tipo_md

        for item in self._root.iter(tipoitem):
            for detalhe in item.iter(dadosbasicos):
                ano  = _parse_ano(detalhe.attrib['ANO'])
                pais = detalhe.attrib['PAIS']
            tipo_orientador = ""
            for maisdetalhe in item.iter(detalhamento):
                if "TIPO-DE-ORIENTACAO" in maisdetalhe.attrib:
                    tipo_orientador = maisdetalhe.attrib['TIPO-DE-ORIENTACAO']
            if ano >= ano_inicio and ano <= ano_fim:
                orientacoes.append(prod.OrientacaoMD(ano, pais, prod.TipoOrientacaoMD(tipo_md), prod.TipoOrientador(tipo_orientador)))

        return orientacoes
    
    def _get_orientacao_doutorado(self, ano_inicio: int, ano_fim: int):
        orientacoes = []

        tipo_md = "DOUTORADO"
        tipoitem = "ORIENTACOES-CONCLUIDAS-PARA-%s"%tipo_md
        dadosbasicos = "DADOS-BASICOS-DE-ORIENTACOES-CONCLUIDAS-PARA-%s"%tipo_md
        detalhamento = "DETALHAMENTO-DE-ORIENTACOES-CONCLUIDAS-PARA-%s"%tipo_md

        for item in self._root.iter(tipoitem):
            for detalhe in item.iter(dadosbasicos):
                ano  = _parse_ano(detalhe.attrib['ANO'])
                pais = detalhe.attrib['PAIS']
            tipo_orientador = ""
            for maisdetalhe in item.iter(detalhamento):
                if "TIPO-DE-ORIENTACAO" in maisdetalhe.attrib:
                    tipo_orientador = maisdetalhe.attrib['TIPO-DE-ORIENTACAO']
            if ano >= ano_inicio and ano <= ano_fim:
                orientacoes.append(prod.OrientacaoMD(ano, pais, prod.TipoOrientacaoMD(tipo_md), prod.TipoOrientador(tipo_orientador)))

        return orientacoes

    def get_orientacao_md(self, ano_inicio: int, ano_fim: int):
        orientacoes = self._get_orientacao_doutorado(ano_inicio, ano_fim)

        orientacoes += self._get_orientacao_mestrado(ano_inicio, ano_fim)

        return orientacoes

    def _get_orientacao_monografia(self, ano_inicio: int, ano_fim: int):
        orientacoes = []

        for item in self._root.iter("OUTRAS-ORIENTACOES-CONCLUIDAS"):
            for detalhe in item.iter("DADOS-BASICOS-DE-OUTRAS-ORIENTACOES-CONCLUIDAS"):
                ano  = _parse_ano(detalhe.attrib['ANO'])
                pais     = detalhe.attrib['PAIS']
                natureza = detalhe.attrib['NATUREZA']

                if natureza == "MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO":
                    if ano >= ano_inicio and ano <= ano_fim:
                        orientacoes.append(prod.OrientacaoMTI(ano, pais, prod.TipoOrientacaoMTI("MONOGRAFIA")))

        return orientacoes
    
    def _get_orientacao_tcc(self, ano_inicio: int, ano_fim: int):
        orientacoes = []

        for item in self._root.iter("OUTRAS-ORIENTACOES-CONCLUIDAS"):
            for detalhe in item.iter("DADOS-BASICOS-DE-OUTRAS-ORIENTACOES-CONCLUIDAS"):
                ano  = _parse_ano(detalhe.attrib['ANO'])
                pais = detalhe.attrib['PAIS']
                natureza = detalhe.attrib['NATUREZA']

                if natureza == "TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO":
                    if ano >= ano_inicio and ano <= ano_fim:
                        orientacoes.append(prod.OrientacaoMTI(ano, pais, prod.TipoOrientacaoMTI("TCC")))

        return orientacoes
    
    def _get_orientacao_iniciacao_cientifica(self, ano_inicio: int, ano_fim: int):
        orientacoes = []

        for item in self._root.iter("OUTRAS-ORIENTACOES-CONCLUIDAS"):
            for detalhe in item.iter("DADOS-BASICOS-DE-OUTRAS-ORIENTACOES-CONCLUIDAS"):
                ano  = _parse_ano(detalhe.attrib['ANO'])
                pais = detalhe.attrib['PAIS']
                natureza = detalhe.attrib['NATUREZA']

                if natureza == "INICIACAO_CIENTIFICA":
                    if ano >= ano_inicio and ano <= ano_fim:
                        orientacoes.append(prod.OrientacaoMTI(ano, pais, prod.TipoOrientacaoMTI("INICIACAO_CIENTIFICA")))

        return orientacoes

    def get_orientacao_mti(self, ano_inicio: int, ano_fim: int):
        orientacoes = self._get_orientacao_monografia(ano_inicio, ano_fim)

        orientacoes += self._get_orientacao_tcc(ano_inicio, ano_fim)

        orientacoes += self._get_orientacao_iniciacao_cientifica(ano_inicio, ano_fim)

        return orientacoes
    
    def get_all_producoes(self, ano_inicio: int, ano_fim: int):
        producoes = []
        
        producoes += self.get_livro(ano_inicio, ano_fim)
        producoes += self.get_capitulo_livro(ano_inicio, ano_fim)
        producoes += self.get_organizacao_livro(ano_inicio, ano_fim)
        producoes += self.get_traducao(ano_inicio, ano_fim)
        producoes += self.get_programa_radio_tv(ano_inicio, ano_fim)
        producoes += self.get_trabalho_evento(ano_inicio, ano_fim)
        producoes += self.get_artistica_cultural(ano_inicio, ano_fim)
        producoes += self.get_registro_patente(ano_inicio, ano_fim)
        producoes += self.get_orientacao_md(ano_inicio, ano_fim)
        producoes += self.get_orientacao_mti(ano_inicio, ano_fim)
        producoes += self.get_artigo(ano_inicio, ano_fim)
        producoes += self.get_organizacao_evento(ano_inicio, ano_fim)
        
        return producoes

def _parse_ano(ano):
    try:
        # Se for uma string que não pode ser convertida para inteiro, dará ValueError
        return int(ano)
    except ValueError:
        # Se for uma string como "rint" ou qualquer outra, retorna 0
        return 0

if __name__ == "__main__":
    cc = CurriculoXML("../Dados/Curriculos/45163294768.xml")

    myList = cc.get_livro(2000, 2025)

    for a in myList:
        print(a)
