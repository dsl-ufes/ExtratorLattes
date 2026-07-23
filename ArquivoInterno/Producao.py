"""
Módulo contendo as classes de produção acadêmica extraídas de currículos Lattes.

Este módulo define classes para representar diferentes tipos de produção acadêmica,
baseadas no XML Schema do Currículo Lattes.
Cada classe corresponde a um tipo específico de produção bibliográfica, técnica ou artística.
"""

from ArquivoInterno.enums import *

class Producao():
    """
    Classe base para todas as produções acadêmicas.
    
    Representa qualquer tipo de produção registrada no Currículo Lattes,
    contendo os atributos básicos comuns a todas as produções.
    
    Attributes:
        _ano (int): Ano de publicação ou realização da produção
        _pais (str): País onde a produção foi publicada ou realizada
    """

    def __init__(self, ano: int, pais: str):
        """
        Inicializa uma produção acadêmica.
        
        Args:
            ano (int): Ano da produção
            pais (str): País da produção
        """
        self._ano = ano
        self._pais = pais

    def get_ano(self):
        """Retorna o ano da produção."""
        return self._ano

    def get_pais(self):
        """Retorna o país da produção."""
        return self._pais

class Livro(Producao):
    """
    Representa um livro publicado.
    
    Corresponde ao elemento LIVRO-PUBLICADO-OU-ORGANIZADO com TIPO="LIVRO_PUBLICADO"
    no XML do Currículo Lattes (DADOS-BASICOS-DO-LIVRO).
    
    Attributes:
        _isbn (str): Número ISBN do livro (atributo do DETALHAMENTO-DO-LIVRO)
        _ano (int): Ano de publicação (herdado de Producao)
        _pais (str): País de publicação (herdado de Producao)
    """

    def __init__(self, ano: int, pais: str, isbn: str):
        """
        Inicializa um livro publicado.
        
        Args:
            ano (int): Ano de publicação
            pais (str): País de publicação
            isbn (str): Número ISBN do livro
        """
        super().__init__(ano, pais)
        self._isbn = isbn
    
    def get_isbn(self):
        """Retorna o ISBN do livro."""
        return self._isbn

    def __str__(self) -> str:
        return "Classe: Livro " + "Ano: " + str(self.get_ano()) + " País: " + self.get_pais() + " ISBN: " + self.get_isbn()

class CapituloLivro(Producao):
    """
    Representa um capítulo de livro publicado.
    
    Corresponde ao elemento CAPITULO-DE-LIVRO-PUBLICADO no XML do Currículo Lattes
    (DADOS-BASICOS-DO-CAPITULO e DETALHAMENTO-DO-CAPITULO).
    
    Attributes:
        _isbn (str): Número ISBN do livro que contém o capítulo
        _ano (int): Ano de publicação (herdado de Producao)
        _pais (str): País de publicação (herdado de Producao)
    """

    def __init__(self, ano: int, pais: str, isbn: str):
        """
        Inicializa um capítulo de livro.
        
        Args:
            ano (int): Ano de publicação
            pais (str): País de publicação
            isbn (str): Número ISBN do livro
        """
        super().__init__(ano, pais)
        self._isbn = isbn

    def get_isbn(self):
        """Retorna o ISBN do livro que contém o capítulo."""
        return self._isbn

    def __str__(self) -> str:
        return "Classe: CapituloLivro " + "Ano: " + str(self.get_ano()) + " País: " + self.get_pais() + " ISBN: " + self.get_isbn()
    
