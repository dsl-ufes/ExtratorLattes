"""
Módulo de pré-processamento de texto para o pipeline QualisLens.

Responsável por:
- Normalização de texto (lowercase, remoção de pontuação, acentos)
- Expansão de abreviações acadêmicas comuns
- Remoção de stopwords irrelevantes
- Separação de sigla + nome quando escritos juntos (ex: "SBRC - Simpósio...")
"""

import html
import re
from typing import Optional

from .utils import strip_accents as _strip_accents

# ── Mapa de abreviações → forma completa ─────────────────────────────────────
# Ordenado do mais longo para o mais curto para evitar substituições parciais.
_ABREVIACOES: list[tuple[str, str]] = [
    (r"\bint['’]?l\b", "international"),
    (r"\bconf\b", "conference"),
    (r"\bsymp\b", "symposium"),
    (r"\bwks(?:p|hp|h)\b", "workshop"),
    # (r"\bc\b", "conference"),        # "C." isolado (ex: "Int'l C. on X")
    # (r"\bsymp\b", "symposium"),
    # (r"\beng\b", "engineering"),
    # (r"\bwksp\b", "workshop"),
    # (r"\bwkshp\b", "workshop"),
    # (r"\bwksh\b", "workshop"),
    # (r"\bproc\b", "processing"),
    # (r"\bj\b", "journal"),           # apenas quando isolado
    # (r"\btrans\b", "transactions"),
    # (r"\bsyst\b", "systems"),
    # (r"\bsys\b", "systems"),
    # (r"\bcomput\b", "computing"),
    # (r"\bcomp\b", "computing"),      # "Comp." (ex: "Theory of Comp.")
    # (r"\bcomm\b", "communications"),
    # (r"\bann\b", "annual"),
    # (r"\bintell\b", "intelligent"),
    # (r"\bappl\b", "applications"),
    # (r"\bmanag\b", "management"),
    # (r"\bnet\b", "network"),
    # (r"\bnets\b", "networks"),
    # (r"\barch\b", "architecture"),
    # (r"\barchit\b", "architecture"),
    # (r"\bdist\b", "distributed"),
    # (r"\bsec\b", "security"),
    # (r"\binfo\b", "information"),
    # (r"\bprog\b", "programming"),
    # (r"\bautom\b", "automation"),
    # (r"\btech\b", "technology"),
    # (r"\btechnol\b", "technology"),
    # (r"\badv\b", "advances"),
    # (r"\bres\b", "research"),
    # # Adicionais
    # (r"\bdes\b", "design"),
    # (r"\bsw\b", "software"),
    # (r"\bemb\b", "embedded"),
    # (r"\balg\b", "algorithms"),
    # (r"\bvis\b", "vision"),
    # (r"\bviz\b", "visualization"),
    # (r"\bsig\b", "signal"),
    # (r"\bsimul\b", "simulation"),
    # (r"\bsim\b", "simulation"),
    # (r"\bmod\b", "modeling"),
    # (r"\bpract\b", "practical"),
    # (r"\bparal\b", "parallel"),
    # (r"\bcap\b", "capability"),
    # (r"\bdet\b", "determination"),
    # (r"\bimpr\b", "improvement"),
    # (r"\bimag\b", "imaging"),
    # (r"\brecog\b", "recognition"),
    # (r"\bdetect\b", "detection"),
]

# Stopwords a remover (palavras isoladas apenas)
_STOPWORDS: frozenset[str] = frozenset({
    "on", "of", "the", "in", "and", "for", "a", "an",
    "with", "to", "at", "by", "from", "proceedings", "anais",
})

# Equivalent Portuguese and English structural terms must compare alike.
_TIPOS_EVENTO = ((r"\bconferencia\b", "conference"), (r"\bsimposio\b", "symposium"),
                 (r"\bcongresso\b", "congress"), (r"\bencontro\b", "meeting"),
                 (r"\boficina\b", "workshop"))

