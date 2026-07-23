"""
Módulo de revisão por LLM para o pipeline QualisLens.

Integra com Ollama local para resolver casos de fuzzy matching ambíguo
(score entre THRESHOLD_LLM e THRESHOLD_AUTO) ou de baixa confiança
(score < THRESHOLD_LLM).

Suporta verificação dupla: quando dois modelos são fornecidos, ambos são
consultados e o resultado é aceito somente se houver concordância. Em caso
de divergência o registro vai para a fila de revisão humana.

Em caso de falha de conexão ou resposta malformada, retorna status LLM_MISS
sem interromper o pipeline.
"""

import json
import logging
from typing import Optional

import requests

from .constants import (
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
    OLLAMA_URL,
    STATUS_LLM_DUPLO_DIVERGE,
    STATUS_LLM_DUPLO_OK,
    STATUS_LLM_LOW_MISS,
    STATUS_LLM_LOW_OK,
    STATUS_LLM_MISS,
    STATUS_LLM_OK,
    THRESHOLD_LLM,
)

logger = logging.getLogger(__name__)

# ── Prompt template ───────────────────────────────────────────────────────────

_PROMPT_TEMPLATE = """\
Você é um especialista em conferências científicas de Computação. \
Identifique a conferência mais provável a partir de um nome escrito \
de forma abreviada, incompleta ou informal.

PASSOS OBRIGATÓRIOS:
1. Expanda o nome escrito usando seu conhecimento de abreviações acadêmicas \
comuns em títulos de conferências de Computação (siglas, pontos, apóstrofos, etc.).

2. Compare o nome expandido SEMANTICAMENTE com cada candidato — não apenas letra a letra.

3. REGRA DE SELEÇÃO: o candidato com maior "similaridade" já foi pré-selecionado \
por um filtro automático. Se após a expansão você reconhecê-lo como correto, escolha-o. \
Só o ignore se o tema for claramente diferente.

4. REGRA DE RECUSA — retorne "escolha": null se:
   - O tema expandido não corresponde ao tema de nenhum dos candidatos
   - A correspondência semântica for fraca em todos os candidatos
   - Você não tiver certeza razoável
   NUNCA escolha apenas porque é o "menos pior".

Nome escrito: "{nome_entrada}"
Título do artigo: "{titulo_artigo}"
Ano do artigo: {ano}

Candidatos:
{candidatos_texto}

Responda APENAS com JSON válido, sem texto extra, sem markdown:
{{
  "escolha": <número 1-N do candidato mais plausível, ou null se nenhum>,
  "confianca": "<alta | media | baixa>",
  "justificativa": "explique qual expansão fez e por que esse candidato"
}}"""


def _formatar_candidatos(candidatos: list[dict]) -> str:
    """
    Formata a lista de candidatos para o prompt da LLM.

    Parameters
    ----------
    candidatos:
        Lista de dicts com sigla, nome, estrato, score.

    Returns
    -------
    str
        Texto numerado, um candidato por linha.
    """
    if not candidatos:
        return "Nenhum candidato disponível."
    linhas = []
    for i, c in enumerate(candidatos, start=1):
        linhas.append(
            f"{i}. {c.get('sigla', '')} — {c['nome']} "
            f"[{c.get('estrato', '?')}] (similaridade: {c['score']}%)"
        )
    return "\n".join(linhas)


