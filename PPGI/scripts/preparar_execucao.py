"""Prepara os arquivos de entrada de uma execução PPGI a partir de currículos Lattes.

Copia os XMLs de origem para ``DadosPPGI/curriculos-{id}/`` e publica todos os
demais insumos de uma execução sob ``DadosPPGI/input/{id}/``: a lista de
docentes (derivada do ``NUMERO-IDENTIFICADOR`` de cada currículo) e os dois
arquivos de overrides, ambos vazios e prontos para receber decisões manuais.
Também publica ``DadosPPGI/config-{id}.json`` (e, com ``--com-metricas``,
``DadosPPGI/config-metricas-{id}.json``), já apontando para os arquivos de
``DadosPPGI/input/{id}/``.

Os overrides de Qualis deixam de ser compartilhados entre execuções: cada
``--id`` recebe seu próprio arquivo vazio, para que decisões de uma execução
não vazem para outra.

Este script não participa da cadeia com hash da Parte 1/Parte 2. Ele só
publica entradas; não gera manifesto e não deve ser nomeado como uma etapa
numerada da pipeline.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DADOS_DIR = BASE_DIR / "DadosPPGI"


class PreparacaoError(RuntimeError):
    pass


def _ler_curriculo(caminho: Path) -> tuple[str, str]:
    """Retorna (numero_identificador, nome_completo) ou levanta PreparacaoError."""
    try:
        raiz = ET.parse(caminho).getroot()
    except ET.ParseError as erro:
        raise PreparacaoError(f"{caminho.name}: XML inválido ({erro})") from erro
    dados_gerais = raiz.find("DADOS-GERAIS")
    numero_id = raiz.attrib.get("NUMERO-IDENTIFICADOR", "")
    if not numero_id and dados_gerais is not None:
        numero_id = dados_gerais.attrib.get("NUMERO-IDENTIFICADOR", "")
    if not numero_id:
        raise PreparacaoError(f"{caminho.name}: sem NUMERO-IDENTIFICADOR")
    nome = dados_gerais.attrib.get("NOME-COMPLETO", "") if dados_gerais is not None else ""
    return numero_id, nome


def _validar_origem(origem: Path) -> list[Path]:
    arquivos = sorted(origem.glob("*.xml"))
    if not arquivos:
        raise PreparacaoError(f"nenhum XML encontrado em {origem}")

    ids_por_arquivo: dict[Path, str] = {}
    arquivos_por_id: dict[str, list[Path]] = {}
    erros: list[str] = []
    sem_sequencia = 0

    for arquivo in arquivos:
        try:
            numero_id, _ = _ler_curriculo(arquivo)
        except PreparacaoError as erro:
            erros.append(str(erro))
            continue
        ids_por_arquivo[arquivo] = numero_id
        arquivos_por_id.setdefault(numero_id, []).append(arquivo)
        try:
            texto = arquivo.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            texto = ""
        if "SEQUENCIA-PRODUCAO" not in texto:
            sem_sequencia += 1

    duplicados = {nid: paths for nid, paths in arquivos_por_id.items() if len(paths) > 1}
    if duplicados:
        for nid, paths in duplicados.items():
            nomes = ", ".join(p.name for p in paths)
            erros.append(f"NUMERO-IDENTIFICADOR {nid} repetido em: {nomes}")

    if erros:
        raise PreparacaoError(
            f"{len(erros)} problema(s) nos currículos de origem:\n" + "\n".join(f"  - {e}" for e in erros)
        )

    print(f"{len(arquivos)} currículo(s) válido(s) em {origem}")
    if sem_sequencia:
        print(
            f"aviso: {sem_sequencia} currículo(s) sem SEQUENCIA-PRODUCAO em alguma produção; "
            "essas ocorrências usarão proveniência incompleta (fallback por fingerprint)."
        )
    return arquivos


def _copiar_curriculos(arquivos: list[Path], destino: Path, force: bool) -> list[tuple[str, str, str]]:
    if destino.exists() and any(destino.iterdir()) and not force:
        raise PreparacaoError(f"{destino} já existe e não está vazio; use --force para sobrescrever")
    destino.mkdir(parents=True, exist_ok=True)

    roster: list[tuple[str, str, str]] = []
    for arquivo in arquivos:
        numero_id, nome = _ler_curriculo(arquivo)
        stem = arquivo.stem
        shutil.copy2(arquivo, destino / f"{stem}.xml")
        roster.append((stem, numero_id, nome))
    return roster


def _escrever_lista(roster: list[tuple[str, str, str]], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    linhas = [f"{stem}, {nome}".rstrip() for stem, _numero_id, nome in roster]
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def _anos_padrao(config_pontuacao: Path) -> tuple[tuple[int, int], tuple[int, int]]:
    """Deriva as janelas de extração a partir dos intervalos de pontuação.

    A janela de conferência acompanha ``nota.intervalo``; a janela de
    periódico acompanha ``prod-min.intervalo``. Extrair um período mais
    estreito que o de pontuação faz produções desaparecerem antes de serem
    contadas, sem nenhum aviso.
    """
    with config_pontuacao.open(encoding="utf-8") as stream:
        info = json.load(stream)
    conferencia = tuple(info["nota"]["intervalo"])
    periodico = tuple(info["prod-min"]["intervalo"])
    return conferencia, periodico


def _escrever_config(caminho: Path, id_execucao: str, args: argparse.Namespace, force: bool) -> None:
    if caminho.exists() and not force:
        raise PreparacaoError(f"{caminho} já existe; use --force para sobrescrever")

    ano_inicio_c, ano_fim_c = args.anos_conferencia
    ano_inicio_p, ano_fim_p = args.anos_periodico

    config = {
        "ano_inicio_conferencia": ano_inicio_c,
        "ano_fim_conferencia": ano_fim_c,
        "ano_inicio_periodico": ano_inicio_p,
        "ano_fim_periodico": ano_fim_p,
        "arquivo_lista_docentes": f"DadosPPGI/input/{id_execucao}/{id_execucao}.list",
        "diretorio_curriculos": f"DadosPPGI/curriculos-{id_execucao}/",
        "diretorio_saida": f"DadosPPGI/saida-{id_execucao}",
        "arquivo_nota_docente": "docente.csv",
        "arquivo_nota_geral": "grupo.csv",
        "arquivo_qualis_journal": "../Classificador/qualis-unificado.csv",
        "arquivo_qualis_conference": "../Classificador/qualis_conferencias.csv",
        "arquivo_publicacoes_ocorrencias": f"DadosPPGI/saida-{id_execucao}/{ano_fim_c}_publicacoes_ocorrencias.csv",
        "arquivo_overrides_deduplicacao": f"DadosPPGI/input/{id_execucao}/deduplicacao_overrides.csv",
        "arquivo_overrides_qualis": f"DadosPPGI/input/{id_execucao}/qualis_overrides.csv",
        "config_pontuacao": str(args.config_pontuacao_rel),
    }
    caminho.write_text(json.dumps(config, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")


def _escrever_csv_vazio(caminho: Path, cabecalho: str, force: bool) -> None:
    if caminho.exists() and not force:
        return
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(cabecalho, encoding="utf-8")


def _escrever_dedup_overrides(caminho: Path, force: bool) -> None:
    cabecalho = (
        "schema_versao,politica_versao,ocorrencia_a,fingerprint_a,ocorrencia_b,"
        "fingerprint_b,acao,justificativa,decidido_por,decidido_em\n"
    )
    _escrever_csv_vazio(caminho, cabecalho, force)


def _escrever_qualis_overrides(caminho: Path, force: bool) -> None:
    cabecalho = (
        "schema_versao,qualis_input_id,acao,qualis_registro_id,justificativa,"
        "decidido_por,decidido_em,politica_versao\n"
    )
    _escrever_csv_vazio(caminho, cabecalho, force)


def _escrever_config_metricas(caminho: Path, id_execucao: str, ano_fim_c: int, force: bool) -> None:
    if caminho.exists() and not force:
        raise PreparacaoError(f"{caminho} já existe; use --force para sobrescrever")
    saida = f"DadosPPGI/saida-{id_execucao}"
    config = {
        "arquivo_publicacoes_unicas": f"{saida}/{ano_fim_c}_publicacoes_unicas.csv",
        "arquivo_publicacoes_ocorrencias": f"{saida}/{ano_fim_c}_publicacoes_ocorrencias.csv",
        "arquivo_deduplicacao_revisao": f"{saida}/{ano_fim_c}_deduplicacao_revisao.csv",
        "arquivo_overrides_deduplicacao": f"DadosPPGI/input/{id_execucao}/deduplicacao_overrides.csv",
        "diretorio_saida": saida,
        "arquivo_cache": f"{saida}/metricas.sqlite",
        "provedor_ranking": "google_scholar",
        "google_scholar": {
            "enabled": True,
            "arquivo_perfis": "",
            "intervalo_minimo_segundos": 2.5,
            "jitter_segundos": 1.0,
        },
        "scopus": {
            "enabled": True,
            "api_key_env": "SCOPUS_API_KEY",
            "insttoken_env": "SCOPUS_INSTTOKEN",
            "incluir_citacoes": True,
            "incluir_metricas_veiculo": True,
        },
        "perfil_distribuicao": "INTERNO",
    }
    caminho.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepara currículos, lista de docentes e configuração para uma execução PPGI."
    )
    parser.add_argument("--id", required=True, help="Identificador da execução (usado em curriculos-{id}/, saida-{id}/, config-{id}.json)")
    parser.add_argument("--curriculos-origem", required=True, type=Path, help="Diretório com os XMLs Lattes de origem")
    parser.add_argument(
        "--config-pontuacao",
        type=Path,
        default=DADOS_DIR / "config-pontuacao.json",
        help="Config de pontuação usada para derivar as janelas de anos (padrão: DadosPPGI/config-pontuacao.json)",
    )
    parser.add_argument("--anos-conferencia", type=int, nargs=2, metavar=("INICIO", "FIM"), help="Sobrepõe a janela de anos de conferência derivada de config_pontuacao")
    parser.add_argument("--anos-periodico", type=int, nargs=2, metavar=("INICIO", "FIM"), help="Sobrepõe a janela de anos de periódico derivada de config_pontuacao")
    parser.add_argument("--com-metricas", action="store_true", help="Também publica DadosPPGI/config-metricas-{id}.json")
    parser.add_argument("--dry-run", action="store_true", help="Só valida e reporta; não copia nem escreve nada")
    parser.add_argument("--force", action="store_true", help="Sobrescreve config e diretório de currículos já existentes")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    id_execucao = args.id

    try:
        conferencia_padrao, periodico_padrao = _anos_padrao(args.config_pontuacao)
    except (OSError, KeyError, json.JSONDecodeError) as erro:
        print(f"erro: não foi possível derivar anos de {args.config_pontuacao}: {erro}", file=sys.stderr)
        return 1
    args.anos_conferencia = tuple(args.anos_conferencia) if args.anos_conferencia else conferencia_padrao
    args.anos_periodico = tuple(args.anos_periodico) if args.anos_periodico else periodico_padrao
    args.config_pontuacao_rel = args.config_pontuacao
    if args.config_pontuacao_rel.is_absolute():
        try:
            args.config_pontuacao_rel = args.config_pontuacao_rel.relative_to(BASE_DIR)
        except ValueError:
            pass

    try:
        arquivos = _validar_origem(args.curriculos_origem)
    except PreparacaoError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1

    print(f"conferência: {args.anos_conferencia[0]}-{args.anos_conferencia[1]}  "
          f"periódico: {args.anos_periodico[0]}-{args.anos_periodico[1]}")

    if args.dry_run:
        for arquivo in arquivos:
            numero_id, nome = _ler_curriculo(arquivo)
            print(f"  {arquivo.stem:20} {numero_id:20} {nome}")
        print("dry-run: nada foi copiado ou escrito.")
        return 0

    destino_curriculos = DADOS_DIR / f"curriculos-{id_execucao}"
    destino_input = DADOS_DIR / "input" / id_execucao
    try:
        roster = _copiar_curriculos(arquivos, destino_curriculos, args.force)
        lista_path = destino_input / f"{id_execucao}.list"
        _escrever_lista(roster, lista_path)
        config_path = DADOS_DIR / f"config-{id_execucao}.json"
        _escrever_config(config_path, id_execucao, args, args.force)
        dedup_overrides_path = destino_input / "deduplicacao_overrides.csv"
        _escrever_dedup_overrides(dedup_overrides_path, args.force)
        qualis_overrides_path = destino_input / "qualis_overrides.csv"
        _escrever_qualis_overrides(qualis_overrides_path, args.force)
        if args.com_metricas:
            config_metricas_path = DADOS_DIR / f"config-metricas-{id_execucao}.json"
            _escrever_config_metricas(config_metricas_path, id_execucao, args.anos_conferencia[1], args.force)
    except PreparacaoError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1

    print(f"{len(roster)} currículo(s) copiado(s) para {destino_curriculos}")
    print(f"entradas da execução em: {destino_input}")
    print(f"  lista de docentes: {lista_path.name}")
    print(f"  overrides de deduplicação (novo, vazio): {dedup_overrides_path.name}")
    print(f"  overrides de Qualis (novo, vazio): {qualis_overrides_path.name}")
    print(f"config: {config_path}")
    if args.com_metricas:
        print(f"config de métricas: {config_metricas_path}")
    print()
    print("Próximo passo:")
    print(f"  python main-part1.py DadosPPGI/config-{id_execucao}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