# Stopwords extras para extracão de acrônimo (organizadoras não entram no acrônimo)
_STOPWORDS_ACR: frozenset[str] = _STOPWORDS | frozenset({"ieee", "acm", "springer", "elsevier"})

# Padrão para detectar "SIGLA - Nome completo" ou "SIGLA: Nome completo"
# Captura siglas de 2-8 letras maiúsculas/dígitos seguidas de separador
_RE_SIGLA_NOME = re.compile(
    r"^([A-Za-z][A-Za-z0-9+./-]{1,14})(?:\s+['’]?\d{2,4})?\s*[-–:]\s*(.+)$",
    re.UNICODE,
)

_SIGLA_IGNORAR: frozenset[str] = frozenset({
    "ACM", "IEEE", "IFIP", "SBC", "USENIX", "SPRINGER",
    "INTERNATIONAL", "NATIONAL", "BRAZILIAN", "CONFERENCE", "SYMPOSIUM",
    "WORKSHOP", "CONGRESS", "CONGRESSO", "SIMPOSIO", "SEMINARIO",
    "ANNUAL", "ANNAIS", "PROCEEDINGS", "THE", "AND", "ON", "OF",
})
_RE_ANO = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_RE_ROMANO = re.compile(r"^[IVXLCDM]+$")
_RE_TOKEN_SIGLA = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-+./'][A-Za-z0-9]+)*")


def _limpar_texto_bruto(texto: str) -> str:
    """Remove entidades HTML e marcadores comuns de texto mal decodificado."""
    resultado = html.unescape(texto)
    resultado = resultado.replace("ï¿½", "").replace("�", "")
    return resultado


def _normalizar_sigla_candidata(token: str) -> Optional[str]:
    token = token.strip(" .,:;()[]{}")
    token = re.sub(r"['’](?:19|20)?\d{2}$", "", token)
    token = re.sub(r"[-_/]?(?:19|20)\d{2}$", "", token)
    token = re.sub(r"(?<=[A-Za-z])(?:19|20)\d{2}$", "", token)
    token = token.strip("-_/+'.")
    if not (2 <= len(token) <= 16):
        return None

    upper = _strip_accents(token).upper()
    if upper in _SIGLA_IGNORAR or upper.isdigit() or _RE_ROMANO.fullmatch(upper):
        return None

    # Um candidato deve parecer sigla: caixa alta, camel case, dígitos ou sinais.
    letras_maiusculas = sum(1 for char in token if char.isupper())
    parece_sigla = (
        token.upper() == token
        or letras_maiusculas >= 2
        or any(char.isdigit() for char in token)
        or any(char in "+-/" for char in token)
    )
    return token if parece_sigla else None


def extrair_siglas_candidatas(texto: str) -> list[str]:
    """Extrai siglas explícitas em prefixos, parênteses e no corpo do evento."""
    if not texto or not isinstance(texto, str):
        return []

    texto = _limpar_texto_bruto(texto)
    trechos: list[str] = []

    prefixo = _RE_SIGLA_NOME.match(texto.strip())
    if prefixo:
        trechos.append(prefixo.group(1))

    trechos.extend(re.findall(r"\(([^()]*)\)", texto))
    trechos.append(texto)

    resultado: list[str] = []
    vistos: set[str] = set()
    for trecho in trechos:
        for token in _RE_TOKEN_SIGLA.findall(trecho):
            candidato = _normalizar_sigla_candidata(token)
            if not candidato:
                continue
            chave = candidato.casefold()
            if chave not in vistos:
                vistos.add(chave)
                resultado.append(candidato)
    return resultado


