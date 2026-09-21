"""
config.py — AUTOMATSUO V3
Configurações centrais do sistema.
"""

from pathlib import Path

# ─────────────────────────────────────────────
#  DIRETÓRIOS
# ─────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.resolve()
ESTADO_DIR  = BASE_DIR / "estado"
LOGS_DIR    = BASE_DIR / "logs"
ESTADO_FILE = ESTADO_DIR / "estado.json"

ESTADO_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
#  VERSÃO
# ─────────────────────────────────────────────
VERSAO = "3.0.1"
NOME   = "AUTOMATSUO V3"

# ─────────────────────────────────────────────
#  TÍTULOS BAAN (detecção por substring)
# ─────────────────────────────────────────────
TITULO_PRINCIPAL  = "tdpuro401m000"
TITULO_JANELA_DTI = "tkcpdo400s000"
TITULO_POPUP      = "tdinvs0001.o"

# Marcador temporário incluído no título da janela principal enquanto o
# BAAN Fake está "imprimindo". A automação usa isso para saber que ainda
# NÃO é seguro iniciar a próxima caixa (evita digitar DTI em campo errado
# porque o foco ainda não voltou para "Recebimento Específico").
TITULO_OCUPADO = "Imprimindo"

# ─────────────────────────────────────────────
#  DELAYS (segundos)
# Tempos calibrados para o BAAN real.
# Reduzir DELAY_TECLA pode causar perda de keystrokes.
# ─────────────────────────────────────────────
DELAY_TECLA        = 0.04   # pausa entre teclas individuais
DELAY_ACAO         = 0.12   # pausa entre ações
DELAY_JANELA       = 0.45   # aguardar janela abrir/fechar
DELAY_IMPRESSAO    = 0.8    # polling de impressão concluída
DELAY_ENTRE_CAIXAS = 0.6    # pausa entre caixas
TIMEOUT_JANELA     = 12.0   # timeout máximo para janela aparecer
TIMEOUT_IMPRESSAO  = 45.0   # timeout máximo para impressão

# ─────────────────────────────────────────────
#  AUTOMAÇÃO
# ─────────────────────────────────────────────
MODO_TESTE    = False    # True = não pressiona Continue/Ok final
MAX_DTIS_GRID = 128      # capacidade máxima da janela tkcpdo400s000 (8×16)

# ─────────────────────────────────────────────
#  INTERFACE — TEMA ESCURO PREMIUM
# ─────────────────────────────────────────────
COR_BG_DARK      = "#0D1117"
COR_BG_SIDEBAR   = "#161B22"
COR_BG_PANEL     = "#1C2128"
COR_BG_CARD      = "#21262D"
COR_BG_ITEM      = "#2D333B"
COR_BG_ITEM_SEL  = "#1A3A5C"
COR_BG_INPUT     = "#0D1117"
COR_BORDER       = "#30363D"
COR_BORDER_LIGHT = "#484F58"

COR_TEXTO        = "#E6EDF3"
COR_TEXTO_SEC    = "#8B949E"
COR_TEXTO_TERT   = "#6E7681"

COR_AZUL         = "#1F6FEB"
COR_AZUL_HOVER   = "#388BFD"
COR_VERDE        = "#3FB950"
COR_AMARELO      = "#D29922"
COR_VERMELHO     = "#F85149"
COR_LARANJA      = "#DB6D28"
COR_CYAN         = "#39D353"

COR_STATUS_OK    = "#3FB950"
COR_STATUS_WARN  = "#D29922"
COR_STATUS_ERR   = "#F85149"
COR_STATUS_INFO  = "#1F6FEB"
COR_STATUS_IDLE  = "#6E7681"

COR_MULTIPLA_BG  = "#0F1E2E"
COR_MULTIPLA_BRD = "#1F6FEB"

# ─────────────────────────────────────────────
#  FONTES
# ─────────────────────────────────────────────
FONTE_MONO   = ("Consolas", 10)
FONTE_MONO_S = ("Consolas", 9)
FONTE_MONO_B = ("Consolas", 10, "bold")
FONTE_TITULO = ("Segoe UI", 13, "bold")
FONTE_NORMAL = ("Segoe UI", 10)
FONTE_SMALL  = ("Segoe UI", 9)
FONTE_GRANDE = ("Segoe UI", 14, "bold")
