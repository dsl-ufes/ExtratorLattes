import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

# Adiciona o diretório pai aos caminhos de importação.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PontuacaoPPGI.NotaInfo import NotaInfo
from PontuacaoPPGI.Pontuacao import Pontuacao
import PontuacaoPPGI.PontuacaoTotal as PontuacaoTotal
import PontuacaoPPGI.utils as ppgiu


SCHEMA_VERSAO = '1'


def get_nome_prefix(nome, ppgi_config):
    return str(ppgi_config['ano_fim_conferencia']) + '_' + nome


def _agora():
    return datetime.now(timezone.utc).isoformat()


def _sha256(caminho):
    if not os.path.exists(caminho):
        return None
    digest = hashlib.sha256()
    with open(caminho, 'rb') as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b''):
            digest.update(bloco)
    return digest.hexdigest()


def _escrever_json_atomico(caminho, dados):
    diretorio = os.path.dirname(caminho) or '.'
    os.makedirs(diretorio, exist_ok=True)
    descritor, temporario = tempfile.mkstemp(prefix='.part2-', suffix='.tmp', dir=diretorio)
    try:
        with os.fdopen(descritor, 'w', encoding='utf-8') as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False, indent=2, sort_keys=True)
            arquivo.write('\n')
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    except BaseException:
        if os.path.exists(temporario):
            os.unlink(temporario)
        raise


def _manifest_base(config_path, ppgi_config, inicio):
    return {
        'schema_versao': SCHEMA_VERSAO,
        'inicio': inicio,
        'configuracao': os.path.abspath(config_path),
        'sha256_ocorrencias': _sha256(ppgi_config['publicacoes_ocorrencias']),
        'sha256_overrides_deduplicacao': _sha256(ppgi_config['overrides_deduplicacao']),
        'relatorios_publicados': [],
    }


def _detalhes_bloqueios(preflight):
    return {
        'deduplicacao': {
            'quantidade': preflight.quantidade_deduplicacao,
            'ocorrencia_ids': list(preflight.ids_deduplicacao),
            'arquivo_revisao': preflight.caminho_revisao_deduplicacao,
        },
        'qualis': {
            'quantidade': preflight.quantidade_qualis,
            'ocorrencia_ids': list(preflight.ids_qualis),
            'arquivo_revisao': preflight.caminho_revisao_qualis,
        },
        'mensagens': list(preflight.mensagens),
    }


def _criar_relatorio_docentes(docentes, nota_info, caminho):
    with ppgiu.create_csv_writer(caminho, nota_info) as arquivo:
        for docente in docentes:
            pontuacao = Pontuacao(docente, nota_info)
            pontuacao.processa_pontuacao()
            pontuacao.calcula_nota()
            pontuacao.write_csv_line(sep=';', file=arquivo)


def _validar_relatorio(caminho):
    if not os.path.isfile(caminho) or os.path.getsize(caminho) == 0:
        raise RuntimeError(f'Relatório temporário inválido: {caminho}')


def _imprimir_bloqueio(preflight, manifest_path):
    print('A pontuação foi interrompida antes do cálculo devido a revisões pendentes.', file=sys.stderr)
    print(f'Revisões de deduplicação: {preflight.quantidade_deduplicacao}.', file=sys.stderr)
    print(f'Revisões Qualis: {preflight.quantidade_qualis}.', file=sys.stderr)
    print(f'Revisão de deduplicação: {preflight.caminho_revisao_deduplicacao}', file=sys.stderr)
    print(f'Revisão Qualis: {preflight.caminho_revisao_qualis}', file=sys.stderr)
    print('Nenhum novo relatório de pontuação foi publicado.', file=sys.stderr)
    print(f'Manifesto da execução: {manifest_path}', file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Calcula a pontuação PPGI.')
    parser.add_argument('config', help='Arquivo de configuração')
    args = parser.parse_args(argv)

    inicio = _agora()
    manifest_path = None
    temporarios = []
    try:
        ppgi_config = ppgiu.config_json(args.config)
        ano = str(ppgi_config['ano_fim_conferencia'])
        diretorio_saida = ppgi_config['dir_out']
        arquivo_docentes = os.path.join(diretorio_saida, get_nome_prefix(ppgi_config['docente_file'], ppgi_config))
        arquivo_geral = os.path.join(diretorio_saida, get_nome_prefix(ppgi_config['geral_file'], ppgi_config))
        manifest_path = os.path.join(diretorio_saida, f'{ano}_execucao.json')
        manifesto = _manifest_base(args.config, ppgi_config, inicio)
        manifesto['status'] = 'EM_EXECUCAO'
        _escrever_json_atomico(manifest_path, manifesto)

        nota_info = NotaInfo(ppgi_config['nota_info'])
        ppgiu.validar_manifest_deduplicacao(diretorio_saida, ano, ppgi_config['overrides_deduplicacao'])
        preflight = ppgiu.preflight_pontuacao(ppgi_config['publicacoes_ocorrencias'], ppgi_config['overrides_deduplicacao'], nota_info, diretorio_saida, ano)
        manifesto['bloqueios'] = _detalhes_bloqueios(preflight)
        if not preflight.pode_pontuar:
            manifesto.update({'status': 'BLOQUEADO_REVISAO', 'fim': _agora()})
            _escrever_json_atomico(manifest_path, manifesto)
            _imprimir_bloqueio(preflight, manifest_path)
            return 2

        docentes = ppgiu.docentes_por_canonicas(os.path.join(diretorio_saida, f'{ano}_publicacoes_unicas.csv'), os.path.join(diretorio_saida, f'{ano}_publicacoes_membros.csv'))
        descritor, temporario_docentes = tempfile.mkstemp(prefix='.part2-docentes-', suffix='.tmp', dir=diretorio_saida)
        os.close(descritor)
        temporarios.append(temporario_docentes)
        descritor, temporario_geral = tempfile.mkstemp(prefix='.part2-geral-', suffix='.tmp', dir=diretorio_saida)
        os.close(descritor)
        temporarios.append(temporario_geral)
        _criar_relatorio_docentes(docentes, nota_info, temporario_docentes)
        PontuacaoTotal.calcula_nota_geral(docentes, nota_info, temporario_geral)
        _validar_relatorio(temporario_docentes)
        _validar_relatorio(temporario_geral)
        os.replace(temporario_docentes, arquivo_docentes)
        temporarios.remove(temporario_docentes)
        os.replace(temporario_geral, arquivo_geral)
        temporarios.remove(temporario_geral)
        manifesto.update({
            'status': 'SUCESSO',
            'fim': _agora(),
            'relatorios_publicados': [
                {'caminho': arquivo_docentes, 'sha256': _sha256(arquivo_docentes)},
                {'caminho': arquivo_geral, 'sha256': _sha256(arquivo_geral)},
            ],
        })
        _escrever_json_atomico(manifest_path, manifesto)
        return 0
    except Exception as erro:
        if manifest_path is not None:
            manifesto = locals().get('manifesto', {'schema_versao': SCHEMA_VERSAO, 'inicio': inicio})
            manifesto.update({
                'status': 'ERRO',
                'fim': _agora(),
                'tipo_erro': type(erro).__name__,
                'mensagem_erro': str(erro),
            })
            _escrever_json_atomico(manifest_path, manifesto)
        print(f'Erro inesperado: {type(erro).__name__}: {erro}', file=sys.stderr)
        return 1
    finally:
        for temporario in temporarios:
            if os.path.exists(temporario):
                os.unlink(temporario)


if __name__ == '__main__':
    raise SystemExit(main())
