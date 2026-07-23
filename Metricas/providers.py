"""Providers for external identity and bibliographic metrics."""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
import requests

from Deduplicacao.core import doi_valido, normalizar, normalizar_doi


def _ano(texto):
    anos = re.findall(r"\b(?:18|19|20)\d{2}\b", texto or "")
    return anos[-1] if anos else ""


def _autores_locais(publicacao):
    autores = publicacao.get("autores") or []
    if isinstance(autores, str):
        try:
            autores = json.loads(autores)
        except (TypeError, ValueError):
            autores = [x.strip() for x in autores.split(",")]
    return [str(x).strip() for x in autores if str(x).strip()]


def _sobrenomes(autores):
    return {normalizar(x).split()[0 if "," in str(x) else -1] for x in autores if normalizar(x).split()}


def _autores_compativeis(locais, externos):
    return not locais or not externos or bool(_sobrenomes(locais) & _sobrenomes(externos))


def _veiculo_local(publicacao):
    return publicacao.get("venue") or publicacao.get("revista") or ""


def _retry_after(resposta, padrao):
    try:
        return max(0, int(resposta.headers.get("Retry-After", padrao)))
    except (TypeError, ValueError):
        return padrao


class ProvedorMetricas:
    nome = "base"
    endpoint_versao = "v1"
    aceita_sem_doi = False

    def __init__(self, session=None, sleep=time.sleep, max_retries=2, jitter=0.0, random_uniform=random.uniform):
        self.session = session or requests.Session()
        self.sleep, self.max_retries = sleep, max_retries
        self.jitter, self.random_uniform = jitter, random_uniform

    def chave_consulta(self, publicacao, doi):
        if doi_valido(doi):
            return "doi", doi
        return "bibliografica", "|".join((normalizar(publicacao.get("titulo")), str(publicacao.get("ano") or "")))

    def consultar(self, publicacao, doi):
        if doi_valido(doi):
            return self.resolver_por_doi(publicacao, doi)
        return self.buscar_candidatos(publicacao) if self.aceita_sem_doi else {"status": "AMBIGUO", "evidencias": {"motivo": "provedor requer DOI"}}

    def resolver_por_doi(self, publicacao, doi):
        raise NotImplementedError

    def buscar_candidatos(self, publicacao):
        return {"status": "AMBIGUO", "evidencias": {"motivo": "busca bibliográfica não implementada"}}

    def _get_json(self, url, params=None, headers=None):
        ultimo = "ERRO_TEMPORARIO"
        for tentativa in range(self.max_retries + 1):
            try:
                resposta = self.session.get(url, params=params, headers=headers, timeout=(5, 30))
                if resposta.status_code == 404: return None, "NAO_ENCONTRADO"
                if resposta.status_code in (401, 403): return None, "CREDENCIAL_AUSENTE"
                if resposta.status_code == 429 or resposta.status_code >= 500:
                    ultimo = "LIMITE_EXCEDIDO" if resposta.status_code == 429 else "ERRO_TEMPORARIO"
                    if tentativa < self.max_retries: self.sleep(_retry_after(resposta, 2 ** tentativa) + self.random_uniform(0, self.jitter))
                    continue
                resposta.raise_for_status()
                return resposta.json(), "RESOLVIDO"
            except (requests.Timeout, requests.ConnectionError, ValueError):
                if tentativa < self.max_retries: self.sleep(2 ** tentativa)
            except requests.RequestException:
                return None, "ERRO_PERMANENTE"
        return None, ultimo


class CrossrefProvider(ProvedorMetricas):
    nome = "crossref"
    endpoint_versao = "works/v1"

    def resolver_por_doi(self, publicacao, doi):
        dados, status = self._get_json("https://api.crossref.org/works/" + doi, headers={"User-Agent": "Extrator-Metricas/2.0"})
        if status != "RESOLVIDO": return {"status": status}
        m = dados["message"]
        return {"status": "RESOLVIDO", "identidade": {"id": m.get("DOI", "").lower(), "doi": m.get("DOI", "").lower(), "title": (m.get("title") or [""])[0], "year": str((m.get("published", {}).get("date-parts", [[""]])[0] or [""])[0]), "type": m.get("type", ""), "issn": m.get("ISSN", [])}, "metricas": []}


