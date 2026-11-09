"""Deterministic, conservative publication deduplication (POLITICA_V2)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from hashlib import sha256
import csv
import json
import os
import re
import time
import unicodedata
from typing import Any, Iterable

SCHEMA_VERSAO = "3"
POLITICA_V2 = {"versao": "2", "titulo_fuzzy_minimo": .96,
               "descricao": "DOI e identificadores estruturais; conflitos seguem para revisão."}
POLITICA_V1 = POLITICA_V2              # compatibility for clients that imported V1

def normalizar_texto(valor: Any) -> str:
    s = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()
normalizar = normalizar_texto

def normalizar_doi(valor: Any) -> str:
    return re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)\s*", "", str(valor or "").strip().lower()).rstrip(" .;,)")
def doi_valido(valor: Any) -> bool: return bool(re.fullmatch(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", normalizar_doi(valor)))
def normalizar_issn(valor: Any) -> str:
    s = re.sub(r"[^0-9Xx]", "", str(valor or "")).upper()
    return s if len(s) == 8 else ""
def normalizar_isbn(valor: Any) -> str:
    s = re.sub(r"[^0-9Xx]", "", str(valor or "")).upper()
    return s if len(s) in (10, 13) else ""
def normalizar_titulo(valor: Any) -> str: return normalizar_texto(valor)
def normalizar_periodico(valor: Any) -> str: return normalizar_texto(valor)
def normalizar_evento(valor: Any) -> str: return normalizar_texto(valor)
def normalizar_paginas(valor: Any) -> str: return re.sub(r"\s+", "", str(valor or "")).lower()
def normalizar_volume(valor: Any) -> str: return normalizar_paginas(valor)

def normalizar_autor(valor: Any) -> str:
    """Normalize Lattes names, including `SILVA, J. R.`."""
    if isinstance(valor, dict):
        ident = valor.get("id_lattes") or valor.get("id_cnpq")
        if ident: return "id:" + str(ident).strip()
        valor = valor.get("nome") or valor.get("nome_citacao") or ""
    s = normalizar_texto(valor)
    partes = s.split()
    return " ".join(partes)

def _tipo(x): return x.get("tipo", "") if isinstance(x, dict) else ("Periódico" if hasattr(x, "get_revista") else "Conferência")
def _valor(x, k, default=""):
    if isinstance(x, dict): return x.get(k, default)
    m = getattr(x, "get_metadados", lambda: None)()
    if k in {"doi","isbn","volume","fasciculo","pagina_inicial","pagina_final"}: return getattr(m, k, default) if m else default
    methods={"ano":"get_ano","titulo":"get_titulo","issn":"get_issn","venue":"get_venue","revista":"get_revista","autores":"get_autores"}
    return getattr(x, methods[k])() if k in methods and hasattr(x, methods[k]) else default
def _prov(x):
    if isinstance(x, dict): return x.get("curriculo_id", ""), x.get("elemento_xml", x.get("tipo", "")), x.get("sequencia", ""), x.get("proveniencia_incompleta", False)
    p=getattr(getattr(getattr(x,"get_metadados",lambda:None)(),"proveniencia",None),"__dict__",{})
    return p.get("curriculo_id", ""),p.get("elemento_xml", _tipo(x)),p.get("sequencia", ""),p.get("incompleta",False)

def conteudo_fingerprint(x: Any) -> str:
    fields={k: _valor(x,k) for k in ("tipo","ano","titulo","doi","issn","isbn","volume","fasciculo","pagina_inicial","pagina_final","venue","revista","estrato","qualis_evento_id","qualis_registro_id")}
    fields["tipo"]=_tipo(x); fields["autores"]=_autores(x)
    return sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()

def id_ocorrencia(x: Any) -> str:
    curriculum, element, sequence, incomplete = _prov(x)
    if not curriculum: raise ValueError("curriculo_id ausente na proveniência")
    if sequence in (None, "", 0, "0"):
        # A missing Lattes sequence cannot claim complete stable provenance.
        sequence = "fallback:" + conteudo_fingerprint(x)[:24]; incomplete=True
        if isinstance(x, dict): x["proveniencia_incompleta"] = True
    return sha256(f"{SCHEMA_VERSAO}|{curriculum}|{element}|{sequence}".encode()).hexdigest()[:24]

def _autores(x):
    a=_valor(x,"autores", [])
    if isinstance(a,str):
        try: a=json.loads(a)
        except json.JSONDecodeError: a=[a]
    details=x.get("autores_detalhados", []) if isinstance(x,dict) else []
    return sorted(filter(None, [normalizar_autor(v) for v in (details or a or [])]))
def _same_authors(a,b):
    aa,bb=set(_autores(a)),set(_autores(b)); return bool(aa and bb and aa & bb)
def _generic(t): return len(t.split()) < 3 or t in {"editorial", "introduction", "preface"}

@dataclass
class Decisao:
    ocorrencia_a:str; ocorrencia_b:str; decisao:str; motivo:str; score_titulo:float=0.0; override:bool=False
@dataclass
class ResultadoDeduplicacao:
    ocorrencias:list[Any]; ids_ocorrencia:dict[int,str]; canonica_por_ocorrencia:dict[str,str]
    publicacoes_unicas:list[dict]; decisoes:list[Decisao]; revisoes:list[Decisao]
    membros:list[dict]=field(default_factory=list); metricas:dict=field(default_factory=dict)

def decidir_par(a,b,id_a,id_b,politica=POLITICA_V2):
    if _tipo(a)!=_tipo(b): return Decisao(id_a,id_b,"NAO_AGRUPAR","tipos diferentes")
    da,db=normalizar_doi(_valor(a,"doi")),normalizar_doi(_valor(b,"doi"))
    if doi_valido(da) and doi_valido(db):
        if da!=db:return Decisao(id_a,id_b,"NAO_AGRUPAR","DOIs válidos diferentes")
        # DOI does not override severe bibliographic disagreements.
        if str(_valor(a,"ano"))!=str(_valor(b,"ano")) or normalizar_titulo(_valor(a,"titulo"))[:12]!=normalizar_titulo(_valor(b,"titulo"))[:12]: return Decisao(id_a,id_b,"REVISAO_MANUAL","DOI igual com conflito grave")
        return Decisao(id_a,id_b,"AGRUPAR","DOI válido idêntico",1)
    if str(_valor(a,"ano"))!=str(_valor(b,"ano")): return Decisao(id_a,id_b,"NAO_AGRUPAR","anos diferentes")
    ta,tb=normalizar_titulo(_valor(a,"titulo")),normalizar_titulo(_valor(b,"titulo")); score=SequenceMatcher(None,ta,tb).ratio()
    ia,ib=normalizar_issn(_valor(a,"issn")),normalizar_issn(_valor(b,"issn"))
    ea,eb=str(_valor(a,"qualis_evento_id")),str(_valor(b,"qualis_evento_id"))
    venue_a=normalizar_periodico(_valor(a,"revista") or _valor(a,"venue")); venue_b=normalizar_periodico(_valor(b,"revista") or _valor(b,"venue"))
    compatible = (ia and ia==ib) or (ea and ea==eb) or (venue_a and venue_a==venue_b)
    if _tipo(a)=="Conferência" and not (ea and ea==eb) and (not da and not db) and (str(_valor(a,"qualis_requer_revisao")).lower()=="true" or str(_valor(b,"qualis_requer_revisao")).lower()=="true"):
        return Decisao(id_a,id_b,"NAO_AGRUPAR","Qualis pendente sem identidade de evento",score)
    if ia and ib and ia!=ib: return Decisao(id_a,id_b,"NAO_AGRUPAR","ISSNs diferentes",score)
    if ta==tb and compatible and (not _generic(ta) or _same_authors(a,b)): return Decisao(id_a,id_b,"AGRUPAR","título e identidade de veículo",score)
    if score>=politica["titulo_fuzzy_minimo"] and compatible and _same_authors(a,b): return Decisao(id_a,id_b,"AGRUPAR","título similar, veículo e autores",score)
    if score>=.80 and compatible:return Decisao(id_a,id_b,"REVISAO_MANUAL","evidência insuficiente",score)
    return Decisao(id_a,id_b,"NAO_AGRUPAR","evidência insuficiente",score)

def ler_overrides(path):
    if not path or not os.path.exists(path):
        if path: raise FileNotFoundError(f"arquivo de overrides configurado não existe: {path}")
        return []
    with open(path,newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))

def _overrides(rows, ids, items):
    out={}; fingerprints={ids[id(x)]:conteudo_fingerprint(x) for x in items}
    for r in rows:
        a,b,action=r.get("ocorrencia_a",""),r.get("ocorrencia_b",""),r.get("acao","")
        if not a and not b: continue
        if a not in fingerprints or b not in fingerprints or a==b: raise ValueError("override tem ocorrência inválida")
        if action not in {"AGRUPAR","NAO_AGRUPAR"}: raise ValueError("ação de override inválida")
        # Legacy in-memory callers are accepted. CSV V2 rows need fingerprints and justification.
        if r.get("schema_versao") and (r.get("fingerprint_a")!=fingerprints[a] or r.get("fingerprint_b")!=fingerprints[b] or not r.get("justificativa","").strip()): raise ValueError("override obsoleto ou sem justificativa")
        k=tuple(sorted((a,b)))
        if k in out and out[k]!=action: raise ValueError("overrides contraditórios")
        out[k]=action
    return out

def _candidate_pairs(items, ids):
    blocks=defaultdict(set)
    for n,x in enumerate(items):
        d=normalizar_doi(_valor(x,"doi")); y=str(_valor(x,"ano")); typ=_tipo(x)
        if doi_valido(d): blocks[("doi",d)].add(n)
        issn=normalizar_issn(_valor(x,"issn")); event=str(_valor(x,"qualis_evento_id"))
        if issn: blocks[("issn",typ,y,issn)].add(n)
        if event: blocks[("event",typ,y,event)].add(n)
        title=normalizar_titulo(_valor(x,"titulo"));
        if title: blocks[("title",typ,y," ".join(title.split()[:4]))].add(n)
    pairs=set()
    for values in blocks.values():
        v=sorted(values)
        for i,a in enumerate(v):
            for b in v[i+1:]: pairs.add((a,b))
    return sorted(pairs,key=lambda p:(ids[id(items[p[0]])],ids[id(items[p[1]])]))

def _merged(member_ids, items):
    rows=[items[i] for i in member_ids]
    def values(key, norm=lambda x:x):
        seen=[]
        for x in rows:
            v=_valor(x,key)
            if v and norm(v) not in [norm(q) for q in seen]:seen.append(v)
        return seen
    estratos=values("estrato"); records=values("qualis_registro_id")
    conflicts=[]
    if len(set(estratos))>1:conflicts.append({"campo":"estrato","valores":estratos,"bloqueia_pontuacao":True})
    if len(set(records))>1:conflicts.append({"campo":"qualis_registro_id","valores":records,"bloqueia_pontuacao":True})
    oid=sorted(id_ocorrencia(x) for x in rows); cid=sha256(("canon|"+"|".join(oid)).encode()).hexdigest()[:24]
    first=rows[0]
    return {"schema_versao":SCHEMA_VERSAO,"publicacao_canonica_id":cid,"tipo":_tipo(first),"ano":_valor(first,"ano"),"titulo":values("titulo")[0] if values("titulo") else "","doi":values("doi",normalizar_doi)[0] if values("doi",normalizar_doi) else "","issn":values("issn",normalizar_issn)[0] if values("issn",normalizar_issn) else "","isbn":values("isbn",normalizar_isbn)[0] if values("isbn",normalizar_isbn) else "","volume":values("volume"),"fasciculo":values("fasciculo"),"pagina_inicial":values("pagina_inicial"),"pagina_final":values("pagina_final"),"venue":values("venue") or values("revista"),"revista":values("revista"),"qualis_evento_id":values("qualis_evento_id")[0] if values("qualis_evento_id") else "","qualis_registro_id":records[0] if len(records)==1 else "","estrato":estratos[0] if len(estratos)==1 else "","autores":json.dumps(sorted(set(sum((_autores(x) for x in rows),[]))),ensure_ascii=False),"variantes_json":json.dumps({k:values(k) for k in ("titulo","doi","issn","isbn","venue","revista","estrato")},ensure_ascii=False),"proveniencia_por_campo_json":json.dumps({k:oid for k in ("titulo","doi","issn","isbn","estrato")}),"conflitos_json":json.dumps(conflicts,ensure_ascii=False),"quantidade_ocorrencias":len(rows),"quantidade_pesquisadores":len(set(_valor(x,"Docente") for x in rows)),"bloqueia_pontuacao":bool(conflicts)}

def deduplicar_publicacoes(ocorrencias, resolucoes_evento=None, overrides=(), politica=POLITICA_V2):
    start=time.perf_counter(); items=list(ocorrencias); ids={id(x):id_ocorrencia(x) for x in items}
    if len(set(ids.values()))!=len(items): raise ValueError("chaves de origem duplicadas")
    ov=_overrides(overrides,ids,items); pairs=_candidate_pairs(items,ids)
    # Overrides create candidates even if indexes do not.
    index={v:k for k,v in enumerate([ids[id(x)] for x in items])}
    pairs=sorted(set(pairs)|{tuple(sorted((index[a],index[b]))) for a,b in ov},key=lambda p:(ids[id(items[p[0]])],ids[id(items[p[1]])]))
    generation=time.perf_counter()-start; decisions=[]; reviews=[]; allowed=[]
    for i,j in pairs:
        d=decidir_par(items[i],items[j],ids[id(items[i])],ids[id(items[j])],politica); k=tuple(sorted((d.ocorrencia_a,d.ocorrencia_b)))
        if k in ov:
            if ov[k]=="AGRUPAR" and d.decisao=="NAO_AGRUPAR": raise ValueError("AGRUPAR não pode ignorar conflito estrutural")
            d=Decisao(d.ocorrencia_a,d.ocorrencia_b,ov[k],"override versionado",d.score_titulo,True)
        decisions.append(d)
        if d.decisao=="AGRUPAR":allowed.append((i,j))
        elif d.decisao=="REVISAO_MANUAL":reviews.append(d)
    # Components are accepted only when every cross-member relationship is affirmative.
    parent=list(range(len(items)))
    def find(a):
        while parent[a]!=a:parent[a]=parent[parent[a]];a=parent[a]
        return a
    for i,j in allowed:
        ai,bj=find(i),find(j)
        if ai==bj:continue
        left=[x for x in range(len(items)) if find(x)==ai]; right=[x for x in range(len(items)) if find(x)==bj]
        bad=False
        for a in left:
            for b in right:
                d=decidir_par(items[a],items[b],ids[id(items[a])],ids[id(items[b])],politica)
                k=tuple(sorted((d.ocorrencia_a,d.ocorrencia_b))); action=ov.get(k,d.decisao)
                if action!="AGRUPAR":bad=True
        if bad:
            r=Decisao(ids[id(items[i])],ids[id(items[j])],"REVISAO_MANUAL","componente ambíguo com conflito",0); decisions.append(r);reviews.append(r)
        else: parent[bj]=ai
    groups=defaultdict(list)
    for i in range(len(items)):groups[find(i)].append(i)
    canon={}; uniques=[]; members=[]
    for g in sorted(groups.values(),key=lambda z:sorted(ids[id(items[i])] for i in z)):
        merged=_merged(g,items); uniques.append(merged)
        for i in g:
            oid=ids[id(items[i])];canon[oid]=merged["publicacao_canonica_id"];members.append({"publicacao_canonica_id":canon[oid],"ocorrencia_id":oid,"Docente":_valor(items[i],"Docente")})
    uniques.sort(key=lambda x:x["publicacao_canonica_id"])
    return ResultadoDeduplicacao(items,ids,canon,uniques,decisions,reviews,members,{"pares_possiveis":len(items)*(len(items)-1)//2,"pares_candidatos":len(pairs),"comparacoes_titulo":len(pairs),"tempo_geracao_candidatos":generation,"tempo_total":time.perf_counter()-start,"ocorrencias":len(items),"publicacoes_unicas":len(uniques),"revisoes":len(reviews)})
