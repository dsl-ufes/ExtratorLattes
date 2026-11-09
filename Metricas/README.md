# Métricas de publicações

O pacote enriquece as publicações canônicas geradas pela Parte 1 do PPGI.
Ele não altera a pontuação.

## Snapshot e cache

Cada execução cria um snapshot imutável. Ele começa como `EM_EXECUCAO` e termina
como `CONCLUIDO`, `PARCIAL` ou `FALHOU`. A exportação aceita somente snapshots
concluídos ou parciais. O replay lê as entradas e os vínculos armazenados no
SQLite. Ele não lê os CSV atuais e não consulta provedores.

Uma execução completa retorna 0. Uma execução parcial retorna 2. Uma falha
inesperada retorna 1. Respostas de métricas ficam no cache por sete dias.
Resultados ausentes ou ambíguos ficam por um dia. Erros temporários, limites,
credenciais e respostas inválidas não entram no cache. No modo offline, cache
expirado recebe `CACHE_EXPIRADO` e conserva `consultada_em`.

`consultada_em` é a hora da consulta ao provedor. `obtida_em` é a hora
representada pela resposta. `registrada_em` é a gravação no banco. `exportada_em`
é a geração do relatório. Um cache hit não cria uma nova aquisição.

## Fontes

O ranking usa somente `google_scholar.citations`. Uma contagem igual a zero é
válida. CAPTCHA, HTTP 429 e páginas inesperadas são falhas de acesso e não
viram zero. O Scholar pode ler perfis opt-in de um CSV com
`lattes_id,docente,scholar_profile_url` antes da busca por título.

Scopus fornece indexação, citações e métricas do veículo como contexto. O
Crossref é uma fonte auxiliar de identidade. Sua contagem de citações não é
armazenada nem exportada.

## Associação Scholar

A pesquisa usa `intitle:"título"`. Um vínculo exige:

- título normalizado igual;
- ano compatível, quando disponível;
- autores disponíveis não incompatíveis;
- autor ou veículo compatível quando a publicação não tem DOI.

Resultados múltiplos compatíveis recebem `AMBIGUO`. Páginas de verificação
recebem `LIMITE_EXCEDIDO`.

O provedor espera 2,5 segundos mais um jitter de até 1 segundo entre
requisições. Esses valores são configuráveis em `config-metricas.json`.
O agente HTTP pode ser definido pela variável `GOOGLE_SCHOLAR_USER_AGENT`.
Scholar fica desabilitado por padrão. Quando habilitado, uma CAPTCHA ou HTTP 429
abre o circuito para o restante da execução. O programa não troca proxy,
identidade ou agente HTTP.

Scopus usa `SCOPUS_API_KEY` e, quando necessário, `SCOPUS_INSTTOKEN`. As
credenciais não são gravadas em SQLite, manifestos ou relatórios.

## Referências de implementação

O formato de consulta por título segue o projeto público
[qLattes](https://github.com/nabormendonca/qlattes), licenciado sob MIT.

Os snapshots, o intervalo entre requisições e os seletores conhecidos do
Google Scholar foram estudados na extensão
[Scholar Watch](https://chromewebstore.google.com/detail/scholar-watch/maljdgiokfadogmhohcbkeoglbajecjl).
O Scholar Watch não publica licença de código. Esta implementação é própria e
não copia seu código.

## Relatórios

`*_metricas_ranking.csv` usa ranking denso por citações Google Scholar. Qualis
e métricas Scopus aparecem somente como contexto nos artefatos internos.
