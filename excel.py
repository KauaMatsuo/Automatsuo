"""
excel.py — AUTOMATSUO V3
Leitura e agrupamento de planilhas BAAN "IMPRIMIR CAIXAS DE IMPORTAÇÃO".

Formato real detectado (validado contra 4 arquivos reais):
  Col 0 (A) — Caixa No.         ex: A001KB68360404
  Col 1 (B) — Proc.Importação   ex: IS0238/26
  Col 2 (C) — N.F.              (ignorado)
  Col 3 (D) — D.T.I.            ex: 547821
  Col 4+    — Ítem, Qtde, etc.  (ignorados)

Resultados validados:
  Uchimura (1953 itens):  128 caixas (108 simples, 20 múltiplas)
  KLTD (83 itens):         62 caixas  (58 simples,  4 múltiplas)
  KLG (21 itens):          12 caixas  (12 simples,  0 múltiplas)
  Planilha separada:       78 caixas  (73 simples,  5 múltiplas)
"""

import re
import threading
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from estado import Caixa, TipoCaixa
from logger import get_logger

log = get_logger("excel")

# ─────────────────────────────────────────────
#  PADRÕES
# ─────────────────────────────────────────────
_RE_DTI  = re.compile(r"^\d{5,7}$")

_LIXO = (
    "date :", "komatsu", "page :", "company :",
    "caixa no", "proc.importa", "proc. importa",
    "d.t.i", "n.f.", "item", "qtde", "container", "observac",
    "ver dti", "debito", "---", "===",
)


def _e_lixo(val) -> bool:
    if val is None:
        return True
    v = str(val).strip()
    if not v or v.lower() == "nan":
        return True
    vl = v.lower()
    return any(p in vl for p in _LIXO)


def _normalizar_float_str(val) -> str:
    """'547821.0' → '547821', outros → str limpo."""
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except (TypeError, ValueError):
        pass
    v = str(val).strip()
    if v.lower() == "nan":
        return ""
    if "." in v:
        partes = v.split(".")
        if partes[0].lstrip("-").isdigit() and (partes[1] == "0" or partes[1] == ""):
            v = partes[0]
    return v


def _val_dti(val) -> Optional[str]:
    v = _normalizar_float_str(val)
    return v if _RE_DTI.match(v) else None


def _val_caixa(val) -> Optional[str]:
    v = _normalizar_float_str(val)
    if not v or len(v) < 4:
        return None
    if _e_lixo(v):
        return None
    if _RE_DTI.match(v):
        return None
    return v


def _val_proc(val) -> str:
    v = _normalizar_float_str(val)
    return v if v and not _e_lixo(v) else ""


# ─────────────────────────────────────────────
#  DETECÇÃO DE COLUNAS
# ─────────────────────────────────────────────
def _detectar_colunas(df: pd.DataFrame) -> Tuple[int, int, int]:
    """Detecta cols Caixa/DTI/Proc a partir da linha de cabeçalho."""
    col_caixa, col_dti, col_proc = 0, 3, 1

    for _, row in df.iterrows():
        partes = " ".join(str(c) for c in row.values if not pd.isna(c)).lower()
        if "caixa no" in partes and ("d.t.i" in partes or "dti" in partes):
            for i, cell in enumerate(row.values):
                cs = str(cell).strip().lower()
                if "caixa no" in cs:
                    col_caixa = i
                elif "d.t.i" in cs or cs == "dti":
                    col_dti = i
                elif "proc.importa" in cs or "proc. importa" in cs:
                    col_proc = i
            log.debug(f"Colunas detectadas: caixa={col_caixa} dti={col_dti} proc={col_proc}")
            break

    return col_caixa, col_dti, col_proc