class OrganizacaoLivro(Producao):
    """
    Representa a organização ou edição de um livro.
    
    Corresponde ao elemento LIVRO-PUBLICADO-OU-ORGANIZADO com TIPO="LIVRO_ORGANIZADO_OU_EDICAO"
    no XML do Currículo Lattes (DADOS-BASICOS-DO-LIVRO).
    
    Attributes:
        _isbn (str): Número ISBN do livro organizado
        _natureza (NaturezaLivro): Tipo do livro organizado (ex: COLETANEA, TEXTO_INTEGRAL, ANAIS)
        _ano (int): Ano de publicação (herdado de Producao)
        _pais (str): País de publicação (herdado de Producao)
    """

    def __init__(self, ano: int, pais: str, isbn: str, natureza: NaturezaLivro):
        """
        Inicializa uma organização de livro.
        
        Args:
            ano (int): Ano de publicação
            pais (str): País de publicação
            isbn (str): Número ISBN do livro
            natureza (NaturezaLivro): Natureza do livro organizado
        """
        super().__init__(ano, pais)
        self._isbn = isbn
        self._natureza = natureza

    def get_isbn(self):
        """Retorna o ISBN do livro organizado."""
        return self._isbn
    
    def get_natureza(self):
        """Retorna a natureza do livro organizado."""
        return self._natureza

    def __str__(self) -> str:
        return "Classe: OrganizacaoLivro " + "Ano: " + str(self.get_ano()) + " País: " + self.get_pais() + " ISBN: " + self.get_isbn() + " natureza: " + str(self.get_natureza())
    
class Traducao(Producao):
    """
    Representa uma tradução de obra.
    
    Corresponde ao elemento TRADUCAO no XML do Currículo Lattes
    (DADOS-BASICOS-DA-TRADUCAO e DETALHAMENTO-DA-TRADUCAO).
    
    Attributes:
        _issn_isbn (str): Número ISSN ou ISBN da obra traduzida
        _natureza (NaturezaTraducao): Tipo da tradução (ex: LIVRO, CAPITULO, ARTIGO)
        _ano (int): Ano de publicação (herdado de Producao)
        _pais (str): País de publicação (herdado de Producao)
    """
    
    def __init__(self, ano: int, pais: str, issn_isbn: str, natureza: NaturezaTraducao):
        """
        Inicializa uma tradução.
        
        Args:
            ano (int): Ano de publicação
            pais (str): País de publicação
            issn_isbn (str): ISSN ou ISBN da obra traduzida
            natureza (NaturezaTraducao): Natureza da tradução
        """
        super().__init__(ano, pais)
        self._issn_isbn = issn_isbn
        self._natureza = natureza
    
    def get_natureza(self):
        """Retorna a natureza da tradução."""
        return self._natureza
    
    def get_issn_isbn(self):
        """Retorna o ISSN ou ISBN da obra traduzida."""
        return self._issn_isbn

    def __str__(self) -> str:
        return "Classe: TraducaoLivro " +"Ano: " + str(self.get_ano()) + " País: " + self.get_pais() + " ISSN/ISBN: " + self.get_issn_isbn() + " natureza: " + str(self.get_natureza())
    
class TrabalhoEvento(Producao):
    """
    Representa um trabalho publicado em evento (conferência, congresso, etc).
    
    Corresponde ao elemento TRABALHO-EM-EVENTOS no XML do Currículo Lattes
    (DADOS-BASICOS-DO-TRABALHO e DETALHAMENTO-DO-TRABALHO).
    
    Attributes:
        _natureza (NaturezaTrabalho): Tipo do trabalho (ex: COMPLETO, RESUMO, RESUMO_EXPANDIDO)
        _classificacao (ClassificacaoEvento): Abrangência do evento (INTERNACIONAL, NACIONAL, REGIONAL, LOCAL)
        _titulo (str): Título do trabalho publicado
        _venue (str): Nome do evento onde foi publicado (ex: nome da conferência)
        _autores (list): Lista com nomes dos autores do trabalho
        _ano (int): Ano de publicação (herdado de Producao)
        _pais (str): País do evento (herdado de Producao)
    """
    
    def __init__(self, ano: int, pais: str, natureza: NaturezaTrabalho, classificacao: ClassificacaoEvento, titulo: str, venue: str, autores: list, metadados=None):
        """
        Inicializa um trabalho publicado em evento.
        
        Args:
            ano (int): Ano de publicação
            pais (str): País do evento
            natureza (NaturezaTrabalho): Natureza do trabalho
            classificacao (ClassificacaoEvento): Classificação do evento
            titulo (str): Título do trabalho
            venue (str): Nome do evento
            autores (list): Lista de autores
        """
        super().__init__(ano, pais)
        self._natureza = natureza
        self._classificacao = classificacao
        self._titulo = titulo
        self._venue = venue
        self._autores = autores
        self._metadados = metadados
    
    def get_natureza(self):
        """Retorna a natureza do trabalho."""
        return self._natureza
    
    def get_classificacao(self):
        """Retorna a classificação do evento."""
        return self._classificacao
    
    def get_titulo(self):
        """Retorna o título do trabalho."""
        return self._titulo
    
    def get_venue(self):
        """Retorna o nome do evento."""
        return self._venue
    
    def get_autores(self):
        """Retorna a lista de autores."""
        return self._autores

    def get_metadados(self):
        return self._metadados
    
    def __str__(self) -> str:
        return "Classe: TrabalhoEvento " + "Ano: " + str(self.get_ano()) + " País: " + self.get_pais() + " classificacao: " + str(self.get_classificacao()) + " natureza: " + str(self.get_natureza())

