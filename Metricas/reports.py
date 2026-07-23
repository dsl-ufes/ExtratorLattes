"""Exportações CSV. Métricas de fontes diferentes não são somadas."""
from __future__ import annotations
import csv, json, os
from datetime import datetime, timezone

def _csv(path, rows, columns):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w=csv.DictWriter(f, fieldnames=columns, extrasaction="ignore"); w.writeheader(); w.writerows(rows)

def exportar(repo, snapshot_id, diretorio, prefixo, ocorrencias=()):
    snapshot = repo.snapshot(snapshot_id)
    if not snapshot:
        raise ValueError("snapshot não encontrado")
    if snapshot["estado"] in {"EM_EXECUCAO", "FALHOU"}:
        raise ValueError("snapshot não pode ser exportado antes da conclusão")
    exportada_em = datetime.now(timezone.utc).isoformat()
    os.makedirs(diretorio, exist_ok=True)
    identidades=repo.itens("identidade", snapshot_id); metricas=repo.itens("metrica_snapshot", snapshot_id); revisoes=repo.itens("revisao", snapshot_id)
    consultas=[{"schema_versao":"2", **x} for x in repo.consultas(snapshot_id)]
    for linhas in (identidades, metricas, revisoes, consultas):
        for linha in linhas:
            linha.setdefault("snapshot_estado", snapshot["estado"])
            linha.setdefault("snapshot_input_hash", snapshot["input_hash"])
            linha.setdefault("exportada_em", exportada_em)
    bases={"identidades":identidades,"publicacoes":_publicacoes(ocorrencias, identidades, metricas),"veiculos":_veiculos(identidades, metricas),"revisao":revisoes,"consultas":consultas}
    for nome, linhas in bases.items():
        cols=sorted({k for x in linhas for k in x} | {"schema_versao","snapshot_id"})
        _csv(os.path.join(diretorio, f"{prefixo}_metricas_{nome}.csv"), linhas, cols)
    por_docente=[]
    vinculos_vistos=set()
    # Replay uses immutable membership captured with the snapshot. The optional
    # argument exists only for compatibility with callers that create old rows.
    ocorrencias = repo.entradas_snapshot(snapshot_id) or list(ocorrencias)
    for o in ocorrencias:
        for m in metricas:
            if m["publicacao_canonica_id"] == o.get("publicacao_canonica_id"):
                chave=(o.get("Docente",""),m["publicacao_canonica_id"],m["provedor"],m["nome_metrica"],m.get("periodo_inicio",""),m.get("periodo_fim",""))
                if chave in vinculos_vistos: continue
                vinculos_vistos.add(chave)
                por_docente.append({"schema_versao":"2","snapshot_id":snapshot_id,"Docente":o.get("Docente",""), **m})
    _csv(os.path.join(diretorio, f"{prefixo}_metricas_docentes.csv"), por_docente, sorted({k for x in por_docente for k in x} | {"schema_versao","snapshot_id","Docente"}))
    resumo={}
    for m in metricas:
        chave=(m["provedor"],m["nome_metrica"],m.get("periodo_inicio",""),m.get("periodo_fim","")); resumo.setdefault(chave, {"schema_versao":"2","snapshot_id":snapshot_id,"provedor":chave[0],"nome_metrica":chave[1],"periodo_inicio":chave[2],"periodo_fim":chave[3],"publicacoes_com_metrica":0})["publicacoes_com_metrica"] += 1
    _csv(os.path.join(diretorio, f"{prefixo}_metricas_resumo.csv"), list(resumo.values()), ["schema_versao","snapshot_id","provedor","nome_metrica","periodo_inicio","periodo_fim","publicacoes_com_metrica"])
    _exportar_ranking(metricas, identidades, ocorrencias, snapshot_id, os.path.join(diretorio, f"{prefixo}_metricas_ranking.csv"))


def _publicacoes(ocorrencias, identidades, metricas):
    pubs={x.get("publicacao_canonica_id", ""): dict(x) for x in ocorrencias}
    for i in identidades:
        p=pubs.setdefault(i["publicacao_canonica_id"], {"publicacao_canonica_id":i["publicacao_canonica_id"]})
        if i["provedor"] == "scopus": p.update({"scopus.indexed": "SIM" if i["status"] == "RESOLVIDO" else ("NAO" if i["status"] == "NAO_ENCONTRADO" else "INDETERMINADO"), "scopus.status": i["status"]})
    for m in metricas:
        p=pubs.setdefault(m["publicacao_canonica_id"], {"publicacao_canonica_id":m["publicacao_canonica_id"]})
        p[m["nome_metrica"]]=m.get("valor"); p[m["nome_metrica"] + ".ano"]=m.get("periodo_fim", "")
        if m["nome_metrica"] == "google_scholar.citations": p["google_scholar.consultada_em"] = m.get("consultada_em", "")
    return list(pubs.values())


