"""
Módulo de matching para o pipeline QualisLens.

Implementa:
- Busca exata por sigla e nome normalizado (via QualisDB)
- Fuzzy matching com rapidfuzz.token_sort_ratio, retornando top-N candidatos
- Resultado unificado com status intermediário (antes de passar pelo LLM)
"""

import json
import logging
from typing import Optional

from rapidfuzz import fuzz, process

from .constants import (
    STATUS_AUTO_FUZZY,
    STATUS_EXATO,
    STATUS_REVISAO_MANUAL,
    THRESHOLD_AUTO,
    THRESHOLD_AUTO_MARGIN,
    THRESHOLD_CANDIDATOS_RUINS,
    TOP_N_CANDIDATOS,
)
from .preprocessor import extrair_acronimo, normalizar, preprocessar_linha
from .qualis_db import QualisDB, get_db
from .constants import POLITICA_VERSAO, STATUS_MANUAL_MISS
import hashlib

logger = logging.getLogger(__name__)

# Colunas internas do subset usado no fuzzy
_COL_NOME_NORM = "nome_norm"
_COL_SIGLA_NORM = "sigla_norm"

_TIPOS_EVENTO = frozenset({"workshop", "conference", "symposium", "congress", "congresso", "meeting"})
_TERMOS_ESTRUTURAIS = frozenset({
    "conference", "symposium", "workshop", "congress", "congresso", "international",
    "annual", "ieee", "acm", "computer", "computing", "systems", "engineering",
})


def _tipo_evento(texto: str) -> set[str]:
    return set(texto.split()) & _TIPOS_EVENTO


def _penalidade_termos_distintivos(query: str, candidato: str) -> float:
    """Penaliza tema contraditório; evita aceitar eventos de nomes parecidos."""
    q = {token for token in query.split() if len(token) >= 6 and token not in _TERMOS_ESTRUTURAIS}
    c = set(candidato.split())
    # Só penaliza palavras específicas. Termos genéricos não devem decidir match.
    ausentes = q - c
    return min(30.0, 10.0 * len(ausentes))


def _token_level_fuzzy(query: str, candidato: str) -> float:
    """
    Compara tokens individualmente via ``partial_ratio``.

    Lida com tokens abreviados ou truncados (ex: "comp" ≈ "computing",
    "des" ≈ "design", "vis" ≈ "vision") pois ``partial_ratio`` detecta
    substrings.

    Parameters
    ----------
    query:
        Texto de consulta normalizado.
    candidato:
        Texto do candidato normalizado.

    Returns
    -------
    float
        Score ponderado pelo comprimento dos tokens da query (0–100).
    """
    q_tokens = query.split()
    c_tokens = candidato.split()
    if not q_tokens or not c_tokens:
        return 0.0
    scores_pesos: list[tuple[float, int]] = []
    for qt in q_tokens:
        if len(qt) < 2:   # letras soltas são ruído
            continue
        best = max(fuzz.partial_ratio(qt, ct) for ct in c_tokens)
        scores_pesos.append((best, len(qt)))
    if not scores_pesos:
        return 0.0
    total_peso = sum(w for _, w in scores_pesos)
    return sum(s * w for s, w in scores_pesos) / total_peso


