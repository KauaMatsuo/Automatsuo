"""
logger.py — AUTOMATSUO V3
Sistema de logs com fila para interface, arquivo diário e nível SUCESSO.
"""

import logging
import queue
import threading
from datetime import datetime
from pathlib import Path

from config import LOGS_DIR

# Fila global consumida pela interface em tempo real
log_queue: queue.Queue = queue.Queue(maxsize=5000)

# Nível customizado
SUCESSO = 25
logging.addLevelName(SUCESSO, "SUCESSO")


def _sucesso(self, msg, *args, **kw):
    if self.isEnabledFor(SUCESSO):
        self._log(SUCESSO, msg, args, **kw)


logging.Logger.sucesso = _sucesso


# ─────────────────────────────────────────────
#  HANDLER → FILA (para a interface)
# ─────────────────────────────────────────────
class _FilaHandler(logging.Handler):
    _MAPA = {
        "DEBUG":    "cinza",
        "INFO":     "azul",
        "SUCESSO":  "verde",
        "WARNING":  "amarelo",
        "ERROR":    "vermelho",
        "CRITICAL": "vermelho",
    }

    def emit(self, record):
        try:
            msg = self.format(record)
            cor = self._MAPA.get(record.levelname, "branco")
            log_queue.put_nowait({"texto": msg, "cor": cor, "nivel": record.levelname})
        except Exception:
            pass


# ─────────────────────────────────────────────
#  HANDLER → ARQUIVO (rotação diária)
# ─────────────────────────────────────────────
class _ArquivoHandler(logging.FileHandler):
    def __init__(self):
        hoje = datetime.now().strftime("%Y-%m-%d")
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        super().__init__(str(LOGS_DIR / f"{hoje}.log"), encoding="utf-8")
        self.setFormatter(logging.Formatter(
            "%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        ))


# ─────────────────────────────────────────────
#  CONFIGURAÇÃO ÚNICA
# ─────────────────────────────────────────────
_configurado = False
_cfg_lock    = threading.Lock()
_FMT         = logging.Formatter(
    "%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


def configurar_logging(nivel: int = logging.DEBUG) -> None:
    global _configurado
    with _cfg_lock:
        if _configurado:
            return
        _configurado = True

    fh = _FilaHandler()
    fh.setFormatter(_FMT)
    fh.setLevel(logging.DEBUG)

    root = logging.getLogger()
    root.setLevel(nivel)
    root.addHandler(fh)

    try:
        ah = _ArquivoHandler()
        ah.setLevel(logging.DEBUG)
        root.addHandler(ah)
    except Exception:
        pass


def get_logger(nome: str) -> logging.Logger:
    configurar_logging()
    return logging.getLogger(f"AUTOMATSUO.{nome}")
