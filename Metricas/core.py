"""Regras conservadoras para identidade externa e métricas."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from Deduplicacao.core import doi_valido, normalizar, normalizar_doi
from .errors import ProviderFailure

POLITICA_METRICAS_V1 = {
    "versao": "2",
    "descricao": "Google Scholar é a única fonte de ranking; Scopus é contexto; Crossref é somente identidade.",
}
SCHEMA_VERSAO = "2"

ESTADOS_FINAIS = {"RESOLVIDO", "NAO_ENCONTRADO", "AMBIGUO", "IDENTIDADE_INCOMPATIVEL", "CREDENCIAL_AUSENTE", "LIMITE_EXCEDIDO", "ERRO_TEMPORARIO", "ERRO_PERMANENTE", "CACHE_AUSENTE", "CACHE_EXPIRADO"}


def agora():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(publicacao):
    campos = (publicacao.get("tipo", ""), publicacao.get("titulo", ""), publicacao.get("ano", ""), publicacao.get("venue", "") or publicacao.get("revista", ""), publicacao.get("autores", ""))
    return hashlib.sha256("|".join(normalizar(x) for x in campos).encode()).hexdigest()


def _autores(valor):
    if not valor:
        return []
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except (TypeError, ValueError):
            valor = valor.split(",")
    return [str(x).strip() for x in valor if str(x).strip()]


def _sobrenomes(autores):
    """Accept both `SILVA, J. R.` and `J R Silva` citation forms."""
    nomes = set()
    for autor in autores:
        partes = normalizar(autor).split()
        if partes:
            nomes.add(partes[0] if ',' in str(autor) else partes[-1])
    return nomes


def _compativel(local, externo):
    """Não aceita DOI quando os metadados disponíveis entram em conflito."""
    doi_local = normalizar_doi(local.get("doi"))
    doi_externo = normalizar_doi(externo.get("doi"))
    if doi_valido(doi_local) and doi_local != doi_externo:
        return False, "DOI incompatível"
    if normalizar(local.get("titulo")) != normalizar(externo.get("title")):
        return False, "título incompatível"
    ano_local, ano_externo = str(local.get("ano") or ""), str(externo.get("year") or "")
    if ano_local and ano_externo and ano_local != ano_externo:
        return False, "ano incompatível"
    tipo = normalizar(local.get("tipo")); externo_tipo = normalizar(externo.get("type"))
    fonte_tipo = normalizar(externo.get("source_type"))
    if tipo and externo_tipo and ("period" in tipo and externo_tipo not in {"journal article", "article"}):
        return False, "tipo incompatível"
    issn_local = normalizar(local.get("issn"))
    issns = {normalizar(x) for x in externo.get("issn", [])}
    if issn_local and issns and issn_local not in issns:
        return False, "ISSN incompatível"
    autores_locais = _autores(local.get("autores"))
    autores_externos = _autores(externo.get("authors"))
    # An exact DOI is decisive. Initial-only author strings are soft evidence.
    if not doi_valido(doi_local) and autores_locais and autores_externos and not (_sobrenomes(autores_locais) & _sobrenomes(autores_externos)):
        return False, "autores incompatíveis"
    return True, ""


@dataclass
class ResultadoEnriquecimento:
    snapshot_id: str
    identidades: list[dict] = field(default_factory=list)
    metricas: list[dict] = field(default_factory=list)
    revisoes: list[dict] = field(default_factory=list)


def enriquecer_publicacoes(
    publicacoes_canonicas,
    provedores,
    repositorio,
    politica=POLITICA_METRICAS_V1,
    snapshot_id=None,
    modo="online",
    revisao_deduplicacao=(),
    refresh=False,
    estrategia_provedores="todos",
    provedores_independentes=(),
):
    if snapshot_id and repositorio.existe_snapshot(snapshot_id):
        raise ValueError("snapshots são imutáveis")
    publicacoes_canonicas = list(publicacoes_canonicas)
    for p in publicacoes_canonicas: p.setdefault("impressao_canonica", fingerprint(p))
    plano = {"primarios": [x.nome for x in provedores], "independentes": [x.nome for x in provedores_independentes], "estrategia": estrategia_provedores}
    snapshot_id = repositorio.criar_snapshot(politica["versao"], modo, snapshot_id, publicacoes_canonicas, plano=plano)
    resultado = ResultadoEnriquecimento(snapshot_id)
    bloqueados = set(revisao_deduplicacao)
    teve_bloqueio = False
    try:
        for publicacao in publicacoes_canonicas:
            canonica_id = publicacao["publicacao_canonica_id"]
            fp = fingerprint(publicacao)
            if canonica_id in bloqueados:
                identidade = _identidade(publicacao, snapshot_id, "deduplicacao", "", "AMBIGUO", fp, {"motivo": "revisão de deduplicação pendente"})
                repositorio.salvar_identidade(identidade); resultado.identidades.append(identidade); continue
            for provedor in provedores_independentes:
                identidade, metricas, revisao = _executar_provedor(publicacao, provedor, repositorio, snapshot_id, modo, fp, refresh, politica)
                identidade["papel_provedor"] = "AUXILIAR"
                identidade["fallback_acionado_por"] = ""
                for metrica in metricas:
                    metrica["papel_provedor"] = "AUXILIAR"
                    metrica["fallback_acionado_por"] = ""
                repositorio.salvar_identidade(identidade)
                repositorio.salvar_metricas(metricas)
                if revisao: repositorio.salvar_revisao(revisao); resultado.revisoes.append(revisao)
                resultado.identidades.append(identidade); resultado.metricas.extend(metricas)
            motivo_fallback = ""
            for indice, provedor in enumerate(provedores):
                identidade, metricas, revisao = _executar_provedor(publicacao, provedor, repositorio, snapshot_id, modo, fp, refresh, politica)
                identidade["papel_provedor"] = "PRIMARIO" if indice == 0 else "FALLBACK"
                identidade["fallback_acionado_por"] = motivo_fallback
                for metrica in metricas:
                    metrica["papel_provedor"] = identidade["papel_provedor"]
                    metrica["fallback_acionado_por"] = motivo_fallback
                repositorio.salvar_identidade(identidade)
                repositorio.salvar_metricas(metricas)
                if revisao: repositorio.salvar_revisao(revisao); resultado.revisoes.append(revisao)
                resultado.identidades.append(identidade); resultado.metricas.extend(metricas)
                if identidade["status"] != "RESOLVIDO": teve_bloqueio = True
                if estrategia_provedores == "fallback":
                    if identidade["status"] == "RESOLVIDO" and any(x.get("valor") is not None for x in metricas):
                        break
                    status_fallback = identidade["status"] if identidade["status"] != "RESOLVIDO" else "SEM_METRICA"
                    motivo_fallback = provedor.nome + ":" + status_fallback
        repositorio.finalizar_snapshot(snapshot_id, "PARCIAL" if teve_bloqueio else "CONCLUIDO")
        return resultado
    except Exception as erro:
        repositorio.finalizar_snapshot(snapshot_id, "FALHOU", erro)
        raise


def _executar_provedor(publicacao, provedor, repositorio, snapshot_id, modo, fp, refresh, politica):
    try:
        return _enriquecer_um(publicacao, provedor, repositorio, snapshot_id, modo, fp, refresh, politica)
    except ProviderFailure as erro:
        resposta={"status": erro.status, "evidencias": {"erro": str(erro)}}
        return _identidade(publicacao, snapshot_id, provedor.nome, "", erro.status, fp, resposta["evidencias"]), [], None


def _identidade(p, snapshot_id, provedor, externo, status, fp, evidencias=None, conflitos=None):
    return {"schema_versao": SCHEMA_VERSAO, "snapshot_id": snapshot_id, "publicacao_canonica_id": p["publicacao_canonica_id"], "impressao_canonica": fp, "provedor": provedor, "identificador_externo": externo, "doi_consultado": normalizar_doi(p.get("doi")), "status": status, "evidencias_json": json.dumps(evidencias or {}, ensure_ascii=False), "conflitos_json": json.dumps(conflitos or {}, ensure_ascii=False), "politica_versao": POLITICA_METRICAS_V1["versao"], "resolvido_em": agora()}


def _enriquecer_um(p, provedor, repo, snapshot_id, modo, fp, refresh, politica=POLITICA_METRICAS_V1):
    doi = normalizar_doi(p.get("doi"))
    if hasattr(provedor, "chave_consulta"):
        tipo_consulta, chave_consulta = provedor.chave_consulta(p, doi)
    else:
        tipo_consulta, chave_consulta = ("doi", doi) if doi_valido(doi) else ("bibliografica", fp)
    resposta = None if refresh else repo.obter_consulta(provedor.nome, tipo_consulta, chave_consulta, provedor.endpoint_versao, permitir_expirada=modo == "offline", politica_versao=politica["versao"])
    cache_hit = resposta is not None
    if resposta and resposta.get("_cache", {}).get("expirado"):
        resposta["status"] = "CACHE_EXPIRADO" if modo == "offline" else resposta["status"]
    if not resposta:
        if modo == "offline":
            resposta = {"status": "CACHE_AUSENTE"}
            repo.registrar_consulta(snapshot_id, p["publicacao_canonica_id"], provedor.nome, tipo_consulta, chave_consulta, False, resposta)
            return _identidade(p, snapshot_id, provedor.nome, "", "CACHE_AUSENTE", fp), [], None
        if hasattr(provedor, "consultar"):
            resposta = provedor.consultar(p, doi)
        elif doi_valido(doi):
            resposta = provedor.resolver_por_doi(p, doi)
        else:
            resposta = {"status": "AMBIGUO", "evidencias": {"motivo": "provedor requer DOI"}}
        # This is the acquisition timestamp. It is deliberately retained on
        # later cache hits and is not the timestamp of this snapshot.
        resposta.setdefault("_cache", {"consultada_em": agora(), "expira_em": ""})
        if resposta.get("status") not in {"ERRO_TEMPORARIO", "LIMITE_EXCEDIDO", "CREDENCIAL_AUSENTE", "ERRO_PERMANENTE"}:
            ttl = 86400 if resposta.get("status") in {"NAO_ENCONTRADO", "AMBIGUO"} else 604800
            repo.salvar_consulta(provedor.nome, tipo_consulta, chave_consulta, resposta, provedor.endpoint_versao, politica_versao=politica["versao"], ttl_seconds=ttl)
    repo.registrar_consulta(snapshot_id, p["publicacao_canonica_id"], provedor.nome, tipo_consulta, chave_consulta, cache_hit, resposta)
    if resposta["status"] != "RESOLVIDO":
        identidade = _identidade(p, snapshot_id, provedor.nome, "", resposta["status"], fp, resposta.get("evidencias"))
        revisao = _revisao(p, provedor.nome, snapshot_id, fp, resposta) if resposta["status"] == "AMBIGUO" else None
        return identidade, [], revisao
    externo = resposta["identidade"]
    validador = getattr(provedor, "validar_identidade", None)
    ok, motivo = validador(p, externo) if validador else _compativel(p, externo)
    if not ok:
        conflito = {"status": "DOI_INCOMPATIVEL", "evidencias": resposta.get("evidencias", {}), "conflitos": {"motivo": motivo}, "identidade": externo}
        return _identidade(p, snapshot_id, provedor.nome, externo.get("id", ""), "IDENTIDADE_INCOMPATIVEL", fp, resposta.get("evidencias"), {"motivo": motivo}), [], _revisao(p, provedor.nome, snapshot_id, fp, conflito)
    evidencias = {"identidade": externo, "consulta": resposta.get("evidencias", {})}
    identidade = _identidade(p, snapshot_id, provedor.nome, externo.get("id", ""), "RESOLVIDO", fp, evidencias)
    metricas = []
    for metrica in resposta.get("metricas", []):
        if metrica.get("valor") is None:
            continue
        cache = resposta.get("_cache", {})
        metricas.append({"schema_versao": SCHEMA_VERSAO, "snapshot_id": snapshot_id, "publicacao_canonica_id": p["publicacao_canonica_id"], "provedor": provedor.nome, "identificador_externo": externo.get("id", ""), "consultada_em": cache.get("consultada_em", agora()), "obtida_em": cache.get("consultada_em", agora()), "registrada_em": agora(), "cache_hit": cache_hit, "cache_age_seconds": cache.get("age_seconds", 0), "cache_expira_em": cache.get("expira_em", ""), "endpoint_versao": provedor.endpoint_versao, "status": "RESOLVIDO", **metrica})
    return identidade, metricas, None


def _revisao(publicacao, provedor, snapshot_id, fp, resposta):
    evidencias = resposta.get("evidencias") or {}
    candidatos = evidencias.get("candidatos") or []
    conflitos = resposta.get("conflitos") or {}
    return {
        "schema_versao": SCHEMA_VERSAO,
        "snapshot_id": snapshot_id,
        "publicacao_canonica_id": publicacao["publicacao_canonica_id"],
        "impressao_canonica": fp,
        "provedor": provedor,
        "metadados_locais_json": json.dumps(publicacao, ensure_ascii=False),
        "candidatos_json": json.dumps(candidatos, ensure_ascii=False),
        "evidencias_json": json.dumps(evidencias, ensure_ascii=False),
        "conflitos_json": json.dumps(conflitos, ensure_ascii=False),
        "motivo": conflitos.get("motivo") or evidencias.get("motivo") or resposta.get("status", "AMBIGUO"),
        "decisao_humana": "",
        "identificador_escolhido": "",
        "justificativa": "",
        "decidido_em": "",
        "politica_versao": POLITICA_METRICAS_V1["versao"],
    }