class OrganizacaoEvento(Producao):
    """
    Representa a organização de um evento acadêmico.
    
    Corresponde ao elemento ORGANIZACAO-DE-EVENTO no XML do Currículo Lattes
    (DADOS-BASICOS-DA-ORGANIZACAO-DE-EVENTO).
    
    Attributes:
        _tipo (TipoEvento): Tipo de evento organizado (ex: CONGRESSO, EXPOSICAO, FEIRA, OLIMPIADA, etc)
        _ano (int): Ano de realização (herdado de Producao)
        _pais (str): País onde ocorreu (herdado de Producao)
    """
    
    def __init__(self, ano: int, pais: str, tipo: TipoEvento):
        """
        Inicializa uma organização de evento.
        
        Args:
            ano (int): Ano de realização
            pais (str): País do evento
            tipo (TipoEvento): Tipo do evento organizado
        """
        super().__init__(ano, pais)
        self._tipo = tipo
    
    def get_tipo(self):
        """Retorna o tipo de evento organizado."""
        return self._tipo

class OrientacaoMD(Producao):
    """
    Representa orientação concluída de Mestrado ou Doutorado.
    
    Corresponde aos elementos ORIENTACOES-CONCLUIDAS-PARA-MESTRADO e
    ORIENTACOES-CONCLUIDAS-PARA-DOUTORADO no XML do Currículo Lattes.
    
    Attributes:
        _tipo_orientacao (TipoOrientacaoMD): Nível da orientação (MESTRADO ou DOUTORADO)
        _tipo_orientador (TipoOrientador): Papel do orientador (ORIENTADOR_PRINCIPAL ou CO_ORIENTADOR)
        _ano (int): Ano de conclusão (herdado de Producao)
        _pais (str): País da instituição (herdado de Producao)
    """
    
    def __init__(self, ano: int, pais: str, tipo_orientacao: TipoOrientacaoMD, tipo_orientador: TipoOrientador):
        """
        Inicializa uma orientação de mestrado ou doutorado.
        
        Args:
            ano (int): Ano de conclusão
            pais (str): País da instituição
            tipo_orientacao (TipoOrientacaoMD): Tipo da orientação (Mestrado/Doutorado)
            tipo_orientador (TipoOrientador): Tipo do orientador
        """
        super().__init__(ano, pais)
        self._tipo_orientacao = tipo_orientacao
        self._tipo_orientador = tipo_orientador
    
    def get_tipo_orientacao(self):
        """Retorna o tipo de orientação (Mestrado ou Doutorado)."""
        return self._tipo_orientacao
    
    def get_tipo_orientador(self):
        """Retorna o tipo de orientador."""
        return self._tipo_orientador

    def __str__(self) -> str:
        return "Classe: OrientacaoMD " + "Ano: " + str(self.get_ano()) + " País: " + self.get_pais() + " tipo orientacao: " + str(self.get_tipo_orientacao().value) + " tipo orientador: " + str(self.get_tipo_orientador().value)