class GoogleScholarProvider(ProvedorMetricas):
    nome = "google_scholar"
    endpoint_versao = "html-search-profile/v2"
    aceita_sem_doi = True
    base_url = "https://scholar.google.com/scholar"

    def __init__(self, session=None, sleep=time.sleep, clock=time.monotonic, random_uniform=random.uniform, intervalo_minimo=2.5, jitter=1.0, user_agent=None, perfis=None):
        super().__init__(session=session, sleep=sleep)
        self.clock, self.random_uniform = clock, random_uniform
        self.intervalo_minimo, self.jitter = intervalo_minimo, jitter
        self.user_agent = user_agent or os.getenv("GOOGLE_SCHOLAR_USER_AGENT", "Mozilla/5.0 (compatible; Extrator-Metricas/2.0)")
        self.perfis, self.ultima_consulta, self.circuito_aberto = perfis or {}, None, ""

    def chave_consulta(self, publicacao, doi):
        return "titulo", "|".join((normalizar(publicacao.get("titulo")), str(publicacao.get("ano") or ""), normalizar_doi(doi), normalizar("|".join(_autores_locais(publicacao))), normalizar(_veiculo_local(publicacao))))

    def resolver_por_doi(self, publicacao, doi): return self._buscar(publicacao)
    def buscar_candidatos(self, publicacao): return self._buscar(publicacao)

    def validar_identidade(self, publicacao, identidade):
        if normalizar(publicacao.get("titulo")) != normalizar(identidade.get("title")): return False, "título incompatível"
        if publicacao.get("ano") and identidade.get("year") and str(publicacao["ano"]) != str(identidade["year"]): return False, "ano incompatível"
        autores = _autores_locais(publicacao)
        if not _autores_compativeis(autores, identidade.get("authors") or []): return False, "autores incompatíveis"
        autor_ok = bool(autores and identidade.get("authors") and _autores_compativeis(autores, identidade["authors"]))
        veiculo_ok = bool(normalizar(_veiculo_local(publicacao)) and normalizar(_veiculo_local(publicacao)) == normalizar(identidade.get("venue")))
        return (True, "") if autor_ok or veiculo_ok else (False, "evidência adicional de autor ou veículo ausente")

    def _request(self, url, params):
        if self.circuito_aberto: return None, "LIMITE_EXCEDIDO"
        self._aguardar_intervalo(); self.ultima_consulta = self.clock()
        try: resposta = self.session.get(url, params=params, headers={"User-Agent": self.user_agent}, timeout=(5, 30))
        except (requests.Timeout, requests.ConnectionError): return None, "ERRO_TEMPORARIO"
        except requests.RequestException: return None, "ERRO_PERMANENTE"
        if resposta.status_code == 429: self.circuito_aberto = "HTTP 429"; return None, "LIMITE_EXCEDIDO"
        if not resposta.ok: return None, "ERRO_TEMPORARIO" if resposta.status_code >= 500 else "ERRO_PERMANENTE"
        return resposta, "RESOLVIDO"

    def _buscar(self, publicacao):
        titulo = str(publicacao.get("titulo") or "").strip()
        if not titulo: return {"status": "NAO_ENCONTRADO", "evidencias": {"motivo": "título ausente"}}
        perfil = publicacao.get("scholar_profile_url") or self.perfis.get(str(publicacao.get("lattes_id") or publicacao.get("Docente") or ""))
        if perfil:
            resultado = self._buscar_no_perfil(publicacao, perfil)
            if resultado["status"] != "NAO_ENCONTRADO": return resultado
        resposta, status = self._request(self.base_url, {"q": 'intitle:"' + titulo.replace('"', ' ') + '"', "hl": "en", "num": 10})
        if status != "RESOLVIDO": return {"status": status}
        candidatos, bloqueado = parse_google_scholar_html(resposta.text, getattr(resposta, "url", self.base_url))
        if bloqueado: self.circuito_aberto = "CAPTCHA ou página inesperada"; return {"status": "LIMITE_EXCEDIDO", "evidencias": {"motivo": self.circuito_aberto}}
        return self._resultado(publicacao, candidatos, {"origem": "busca", "url_consulta": getattr(resposta, "url", self.base_url), "candidatos": candidatos})

    def _buscar_no_perfil(self, publicacao, perfil):
        candidatos, inicio = [], 0
        while True:
            resposta, status = self._request(perfil, {"cstart": inicio, "pagesize": 100})
            if status != "RESOLVIDO": return {"status": status}
            pagina, bloqueado = parse_google_scholar_profile_html(resposta.text, getattr(resposta, "url", perfil))
            if bloqueado: self.circuito_aberto = "CAPTCHA ou página inesperada"; return {"status": "LIMITE_EXCEDIDO", "evidencias": {"motivo": self.circuito_aberto}}
            candidatos.extend(pagina)
            if len(pagina) < 100: break
            inicio += 100
        return self._resultado(publicacao, candidatos, {"origem": "perfil", "perfil": perfil, "candidatos": candidatos})

    def _resultado(self, publicacao, candidatos, evidencias):
        compativeis = [x for x in candidatos if x.get("citations") is not None and self.validar_identidade(publicacao, x)[0]]
        if not compativeis: return {"status": "NAO_ENCONTRADO", "evidencias": evidencias}
        if len({x["id"] for x in compativeis}) != 1: return {"status": "AMBIGUO", "evidencias": evidencias}
        x = compativeis[0]
        return {"status": "RESOLVIDO", "identidade": x, "evidencias": evidencias, "metricas": [{"nome_metrica": "google_scholar.citations", "valor": x["citations"], "unidade": "citacoes", "periodo_inicio": "", "periodo_fim": "", "categoria": ""}]}

    def _aguardar_intervalo(self):
        if self.ultima_consulta is not None:
            restante = self.intervalo_minimo + self.random_uniform(0, self.jitter) - (self.clock() - self.ultima_consulta)
            if restante > 0: self.sleep(restante)


