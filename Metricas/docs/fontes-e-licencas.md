# Fontes, licenças e acesso

Perfil de distribuição: `INTERNO`.

O Google Scholar fornece a única contagem usada no ranking. O sistema mantém a
URL de evidência e a data da consulta. CAPTCHA, HTTP 429 e páginas inesperadas
são falhas de acesso. Elas nunca são registradas como zero.

Scopus é acessado somente pela API oficial da Elsevier. A chave vem de
`SCOPUS_API_KEY`. O token opcional vem de `SCOPUS_INSTTOKEN`. Não grave estes
valores em arquivos, URLs, logs, snapshots, testes ou Git.

No início da execução, o provedor testa as capacidades autorizadas. Falta de
permissão ou erro produz `INDETERMINADO`. `NAO` só é produzido após busca
válida sem resultado. A saída interna deve manter a atribuição e os links
exigidos pela Elsevier: [Scopus API Guide](https://dev.elsevier.com/guides/Scopus%20API%20Guide_V1_20230907.pdf), [Journal Metrics](https://dev.elsevier.com/journal_metrics.html) e [Scopus Attribution Guide](https://dev.elsevier.com/tecdoc_attribution_scopus.html).

Crossref é somente um apoio de identidade. A contagem de citações do Crossref
não é armazenada nem exportada.