class OrientacaoMTI(Producao):
    """
    Representa orientações concluídas de Monografia, TCC ou Iniciação Científica.
    
    Corresponde ao elemento OUTRAS-ORIENTACOES-CONCLUIDAS no XML do Currículo Lattes,
    filtrando por natureza específica (MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO,
    TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO ou INICIACAO_CIENTIFICA).
    
    Attributes:
        _tipo_orientacao (TipoOrientacaoMTI): Tipo de orientação (MONOGRAFIA, TCC ou INICIACAO_CIENTIFICA)
        _ano (int): Ano de conclusão (herdado de Producao)
        _pais (str): País da instituição (herdado de Producao)
    """
    
    def __init__(self, ano: int, pais: str, tipo_orientacao: TipoOrientacaoMTI):
        """
        Inicializa uma orientação de monografia, TCC ou iniciação científica.
        
        Args:
            ano (int): Ano de conclusão
            pais (str): País da instituição
            tipo_orientacao (TipoOrientacaoMTI): Tipo da orientação
        """
        super().__init__(ano, pais)
        self._tipo_orientacao = tipo_orientacao
    
    def get_tipo_orientacao(self):
        """Retorna o tipo de orientação."""
        return self._tipo_orientacao

    def __str__(self) -> str:
        return "Classe: OrientacaoMTI " + "Tipo: " + str(self.get_tipo_orientacao()) + " Ano: " + str(self.get_ano()) + " País: " + self.get_pais()
        
class RegistroPatente(Producao):
    """
    Representa registro ou patente de propriedade intelectual.
    
    Corresponde ao elemento REGISTRO-OU-PATENTE no XML do Currículo Lattes.
    Inclui patentes, softwares, cultivares protegidas, desenhos industriais, marcas e
    topografias de circuito integrado.
    
    Attributes:
        _ano (int): Ano de concessão ou depósito (herdado de Producao)
        _pais (str): País do registro (herdado de Producao)
    """
    
    def __init__(self, ano: int, pais: str):
        """
        Inicializa um registro ou patente.
        
        Args:
            ano (int): Ano de concessão ou depósito
            pais (str): País do registro
        """
        super().__init__(ano, pais)
        
    def __str__(self) -> str:
        return "Classe: RegistroPatente " + " Ano: " + str(self.get_ano()) + " País: " + self.get_pais()

class ArtisticaCultural(Producao):
    """
    Classe base para produções artísticas e culturais.
    
    Corresponde ao elemento PRODUCAO-ARTISTICA-CULTURAL no XML do Currículo Lattes.
    Inclui diversos tipos como apresentações, obras de artes visuais, composições musicais,
    sonoplastia, entre outras.
    
    Attributes:
        _ano (int): Ano de realização (herdado de Producao)
        _pais (str): País de realização (herdado de Producao)
    """

    def __init__(self, ano: int, pais: str):
        """
        Inicializa uma produção artística/cultural.
        
        Args:
            ano (int): Ano de realização
            pais (str): País de realização
        """
        super().__init__(ano, pais)

    def __str__(self) -> str:
        return "Classe: ArtisticaCultural " + " Ano: " + str(self.get_ano()) + " País: " + self.get_pais()

class Musica(ArtisticaCultural):
    """
    Representa produções na área de música.
    
    Corresponde ao elemento MUSICA dentro de PRODUCAO-ARTISTICA-CULTURAL no XML do Currículo Lattes
    (DADOS-BASICOS-DE-MUSICA).
    Inclui composições musicais, arranjos, interpretações e outras produções musicais.
    
    Attributes:
        _ano (int): Ano de realização (herdado de ArtisticaCultural)
        _pais (str): País de realização (herdado de ArtisticaCultural)
    """
    
    def __init__(self, ano: int, pais: str):
        """
        Inicializa uma produção musical.
        
        Args:
            ano (int): Ano de realização
            pais (str): País de realização
        """
        super().__init__(ano, pais)
        
    def __str__(self) -> str:
        return "Classe: Musica " + " Ano: " + str(self.get_ano()) + " País: " + self.get_pais()
    
class ArtesVisuais(ArtisticaCultural):
    """
    Representa produções na área de artes visuais.
    
    Corresponde ao elemento ARTES-VISUAIS dentro de PRODUCAO-ARTISTICA-CULTURAL no XML do Currículo Lattes
    (DADOS-BASICOS-DE-ARTES-VISUAIS).
    Inclui pinturas, esculturas, fotografias, instalações e outras obras de artes visuais.
    
    Attributes:
        _ano (int): Ano de realização (herdado de ArtisticaCultural)
        _pais (str): País de realização (herdado de ArtisticaCultural)
    """
    
    def __init__(self, ano: int, pais: str):
        """
        Inicializa uma produção de artes visuais.
        
        Args:
            ano (int): Ano de realização
            pais (str): País de realização
        """
        super().__init__(ano, pais)
        
    def __str__(self) -> str:
        return "Classe: ArtesVisuais " + " Ano: " + str(self.get_ano()) + " País: " + self.get_pais()
    