def _veiculos(identidades, metricas):
    por_id={i["publicacao_canonica_id"]:i for i in identidades if i["provedor"] == "scopus" and i["status"] == "RESOLVIDO"}; saida=[]
    for pid, i in por_id.items():
        evidencia=json.loads(i.get("evidencias_json", "{}")); ident=evidencia.get("identidade", {})
        linha={"source_id":ident.get("source_id", ""), "titulo_veiculo":ident.get("vehicle_title") or ident.get("venue", ""), "tipo_veiculo":ident.get("vehicle_type", "")}
        for m in metricas:
            if m["publicacao_canonica_id"] == pid and m["nome_metrica"].startswith("scopus."):
                linha[m["nome_metrica"]]=m.get("valor"); linha[m["nome_metrica"] + ".ano"]=m.get("periodo_fim", "")
        saida.append(linha)
    return saida


def _exportar_ranking(metricas, identidades, ocorrencias, snapshot_id, caminho):
    publicacoes={}
    for ocorrencia in ocorrencias:
        canonica_id=ocorrencia.get("publicacao_canonica_id","")
        atual=publicacoes.get(canonica_id)
        if atual is None or ocorrencia.get("ocorrencia_id") == canonica_id:
            publicacoes[canonica_id]=ocorrencia
    itens=[m for m in metricas if m.get("nome_metrica") == "google_scholar.citations"]
    contexto={}
    for m in metricas:
        contexto.setdefault(m["publicacao_canonica_id"], {})[m.get("nome_metrica")]=m.get("valor")
    estados={i["publicacao_canonica_id"]:i.get("status") for i in identidades if i.get("provedor") == "google_scholar"}
    cobertura={"elegiveis": len(publicacoes), "resolvidas": sum(x == "RESOLVIDO" for x in estados.values()), "ausentes": sum(x == "NAO_ENCONTRADO" for x in estados.values()), "ambiguas": sum(x == "AMBIGUO" for x in estados.values()), "bloqueadas": sum(x in {"LIMITE_EXCEDIDO", "ERRO_TEMPORARIO", "ERRO_PERMANENTE"} for x in estados.values())}
    itens.sort(key=lambda x: (-float(x["valor"]),x["publicacao_canonica_id"]))
    linhas=[]; anterior=None; posicao=0
    for indice, metrica in enumerate(itens, 1):
            if anterior != metrica["valor"]: posicao += 1; anterior = metrica["valor"]
            publicacao=publicacoes.get(metrica["publicacao_canonica_id"],{})
            linhas.append({
                "schema_versao":"2","snapshot_id":snapshot_id,"ranking_na_fonte":posicao,
                "publicacao_canonica_id":metrica["publicacao_canonica_id"],"titulo":publicacao.get("titulo",""),
                "ano":publicacao.get("ano",""),"tipo":publicacao.get("tipo",""),
                "veiculo":publicacao.get("venue") or publicacao.get("revista","") ,"provedor":"google_scholar",
                "qualis":publicacao.get("Qualis") or publicacao.get("qualis", ""),
                "scopus.citations":contexto.get(metrica["publicacao_canonica_id"], {}).get("scopus.citations", ""),
                "scopus.citescore":contexto.get(metrica["publicacao_canonica_id"], {}).get("scopus.citescore", ""),
                **{"cobertura_scholar." + k:v for k,v in cobertura.items()},
                "papel_provedor":metrica.get("papel_provedor",""),"fallback_acionado_por":metrica.get("fallback_acionado_por",""),
                "nome_metrica":"google_scholar.citations","valor":metrica.get("valor"),"unidade":metrica.get("unidade",""),
            })
    resolvidas={x["publicacao_canonica_id"] for x in itens}
    for canonica_id, publicacao in publicacoes.items():
        if canonica_id in resolvidas:
            continue
        linhas.append({"schema_versao":"2", "snapshot_id":snapshot_id, "ranking_na_fonte":"", "publicacao_canonica_id":canonica_id,
            "titulo":publicacao.get("titulo", ""), "ano":publicacao.get("ano", ""), "tipo":publicacao.get("tipo", ""), "veiculo":publicacao.get("venue") or publicacao.get("revista", ""),
            "qualis":publicacao.get("Qualis") or publicacao.get("qualis", ""), "provedor":"google_scholar", "nome_metrica":"google_scholar.citations", "valor":"", "unidade":"citacoes",
            **{"cobertura_scholar." + k:v for k,v in cobertura.items()}})
    colunas=["schema_versao","snapshot_id","ranking_na_fonte","publicacao_canonica_id","titulo","ano","tipo","veiculo","qualis","provedor","scopus.citations","scopus.citescore","cobertura_scholar.elegiveis","cobertura_scholar.resolvidas","cobertura_scholar.ausentes","cobertura_scholar.ambiguas","cobertura_scholar.bloqueadas","papel_provedor","fallback_acionado_por","nome_metrica","valor","unidade"]
    _csv(caminho,linhas,colunas)