def _score_hibrido(
    query: str,
    candidato: str,
    acr_query: str,
    acr_candidato: str,
) -> float:
    """
    Score composto combinando quatro sinais de similaridade.

    Sinais (em ordem de confiabilidade decrescente):

    1. ``token_set_ratio``   — robusto a reordenação e subconjuntos de tokens
    2. ``token_sort_ratio``  — bom para frases com palavras na ordem diferente
    3. ``_token_level_fuzzy`` — detecta tokens abreviados/truncados (via partial_ratio)
    4. Acrônimo               — sinal secundário quando ambos têm acrônimo útil

    O score final combina os sinais de nome. Isso evita que um único
    ``token_set_ratio`` alto aceite nomes genéricos como "the 2013 conference".

    Parameters
    ----------
    query:
        Nome normalizado da entrada.
    candidato:
        Nome normalizado do candidato no banco.
    acr_query:
        Acrônimo extraído da entrada original.
    acr_candidato:
        Acrônimo pré-computado do candidato.

    Returns
    -------
    float
        Score entre 0 e 100.
    """
    s_tset = fuzz.token_set_ratio(query, candidato)    # melhor para subsets
    s_tsort = fuzz.token_sort_ratio(query, candidato)  # melhor para reordenação
    s_tok = _token_level_fuzzy(query, candidato)        # melhor para abreviações

    # Acrônimo: útil quando ambos têm comprimento compatível
    s_acr = 0.0
    if acr_query and acr_candidato and len(acr_query) >= 3 and len(acr_candidato) >= 3:
        s_acr = fuzz.ratio(acr_query, acr_candidato)

    score_nome = 0.38 * s_tset + 0.37 * s_tsort + 0.25 * s_tok
    quantidade_query = len(query.split())
    quantidade_candidato = len(candidato.split())
    if quantidade_query and quantidade_candidato:
        equilibrio = min(quantidade_query, quantidade_candidato) / max(
            quantidade_query, quantidade_candidato
        )
        score_nome *= 0.88 + 0.12 * equilibrio

    score_com_acronimo = 0.82 * score_nome + 0.18 * s_acr
    return round(max(score_nome, score_com_acronimo) - _penalidade_termos_distintivos(query, candidato), 1)


def _candidatos_para_json(candidatos: list[dict]) -> str:
    """
    Serializa a lista de candidatos fuzzy como JSON string.

    Parameters
    ----------
    candidatos:
        Lista de dicts com chaves: sigla, nome, estrato, score.

    Returns
    -------
    str
        JSON compacto.
    """
    return json.dumps(candidatos, ensure_ascii=False)


def _busca_fuzzy(
    nome_norm: str,
    siglas_norm: set[str],
    acr_nome: str,
    db: QualisDB,
    ano: int,
) -> list[dict]:
    """
    Executa fuzzy matching híbrido contra o subset do quadriênio correto.

    Estratégia:
    1. Pré-filtro amplo via ``token_set_ratio`` para não perder candidatos
       que o ``token_sort_ratio`` isolado descartaria.
    2. Re-pontuação com ``_score_hibrido``: combina token_set_ratio,
       token_sort_ratio, token-level fuzzy (abreviações) e acrônimo.
    3. Matching por sigla normalizada como sinal adicional.

    Parameters
    ----------
    nome_norm:
        Nome da conferência já normalizado.
    sigla_norm:
        Sigla normalizada (pode ser None).
    acr_nome:
        Acrônimo extraído do nome original.
    db:
        Instância QualisDB.
    ano:
        Ano de publicação — define o subset do quadriênio.

    Returns
    -------
    list[dict]
        Lista de candidatos, cada um com: sigla, nome, estrato, quadrienio, score.
    """
    subset = db.get_subset_quadrienio(ano)
    if subset.empty:
        return []

    nomes_norm = subset["nome_norm"].tolist()
    acrs_candidato = subset["acronimo"].tolist() if "acronimo" in subset.columns else [""] * len(subset)

    # Unir pré-filtros complementares. O token_set é amplo; o token_sort evita
    # perder candidatos cujo conjunto de palavras é semelhante, mas não contido.
    pre_filtro = []
    if nome_norm:
        pre_filtro.extend(process.extract(
            nome_norm,
            nomes_norm,
            scorer=fuzz.token_set_ratio,
            limit=TOP_N_CANDIDATOS * 10,
        ))
        pre_filtro.extend(process.extract(
            nome_norm,
            nomes_norm,
            scorer=fuzz.token_sort_ratio,
            limit=TOP_N_CANDIDATOS * 10,
        ))

    # Re-pontuar com score híbrido
    candidatos_idx: dict[int, float] = {}
    for _match_str, _pre_score, idx in pre_filtro:
        score = _score_hibrido(nome_norm, nomes_norm[idx], acr_nome, acrs_candidato[idx])
        candidatos_idx[idx] = score

    # Uma sigla explícita em qualquer parte do texto é um sinal forte, mas não
    # é tratada como busca exata quando aparece apenas no corpo do nome.
    for sigla_norm in siglas_norm:
        mascara = subset["sigla_norm"] == sigla_norm
        for idx in subset.index[mascara]:
            posicao = subset.index.get_loc(idx)
            candidatos_idx[posicao] = max(candidatos_idx.get(posicao, 0.0), 94.0)

    # Ordenar por score desc e pegar top N
    top_indices = sorted(candidatos_idx.items(), key=lambda x: x[1], reverse=True)

    candidatos = []
    # Um evento pode ter aliases na base. Consolide-os antes da margem para não
    # transformar aliases do mesmo evento em "segundo colocado" artificial.
    identidades: set[str] = set()
    for idx, score in top_indices:
        row = subset.iloc[idx]
        identidade = str(row["sigla_norm"]) or str(row["nome_norm"])
        if identidade in identidades:
            continue
        identidades.add(identidade)
        candidatos.append(
            {
                "sigla": row["sigla"],
                "nome": row["nome"],
                "estrato": row["estrato"],
                "quadrienio": row["quadrienio"],
                "qualis_evento_id": row["qualis_evento_id"],
                "qualis_registro_id": row["qualis_registro_id"],
                "score": score,
            }
        )
        if len(candidatos) == TOP_N_CANDIDATOS:
            break

    return candidatos