def extrair_siglas_fortes(texto: str) -> list[str]:
    """Extrai siglas em posições que as identificam com pouca ambiguidade."""
    if not texto or not isinstance(texto, str):
        return []

    texto = _limpar_texto_bruto(texto).strip()
    trechos: list[str] = []
    prefixo = _RE_SIGLA_NOME.match(texto)
    if prefixo:
        # A normal title-case word before '-' is a name, not evidence of acronym.
        token = prefixo.group(1)
        if token.upper() == token or any(ch.isdigit() for ch in token):
            trechos.append(token)
    # Parentheses are candidates only.  They become strong only for upper-case
    # acronym-only input; a surrounding conflicting name is checked by matcher.
    for parenthetical in re.findall(r"\(([^()]*)\)", texto):
        if parenthetical.strip().upper() == parenthetical.strip():
            trechos.append(parenthetical)

    # Formatos comuns do Lattes: "WebMedia 2010" e ". AINA 2008."
    sufixo = re.search(
        r"(?:^|[.;])\s*([A-Za-z][A-Za-z0-9+./-]{1,14})"
        r"\s+['’]?(?:19|20)?\d{2,4}\s*\.?$",
        texto,
    )
    if sufixo:
        token = sufixo.group(1)
        if token.upper() == token or any(ch.isdigit() for ch in token):
            trechos.append(token)

    resultado: list[str] = []
    vistos: set[str] = set()
    for trecho in trechos:
        for token in _RE_TOKEN_SIGLA.findall(trecho):
            candidato = _normalizar_sigla_candidata(token)
            if candidato and candidato.casefold() not in vistos:
                vistos.add(candidato.casefold())
                resultado.append(candidato)
    return resultado


def extrair_acronimo(texto: str) -> str:
    """
    Gera acrônimo a partir do nome de uma conferência.

    Usa a primeira letra de cada token significativo (não-stopword).
    Opera sobre o texto bruto (apenas lowercase + sem acentos) para preservar
    os tokens originais antes da expansão de abreviações.

    Exemplos
    --------
    ``"International Conference on Computer Vision"`` → ``"ICCV"``
    ``"ACM Symposium on Theory of Computing"``         → ``"STC"``

    Parameters
    ----------
    texto:
        Nome da conferência em formato livre.

    Returns
    -------
    str
        Acrônimo em maiúsculas.
    """
    if not texto or not isinstance(texto, str):
        return ""
    clean = _strip_accents(texto.lower())
    tokens = re.findall(r"[a-z0-9]+", clean)
    return "".join(t[0] for t in tokens if t and t not in _STOPWORDS_ACR).upper()


def separar_sigla_nome(texto: str) -> tuple[Optional[str], str]:
    """
    Separa sigla e nome quando escritos juntos no campo `nome_conferencia`.

    Exemplos:
    - ``"SBRC - Simpósio Brasileiro de Redes"`` → ``("SBRC", "Simpósio Brasileiro de Redes")``
    - ``"ICSE: International Conf. on Software Eng."`` → ``("ICSE", "International Conf. on Software Eng.")``
    - ``"International Conference on X"`` → ``(None, "International Conference on X")``

    Parameters
    ----------
    texto:
        Valor bruto do campo `nome_conferencia`.

    Returns
    -------
    tuple[Optional[str], str]
        (sigla, nome) — sigla é None quando não detectada no texto.
    """
    if not texto or not isinstance(texto, str):
        return None, str(texto) if texto else ""

    texto = _limpar_texto_bruto(texto).strip()
    m = _RE_SIGLA_NOME.match(texto)
    if m:
        sigla = m.group(1).strip()
        nome = m.group(2).strip()
        return sigla, nome
    return None, texto