def _scholar_bloqueado(html, url):
    texto = (html or "").lower()
    soup = BeautifulSoup(html or "", "html.parser")
    return "/sorry/" in (url or "") or any(x in texto for x in ("unusual traffic", "not a robot", "our systems have detected")) or bool(soup.select_one("#gs_captcha_f, form[action*='/sorry/']"))


def parse_google_scholar_html(html, url_final=""):
    soup = BeautifulSoup(html or "", "html.parser")
    if _scholar_bloqueado(html, url_final): return [], True
    if html and not soup.select_one(".gs_r, #gs_res_ccl, #gs_res_ccl_mid") and "did not match any articles" not in (html or "").lower(): return [], True
    resultados = []
    for registro in soup.select(".gs_r"):
        conteudo = registro.select_one(".gs_ri") or registro; cabecalho = conteudo.select_one(".gs_rt")
        if not cabecalho: continue
        link = cabecalho.select_one("a"); titulo = re.sub(r"^\[[^]]+\]\s*", "", (link or cabecalho).get_text(" ", strip=True))
        meta = (conteudo.select_one(".gs_a").get_text(" ", strip=True) if conteudo.select_one(".gs_a") else ""); partes = [x.strip() for x in meta.split(" - ")]
        rodape = conteudo.select_one(".gs_fl"); citacoes = 0 if rodape else None; ident = registro.get("data-cid", ""); evidencia = ""
        for a in rodape.select("a") if rodape else []:
            m = re.search(r"Cited by\s+([\d.,\s]+)", a.get_text(" ", strip=True), re.I)
            if m:
                citacoes = int(re.sub(r"\D", "", m.group(1)) or 0); ident = (parse_qs(urlparse(a.get("href", "")).query).get("cites") or [ident])[0]; evidencia = urljoin("https://scholar.google.com", a.get("href", "")); break
        link_publicacao = urljoin("https://scholar.google.com", link.get("href", "")) if link else ""
        ident = ident or hashlib.sha256((normalizar(titulo) + meta + link_publicacao).encode()).hexdigest()[:20]
        resultados.append({"id": ident, "doi": "", "title": titulo, "year": _ano(meta), "type": "", "issn": [], "authors": [x.strip() for x in (partes[0] if partes else "").split(",") if x.strip()], "venue": re.sub(r"\b(?:18|19|20)\d{2}\b", "", partes[1]).strip(" ,") if len(partes) > 1 else "", "citations": citacoes, "url_publicacao": link_publicacao, "url_evidencia": evidencia or url_final})
    return resultados, False


def parse_google_scholar_profile_html(html, url_final=""):
    if _scholar_bloqueado(html, url_final): return [], True
    soup = BeautifulSoup(html or "", "html.parser"); linhas = soup.select("tr.gsc_a_tr")
    if html and not linhas: return [], True
    resultados = []
    for linha in linhas:
        titulo = linha.select_one("a.gsc_a_at"); cit = linha.select_one(".gsc_a_ac")
        if not titulo: continue
        cinza = [x.get_text(" ", strip=True) for x in linha.select(".gs_gray")]; ano = linha.select_one(".gsc_a_y")
        resultados.append({"id": (cit or titulo).get("href", "") or hashlib.sha256(titulo.get_text().encode()).hexdigest()[:20], "doi": "", "title": titulo.get_text(" ", strip=True), "year": ano.get_text(" ", strip=True) if ano else _ano(" ".join(cinza)), "type": "", "issn": [], "authors": [x.strip() for x in (cinza[0] if cinza else "").split(",") if x.strip()], "venue": cinza[1] if len(cinza) > 1 else "", "citations": int(re.sub(r"\D", "", cit.get_text(" ", strip=True)) or 0) if cit else 0, "url_publicacao": urljoin("https://scholar.google.com", titulo.get("href", "")), "url_evidencia": url_final})
    return resultados, False


