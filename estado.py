"""
estado.py — AUTOMATSUO V3
Gerenciamento de estado persistente com auto-save e retomada de sessão.
"""

import json
import threading
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime
from typing import Optional, List

from config import ESTADO_FILE
from logger import get_logger

log = get_logger("estado")


# ─────────────────────────────────────────────
#  ENUMS
# ─────────────────────────────────────────────
class StatusGlobal(str, Enum):
    OCIOSO      = "ocioso"
    PROCESSANDO = "processando"
    IMPRIMINDO  = "imprimindo"
    PAUSADO     = "pausado"
    CONCLUIDO   = "concluido"
    ERRO        = "erro"
    PARADO      = "parado"


class StatusCaixa(str, Enum):
    PENDENTE   = "pendente"
    ATUAL      = "atual"
    IMPRIMINDO = "imprimindo"
    CONCLUIDA  = "concluida"
    ERRO       = "erro"
    PULADA     = "pulada"


class TipoCaixa(str, Enum):
    SIMPLES  = "SIMPLES"
    MULTIPLA = "MULTIPLA"


# ─────────────────────────────────────────────
#  DATACLASSES
# ─────────────────────────────────────────────
@dataclass
class Caixa:
    caixa:  str
    tipo:   str
    dtis:   List[str]
    status: str = StatusCaixa.PENDENTE.value
    proc:   str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Caixa":
        campos = {"caixa", "tipo", "dtis", "status", "proc"}
        return cls(**{k: v for k, v in d.items() if k in campos})


@dataclass
class EstadoSistema:
    fila:               List[dict] = field(default_factory=list)
    indice_atual:       int        = 0
    status:             str        = StatusGlobal.OCIOSO.value
    etapa:              str        = ""
    caixa_atual:        str        = ""
    dti_atual:          str        = ""
    total:              int        = 0
    concluidas:         int        = 0
    erros:              int        = 0
    puladas:            int        = 0
    arquivo_excel:      str        = ""
    inicio_sessao:      str        = ""
    ultima_atualizacao: str        = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EstadoSistema":
        obj = cls()
        for k, v in d.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj

    @property
    def progresso(self) -> float:
        return (self.concluidas / self.total) if self.total else 0.0

    @property
    def tem_fila(self) -> bool:
        return len(self.fila) > 0


# ─────────────────────────────────────────────
#  GERENCIADOR
# ─────────────────────────────────────────────
class GerenciadorEstado:
    """Thread-safe. Auto-save a cada 5 s quando há mudanças."""

    def __init__(self):
        self._lock   = threading.RLock()
        self._estado = EstadoSistema()
        self._dirty  = False
        self._ativo  = True
        self._iniciar_auto_save()

    # ── Leitura ─────────────────────────────
    @property
    def estado(self) -> EstadoSistema:
        with self._lock:
            return self._estado

    def get_fila(self) -> List[Caixa]:
        with self._lock:
            return [Caixa.from_dict(d) for d in self._estado.fila]

    def get_caixa(self, idx: int) -> Optional[Caixa]:
        with self._lock:
            if 0 <= idx < len(self._estado.fila):
                return Caixa.from_dict(self._estado.fila[idx])
            return None

    # ── Escrita ─────────────────────────────
    def definir_fila(self, caixas: List[Caixa], arquivo: str = "") -> None:
        with self._lock:
            self._estado.fila           = [c.to_dict() for c in caixas]
            self._estado.total          = len(caixas)
            self._estado.indice_atual   = 0
            self._estado.concluidas     = 0
            self._estado.erros          = 0
            self._estado.puladas        = 0
            self._estado.status         = StatusGlobal.OCIOSO.value
            self._estado.caixa_atual    = ""
            self._estado.arquivo_excel  = arquivo
            self._estado.inicio_sessao  = datetime.now().isoformat()
            self._dirty = True
        log.info(f"Fila definida: {len(caixas)} caixas")

    def atualizar_status(self, status: StatusGlobal, etapa: str = "",
                         caixa: str = "", dti: str = "") -> None:
        with self._lock:
            self._estado.status             = status.value
            if etapa: self._estado.etapa    = etapa
            if caixa: self._estado.caixa_atual = caixa
            if dti:   self._estado.dti_atual   = dti
            self._estado.ultima_atualizacao = datetime.now().isoformat()
            self._dirty = True

    def atualizar_status_caixa(self, idx: int, status: StatusCaixa) -> None:
        with self._lock:
            if 0 <= idx < len(self._estado.fila):
                self._estado.fila[idx]["status"] = status.value
                if status == StatusCaixa.CONCLUIDA:
                    self._estado.concluidas += 1
                elif status == StatusCaixa.ERRO:
                    self._estado.erros += 1
                elif status == StatusCaixa.PULADA:
                    self._estado.puladas += 1
                self._dirty = True

    def avancar_indice(self) -> None:
        with self._lock:
            self._estado.indice_atual += 1
            self._dirty = True

    def resetar(self) -> None:
        with self._lock:
            self._estado = EstadoSistema()
            self._dirty  = True
        self.salvar()

    # ── Persistência ────────────────────────
    def salvar(self) -> None:
        with self._lock:
            try:
                ESTADO_FILE.parent.mkdir(parents=True, exist_ok=True)
                tmp = ESTADO_FILE.with_suffix(".tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._estado.to_dict(), f, indent=2, ensure_ascii=False)
                tmp.replace(ESTADO_FILE)
                self._dirty = False
            except Exception as e:
                log.error(f"Falha ao salvar estado: {e}")

    def carregar(self) -> bool:
        try:
            if not ESTADO_FILE.exists():
                return False
            with open(ESTADO_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            with self._lock:
                self._estado = EstadoSistema.from_dict(d)
            log.info(f"Estado carregado: idx={self._estado.indice_atual} "
                     f"total={self._estado.total}")
            return True
        except Exception as e:
            log.warning(f"Não foi possível carregar estado: {e}")
            return False

    def tem_sessao_anterior(self) -> bool:
        try:
            if not ESTADO_FILE.exists():
                return False
            with open(ESTADO_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            total      = d.get("total", 0)
            concluidas = d.get("concluidas", 0)
            status     = d.get("status", "")
            fila       = d.get("fila", [])
            return (
                total > 0
                and len(fila) > 0
                and concluidas < total
                and status not in (StatusGlobal.CONCLUIDO.value,
                                   StatusGlobal.OCIOSO.value)
            )
        except Exception:
            return False

    def parar(self) -> None:
        self._ativo = False
        self.salvar()

    def _iniciar_auto_save(self) -> None:
        def _loop():
            while self._ativo:
                time.sleep(5)
                with self._lock:
                    d = self._dirty
                if d:
                    self.salvar()
        threading.Thread(target=_loop, daemon=True, name="AutoSave").start()


# Singleton global
gerenciador_estado = GerenciadorEstado()
