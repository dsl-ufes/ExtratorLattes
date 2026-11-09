import json


class NotaInfo():

    def __init__(self, config_path):
        with open(config_path, 'r') as f:
            info = json.load(f)
            
            self.__carrega_prod_min_info(info['prod-min'])
            self.__carrega_nota_info(info['nota'])

    def __carrega_nota_info(self, nota_config):
        self.nota_ano_inicio = nota_config['intervalo'][0]
        self.nota_ano_fim = nota_config['intervalo'][1]
        self.nota_min = nota_config['nota-min']
        self.nota_multiplo = nota_config['nota-multiplo']
        self.info_valores = {}
        
        for v in nota_config['valores']:
            for tag in v['tags']:
                self.info_valores[tag] = v['valor']
    
    def __carrega_prod_min_info(self, prod_min_config):
        self.prod_min_ano_inicio = prod_min_config['intervalo'][0]
        self.prod_min_ano_fim = prod_min_config['intervalo'][1]
        self.prod_min_tag = prod_min_config['prod-min-tag']
        self.prod_min_qtd = prod_min_config['prod-min-qtd']

        self.prod_min_valid_tags = set()

        for tag in prod_min_config['valid-tags']:
            self.prod_min_valid_tags.add(tag)

    def get_prod_min_tag(self):
        return self.prod_min_tag
    
    def get_prod_min_intervalo(self):
        return (self.prod_min_ano_inicio, self.prod_min_ano_fim)

    def get_prod_min_qtd(self):
        return self.prod_min_qtd
    
    def get_nota_min_value(self):
        return self.nota_min

    def get_nota_intervalo(self):
        return (self.nota_ano_inicio, self.nota_ano_fim)

    def alcancou_prod_min(self, qtd):
        return qtd >= self.prod_min_qtd

    def alcancou_nota_min(self, nota):
        return nota >= self.nota_min

    def arrendonda_nota(self, nota, mult = None):
        """
            Arredonda a nota para baixo até o múltiplo mais próximo de significância.

            O mútiplo pode ser definido em mult, ou o múltiplo usado será referente ao
            que está presente no objeto NotaInfo.
        """
        if mult is not None and mult <= 0:
            raise ValueError("NotaInfo.arrendonda_nota: mult deve ser maior que zero.")
        if self.nota_multiplo <= 0:
            raise ValueError("NotaInfo.arrendonda_nota: nota-multiplo no arquivo de configuração deve ser maior que zero.")
        
        import math
        if mult is None:
            return math.floor(nota / self.nota_multiplo) * self.nota_multiplo
        return math.floor(nota / mult) * mult

    def prod_valida_para_nota(self, prod_ano: int):
        if prod_ano >= self.nota_ano_inicio and prod_ano <= self.nota_ano_fim:
            return True
        return False

    def valor_qualis(self, qualis_tag: str):
        """
            Retorna o valor da produção(por sua tag e ano) no cálculo da pontuação.
            Se uma produção não pode ser considerada, retorna zero.
        """
        if qualis_tag in self.info_valores:
            return self.info_valores[qualis_tag]
        return 0
    
    def is_prod_min(self, qualis_tag: str, ano: int):
        """
            Verifica se uma produção(por sua tag e ano) pode ser considerada na
            quantidade de produções mínimas necessárias para o recredenciamento.
        """
        if ano >= self.prod_min_ano_inicio and ano <= self.prod_min_ano_fim:
            if qualis_tag in self.prod_min_valid_tags:
                return True
        return False