class ScopusProvider(ProvedorMetricas):
    """Official Elsevier Scopus API provider. It never stores credentials."""
    nome = "scopus"
    endpoint_versao = "search-abstract-serial/v1"
    aceita_sem_doi = True
    base_url = "https://api.elsevier.com/content"

    def __init__(self, *args, api_key_env="SCOPUS_API_KEY", insttoken_env="SCOPUS_INSTTOKEN", **kwargs):
        super().__init__(*args, **kwargs); self.api_key_env, self.insttoken_env = api_key_env, insttoken_env; self.capacidades = None; self.quota = {}

    def chave_consulta(self, publicacao, doi):
        conhecido = publicacao.get("scopus_id") or publicacao.get("eid") or ""
        return ("doi", doi) if doi_valido(doi) else (("scopus_id", conhecido) if conhecido else ("bibliografica", "|".join((normalizar(publicacao.get("titulo")), str(publicacao.get("ano") or ""), normalizar("|".join(_autores_locais(publicacao))), normalizar(_veiculo_local(publicacao))))))

    def _headers(self):
        chave = os.getenv(self.api_key_env)
        if not chave: return None
        h = {"X-ELS-APIKey": chave, "Accept": "application/json"}; token = os.getenv(self.insttoken_env)
        if token: h["X-ELS-Insttoken"] = token
        return h

    def _scopus_get(self, path, params=None):
        h = self._headers()
        if not h: return None, "CREDENCIAL_AUSENTE"
        dados, status = self._get_json(self.base_url + path, params=params, headers=h)
        return dados, status

    def detectar_capacidades(self):
        if self.capacidades is not None: return self.capacidades
        _, status = self._scopus_get("/search/scopus", {"query": "DOI(10.0000/invalid)", "count": 1})
        self.capacidades = {"search": status == "RESOLVIDO", "abstract": status == "RESOLVIDO", "serial": status == "RESOLVIDO", "estado": "DISPONIVEL" if status == "RESOLVIDO" else "INDETERMINADO", "motivo": status}
        return self.capacidades

    def consultar(self, publicacao, doi):
        caps = self.detectar_capacidades()
        if not caps["search"]: return {"status": "INDETERMINADO", "evidencias": {"capacidades": caps}}
        if doi_valido(doi): return self.resolver_por_doi(publicacao, doi)
        conhecido = publicacao.get("eid") or publicacao.get("scopus_id")
        if conhecido: return self.resolver_por_id(publicacao, conhecido)
        return self.buscar_candidatos(publicacao)

    def resolver_por_doi(self, publicacao, doi):
        return self._resolver_busca(publicacao, "DOI(" + doi + ")")

    def resolver_por_id(self, publicacao, identificador):
        return self._resolver_busca(publicacao, "EID(" + str(identificador).replace("eid:", "") + ")")

    def buscar_candidatos(self, publicacao):
        termos = 'TITLE({})'.format(str(publicacao.get("titulo") or "").replace('"', " "))
        if publicacao.get("ano"): termos += " AND PUBYEAR IS " + str(publicacao["ano"])
        autor = next(iter(_sobrenomes(_autores_locais(publicacao))), "")
        if autor: termos += " AND AUTHLASTNAME(" + autor + ")"
        return self._resolver_busca(publicacao, termos)

    def _resolver_busca(self, publicacao, query):
        dados, status = self._scopus_get("/search/scopus", {"query": query, "count": 10, "view": "COMPLETE"})
        if status == "NAO_ENCONTRADO": return {"status": "NAO_ENCONTRADO"}
        if status != "RESOLVIDO": return {"status": "INDETERMINADO", "evidencias": {"motivo": status}}
        entradas = (dados.get("search-results") or {}).get("entry") or []
        candidatos = [self._identidade(x) for x in entradas]
        compativeis = [x for x in candidatos if _identidade_bibliografica_compativel(publicacao, x)]
        if not compativeis: return {"status": "NAO_ENCONTRADO", "evidencias": {"candidatos": candidatos}}
        if len({x["id"] for x in compativeis}) != 1: return {"status": "AMBIGUO", "evidencias": {"candidatos": compativeis}}
        escolhido = next(x for x in entradas if self._identidade(x)["id"] == compativeis[0]["id"])
        return self._resultado(escolhido)

    def _resultado(self, entrada):
        identidade = self._identidade(entrada); metricas = [{"nome_metrica": "scopus.citations", "valor": _inteiro(entrada.get("citedby-count")), "unidade": "citacoes", "periodo_inicio": "", "periodo_fim": "", "categoria": ""}]
        veiculo, status = self._serial(identidade)
        if status == "RESOLVIDO":
            metricas.extend(self._metricas_veiculo(veiculo))
            identidade.update({"source_id": str(veiculo.get("source-id") or identidade.get("source_id") or ""), "vehicle_title": veiculo.get("dc:title") or identidade.get("venue", ""), "vehicle_type": veiculo.get("source-type") or "", "vehicle_url": veiculo.get("prism:url") or ""})
        return {"status": "RESOLVIDO", "identidade": identidade, "metricas": metricas, "evidencias": {"registro": entrada.get("prism:url", ""), "citacoes": entrada.get("prism:url", ""), "veiculo_status": status}}

    def _serial(self, identidade):
        params = {"count": 1, "view": "ENHANCED"}
        if identidade.get("source_id"): params["source-id"] = identidade["source_id"]
        elif identidade.get("issn"): params["issn"] = identidade["issn"][0]
        else: return {}, "NAO_ENCONTRADO"
        dados, status = self._scopus_get("/serial/title", params)
        entradas = ((dados or {}).get("serial-metadata-response") or {}).get("entry") or []
        return (entradas[0], "RESOLVIDO") if entradas else ({}, status if status != "RESOLVIDO" else "NAO_ENCONTRADO")

    def _metricas_veiculo(self, v):
        saida = []
        for nome, chave, ano in (("scopus.citescore", "citeScoreCurrentMetric", "citeScoreYearInfo"), ("scopus.citescore_tracker", "citeScoreTracker", "citeScoreTrackerYearInfo"), ("scopus.sjr", "SJRList", "SJRList"), ("scopus.snip", "SNIPList", "SNIPList")):
            valor = v.get(chave)
            if isinstance(valor, dict): valor = valor.get("$") or valor.get("value")
            if isinstance(valor, list):
                valor = (valor[0].get("$") or valor[0].get("value")) if valor else None
            if valor is not None: saida.append({"nome_metrica": nome, "valor": valor, "unidade": "indice", "periodo_inicio": str(v.get(ano, "")), "periodo_fim": str(v.get(ano, "")), "categoria": ""})
        for categoria in v.get("subject-area", []) if isinstance(v.get("subject-area"), list) else []:
            saida.append({"nome_metrica": "scopus.category", "valor": categoria.get("$", ""), "unidade": "categoria", "periodo_inicio": "", "periodo_fim": "", "categoria": categoria.get("@code", "")})
        return saida

    @staticmethod
    def _identidade(x):
        autores = [a.strip() for a in str(x.get("dc:creator") or "").split(",") if a.strip()]
        issn = [x[k] for k in ("prism:issn", "prism:eIssn") if x.get(k)]
        return {"id": x.get("dc:identifier", "").replace("SCOPUS_ID:", ""), "eid": x.get("eid", ""), "doi": normalizar_doi(x.get("prism:doi")), "title": x.get("dc:title", ""), "year": str(x.get("prism:coverDate", ""))[:4], "type": x.get("subtypeDescription", ""), "issn": issn, "authors": autores, "venue": x.get("prism:publicationName", ""), "source_id": x.get("source-id", ""), "source_type": x.get("prism:aggregationType", ""), "record_url": x.get("prism:url", "")}


def _inteiro(valor):
    try: return int(valor)
    except (ValueError, TypeError): return None


def _identidade_bibliografica_compativel(publicacao, identidade):
    doi = normalizar_doi(publicacao.get("doi"))
    if doi_valido(doi) and doi != normalizar_doi(identidade.get("doi")): return False
    if normalizar(publicacao.get("titulo")) != normalizar(identidade.get("title")): return False
    if publicacao.get("ano") and identidade.get("year") and str(publicacao["ano"]) != str(identidade["year"]): return False
    autores = _autores_locais(publicacao); externos = identidade.get("authors") or []
    if not _autores_compativeis(autores, externos): return False
    return doi_valido(doi) or bool((autores and externos) or (normalizar(_veiculo_local(publicacao)) and normalizar(_veiculo_local(publicacao)) == normalizar(identidade.get("venue"))))