class ArtesCenicas (ArtisticaCultural):
    """
    Representa produções na área de artes cênicas.
    
    Corresponde ao elemento ARTES-CENICAS dentro de PRODUCAO-ARTISTICA-CULTURAL no XML do Currículo Lattes
    (DADOS-BASICOS-DE-ARTES-CENICAS).
    Inclui peças teatrais, performances, direção teatral, coreografias e outras produções cênicas.
    
    Attributes:
        _ano (int): Ano de realização (herdado de ArtisticaCultural)
        _pais (str): País de realização (herdado de ArtisticaCultural)
    """
    
    def __init__(self, ano: int, pais: str):
        """
        Inicializa uma produção de artes cênicas.
        
        Args:
            ano (int): Ano de realização
            pais (str): País de realização
        """
        super().__init__(ano, pais)
        
    def __str__(self) -> str:
        return "Classe: ArtesCenicas " + " Ano: " + str(self.get_ano()) + " País: " + self.get_pais()
           
class Artigo(Producao):
    """
    Representa um artigo publicado em periódico ou revista.
    
    Corresponde ao elemento ARTIGO-PUBLICADO no XML do Currículo Lattes
    (DADOS-BASICOS-DO-ARTIGO e DETALHAMENTO-DO-ARTIGO).
    
    Attributes:
        _issn (str): Número ISSN do periódico onde foi publicado
        _natureza (NaturezaArtigo): Tipo do artigo (COMPLETO ou RESUMO)
        _titulo (str): Título do artigo
        _revista (str): Nome do periódico ou revista
        _autores (list): Lista com nomes dos autores do artigo
        _ano (int): Ano de publicação (herdado de Producao)
        _pais (str): País de publicação (herdado de Producao)
    """
    
    def __init__(self, ano: int, pais: str, issn: str, natureza: NaturezaArtigo, titulo: str, revista: str, autores: list, metadados=None):
        """
        Inicializa um artigo publicado.
        
        Args:
            ano (int): Ano de publicação
            pais (str): País de publicação
            issn (str): Número ISSN do periódico
            natureza (NaturezaArtigo): Natureza do artigo
            titulo (str): Título do artigo
            revista (str): Nome da revista/periódico
            autores (list): Lista de autores
        """
        super().__init__(ano, pais)
        self._issn = issn
        self._natureza = natureza
        self._titulo = titulo
        self._revista = revista
        self._autores = autores
        self._metadados = metadados
    
    def get_issn(self):
        """Retorna o ISSN do periódico."""
        return self._issn
    
    def get_natureza(self):
        """Retorna a natureza do artigo."""
        return self._natureza

    def get_titulo(self):
        """Retorna o título do artigo."""
        return self._titulo
    
    def get_revista(self):
        """Retorna o nome da revista/periódico."""
        return self._revista
    
    def get_autores(self):
        """Retorna a lista de autores."""
        return self._autores

    def get_metadados(self):
        return self._metadados

class ProgramaRadioTV(Producao):
    """
    Representa um programa de rádio ou televisão.
    
    Corresponde ao elemento PROGRAMA-DE-RADIO-OU-TV no XML do Currículo Lattes
    (DADOS-BASICOS-DO-PROGRAMA-DE-RADIO-OU-TV).
    
    Attributes:
        _natureza (NaturezaPrograma): Tipo do programa (ex: ENTREVISTA, MESA_REDONDA, PROGRAMA_DE_RADIO, PROGRAMA_DE_TV)
        _ano (int): Ano de veiculação (herdado de Producao)
        _pais (str): País de veiculação (herdado de Producao)
    """
    
    def __init__(self, ano: int, pais: str, natureza: NaturezaPrograma):
        """
        Inicializa um programa de rádio ou TV.
        
        Args:
            ano (int): Ano de veiculação
            pais (str): País de veiculação
            natureza (NaturezaPrograma): Natureza do programa
        """
        super().__init__(ano, pais)
        self._natureza = natureza
        
    def get_natureza(self):
        """Retorna a natureza do programa."""
        return self._natureza