def _chamar_ollama(prompt: str, model: str = OLLAMA_MODEL) -> Optional[dict]:
    """
    Chama a API do Ollama com o prompt dado e retorna o JSON parseado.

    Em caso de qualquer erro (conexão, timeout, JSON inválido), retorna None
    sem lançar exceção — o pipeline deve continuar.

    Parameters
    ----------
    prompt:
        Texto do prompt a enviar ao modelo.
    model:
        Nome do modelo Ollama a usar.

    Returns
    -------
    Optional[dict]
        Dicionário com escolha, confianca e justificativa, ou None em falha.
    """
    payload = {
        "model": model,
        "format": "json",
        "stream": False,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        resp = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        parsed = json.loads(content)
        return parsed
    except requests.exceptions.ConnectionError as exc:
        logger.warning("Ollama indisponível (ConnectionError): %s", exc)
    except requests.exceptions.Timeout:
        logger.warning("Ollama timeout após %ds (model=%s)", OLLAMA_TIMEOUT_SECONDS, model)
    except requests.exceptions.HTTPError as exc:
        logger.warning("Ollama HTTP error: %s", exc)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Resposta do Ollama malformada (model=%s): %s", model, exc)
    return None


def _status_a_partir_de_resposta(
    resposta: Optional[dict],
    score_fuzzy: float,
) -> tuple[str, Optional[str]]:
    """
    Determina o status de saída a partir da resposta da LLM e do score fuzzy.

    Regras:
    - score >= THRESHOLD_LLM (60-85): LLM decide
      - LLM achou → LLM_OK
      - LLM não achou → LLM_MISS (revisão humana)
    - score < THRESHOLD_LLM: LLM opina, humano decide sempre
      - LLM achou → LLM_LOW_OK (revisão humana)
      - LLM não achou → LLM_LOW_MISS (revisão humana)

    Parameters
    ----------
    resposta:
        Dict parseado da LLM ou None em falha.
    score_fuzzy:
        Score do top candidato do fuzzy.

    Returns
    -------
    tuple[str, Optional[str]]
        (status, motivo_texto)
    """
    faixa_alta = score_fuzzy >= THRESHOLD_LLM

    if resposta is None:
        motivo = "Ollama indisponível ou resposta inválida"
        status = STATUS_LLM_MISS if faixa_alta else STATUS_LLM_LOW_MISS
        return status, motivo

    escolha = resposta.get("escolha")
    justificativa = resposta.get("justificativa", "")

    if escolha is not None:
        status = STATUS_LLM_OK if faixa_alta else STATUS_LLM_LOW_OK
    else:
        status = STATUS_LLM_MISS if faixa_alta else STATUS_LLM_LOW_MISS

    motivo = justificativa or "(sem justificativa)"
    return status, motivo


def _extrair_candidato(
    resposta: Optional[dict],
    candidatos: list[dict],
) -> tuple[Optional[int], Optional[dict]]:
    """
    Extrai o índice 0-based e o dict do candidato escolhido pela LLM.

    Parameters
    ----------
    resposta:
        Resposta parseada da LLM.
    candidatos:
        Lista de candidatos.

    Returns
    -------
    tuple[Optional[int], Optional[dict]]
        (índice 0-based, dict do candidato) ou (None, None).
    """
    if resposta is None:
        return None, None
    escolha_num = resposta.get("escolha")
    if escolha_num is None:
        return None, None
    try:
        idx = int(escolha_num) - 1
        if 0 <= idx < len(candidatos):
            return idx, candidatos[idx]
    except (ValueError, TypeError):
        logger.warning("LLM retornou escolha inválida: %r", escolha_num)
    return None, None


def _revisar_simples(
    prompt: str,
    candidatos: list[dict],
    score_fuzzy: float,
    nome_entrada: str,
    model: str,
) -> dict:
    """
    Executa revisão com um único modelo Ollama.

    Parameters
    ----------
    prompt:
        Texto completo do prompt.
    candidatos:
        Lista de candidatos fuzzy.
    score_fuzzy:
        Score do melhor candidato.
    nome_entrada:
        Nome original (para log).
    model:
        Nome do modelo Ollama.

    Returns
    -------
    dict
        Resultado com campos qualis_*.
    """
    logger.info("[LLM] Testando modelo '%s' para: %r", model, nome_entrada)
    resposta = _chamar_ollama(prompt, model)
    logger.debug("Resposta Ollama (%s): %s", model, resposta)

    status, motivo = _status_a_partir_de_resposta(resposta, score_fuzzy)
    escolha_idx, melhor = _extrair_candidato(resposta, candidatos)
    confianca_llm = resposta.get("confianca") if resposta else None

    logger.info(
        "[LLM] '%s' [%s] → status=%s  confianca=%s  escolha=%s",
        nome_entrada, model, status, confianca_llm, escolha_idx,
    )

    return {
        "qualis_estrato": melhor.get("estrato") if melhor else None,
        "qualis_sigla": melhor.get("sigla") if melhor else None,
        "qualis_nome_oficial": melhor.get("nome") if melhor else None,
        "qualis_quadrienio": melhor.get("quadrienio") if melhor else None,
        "qualis_score_llm": confianca_llm,
        "qualis_status": status,
        "qualis_llm_motivo": motivo,
        "llm_m1_modelo": model,
        "llm_m1_confianca": confianca_llm,
        "llm_m1_escolheu": "Sim" if escolha_idx is not None else "Não",
        "llm_m2_modelo": None,
        "llm_m2_confianca": None,
        "llm_m2_escolheu": None,
        "_llm_escolha_idx": escolha_idx,
    }


def _revisar_duplo(
    prompt: str,
    candidatos: list[dict],
    score_fuzzy: float,
    nome_entrada: str,
    modelos: list[str],
) -> dict:
    """
    Executa revisão com dois modelos e compara as respostas.

    Lógica de consenso:
    - Ambos escolhem o MESMO candidato → LLM_DUPLO_OK (score alto) ou LLM_LOW_OK (score baixo)
    - Ambos recusam (null) → LLM_MISS / LLM_LOW_MISS conforme score
    - Divergem (escolhas diferentes) → LLM_DUPLO_DIVERGE (→ revisão humana)

    Parameters
    ----------
    prompt:
        Texto completo do prompt.
    candidatos:
        Lista de candidatos fuzzy.
    score_fuzzy:
        Score do melhor candidato.
    nome_entrada:
        Nome original (para log).
    modelos:
        Lista com exatamente 2 nomes de modelo.

    Returns
    -------
    dict
        Resultado com campos qualis_*.
    """
    model_a, model_b = modelos[0], modelos[1]
    logger.info("[LLM duplo] Testando modelo 1/2: '%s' para: %r", model_a, nome_entrada)
    resp_a = _chamar_ollama(prompt, model_a)
    logger.info("[LLM duplo] Testando modelo 2/2: '%s' para: %r", model_b, nome_entrada)
    resp_b = _chamar_ollama(prompt, model_b)

    idx_a, melhor_a = _extrair_candidato(resp_a, candidatos)
    idx_b, _ = _extrair_candidato(resp_b, candidatos)

    just_a = (resp_a.get("justificativa", "") if resp_a else "")
    just_b = (resp_b.get("justificativa", "") if resp_b else "")
    conf_a = resp_a.get("confianca") if resp_a else None
    conf_b = resp_b.get("confianca") if resp_b else None
    escolha_a, escolha_b = idx_a, idx_b  # guarda escolha original antes da lógica de consenso

    faixa_alta = score_fuzzy >= THRESHOLD_LLM

    if idx_a is not None and idx_a == idx_b:
        # Consenso
        status = STATUS_LLM_DUPLO_OK if faixa_alta else STATUS_LLM_LOW_OK
        motivo = f"[{model_a}+{model_b} concordam] {just_a}"
        melhor = melhor_a
        confianca = conf_a

    elif idx_a is None and idx_b is None:
        # Ambos recusaram
        status = STATUS_LLM_MISS if faixa_alta else STATUS_LLM_LOW_MISS
        motivo = f"[{model_a}+{model_b} sem escolha] {(just_a or just_b).strip()}"
        melhor = None
        confianca = None

    else:
        # Divergência
        desc_a = f"{model_a}→{idx_a + 1 if idx_a is not None else 'null'}"
        desc_b = f"{model_b}→{idx_b + 1 if idx_b is not None else 'null'}"
        status = STATUS_LLM_DUPLO_DIVERGE
        motivo = f"Modelos divergem: {desc_a} vs {desc_b}. {just_a} | {just_b}"
        melhor = None
        confianca = "baixa"
        idx_a = None  # não aceitar nenhum

    logger.info(
        "[LLM duplo] '%s': %s + %s → status=%s",
        nome_entrada, model_a, model_b, status,
    )

    return {
        "qualis_estrato": melhor.get("estrato") if melhor else None,
        "qualis_sigla": melhor.get("sigla") if melhor else None,
        "qualis_nome_oficial": melhor.get("nome") if melhor else None,
        "qualis_quadrienio": melhor.get("quadrienio") if melhor else None,
        "qualis_score_llm": confianca,
        "qualis_status": status,
        "qualis_llm_motivo": motivo,
        "llm_m1_modelo": model_a,
        "llm_m1_confianca": conf_a,
        "llm_m1_escolheu": "Sim" if escolha_a is not None else "Não",
        "llm_m2_modelo": model_b,
        "llm_m2_confianca": conf_b,
        "llm_m2_escolheu": "Sim" if escolha_b is not None else "Não",
        "_llm_escolha_idx": idx_a,
    }


def revisar(
    nome_entrada: str,
    ano: int,
    candidatos: list[dict],
    score_fuzzy: float,
    modelos: Optional[list[str]] = None,
    titulo_artigo: Optional[str] = None,
) -> dict:
    """
    Envia os candidatos fuzzy para revisão pela LLM e retorna o resultado
    com status, estrato e motivo preenchidos.

    Se ``modelos`` tiver dois elementos, usa verificação dupla: ambos os
    modelos são consultados e o resultado só é aceito com consenso.

    Parameters
    ----------
    nome_entrada:
        Nome original da conferência (campo livre do pesquisador).
    ano:
        Ano de publicação.
    candidatos:
        Lista de top-N candidatos do fuzzy (cada um com sigla, nome, estrato, score).
    score_fuzzy:
        Score do melhor candidato fuzzy.
    modelos:
        Lista com 1 ou 2 nomes de modelos Ollama.
        Deve conter 1 ou 2 modelos. Sem uma lista explícita, nenhuma chamada é
        feita e a função lança ``ValueError``.
    titulo_artigo:
        Título do artigo — usado como contexto temático para ajudar o LLM
        a verificar se o candidato escolhido é compatível com o tema.

    Returns
    -------
    dict
        Dicionário com:
        - qualis_estrato, qualis_nome_oficial, qualis_quadrienio
        - qualis_score_llm  (confianca: "alta" | "media" | "baixa" | None)
        - qualis_status
        - qualis_llm_motivo
        - _llm_escolha_idx  (índice 0-based na lista de candidatos, ou None)
    """
    if not modelos:
        raise ValueError("A revisão por LLM exige ao menos um modelo explícito")

    candidatos_texto = _formatar_candidatos(candidatos)
    prompt = _PROMPT_TEMPLATE.format(
        nome_entrada=nome_entrada,
        titulo_artigo=titulo_artigo or "não informado",
        ano=ano,
        candidatos_texto=candidatos_texto,
    )

    modelos_efetivos = modelos

    if len(modelos_efetivos) >= 2:
        return _revisar_duplo(prompt, candidatos, score_fuzzy, nome_entrada, modelos_efetivos[:2])
    return _revisar_simples(prompt, candidatos, score_fuzzy, nome_entrada, modelos_efetivos[0])