def normalizar(texto: str) -> str:
    """
    Aplica o pipeline completo de normalização a um nome de conferência.

    Etapas (nesta ordem):
    1. Lowercase
    2. Remoção de acentos
    3. Expansão de abreviações comuns
    4. Remoção de pontuação e caracteres especiais
    5. Remoção de stopwords isoladas
    6. Colapso de espaços extras

    Parameters
    ----------
    texto:
        Nome da conferência em formato livre.

    Returns
    -------
    str
        Texto normalizado.
    """
    if not texto or not isinstance(texto, str):
        return ""

    resultado = _limpar_texto_bruto(texto).lower().strip()
    resultado = _strip_accents(resultado)

    # Números de edição e anos não identificam a série do evento.
    resultado = _RE_ANO.sub(" ", resultado)
    resultado = re.sub(r"\b\d+(?:st|nd|rd|th|o|a)?\b", " ", resultado)
    resultado = re.sub(r"\b[ivxlcdm]{2,}\b", " ", resultado)

    # Expandir abreviações antes de remover pontuação
    for padrao, expansao in _ABREVIACOES:
        resultado = re.sub(padrao, expansao, resultado)
    for padrao, expansao in _TIPOS_EVENTO:
        resultado = re.sub(padrao, expansao, resultado)

    # Remover pontuação (exceto espaços)
    resultado = re.sub(r"[^\w\s]", " ", resultado)

    # Remover stopwords isoladas
    tokens = resultado.split()
    tokens = [t for t in tokens if t not in _STOPWORDS]
    resultado = " ".join(tokens)

    # Colapsar espaços
    resultado = re.sub(r"\s+", " ", resultado).strip()
    return resultado


def preprocessar_linha(
    nome_conferencia: str,
    sigla_entrada: Optional[str] = None,
) -> dict:
    """
    Pré-processa uma linha de entrada, extraindo e normalizando sigla e nome.

    Se `sigla_entrada` for fornecida, ela é usada diretamente (normalizada).
    Caso contrário, tenta extrair a sigla do próprio campo `nome_conferencia`
    via ``separar_sigla_nome``.

    Parameters
    ----------
    nome_conferencia:
        Valor bruto do campo `nome_conferencia` da planilha de entrada.
    sigla_entrada:
        Valor bruto do campo `sigla_conferencia` (pode ser None ou vazio).

    Returns
    -------
    dict
        Dicionário com as chaves:
        - ``sigla_informada``: valor bruto de ``sigla_entrada``, sem fallback
          por extração; usado para reproduzir a identidade do input reportado
          (``qualis_input_id``) de forma estável entre chamadas
        - ``sigla_original``: sigla fornecida pelo pesquisador (ou extraída)
        - ``nome_original``: nome limpo (sem sigla prefixada)
        - ``sigla_norm``: sigla normalizada para busca
        - ``nome_norm``: nome normalizado para busca
    """
    nome_conferencia = _limpar_texto_bruto(str(nome_conferencia or ""))

    # Separar sigla embutida no campo nome (ex: "SBRC - Simpósio...")
    sigla_extraida, nome_limpo = separar_sigla_nome(nome_conferencia)

    # Prioridade: sigla_entrada > sigla extraída do nome
    sigla_original: Optional[str]
    if sigla_entrada and str(sigla_entrada).strip():
        sigla_original = str(sigla_entrada).strip()
    else:
        sigla_original = sigla_extraida

    siglas_candidatas = extrair_siglas_candidatas(nome_conferencia)
    siglas_fortes = extrair_siglas_fortes(nome_conferencia)
    if sigla_original:
        siglas_candidatas = [sigla_original] + [
            item for item in siglas_candidatas
            if item.casefold() != sigla_original.casefold()
        ]
        siglas_fortes = [sigla_original] + [
            item for item in siglas_fortes
            if item.casefold() != sigla_original.casefold()
        ]

    nome_para_match = nome_limpo
    for sigla in siglas_fortes:
        nome_para_match = re.sub(
            rf"(?<!\w){re.escape(sigla)}(?!\w)",
            " ",
            nome_para_match,
            flags=re.IGNORECASE,
        )

    return {
        "venue_informado": nome_conferencia,
        "sigla_informada": sigla_entrada,
        "sigla_original": sigla_original,
        "siglas_candidatas": siglas_candidatas,
        "siglas_fortes": siglas_fortes,
        "nome_original": nome_limpo,
        "sigla_norm": normalizar(sigla_original) if sigla_original else None,
        "nome_norm": normalizar(nome_para_match),
    }
