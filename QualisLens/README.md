# QualisLens

O QualisLens associa trabalhos em eventos às classificações Qualis CAPES dos
quadriênios 2017–2020 e 2021–2024. Ele é usado pela Parte 1 da pipeline PPGI.

## Contrato de classificação

O fluxo padrão não usa rede nem modelo de linguagem. Ele produz somente estes
resultados automáticos:

- `EXATO`: nome ou sigla oficial compatível.
- `AUTO_FUZZY`: score de pelo menos 88, margem de pelo menos 8 e sinais
  estruturais compatíveis.
- `REVISAO_MANUAL`: dados ambíguos, conflitantes ou insuficientes.

Casos em revisão não recebem estrato automático.

A integração legada usa:

```python
QualisConferencia.get_match(venue, ano, sigla=None)
QualisConferencia.get_estrato(venue, ano=None, sigla=None)
```

Sem `ano`, a API emite um aviso de depreciação e usa a semântica da base
2017–2020.

## Bases e atualização

As bases canônicas estão em `base/`. `base/metadata.json` registra origem,
hashes e contagens. `Classificador/qualis-unificado.csv` é a projeção de duas
colunas usada pela classificação de periódicos da Parte 1.

Atualize os eventos e periódicos oficiais a partir da raiz do repositório:

```bash
python QualisLens/scripts/atualizar_sucupira.py \
  --area COMPUTAÇÃO \
  --quadrienio 2021-2024
```

O script baixa os XLSX da Plataforma Sucupira, valida os dois arquivos e só
então publica as novas bases. Uma falha preserva as bases anteriores.

Para converter arquivos já baixados sem rede:

```bash
python QualisLens/scripts/atualizar_sucupira.py \
  --offline \
  --eventos-xlsx caminho/eventos.xlsx \
  --periodicos-xlsx caminho/periodicos.xlsx
```

A atualização não adiciona aliases de ISSN obtidos de Scopus, JCR ou outras
fontes externas.

## Revisão manual no PPGI

A Parte 1 gera a fila `<ano>_qualis_revisao.csv`. Registre a decisão em
`PPGI/DadosPPGI/input/qualis_overrides.csv`, usando `ASSOCIAR` com um
`qualis_registro_id` ou `SEM_CORRESPONDENCIA`. Depois, execute novamente a
Parte 1.

Consulte [../PPGI/README.md](../PPGI/README.md) para o fluxo completo.