def _identidade(resultado: dict) -> tuple[str, str, str]:
    return (
        normalizar(str(resultado.get("sigla", ""))),
        normalizar(str(resultado.get("nome", ""))),
        str(resultado.get("quadrienio", "")),
    )


def _buscar_exato(pre: dict, db: QualisDB, ano: int) -> tuple[Optional[dict], Optional[str]]:
    """Resolve siglas fortes e nome exato; conflitos são devolvidos para revisão."""
    por_nome = (
        db.buscar_por_sigla_e_nome(None, pre["nome_norm"], ano)
        if pre["nome_norm"]
        else None
    )

    por_sigla: list[dict] = []
    identidades: set[tuple[str, str, str]] = set()
    # Mixed-case tokens (for example WebMedia) become strong only here: the
    # official base must corroborate them.  This keeps ordinary title-case
    # words out of exact matching.
    siglas_verificar = list(pre.get("siglas_fortes", []))
    for sigla in pre.get("siglas_candidatas", []):
        if sigla not in siglas_verificar and any(char.islower() for char in sigla):
            siglas_verificar.append(sigla)
    for sigla in siglas_verificar:
        resultado = db.buscar_por_sigla_e_nome(sigla, None, ano)
        if resultado and _identidade(resultado) not in identidades:
            identidades.add(_identidade(resultado))
            por_sigla.append(resultado)

    if por_nome and por_nome.get("ambiguo"):
        return None, "nome_exato_ambiguo"
    if any(resultado.get("ambiguo") for resultado in por_sigla):
        return None, "sigla_exata_ambigua"

    if len(por_sigla) > 1:
        if por_nome:
            iguais_ao_nome = [
                resultado for resultado in por_sigla
                if _identidade(resultado) == _identidade(por_nome)
            ]
            if len(iguais_ao_nome) == 1:
                return iguais_ao_nome[0], None
        return None, "multiplas_siglas_explicitas"

    if por_sigla and por_nome and _identidade(por_sigla[0]) != _identidade(por_nome):
        return None, "conflito_sigla_nome"
    if por_sigla:
        # A supplied name is evidence.  An acronym must not override a
        # different workshop/conference or a topical name conflict.
        nome_informado = pre.get("nome_norm", "")
        if nome_informado and len(nome_informado.split()) > 1:
            candidato = normalizar(por_sigla[0]["nome"])
            tipos = _tipo_evento(nome_informado), _tipo_evento(candidato)
            score = _score_hibrido(nome_informado, candidato, "", "")
            if (tipos[0] and tipos[1] and not (tipos[0] & tipos[1])) or score < 80:
                return None, "conflito_sigla_nome"
        return por_sigla[0], None
    return por_nome, None


