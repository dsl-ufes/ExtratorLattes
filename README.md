# ExtratorLattes

O ExtratorLattes lê currículos XML da Plataforma Lattes e produz dados para
avaliação de programas de pós-graduação. A pipeline atual do PPGI classifica
publicações, deduplica registros entre docentes, calcula pontuações e, de modo
opcional, gera métricas externas.

## Pipeline PPGI

```text
XML Lattes
  -> Parte 1: classificação Qualis e deduplicação
  -> publicações canônicas e arquivos de auditoria
  -> Parte 2: pré-verificação e pontuação
  -> relatórios de docentes e do programa

publicações canônicas
  -> Métricas externas opcionais
  -> snapshot SQLite e ranking de citações
```

1. A Parte 1 lê os XMLs, classifica periódicos e eventos, e deduplica
   publicações entre docentes.
2. A Parte 2 só calcula a pontuação quando não existem revisões pendentes de
   Qualis ou deduplicação no intervalo avaliado.
3. As métricas externas não alteram a pontuação.

## Componentes

- `ArquivoInterno/`: leitura do XML Lattes e metadados de proveniência.
- `Classificador/`: classificação Qualis de periódicos e integração do
  QualisLens para eventos.
- `QualisLens/`: associação conservadora de eventos ao Qualis CAPES e scripts
  para atualizar as bases Sucupira.
- `Deduplicacao/`: formação de publicações canônicas e fila de revisão.
- `Metricas/`: snapshots, cache SQLite e relatórios de métricas externas.
- `PPGI/`: comandos da pipeline de avaliação do PPGI.
- `PIIC/`: aplicação independente para editais de iniciação científica.

## Executar o PPGI

Crie e ative um ambiente virtual na raiz do repositório, depois instale as
dependências dentro dele:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

python -m pip install -r requirements.txt
```

Depois, execute os comandos a partir de `PPGI/`, na ordem abaixo. Consulte
[PPGI/README.md](PPGI/README.md) para o detalhamento das entradas, das
saídas e dos códigos de saída.

### Passo 0: preparar as entradas a partir de currículos Lattes

Para montar uma nova execução a partir de uma pasta de currículos Lattes
baixados, use `PPGI/scripts/preparar_execucao.py`. Ele copia os XMLs,
deriva a lista de docentes a partir do `NUMERO-IDENTIFICADOR` de cada
currículo, e publica um `config-{id}.json` e os arquivos de override vazios
já apontando um para o outro:

```bash
cd PPGI
python scripts/preparar_execucao.py \
  --id 2025 \
  --curriculos-origem /caminho/para/os/xmls
  --com-metricas
