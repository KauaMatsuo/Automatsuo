"""
main.py — AUTOMATSUO V3
Ponto de entrada. Execute com:
    python main.py
"""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from logger import configurar_logging, get_logger
configurar_logging(logging.DEBUG)
log = get_logger("main")


def verificar_deps() -> bool:
    ausentes = []
    for mod, pkg in [("pandas", "pandas"), ("openpyxl", "openpyxl")]:
        try:
            __import__(mod)
        except ImportError:
            ausentes.append(pkg)

    for mod in ["tkinter"]:
        try:
            __import__(mod)
        except ImportError:
            ausentes.append(f"{mod} (sudo apt install python3-tk)")

    for mod, pkg in [("pyautogui", "pyautogui"), ("pygetwindow", "pygetwindow")]:
        try:
            __import__(mod)
        except ImportError:
            log.warning(f"Opcional ausente: {mod} — modo simulação ativo.")

    if ausentes:
        log.error(f"Dependências obrigatórias ausentes: {', '.join(ausentes)}")
        log.error("Execute:  pip install " + " ".join(
            p for p in ausentes if "apt" not in p))
        return False
    return True


def main():
    log.info("=" * 60)
    log.info("  AUTOMATSUO V3 — Sistema de Impressão de Etiquetas BAAN")
    log.info("=" * 60)

    if not verificar_deps():
        sys.exit(1)

    from interface import AutomatsuoApp
    AutomatsuoApp().iniciar()
    log.info("AUTOMATSUO V3 encerrado.")


if __name__ == "__main__":
    main()