def qualis_input_id(nome: str, ano: int, sigla: Optional[str] = None) -> str:
    """Identity of reported input. It never uses XML or publication sequence."""
    payload = "\x1f".join((POLITICA_VERSAO, str(ano), normalizar(nome), normalizar(sigla or "")))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def validar_resultado(resultado: dict) -> dict:
    """Apply output invariants at one boundary."""
    status = resultado.get("qualis_status")
    accepted = {STATUS_EXATO, STATUS_AUTO_FUZZY, "LLM_OK", "LLM_DUPLO_OK", "MANUAL_OK"}
    selected = bool(resultado.get("qualis_registro_id") and resultado.get("qualis_estrato"))
    if status == "ERRO":
        resultado["qualis_requer_revisao"] = True
    elif status == STATUS_MANUAL_MISS:
        resultado["qualis_requer_revisao"] = False
    elif status in accepted and not selected:
        resultado["qualis_status"] = STATUS_REVISAO_MANUAL
        resultado["qualis_requer_revisao"] = True
        resultado["qualis_obs"] = ((resultado.get("qualis_obs") or "") + "; resultado_aceito_sem_registro").strip("; ")
    else:
        resultado["qualis_requer_revisao"] = status in {STATUS_REVISAO_MANUAL, "LLM_MISS", "LLM_LOW_OK", "LLM_LOW_MISS", "LLM_DUPLO_DIVERGE", "ERRO"}
    return resultado


def _resultado(
    *,
    status: str,
    candidatos: list[dict],
    pre: dict,
    estrato: Optional[str] = None,
    sigla: Optional[str] = None,
    nome: Optional[str] = None,
    quadrienio: Optional[str] = None,
    evento_id: Optional[str] = None,
    registro_id: Optional[str] = None,
    score: float = 0.0,
    margem: float = 0.0,
    observacoes: Optional[list[str]] = None,
    precisa_llm: bool = False,
) -> dict:
    # Usa sigla_informada (o valor bruto recebido), não sigla_original (que
    # pode ter sido extraída do próprio nome). QualisConferencia.get_match
    # calcula a chave de busca de overrides com o mesmo sigla bruto recebido
    # do chamador; usar o valor pós-extração aqui faria o ID reportado ao
    # humano divergir da chave realmente usada na busca de overrides sempre
    # que o texto do evento contivesse uma sigla extraível (ex.: "SC24: ...").
    result = {
        "qualis_input_id": qualis_input_id(pre.get("venue_informado", pre.get("nome_original", "")), pre.get("ano", 0), pre.get("sigla_informada")),
        "qualis_evento_id": evento_id,
        "qualis_registro_id": registro_id,
        "qualis_estrato": estrato,
        "qualis_sigla": sigla,
        "qualis_nome_oficial": nome,
        "qualis_quadrienio": quadrienio,
        "qualis_score_fuzzy": score,
        "qualis_score_margem": margem,
        "qualis_score_llm": None,
        "qualis_status": status,
        "qualis_requer_revisao": False,
        "qualis_candidatos": _candidatos_para_json(candidatos),
        "qualis_llm_motivo": None,
        "qualis_obs": "; ".join(observacoes or []) or None,
        "qualis_origem_decisao": "automatico",
        "qualis_politica_versao": POLITICA_VERSAO,
        "qualis_justificativa": None,
        "qualis_decidido_por": None,
        "qualis_decidido_em": None,
        "_pre": pre,
        "_candidatos_lista": candidatos,
        "_precisa_llm": precisa_llm,
    }
    return validar_resultado(result)


