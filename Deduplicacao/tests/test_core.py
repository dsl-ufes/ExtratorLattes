import unittest

from Deduplicacao import deduplicar_publicacoes


def publicacao(**extra):
    base = {
        'tipo': 'Periódico', 'ano': 2024, 'titulo': 'A method for testing',
        'revista': 'Journal of Tests', 'venue': '', 'issn': '1234-5678',
        'doi': '', 'curriculo_id': '1', 'sequencia': 1, 'autores': ['Ana'],
    }
    base.update(extra)
    return base


class DeduplicacaoTest(unittest.TestCase):
    def test_doi_identico_agrupar_e_doi_distinto_bloquear(self):
        a = publicacao(doi='https://doi.org/10.1000/test')
        b = publicacao(curriculo_id='2', doi='10.1000/test')
        self.assertEqual(len(deduplicar_publicacoes([a, b]).publicacoes_unicas), 1)
        b['doi'] = '10.1000/outro'
        self.assertEqual(len(deduplicar_publicacoes([a, b]).publicacoes_unicas), 2)

    def test_tipo_e_conflito_estrutural_nao_agrupar(self):
        a = publicacao()
        self.assertEqual(len(deduplicar_publicacoes([a, publicacao(tipo='Conferência', curriculo_id='2')]).publicacoes_unicas), 2)
        self.assertEqual(len(deduplicar_publicacoes([a, publicacao(curriculo_id='2', issn='9999-9999')]).publicacoes_unicas), 2)

    def test_override_e_ordem_estavel(self):
        a, b = publicacao(curriculo_id='1'), publicacao(curriculo_id='2')
        primeiro = deduplicar_publicacoes([a, b])
        ids = list(primeiro.canonica_por_ocorrencia)
        override = [{'ocorrencia_a': ids[0], 'ocorrencia_b': ids[1], 'acao': 'NAO_AGRUPAR'}]
        self.assertEqual(len(deduplicar_publicacoes([b, a], overrides=override).publicacoes_unicas), 2)


if __name__ == '__main__':
    unittest.main()