```

O comando cria:

- `DadosPPGI/curriculos-2025/`: cópia dos XMLs.
- `DadosPPGI/input/2025/2025.list`: lista de docentes derivada dos XMLs.
- `DadosPPGI/input/2025/qualis_overrides.csv` e
  `DadosPPGI/input/2025/deduplicacao_overrides.csv`: overrides vazios,
  prontos para o Passo 2.
- `DadosPPGI/config-2025.json`: já referenciando os três arquivos acima.

Use `--force` para sobrescrever uma execução já preparada com o mesmo `--id`,
e `--com-metricas` para também publicar `DadosPPGI/config-metricas-2025.json`
(ver Passo 4). O comando imprime, ao final, o comando exato do Passo 1 a
executar em seguida. Ele não participa da cadeia de hashes da Parte 1/Parte
2 - só publica entradas.

### Passo 1: Parte 1 - classificação e deduplicação

```bash
python main-part1.py DadosPPGI/config-{id}.json
```

Os caminhos de override mostrados no Passo 2 abaixo seguem o
que estiver em `arquivo_overrides_qualis` e `arquivo_overrides_deduplicacao`
nesse mesmo arquivo de configuração.

Ao final, o comando imprime um resumo. Observe:

- **"Parte 1 concluída sem pendências"**: nenhuma revisão pendente. Siga para
  o Passo 3 (Parte 2).
- **"Parte 1 concluída com revisões pendentes"**: existem eventos sem Qualis
  automático e/ou pares de publicações com deduplicação ambígua. O resumo
  lista as quantidades e os caminhos exatos dos arquivos de revisão e de
  overrides a editar. Siga para o Passo 2.

Arquivos publicados em `DadosPPGI/saida/` (ou no diretório configurado em
`diretorio_saida`):

- `<ano>_publicacoes_ocorrencias.csv`: uma linha por produção por docente.
- `<ano>_publicacoes_unicas.csv` e `<ano>_publicacoes_membros.csv`:
  publicações canônicas e os docentes vinculados a cada uma.
- `<ano>_qualis_revisao.csv`: eventos sem estrato automático.
- `<ano>_deduplicacao_revisao.csv`: pares de ocorrências com agrupamento
  ambíguo.
- `<ano>_deduplicacao_manifest.json`: hashes das saídas acima; publicado por
  último, é o marcador de conclusão da Parte 1.

### Passo 2: resolver revisões pendentes (se houver)

Não edite os CSVs gerados pela Parte 1. Abra os dois arquivos de revisão
indicados no resumo do Passo 1 e registre as decisões nos arquivos de
override apontados por `arquivo_overrides_qualis` e
`arquivo_overrides_deduplicacao` no seu `config-{id}.json` (o próprio resumo do
Passo 1 imprime o caminho exato usado nessa execução):

- Eventos sem Qualis automático -> arquivo de `arquivo_overrides_qualis`
  (por padrão `DadosPPGI/input/qualis_overrides.csv`; com o Passo 0,
  `DadosPPGI/input/{id}/qualis_overrides.csv`). Cada linha usa `ASSOCIAR`
  com um `qualis_registro_id` (visto na coluna `Candidatos JSON` da fila) ou
  `SEM_CORRESPONDENCIA`.
- Deduplicação ambígua -> arquivo de `arquivo_overrides_deduplicacao` (por
  padrão `DadosPPGI/input/publicacoes_deduplicacao_overrides.csv`; com o
  Passo 0, `DadosPPGI/input/{id}/deduplicacao_overrides.csv`). Cada linha
  usa `AGRUPAR` ou `NAO_AGRUPAR`, referenciando os IDs e fingerprints
  exatos mostrados na fila atual.

Depois de editar qualquer override, repita o Passo 1. Releia o resumo: uma
decisão pode resolver mais de uma pendência ao mesmo tempo (por exemplo, um
evento associado ao Qualis pode destravar um agrupamento de deduplicação que
dependia da identidade daquele evento). Repita até ver "sem pendências".

### Passo 3: Parte 2 - pontuação

```bash
python main-part2.py DadosPPGI/config-{id}.json
```

Observe o código de saída:

- **`0`**: sucesso. `DadosPPGI/saida/<ano>_docente.csv` (nota por docente) e
  `<ano>_grupo.csv` (nota do programa) foram publicados.
- **`1`**: erro. Abra `DadosPPGI/saida/<ano>_execucao.json` e veja os campos
  `tipo_erro` e `mensagem_erro`.

O mesmo `<ano>_execucao.json` registra o estado da execução
(`EM_EXECUCAO`, `SUCESSO`, `BLOQUEADO_REVISAO` ou `ERRO`) e os hashes dos
relatórios publicados.

### Passo 4 (opcional): métricas externas e ranking de citações

Este passo lê apenas as publicações canônicas da Parte 1 e nunca altera a
pontuação. Antes de executar:

1. **Garanta que existe o arquivo de configuração de métricas**, gerado no Passo 0 com `--com-metricas`, `DadosPPGI/config-metricas-{id}.json`.

2. **Defina a chave de API do Scopus como variável de ambiente antes de
   rodar** (o JSON acima só guarda o *nome* da variável em `api_key_env`,
   nunca a chave em si; não coloque a chave dentro do arquivo de
   configuração):

   ```bash
   export SCOPUS_API_KEY="sua-chave-aqui"
   export SCOPUS_INSTTOKEN="seu-insttoken-aqui"   # se a sua chave exigir
   ```

   Sem a chave, o Scopus fica com status `CREDENCIAL_AUSENTE` para cada
   publicação - o comando continua funcionando, só fica sem esse contexto
   adicional.

3. **Execute o comando** a partir de `PPGI/`:

   ```bash
   python main-metricas.py DadosPPGI/config-metricas-{id}.json
   echo "código de saída: $?"
   ```

   Use `--offline` para reexportar somente o que já está em cache (sem
   novas consultas) ou `--refresh` para forçar novas consultas às fontes.

Observe a última linha impressa (`<snapshot_id> <estado>`) e o código de
saída:

- **`CONCLUIDO` / código `0`**: todas as publicações elegíveis foram
  consultadas com sucesso.
- **`PARCIAL` / código `2`**: parte das publicações ficou sem resolução
  (limite de taxa do Google Scholar, publicação sem DOI).
- **código `1`**: falha antes de gerar o snapshot.

Depois, abra `DadosPPGI/saida/<ano>_metricas_ranking.csv`: as colunas
`cobertura_scholar.elegiveis/resolvidas/ausentes/ambiguas/bloqueadas` mostram
quanto do programa o ranking realmente cobre, mesmo em um snapshot parcial.
Os demais relatórios (`<ano>_metricas_identidades.csv`,
`_publicacoes.csv`, `_veiculos.csv`, `_revisao.csv`, `_consultas.csv`,
`_docentes.csv`, `_resumo.csv`) ficam no mesmo diretório e são independentes
dos relatórios de pontuação da Parte 2.

## Classificação Qualis

Periódicos usam a projeção em `Classificador/qualis-unificado.csv`. Eventos
usam as bases canônicas do QualisLens para os quadriênios 2017–2020 e
2021–2024.

O matching de eventos é conservador. Ele aceita correspondência exata ou fuzzy
somente quando os sinais textuais e estruturais são suficientes. Casos ambíguos
não recebem estrato automático. Eles entram em revisão manual.

Atualize as bases oficiais e a projeção de periódicos com aliases de ISSN:

```bash
python QualisNovo/criaArquivoQualis.py
```

O comando baixa e valida as bases Sucupira antes de publicar os artefatos.
Veja [QualisLens/README.md](QualisLens/README.md) para o fluxo offline e os
detalhes da importação.

## Métricas externas

As métricas usam snapshots imutáveis e um cache SQLite. Elas não mudam os
relatórios de pontuação. Veja o Passo 4 em [Executar o PPGI](#executar-o-ppgi)
para o passo a passo de execução e [Metricas/README.md](Metricas/README.md)
para os detalhes dos provedores e do formato do cache.

## Licença

GNU General Public License v3.0.
