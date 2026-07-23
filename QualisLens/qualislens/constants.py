"""
Constantes globais do pipeline QualisLens.
Ajuste os thresholds empiricamente em uma amostra rotulada antes de rodar no dataset completo.
"""

# ── Thresholds de confiança ────────────────────────────────────────────────────
THRESHOLD_AUTO: int = 88
# Além do score mínimo, um match fuzzy só é automático quando o primeiro
# candidato abre esta margem sobre o segundo. Empates e quase-empates vão para
# revisão, mesmo que o score absoluto seja alto.
THRESHOLD_AUTO_MARGIN: int = 8
THRESHOLD_LLM: int = 60
THRESHOLD_CANDIDATOS_RUINS: int = 68
# score do melhor candidato abaixo deste valor → candidatos são provavelmente ruído
# do token_sort_ratio, não há sentido chamar o LLM; vai direto para LLM_MISS/revisão

# ── Modelo LLM ────────────────────────────────────────────────────────────────
OLLAMA_URL: str = "http://localhost:11434/api/chat"
OLLAMA_MODEL: str = "llama3.2:3b"
OLLAMA_TIMEOUT_SECONDS: int = 60

# ── Quadriênios disponíveis ───────────────────────────────────────────────────
QUADRIENIO_ANTIGO: str = "2017-2020"
QUADRIENIO_RECENTE: str = "2021-2024"
ANO_INICIO_ANTIGO: int = 2017
ANO_FIM_ANTIGO: int = 2020
ANO_INICIO_RECENTE: int = 2021
ANO_FIM_RECENTE: int = 2024

# ── Paths padrão das bases ────────────────────────────────────────────────────
PATH_BASE_2017: str = "base/qualis_2017_2020.csv"
PATH_BASE_2025: str = "base/qualis_2021_2024.csv"

# ── Status de saída possíveis ─────────────────────────────────────────────────
STATUS_EXATO: str = "EXATO"
STATUS_AUTO_FUZZY: str = "AUTO_FUZZY"
STATUS_LLM_OK: str = "LLM_OK"
STATUS_LLM_MISS: str = "LLM_MISS"
STATUS_LLM_LOW_OK: str = "LLM_LOW_OK"
STATUS_LLM_LOW_MISS: str = "LLM_LOW_MISS"
STATUS_MANUAL_OK: str = "MANUAL_OK"
STATUS_MANUAL_MISS: str = "MANUAL_MISS"
STATUS_LLM_DUPLO_OK: str = "LLM_DUPLO_OK"         # ambos modelos concordam → aceito
STATUS_LLM_DUPLO_DIVERGE: str = "LLM_DUPLO_DIVERGE"  # modelos divergem → revisão humana
STATUS_REVISAO_MANUAL: str = "REVISAO_MANUAL"

# Statuses que requerem revisão humana
STATUSES_REVISAO: list[str] = [
    STATUS_REVISAO_MANUAL,
    STATUS_LLM_MISS,
    STATUS_LLM_LOW_OK,
    STATUS_LLM_LOW_MISS,
    STATUS_LLM_DUPLO_DIVERGE,
]

# ── Número de candidatos retornados pelo fuzzy ────────────────────────────────
TOP_N_CANDIDATOS: int = 5

# Identifica as regras que geraram ``qualis_input_id``.  Altere quando uma
# mudança de política puder alterar uma decisão humana já registrada.
POLITICA_VERSAO: str = "2"