def match(
    nome_conferencia: str,
    ano: int,
    sigla_conferencia: Optional[str] = None,
    db: Optional[QualisDB] = None,
) -> dict:
    """
    Executa o pipeline de matching para um único artigo.

    Fluxo:
    1. Pré-processamento (normalização + separação sigla/nome)
    2. Busca exata por sigla e nome
    3. Se não encontrou: fuzzy matching

    O resultado inclui sempre ``qualis_candidatos`` (top-3 do fuzzy) para
    rastreabilidade, mesmo nos casos de match exato.

    Parameters
    ----------
    nome_conferencia:
        Valor bruto do campo ``nome_conferencia``.
    ano:
        Ano de publicação.
    sigla_conferencia:
        Valor bruto do campo ``sigla_conferencia`` (pode ser None).
    db:
        Instância QualisDB (usa singleton se None).

    Returns
    -------
    dict
        Dicionário com as chaves de saída do pipeline:
        - qualis_estrato, qualis_nome_oficial, qualis_quadrienio
        - qualis_score_fuzzy, qualis_status
        - qualis_candidatos  (JSON string)
        - qualis_obs
        - _pre  (dict interno com dados do pré-processamento — usado pelo LLM)
        - _candidatos_lista  (lista interna — usada pelo LLM)
    """
    if db is None:
        db = get_db()

    try:
        ano = int(ano)
    except (TypeError, ValueError):
        ano = 0

    # 1. Pré-processamento
    pre = preprocessar_linha(nome_conferencia, sigla_conferencia)
    pre["ano"] = ano
    nome_norm = pre["nome_norm"]
    siglas_norm = {
        normalizar(sigla)
        for sigla in pre.get("siglas_candidatas", [])
        if normalizar(sigla)
    }
    acr_nome = extrair_acronimo(nome_norm)

    logger.debug(
        "match | nome_norm=%r  sigla_norm=%r  ano=%s",
        nome_norm,
        sorted(siglas_norm),
        ano,
    )

    # Calcular fuzzy candidatos sempre (para rastreabilidade e uso pelo LLM)
    if ano <= 0 or (not nome_norm and not siglas_norm):
        motivo = "ano_invalido" if ano <= 0 else "nome_e_sigla_vazios"
        return _resultado(
            status=STATUS_REVISAO_MANUAL,
            candidatos=[],
            pre=pre,
            observacoes=[motivo],
        )

    candidatos = _busca_fuzzy(nome_norm, siglas_norm, acr_nome, db, ano)
    score_top = candidatos[0]["score"] if candidatos else 0.0
    score_segundo = candidatos[1]["score"] if len(candidatos) > 1 else 0.0
    margem = round(score_top - score_segundo, 1)

    # 2. Busca exata
    exato, conflito_exato = _buscar_exato(pre, db, ano)

    # Flag de diferença de estrato entre quadriênios
    obs_parts: list[str] = []
    if exato and exato.get("extrapolado"):
        obs_parts.append("extrapolado")
    sigla_observada = exato.get("sigla") if exato else pre.get("sigla_original")
    if sigla_observada:
        ambos = db.estrato_em_ambos_quadrienios(sigla_observada)
        if ambos and len(set(ambos.values())) > 1:
            detalhes = "; ".join(f"{q}={e}" for q, e in sorted(ambos.items()))
            obs_parts.append(f"estrato_diferente_entre_quadrienios: {detalhes}")

    if conflito_exato:
        obs_parts.append(conflito_exato)
        return _resultado(
            status=STATUS_REVISAO_MANUAL,
            candidatos=candidatos,
            pre=pre,
            score=score_top,
            margem=margem,
            observacoes=obs_parts,
            precisa_llm=bool(candidatos),
        )

    if exato:
        logger.info(
            "match EXATO | sigla=%r  estrato=%s  quadrienio=%s",
            exato["sigla"],
            exato["estrato"],
            exato["quadrienio"],
        )
        is_alt = bool(exato.get("extrapolado"))
        if is_alt:
            obs_parts.append("periodo_incompativel_requer_override")
        return _resultado(
            status=STATUS_REVISAO_MANUAL if is_alt else STATUS_EXATO,
            candidatos=candidatos,
            pre=pre,
            estrato=exato["estrato"],
            sigla=exato["sigla"],
            nome=exato["nome"],
            quadrienio=exato["quadrienio"],
            evento_id=exato.get("qualis_evento_id"),
            registro_id=exato.get("qualis_registro_id"),
            score=100.0,
            margem=margem,
            observacoes=obs_parts,
        )

    # 3. Fuzzy — aceitar somente com sinais textuais e estruturais coerentes.
    tipo_query = _tipo_evento(nome_norm)
    tipo_candidato = _tipo_evento(candidatos[0]["nome"].lower()) if candidatos else set()
    tipo_incompativel = bool(tipo_query and tipo_candidato and not (tipo_query & tipo_candidato))
    if tipo_incompativel:
        obs_parts.append("tipo_evento_incompativel")
    if score_top >= THRESHOLD_AUTO and margem >= THRESHOLD_AUTO_MARGIN and not tipo_incompativel:
        melhor = candidatos[0]
        logger.info(
            "match AUTO_FUZZY | score=%.1f  sigla=%r  estrato=%s",
            score_top,
            melhor["sigla"],
            melhor["estrato"],
        )
        if melhor.get("extrapolado") or (exato and exato.get("extrapolado")):
            obs_parts.append("extrapolado")
        return _resultado(
            status=STATUS_AUTO_FUZZY,
            candidatos=candidatos,
            pre=pre,
            estrato=melhor["estrato"],
            sigla=melhor["sigla"],
            nome=melhor["nome"],
            quadrienio=melhor["quadrienio"],
            evento_id=melhor.get("qualis_evento_id"),
            registro_id=melhor.get("qualis_registro_id"),
            score=score_top,
            margem=margem,
            observacoes=obs_parts,
        )

    # Score < THRESHOLD_AUTO → candidatos ruins ou precisa de LLM
    if score_top < THRESHOLD_CANDIDATOS_RUINS:
        # Candidatos com score tão baixo são apenas ruído do token_sort_ratio.
        # Não adianta chamar o LLM — os candidatos não são semânticamente relevantes.
        logger.info(
            "match SEM_CANDIDATOS | score=%.1f < %d → direto para revisão",
            score_top,
            THRESHOLD_CANDIDATOS_RUINS,
        )
        obs_parts.append(
            f"score_abaixo_minimo:{score_top}<{THRESHOLD_CANDIDATOS_RUINS}"
        )
        return _resultado(
            status=STATUS_REVISAO_MANUAL,
            candidatos=candidatos,
            pre=pre,
            score=score_top,
            margem=margem,
            observacoes=obs_parts,
        )

    # Score entre THRESHOLD_CANDIDATOS_RUINS e THRESHOLD_AUTO → encaminhar para LLM
    logger.info(
        "match FUZZY_PENDENTE | score=%.1f → encaminhar para LLM",
        score_top,
    )
    if score_top >= THRESHOLD_AUTO and margem < THRESHOLD_AUTO_MARGIN:
        obs_parts.append(
            f"margem_insuficiente:{margem}<{THRESHOLD_AUTO_MARGIN}"
        )
    else:
        obs_parts.append(f"score_intermediario:{score_top}<{THRESHOLD_AUTO}")
    return _resultado(
        status=STATUS_REVISAO_MANUAL,
        candidatos=candidatos,
        pre=pre,
        score=score_top,
        margem=margem,
        observacoes=obs_parts,
        precisa_llm=True,
    )
