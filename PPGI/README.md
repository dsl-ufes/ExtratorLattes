# Pipeline de avaliação do PPGI

Esta aplicação processa os currículos Lattes dos docentes do PPGI. Ela produz
publicações classificadas e deduplicadas, calcula a pontuação e pode enriquecer
as publicações canônicas com métricas externas.

## Fluxo

```text
Parte 1: XML Lattes -> ocorrências -> Qualis -> deduplicação -> auditoria
Parte 2: auditoria aprovada -> pontuação -> relatórios
Métricas: publicações canônicas -> snapshot SQLite -> ranking
```

Execute os comandos a partir deste diretório:

```bash
python -m pip install -r ../requirements.txt

python main-part1.py DadosPPGI/config.json
python main-part2.py DadosPPGI/config.json

# Opcional. Não muda a pontuação.
python main-metricas.py DadosPPGI/config-metricas.json
```

## Entradas

`DadosPPGI/config.json` define os períodos, os caminhos e as regras de
pontuação. Os campos principais são:

- `arquivo_lista_docentes`: lista de docentes no formato
  `numero_lattes, nome`.
- `diretorio_curriculos`: XMLs dos currículos Lattes.
- `arquivo_qualis_journal`: base Qualis de periódicos.
- `arquivo_qualis_conference`: base Qualis legada de eventos, combinada com as
  bases recentes do QualisLens.
- `arquivo_overrides_qualis`: decisões manuais de classificação de eventos.
- `arquivo_overrides_deduplicacao`: decisões manuais de deduplicação.
- `config_pontuacao`: regras para produção mínima e cálculo da nota.

Os arquivos de entrada distribuídos ficam em `DadosPPGI/input/`. As bases
recentes do QualisLens ficam em `../QualisLens/base/`.

## Parte 1: classificação e deduplicação

A Parte 1 extrai periódicos e trabalhos completos em eventos dos XMLs. Ela
classifica periódicos por ISSN e eventos pelo nome, ano e sigla quando houver.

O matching de eventos aceita correspondências exatas e correspondências fuzzy
com evidências suficientes. Correspondências ambíguas entram em revisão. Um
evento em revisão não recebe estrato automático.

Depois da classificação, a Parte 1 agrupa as ocorrências na mesma publicação
canônica. DOI válido igual é a evidência mais forte. DOI diferente, tipo
diferente e ano diferente não formam um grupo automático. Casos incertos
entram em revisão.

Para o ano final configurado, a Parte 1 publica em `DadosPPGI/saida/`:

- `<ano>_publicacoes_ocorrencias.csv`
- `<ano>_publicacoes_unicas.csv`
- `<ano>_publicacoes_membros.csv`
- `<ano>_deduplicacao_decisoes.csv`
- `<ano>_deduplicacao_revisao.csv`
- `<ano>_qualis_revisao.csv`
- `<ano>_deduplicacao_manifest.json`

O manifesto é publicado por último. Ele registra hashes das entradas e o
estado da deduplicação.

## Revisões manuais

Não edite os CSVs gerados pela Parte 1.

Para eventos, use `DadosPPGI/input/qualis_overrides.csv`. Cada decisão usa
`ASSOCIAR`, com um `qualis_registro_id`, ou `SEM_CORRESPONDENCIA`.

Para deduplicação, use
`DadosPPGI/input/publicacoes_deduplicacao_overrides.csv`. As ações são
`AGRUPAR` e `NAO_AGRUPAR`. As decisões precisam referenciar os IDs e
fingerprints mostrados na fila de revisão atual.

Depois de alterar qualquer override, execute novamente a Parte 1.

## Parte 2: pontuação

A Parte 2 verifica o manifesto e as filas de revisão antes do cálculo. Uma
revisão de Qualis ou deduplicação dentro do intervalo da nota bloqueia a
execução. Quando há bloqueio, o comando retorna `2` e não publica novos
relatórios de pontuação.

Quando a pré-verificação passa, a Parte 2 lê as publicações canônicas e seus
membros. Uma publicação canônica conta uma vez na nota do grupo. Cada docente
membro recebe uma vez o crédito individual.

As regras estão no arquivo definido por `config_pontuacao`, normalmente
`DadosPPGI/config-pontuacao.json`.

As saídas são:

- `<ano>_docente.csv`: pontuação por docente.
- `<ano>_grupo.csv`: pontuação do programa.
- `<ano>_execucao.json`: manifesto da execução e seus hashes.

Os estados do manifesto são `EM_EXECUCAO`, `SUCESSO`,
`BLOQUEADO_REVISAO` e `ERRO`. Os códigos de saída são `0` para sucesso, `2`
para bloqueio por revisão e `1` para erro.

## Métricas externas

`main-metricas.py` lê somente as publicações canônicas. Ele valida o manifesto
da deduplicação e cria um snapshot imutável no SQLite configurado por
`arquivo_cache`.

O ranking usa citações do Google Scholar. Crossref ajuda a validar a identidade
por DOI. Scopus pode adicionar indexação, citações e métricas de veículo como
contexto. Para Scopus, defina `SCOPUS_API_KEY` e, se necessário,
`SCOPUS_INSTTOKEN`.

Use `--offline` para exportar somente dados presentes no cache. Use
`--refresh` para consultar novamente as fontes. O comando retorna `0` para um
snapshot concluído, `2` para um snapshot parcial e `1` para falha.

Os relatórios de métricas são independentes dos relatórios de pontuação. Veja
também [../Metricas/README.md](../Metricas/README.md).

## Atualizar as bases Qualis

Execute o comando a partir da raiz do repositório:

```bash
python QualisLens/scripts/atualizar_sucupira.py \
  --area COMPUTAÇÃO \
  --quadrienio 2021-2024
```

O script valida os XLSX de eventos e periódicos antes de substituir as bases.
Ele preserva as bases anteriores quando a atualização falha.