# ─────────────────────────────────────────────
#  LEITURA PRINCIPAL
# ─────────────────────────────────────────────
def ler_excel(caminho: str) -> Tuple[List[Caixa], List[str]]:
    """
    Lê planilha BAAN e retorna (caixas_ordenadas, avisos).
    Agrupa DTIs por caixa, classifica SIMPLES/MÚLTIPLA.
    """
    path = Path(caminho)
    avisos: List[str] = []

    if not path.exists():
        return [], [f"Arquivo não encontrado: {caminho}"]

    try:
        xl = pd.ExcelFile(str(path))
        df = pd.read_excel(str(path), sheet_name=xl.sheet_names[0],
                           header=None, dtype=str)
    except Exception as e:
        return [], [f"Erro ao abrir Excel: {e}"]

    if df.empty:
        return [], ["Planilha vazia."]

    n_cols = len(df.columns)
    log.info(f"Excel: {path.name} | {len(df)} linhas | {n_cols} colunas")

    col_caixa, col_dti, col_proc = _detectar_colunas(df)
    col_caixa = min(col_caixa, n_cols - 1)
    col_dti   = min(col_dti,   n_cols - 1)
    col_proc  = min(col_proc,  n_cols - 1)

    # ── Extrair registros ───────────────────
    grupos: dict = {}
    ignoradas = 0

    for _, row in df.iterrows():
        try:
            caixa_raw = row.iloc[col_caixa] if col_caixa < len(row) else None
            dti_raw   = row.iloc[col_dti]   if col_dti   < len(row) else None
            proc_raw  = row.iloc[col_proc]  if col_proc  < len(row) else None

            caixa = _val_caixa(caixa_raw)
            dti   = _val_dti(dti_raw)

            if not caixa or not dti:
                ignoradas += 1
                continue

            proc = _val_proc(proc_raw)

            if caixa not in grupos:
                grupos[caixa] = {"dtis": [], "proc": proc}
            if dti not in grupos[caixa]["dtis"]:
                grupos[caixa]["dtis"].append(dti)
            if proc and not grupos[caixa]["proc"]:
                grupos[caixa]["proc"] = proc

        except Exception:
            ignoradas += 1

    log.info(f"Grupos: {len(grupos)} caixas | {ignoradas} linhas ignoradas")

    if not grupos:
        return [], [
            "Nenhum dado válido encontrado.\n"
            "Verifique se é uma planilha BAAN 'IMPRIMIR CAIXAS DE IMPORTAÇÃO'."
        ]

    # ── Ordenar e classificar ───────────────
    resultado: List[Caixa] = []
    n_s = n_m = 0

    for chave in sorted(grupos):
        g    = grupos[chave]
        dtis = sorted(g["dtis"])
        tipo = TipoCaixa.MULTIPLA if len(dtis) > 1 else TipoCaixa.SIMPLES
        if tipo == TipoCaixa.MULTIPLA:
            n_m += 1
        else:
            n_s += 1
        resultado.append(Caixa(caixa=chave, tipo=tipo.value,
                               dtis=dtis, proc=g["proc"]))

    log.sucesso(f"Processado: {len(resultado)} caixas "
                f"({n_s} simples, {n_m} múltiplas)")

    if n_m > 0:
        avisos.append(f"{n_m} caixa(s) com múltiplas DTIs — usarão fluxo Recebimento Específico.")

    return resultado, avisos


# ─────────────────────────────────────────────
#  PROCESSAMENTO ASSÍNCRONO
# ─────────────────────────────────────────────
def processar_async(caminho: str, callback_ok, callback_erro) -> threading.Thread:
    def _run():
        try:
            caixas, avisos = ler_excel(caminho)
            if caixas:
                callback_ok(caixas, avisos)
            else:
                callback_erro(avisos or ["Nenhuma caixa encontrada."])
        except Exception as e:
            log.error(f"Erro fatal ao processar Excel: {e}", exc_info=True)
            callback_erro([f"Erro inesperado: {e}"])

    t = threading.Thread(target=_run, daemon=True, name="ExcelReader")
    t.start()
    return t
