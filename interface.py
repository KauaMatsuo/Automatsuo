"""
interface.py — AUTOMATSUO V3
Interface gráfica premium com tema escuro, fila visual, logs em tempo real
e painel de debug da automação.
"""

import queue
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

import config as cfg
from config import (
    COR_AMARELO, COR_AZUL, COR_AZUL_HOVER,
    COR_BG_CARD, COR_BG_DARK, COR_BG_ITEM, COR_BG_ITEM_SEL,
    COR_BG_PANEL, COR_BG_SIDEBAR, COR_BORDER, COR_BORDER_LIGHT,
    COR_MULTIPLA_BRD, COR_MULTIPLA_BG,
    COR_STATUS_ERR, COR_STATUS_IDLE, COR_STATUS_INFO, COR_STATUS_OK,
    COR_STATUS_WARN, COR_TEXTO, COR_TEXTO_SEC, COR_TEXTO_TERT,
    COR_VERDE, COR_VERMELHO,
    FONTE_MONO, FONTE_MONO_B, FONTE_MONO_S,
    FONTE_SMALL, FONTE_TITULO,
    NOME, VERSAO,
)
from automacao import debug as debug_ctx, motor
from estado import (
    Caixa, StatusCaixa, StatusGlobal, TipoCaixa,
    gerenciador_estado,
)
from excel import processar_async
from logger import get_logger, log_queue

log = get_logger("interface")

# ─────────────────────────────────────────────
#  MAPEAMENTOS DE COR
# ─────────────────────────────────────────────
_COR_LOG = {
    "azul":     COR_STATUS_INFO,
    "verde":    COR_STATUS_OK,
    "amarelo":  COR_STATUS_WARN,
    "vermelho": COR_STATUS_ERR,
    "cinza":    COR_TEXTO_TERT,
    "branco":   COR_TEXTO,
}

_COR_STATUS_G = {
    StatusGlobal.OCIOSO.value:      COR_STATUS_IDLE,
    StatusGlobal.PROCESSANDO.value: COR_STATUS_INFO,
    StatusGlobal.IMPRIMINDO.value:  COR_AZUL,
    StatusGlobal.PAUSADO.value:     COR_AMARELO,
    StatusGlobal.CONCLUIDO.value:   COR_STATUS_OK,
    StatusGlobal.ERRO.value:        COR_STATUS_ERR,
    StatusGlobal.PARADO.value:      COR_AMARELO,
}

_LABEL_STATUS_G = {
    StatusGlobal.OCIOSO.value:      "● OCIOSO",
    StatusGlobal.PROCESSANDO.value: "◉ PROCESSANDO",
    StatusGlobal.IMPRIMINDO.value:  "◈ IMPRIMINDO",
    StatusGlobal.PAUSADO.value:     "⏸ PAUSADO",
    StatusGlobal.CONCLUIDO.value:   "✔ CONCLUÍDO",
    StatusGlobal.ERRO.value:        "✖ ERRO",
    StatusGlobal.PARADO.value:      "⏹ PARADO",
}

_COR_STATUS_C = {
    StatusCaixa.PENDENTE.value:    COR_TEXTO_TERT,
    StatusCaixa.ATUAL.value:       COR_AZUL,
    StatusCaixa.IMPRIMINDO.value:  COR_AZUL_HOVER,
    StatusCaixa.CONCLUIDA.value:   COR_STATUS_OK,
    StatusCaixa.ERRO.value:        COR_STATUS_ERR,
    StatusCaixa.PULADA.value:      COR_AMARELO,
}

_LABEL_STATUS_C = {
    StatusCaixa.PENDENTE.value:    "● PENDENTE",
    StatusCaixa.ATUAL.value:       "◉ PROCESSANDO",
    StatusCaixa.IMPRIMINDO.value:  "◈ IMPRIMINDO",
    StatusCaixa.CONCLUIDA.value:   "✔ CONCLUÍDA",
    StatusCaixa.ERRO.value:        "✖ ERRO",
    StatusCaixa.PULADA.value:      "⊖ PULADA",
}


# ─────────────────────────────────────────────
#  WIDGETS AUXILIARES
# ─────────────────────────────────────────────
class _Btn(tk.Label):
    """Botão visual sem ttk — compatível com tema escuro."""

    def __init__(self, parent, texto: str, cor: str,
                 cor_hover: str = None, cmd=None, w: int = 14, **kw):
        self._cor    = cor
        self._hover  = cor_hover or self._dim(cor)
        self._cmd    = cmd
        self._off    = False
        super().__init__(parent, text=texto, bg=cor, fg=COR_TEXTO,
                         font=FONTE_MONO_B, width=w, anchor="center",
                         cursor="hand2", relief="flat", padx=8, pady=6, **kw)
        self.bind("<Enter>",    self._e_in)
        self.bind("<Leave>",    self._e_out)
        self.bind("<Button-1>", self._click)

    def _e_in(self, _=None):
        if not self._off: self.config(bg=self._hover)
    def _e_out(self, _=None):
        if not self._off: self.config(bg=self._cor)
    def _click(self, _=None):
        if not self._off and self._cmd: self._cmd()

    def habilitar(self):
        self._off = False
        self.config(bg=self._cor, fg=COR_TEXTO, cursor="hand2")
    def desabilitar(self):
        self._off = True
        self.config(bg=COR_BORDER, fg=COR_TEXTO_TERT, cursor="arrow")

    @staticmethod
    def _dim(c: str) -> str:
        try:
            r, g, b = int(c[1:3],16), int(c[3:5],16), int(c[5:7],16)
            return f"#{int(r*.75):02x}{int(g*.75):02x}{int(b*.75):02x}"
        except Exception:
            return c


# ═══════════════════════════════════════════════════════════════
#  JANELA PRINCIPAL
# ═══════════════════════════════════════════════════════════════
class AutomatsuoApp:

    def __init__(self):
        self.root = tk.Tk()
        self._configurar_janela()
        self._aplicar_estilos()

        # Estado interno
        self._arquivo     = ""
        self._caixas:     List[Caixa] = []
        self._widgets:    Dict[int, dict] = {}
        self._modo_teste  = tk.BooleanVar(value=False)
        self._mostrar_dbg = tk.BooleanVar(value=False)

        # Hotkeys
        self.root.bind("<F9>",  lambda e: self._cmd_iniciar())
        self.root.bind("<F10>", lambda e: self._cmd_parar())
        self.root.bind("<F11>", lambda e: self._cmd_pausar())
        self.root.bind("<F12>", lambda e: self._cmd_continuar())

        # Callbacks do motor
        motor.on_status          = self._cb_status
        motor.on_caixa_iniciada  = self._cb_caixa_iniciada
        motor.on_caixa_concluida = self._cb_caixa_concluida
        motor.on_caixa_erro      = self._cb_caixa_erro
        motor.on_progresso       = self._cb_progresso
        motor.on_concluido       = self._cb_concluido

        # Callback de debug
        debug_ctx.registrar_callback(self._cb_debug)

        # Construir UI
        self._build_topbar()
        corpo = tk.Frame(self.root, bg=COR_BG_DARK)
        corpo.pack(fill="both", expand=True)
        self._build_sidebar(corpo)
        tk.Frame(corpo, bg=COR_BORDER, width=1).pack(side="left", fill="y")
        self._build_fila(corpo)
        tk.Frame(corpo, bg=COR_BORDER, width=1).pack(side="left", fill="y")
        self._build_logs(corpo)
        self._build_statusbar()

        # Polls
        self._poll_logs()
        self._poll_debug()

        # Verificar sessão anterior após renderizar
        self.root.after(400, self._verificar_sessao)

    # ─────────────────────────────────────────
    #  CONFIGURAÇÃO
    # ─────────────────────────────────────────
    def _configurar_janela(self):
        self.root.title(f"AUTOMATSUO V3  —  Sistema de Impressão de Etiquetas BAAN")
        self.root.geometry("1400x840")
        self.root.minsize(1100, 680)
        self.root.configure(bg=COR_BG_DARK)
        self.root.protocol("WM_DELETE_WINDOW", self._fechar)
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"1400x840+{max(0,(sw-1400)//2)}+{max(0,(sh-840)//2)}")

    def _aplicar_estilos(self):
        """
        BUGFIX CRÍTICO: copia o layout padrão antes de criar estilo customizado.
        Corrige: _tkinter.TclError: Layout Horizontal.Dark.TProgressbar not found
        """
        s = ttk.Style()
        s.theme_use("clam")

        # Copiar layout do progressbar padrão
        try:
            layout = s.layout("Horizontal.TProgressbar")
            s.layout("Dark.TProgressbar", layout)
        except Exception:
            pass

        s.configure("Dark.TProgressbar",
                    troughcolor=COR_BORDER,
                    background=COR_AZUL,
                    bordercolor=COR_BORDER,
                    lightcolor=COR_AZUL,
                    darkcolor=COR_AZUL,
                    thickness=10)

        s.configure("Vertical.TScrollbar",
                    background=COR_BG_ITEM,
                    troughcolor=COR_BG_PANEL,
                    arrowcolor=COR_TEXTO_SEC,
                    bordercolor=COR_BORDER)
        s.map("Vertical.TScrollbar",
              background=[("active", COR_BORDER_LIGHT)])

    # ─────────────────────────────────────────
    #  TOP BAR
    # ─────────────────────────────────────────
    def _build_topbar(self):
        tb = tk.Frame(self.root, bg=COR_BG_SIDEBAR, height=52)
        tb.pack(fill="x")
        tb.pack_propagate(False)

        tk.Label(tb, text="⬡ AUTOMATSUO V3",
                 bg=COR_BG_SIDEBAR, fg=COR_TEXTO,
                 font=("Segoe UI", 14, "bold")).pack(side="left", padx=16, pady=10)

        tk.Frame(tb, bg=COR_BORDER, width=1).pack(side="left", fill="y", padx=10)

        for txt in ["F9 Iniciar", "F10 Parar", "F11 Pausar", "F12 Continuar"]:
            tk.Label(tb, text=txt, bg=COR_BG_SIDEBAR,
                     fg=COR_TEXTO_TERT, font=FONTE_SMALL).pack(side="left", padx=8)

        self._lbl_clock = tk.Label(tb, text="", bg=COR_BG_SIDEBAR,
                                   fg=COR_TEXTO_SEC, font=FONTE_SMALL)
        self._lbl_clock.pack(side="right", padx=16)
        self._tick_clock()

        tk.Frame(self.root, bg=COR_BORDER, height=1).pack(fill="x")

    # ─────────────────────────────────────────
    #  SIDEBAR
    # ─────────────────────────────────────────
    def _build_sidebar(self, parent):
        sb = tk.Frame(parent, bg=COR_BG_SIDEBAR, width=268)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        # ── Arquivo ──────────────────────────
        self._sec(sb, "ARQUIVO EXCEL")
        self._lbl_arq = tk.Label(sb, text="Nenhum arquivo selecionado",
                                 bg=COR_BG_SIDEBAR, fg=COR_TEXTO_TERT,
                                 font=FONTE_SMALL, wraplength=230, justify="left")
        self._lbl_arq.pack(anchor="w", padx=12, pady=(2, 6))
        _Btn(sb, "📂  Abrir Excel", COR_BG_CARD, w=26,
             cmd=self._cmd_abrir).pack(padx=12, pady=(0,10), fill="x")

        # ── Modo ─────────────────────────────
        self._sec(sb, "MODO")
        tk.Checkbutton(sb, text="  Modo Teste (sem confirmar)",
                       variable=self._modo_teste,
                       bg=COR_BG_SIDEBAR, fg=COR_TEXTO_SEC,
                       activebackground=COR_BG_SIDEBAR,
                       selectcolor=COR_BG_ITEM,
                       font=FONTE_SMALL).pack(anchor="w", padx=12, pady=(2,8))

        # ── Controles ────────────────────────
        self._sec(sb, "CONTROLES  (Hotkeys)")
        self._btn_ini  = _Btn(sb, "▶  Iniciar      F9",  COR_VERDE,   w=26, cmd=self._cmd_iniciar)
        self._btn_pau  = _Btn(sb, "⏸  Pausar      F11",  COR_AMARELO, w=26, cmd=self._cmd_pausar)
        self._btn_con  = _Btn(sb, "▶▶ Continuar   F12",  COR_AZUL,    w=26, cmd=self._cmd_continuar)
        self._btn_par  = _Btn(sb, "⏹  Parar       F10",  COR_VERMELHO,w=26, cmd=self._cmd_parar)
        for b in [self._btn_ini, self._btn_pau, self._btn_con, self._btn_par]:
            b.pack(padx=12, pady=2, fill="x")

        # ── Estatísticas ─────────────────────
        self._sec(sb, "ESTATÍSTICAS")
        self._stats: Dict[str, tk.Label] = {}
        for k, r in [("total","Total"), ("simples","Simples"),
                     ("multiplas","Múltiplas"), ("concluidas","Concluídas"),
                     ("erros","Erros")]:
            row = tk.Frame(sb, bg=COR_BG_SIDEBAR)
            row.pack(fill="x", padx=12, pady=1)
            tk.Label(row, text=r, bg=COR_BG_SIDEBAR,
                     fg=COR_TEXTO_SEC, font=FONTE_SMALL).pack(side="left")
            lbl = tk.Label(row, text="—", bg=COR_BG_SIDEBAR,
                           fg=COR_TEXTO, font=FONTE_MONO_B)
            lbl.pack(side="right")
            self._stats[k] = lbl

        # Barra de progresso
        tk.Label(sb, text="Progresso", bg=COR_BG_SIDEBAR,
                 fg=COR_TEXTO_SEC, font=FONTE_SMALL).pack(anchor="w", padx=12, pady=(8,2))
        self._pct = tk.DoubleVar(value=0)
        self._pb  = ttk.Progressbar(sb, variable=self._pct, maximum=100,
                                    style="Dark.TProgressbar", orient="horizontal")
        self._pb.pack(fill="x", padx=12)
        self._lbl_pct = tk.Label(sb, text="0 / 0",
                                 bg=COR_BG_SIDEBAR, fg=COR_TEXTO_TERT, font=FONTE_SMALL)
        self._lbl_pct.pack(anchor="e", padx=12)

        # ── Ferramentas ───────────────────────
        self._sec(sb, "FERRAMENTAS")
        _Btn(sb, "🧪 Abrir BAAN Fake", COR_BG_CARD, w=26,
             cmd=self._cmd_baan_fake).pack(padx=12, pady=2, fill="x")
        _Btn(sb, "🗑  Limpar Fila",     COR_BG_CARD, w=26,
             cmd=self._cmd_limpar_fila).pack(padx=12, pady=2, fill="x")
        _Btn(sb, "📋 Limpar Logs",      COR_BG_CARD, w=26,
             cmd=self._cmd_limpar_logs).pack(padx=12, pady=2, fill="x")

        # ── Debug toggle ──────────────────────
        self._sec(sb, "DEBUG")
        tk.Checkbutton(sb, text="  Mostrar Painel Debug",
                       variable=self._mostrar_dbg,
                       command=self._toggle_debug,
                       bg=COR_BG_SIDEBAR, fg=COR_TEXTO_SEC,
                       activebackground=COR_BG_SIDEBAR,
                       selectcolor=COR_BG_ITEM,
                       font=FONTE_SMALL).pack(anchor="w", padx=12, pady=(2,8))

    def _sec(self, parent, titulo: str):
        tk.Label(parent, text=titulo, bg=COR_BG_SIDEBAR,
                 fg=COR_TEXTO_TERT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12, pady=(12,2))
        tk.Frame(parent, bg=COR_BORDER, height=1).pack(fill="x", padx=8)

    # ─────────────────────────────────────────
    #  FILA VISUAL
    # ─────────────────────────────────────────
    def _build_fila(self, parent):
        painel = tk.Frame(parent, bg=COR_BG_DARK)
        painel.pack(side="left", fill="both", expand=True)

        hdr = tk.Frame(painel, bg=COR_BG_PANEL, height=40)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="FILA DE IMPRESSÃO",
                 bg=COR_BG_PANEL, fg=COR_TEXTO,
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=16, pady=10)
        self._lbl_count = tk.Label(hdr, text="0 itens",
                                   bg=COR_BG_PANEL, fg=COR_TEXTO_TERT, font=FONTE_SMALL)
        self._lbl_count.pack(side="left", padx=4)
        self._auto_scroll = tk.BooleanVar(value=True)
        tk.Checkbutton(hdr, text="Auto-scroll", variable=self._auto_scroll,
                       bg=COR_BG_PANEL, fg=COR_TEXTO_SEC,
                       activebackground=COR_BG_PANEL, selectcolor=COR_BG_ITEM,
                       font=FONTE_SMALL).pack(side="right", padx=12)

        tk.Frame(painel, bg=COR_BORDER, height=1).pack(fill="x")

        cont = tk.Frame(painel, bg=COR_BG_DARK)
        cont.pack(fill="both", expand=True)

        self._cv = tk.Canvas(cont, bg=COR_BG_DARK, highlightthickness=0)
        sb_cv    = ttk.Scrollbar(cont, orient="vertical", command=self._cv.yview)
        self._cv.configure(yscrollcommand=sb_cv.set)
        sb_cv.pack(side="right", fill="y")
        self._cv.pack(side="left", fill="both", expand=True)

        self._fr_fila = tk.Frame(self._cv, bg=COR_BG_DARK)
        self._cv_win  = self._cv.create_window((0,0), window=self._fr_fila, anchor="nw")

        self._fr_fila.bind("<Configure>",
                           lambda e: self._cv.configure(scrollregion=self._cv.bbox("all")))
        self._cv.bind("<Configure>",
                      lambda e: self._cv.itemconfig(self._cv_win, width=e.width))
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._cv.bind(ev, self._scroll)

        # Placeholder
        self._ph = tk.Label(self._fr_fila,
                            text="Carregue um arquivo Excel para iniciar\n\n📂  Botão 'Abrir Excel' na sidebar",
                            bg=COR_BG_DARK, fg=COR_TEXTO_TERT,
                            font=("Segoe UI", 12), justify="center")
        self._ph.pack(pady=80)

    def _scroll(self, e):
        d = -1 if (e.num == 4 or e.delta > 0) else 1
        self._cv.yview_scroll(d, "units")

    # ─────────────────────────────────────────
    #  PAINEL LOGS + STATUS + DEBUG
    # ─────────────────────────────────────────
    def _build_logs(self, parent):
        painel = tk.Frame(parent, bg=COR_BG_DARK, width=380)
        painel.pack(side="left", fill="y")
        painel.pack_propagate(False)

        # Header logs
        hdr = tk.Frame(painel, bg=COR_BG_PANEL, height=40)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="LOGS EM TEMPO REAL",
                 bg=COR_BG_PANEL, fg=COR_TEXTO,
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=16, pady=10)
        tk.Frame(painel, bg=COR_BORDER, height=1).pack(fill="x")

        # Área texto
        fr_txt = tk.Frame(painel, bg=COR_BG_DARK)
        fr_txt.pack(fill="both", expand=True)
        sb_txt = ttk.Scrollbar(fr_txt, orient="vertical")
        self._txt = tk.Text(fr_txt, bg=COR_BG_DARK, fg=COR_TEXTO,
                            font=FONTE_MONO_S, wrap="word", state="disabled",
                            yscrollcommand=sb_txt.set, relief="flat",
                            padx=8, pady=4, cursor="arrow")
        sb_txt.configure(command=self._txt.yview)
        sb_txt.pack(side="right", fill="y")
        self._txt.pack(side="left", fill="both", expand=True)
        for nivel, cor in _COR_LOG.items():
            self._txt.tag_configure(nivel, foreground=cor)
        self._txt.tag_configure("ts", foreground=COR_TEXTO_TERT)

        # Status atual
        tk.Frame(painel, bg=COR_BORDER, height=1).pack(fill="x")
        fr_st = tk.Frame(painel, bg=COR_BG_PANEL)
        fr_st.pack(fill="x")
        tk.Label(fr_st, text="STATUS", bg=COR_BG_PANEL,
                 fg=COR_TEXTO_TERT, font=("Segoe UI",8,"bold")).pack(anchor="w", padx=12, pady=(6,2))
        self._lbl_sg = tk.Label(fr_st, text="● OCIOSO",
                                bg=COR_BG_PANEL, fg=COR_STATUS_IDLE,
                                font=("Segoe UI", 11, "bold"))
        self._lbl_sg.pack(anchor="w", padx=12)
        self._lbl_caixa = tk.Label(fr_st, text="—",
                                   bg=COR_BG_PANEL, fg=COR_TEXTO_SEC, font=FONTE_MONO)
        self._lbl_caixa.pack(anchor="w", padx=12, pady=(0,8))

        # Painel debug (inicialmente oculto)
        self._fr_debug = tk.Frame(painel, bg=COR_BG_CARD,
                                  highlightbackground=COR_BORDER, highlightthickness=1)
        # não empacotado ainda — controlado por _toggle_debug
        self._debug_vars: Dict[str, tk.StringVar] = {}
        self._build_debug_panel()

    def _build_debug_panel(self):
        f = self._fr_debug
        tk.Label(f, text="PAINEL DEBUG", bg=COR_BG_CARD,
                 fg=COR_TEXTO_TERT, font=("Segoe UI",8,"bold")
                 ).pack(anchor="w", padx=10, pady=(6,2))
        tk.Frame(f, bg=COR_BORDER, height=1).pack(fill="x")

        campos = [
            ("etapa",        "Etapa"),
            ("janela",       "Janela"),
            ("campo",        "Campo"),
            ("proxima",      "Próxima ação"),
            ("ultimo_tab",   "Último TAB"),
            ("ultimo_enter", "Último ENTER"),
        ]
        for k, label in campos:
            row = tk.Frame(f, bg=COR_BG_CARD)
            row.pack(fill="x", padx=10, pady=1)
            tk.Label(row, text=f"{label}:", bg=COR_BG_CARD,
                     fg=COR_TEXTO_TERT, font=FONTE_SMALL, width=14, anchor="w"
                     ).pack(side="left")
            var = tk.StringVar(value="—")
            tk.Label(row, textvariable=var, bg=COR_BG_CARD,
                     fg=COR_AZUL_HOVER, font=FONTE_MONO_S, anchor="w"
                     ).pack(side="left", fill="x", expand=True)
            self._debug_vars[k] = var

    def _toggle_debug(self):
        if self._mostrar_dbg.get():
            self._fr_debug.pack(fill="x", side="bottom")
        else:
            self._fr_debug.pack_forget()

    # ─────────────────────────────────────────
    #  STATUS BAR
    # ─────────────────────────────────────────
    def _build_statusbar(self):
        tk.Frame(self.root, bg=COR_BORDER, height=1).pack(fill="x")
        sb = tk.Frame(self.root, bg=COR_BG_SIDEBAR, height=26)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        self._lbl_sb = tk.Label(sb, text="Pronto", bg=COR_BG_SIDEBAR,
                                fg=COR_TEXTO_SEC, font=FONTE_SMALL)
        self._lbl_sb.pack(side="left", padx=12)
        self._lbl_sb_arq = tk.Label(sb, text="", bg=COR_BG_SIDEBAR,
                                    fg=COR_TEXTO_TERT, font=FONTE_SMALL)
        self._lbl_sb_arq.pack(side="right", padx=12)

    # ─────────────────────────────────────────
    #  RENDER DA FILA
    # ─────────────────────────────────────────
    def _render_fila(self, caixas: List[Caixa]):
        for w in self._fr_fila.winfo_children():
            w.destroy()
        self._widgets.clear()

        if not caixas:
            tk.Label(self._fr_fila, text="Fila vazia",
                     bg=COR_BG_DARK, fg=COR_TEXTO_TERT,
                     font=("Segoe UI", 12)).pack(pady=40)
            return

        for idx, c in enumerate(caixas):
            self._item_fila(idx, c)

        self._lbl_count.config(text=f"{len(caixas)} itens")

    def _item_fila(self, idx: int, c: Caixa):
        multi = (c.tipo == TipoCaixa.MULTIPLA.value)
        bg    = COR_MULTIPLA_BG if multi else COR_BG_ITEM
        brd   = COR_MULTIPLA_BRD if multi else COR_BORDER
        bw    = 2 if multi else 1

        fo = tk.Frame(self._fr_fila, bg=COR_BG_DARK, pady=2, padx=6)
        fo.pack(fill="x")
        fr = tk.Frame(fo, bg=bg, highlightbackground=brd, highlightthickness=bw)
        fr.pack(fill="x")

        # Linha 1
        l1 = tk.Frame(fr, bg=bg)
        l1.pack(fill="x", padx=10, pady=(7,2))
        tk.Label(l1, text=f"#{idx+1:03d}", bg=bg, fg=COR_TEXTO_TERT,
                 font=FONTE_MONO_S, width=5).pack(side="left")

        badge_c = COR_AZUL if multi else COR_VERDE
        bfr = tk.Frame(l1, bg=badge_c, padx=4, pady=1)
        bfr.pack(side="left", padx=(4,8))
        tk.Label(bfr, text="MÚLTIPLA" if multi else "SIMPLES",
                 bg=badge_c, fg=COR_TEXTO, font=("Segoe UI",7,"bold")).pack()

        lbl_c = tk.Label(l1, text=c.caixa, bg=bg, fg=COR_TEXTO,
                         font=FONTE_MONO_B if multi else FONTE_MONO)
        lbl_c.pack(side="left", padx=(0,8))

        if c.proc:
            tk.Label(l1, text=c.proc, bg=bg, fg=COR_TEXTO_TERT,
                     font=FONTE_MONO_S).pack(side="left")

        lbl_st = tk.Label(l1, text="● PENDENTE", bg=bg,
                          fg=COR_TEXTO_TERT, font=FONTE_SMALL)
        lbl_st.pack(side="right")

        # Linha 2 — DTIs
        l2 = tk.Frame(fr, bg=bg)
        l2.pack(fill="x", padx=10, pady=(0,7))
        n = len(c.dtis)
        txt_dtis = "  ".join(c.dtis[:8])
        if n > 8: txt_dtis += f"  +{n-8}"
        tk.Label(l2, text=f"DTI{'s' if n>1 else ''}: {txt_dtis}",
                 bg=bg, fg=COR_TEXTO_SEC, font=FONTE_MONO_S).pack(side="left")
        tk.Label(l2, text=f"{n} DTI{'s' if n>1 else ''}",
                 bg=bg, fg=badge_c, font=FONTE_SMALL).pack(side="right")

        self._widgets[idx] = {
            "fr": fr, "fo": fo, "lbl_st": lbl_st,
            "lbl_c": lbl_c, "multi": multi, "bg": bg,
        }

    def _update_item(self, idx: int, status: StatusCaixa):
        if idx not in self._widgets:
            return
        w   = self._widgets[idx]
        cor = _COR_STATUS_C.get(status.value, COR_TEXTO_TERT)
        txt = _LABEL_STATUS_C.get(status.value, "● PENDENTE")
        try:
            w["lbl_st"].config(text=txt, fg=cor)

            if status == StatusCaixa.ATUAL:
                new_bg = COR_BG_ITEM_SEL
                w["fr"].config(bg=new_bg, highlightbackground=COR_AZUL_HOVER,
                               highlightthickness=2)
                for child in w["fr"].winfo_children():
                    try:
                        child.config(bg=new_bg)
                        for gc in child.winfo_children():
                            try: gc.config(bg=new_bg)
                            except Exception: pass
                    except Exception: pass
                w["lbl_c"].config(bg=new_bg)
                w["lbl_st"].config(bg=new_bg)
                if self._auto_scroll.get():
                    self.root.after(80, lambda i=idx: self._scroll_to(i))

            elif status == StatusCaixa.CONCLUIDA:
                bg = w["bg"]
                w["fr"].config(bg=bg, highlightbackground=COR_STATUS_OK,
                               highlightthickness=1)
                self._recorrer_bg(w["fr"], bg)

            elif status == StatusCaixa.ERRO:
                bg = "#1A0808"
                w["fr"].config(bg=bg, highlightbackground=COR_VERMELHO,
                               highlightthickness=2)
                self._recorrer_bg(w["fr"], bg)

        except tk.TclError:
            pass

    def _recorrer_bg(self, widget, bg: str):
        try:
            widget.config(bg=bg)
        except Exception:
            pass
        for ch in widget.winfo_children():
            self._recorrer_bg(ch, bg)

    def _scroll_to(self, idx: int):
        n = len(self._caixas)
        if n == 0: return
        self._cv.yview_moveto(max(0, (idx / n) - 0.12))

    # ─────────────────────────────────────────
    #  POLLS
    # ─────────────────────────────────────────
    def _poll_logs(self):
        try:
            for _ in range(60):
                item = log_queue.get_nowait()
                self._append_log(item["texto"], item["cor"])
        except queue.Empty:
            pass
        self.root.after(80, self._poll_logs)

    def _poll_debug(self):
        """Atualiza widgets do painel debug com dados atuais."""
        if self._mostrar_dbg.get():
            snap = debug_ctx.snapshot()
            for k, var in self._debug_vars.items():
                v = snap.get(k, "—") or "—"
                try:
                    var.set(str(v)[:60])
                except Exception:
                    pass
        self.root.after(200, self._poll_debug)

    def _append_log(self, texto: str, cor: str = "branco"):
        try:
            self._txt.configure(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            self._txt.insert("end", f"[{ts}] ", "ts")
            self._txt.insert("end", texto + "\n", cor)
            self._txt.configure(state="disabled")
            self._txt.see("end")
            # Limitar a 2000 linhas
            n = int(self._txt.index("end-1c").split(".")[0])
            if n > 2000:
                self._txt.configure(state="normal")
                self._txt.delete("1.0", "100.0")
                self._txt.configure(state="disabled")
        except tk.TclError:
            pass

    # ─────────────────────────────────────────
    #  CALLBACKS DO MOTOR
    # ─────────────────────────────────────────
    def _cb_status(self, s: StatusGlobal, msg: str):
        self.root.after(0, lambda: self._update_status(s, msg))

    def _cb_caixa_iniciada(self, idx: int, c: Caixa):
        self.root.after(0, lambda: self._update_item(idx, StatusCaixa.ATUAL))
        dtis_str = ", ".join(c.dtis[:3]) + ("…" if len(c.dtis) > 3 else "")
        self.root.after(0, lambda: self._lbl_caixa.config(
            text=f"{c.caixa}  [{c.tipo}]  {dtis_str}"))

    def _cb_caixa_concluida(self, idx: int, c: Caixa):
        self.root.after(0, lambda: self._update_item(idx, StatusCaixa.CONCLUIDA))
        self.root.after(0, self._update_stats_do_estado)

    def _cb_caixa_erro(self, idx: int, c: Caixa, e: str):
        self.root.after(0, lambda: self._update_item(idx, StatusCaixa.ERRO))
        self.root.after(0, self._update_stats_do_estado)

    def _cb_progresso(self, atual: int, total: int):
        self.root.after(0, lambda: self._update_progresso(atual, total))

    def _cb_concluido(self):
        self.root.after(0, self._on_concluido)

    def _cb_debug(self, snap: dict):
        # callback do debug_ctx — apenas sinaliza, o poll atualiza a UI
        pass

    def _on_concluido(self):
        est = gerenciador_estado.estado
        messagebox.showinfo(
            "Automação Concluída",
            f"Processamento finalizado!\n\n"
            f"✔ Concluídas: {est.concluidas}\n"
            f"✖ Erros:       {est.erros}\n"
            f"Total:         {est.total}",
        )

    # ─────────────────────────────────────────
    #  ATUALIZAÇÃO DE UI
    # ─────────────────────────────────────────
    def _update_status(self, s: StatusGlobal, msg: str):
        cor = _COR_STATUS_G.get(s.value, COR_STATUS_IDLE)
        txt = _LABEL_STATUS_G.get(s.value, s.value.upper())
        try:
            self._lbl_sg.config(text=txt, fg=cor)
            if msg:
                self._lbl_sb.config(text=msg)
        except tk.TclError:
            pass

    def _update_progresso(self, atual: int, total: int):
        pct = (atual / total * 100) if total else 0
        try:
            self._pct.set(pct)
            self._lbl_pct.config(text=f"{atual} / {total}")
        except tk.TclError:
            pass

    def _update_stats(self, caixas: List[Caixa]):
        n  = len(caixas)
        ns = sum(1 for c in caixas if c.tipo == TipoCaixa.SIMPLES.value)
        nm = sum(1 for c in caixas if c.tipo == TipoCaixa.MULTIPLA.value)
        try:
            self._stats["total"].config(text=str(n))
            self._stats["simples"].config(text=str(ns))
            self._stats["multiplas"].config(text=str(nm))
            self._stats["concluidas"].config(text="0")
            self._stats["erros"].config(text="0")
            self._lbl_count.config(text=f"{n} itens")
        except tk.TclError:
            pass

    def _update_stats_do_estado(self):
        est = gerenciador_estado.estado
        try:
            self._stats["concluidas"].config(
                text=str(est.concluidas), fg=COR_STATUS_OK)
            self._stats["erros"].config(
                text=str(est.erros),
                fg=COR_STATUS_ERR if est.erros else COR_TEXTO)
            self._update_progresso(est.concluidas + est.erros, est.total)
        except tk.TclError:
            pass

    # ─────────────────────────────────────────
    #  COMANDOS
    # ─────────────────────────────────────────
    def _cmd_abrir(self):
        path = filedialog.askopenfilename(
            title="Selecionar planilha BAAN",
            filetypes=[("Excel", "*.xlsx *.xls *.xlsm"), ("Todos", "*.*")],
        )
        if not path:
            return
        self._arquivo = path
        nome = path.replace("\\", "/").split("/")[-1]
        self._lbl_arq.config(text=nome, fg=COR_TEXTO)
        self._lbl_sb_arq.config(text=path)
        self._lbl_sb.config(text=f"Processando {nome}…")
        self._append_log(f"Abrindo: {path}", "azul")
        self._btn_ini.desabilitar()
        processar_async(path,
                        callback_ok=self._on_excel_ok,
                        callback_erro=self._on_excel_erro)

    def _on_excel_ok(self, caixas, avisos):
        self.root.after(0, lambda: self._aplicar_caixas(caixas, avisos))

    def _aplicar_caixas(self, caixas, avisos):
        self._caixas = caixas
        gerenciador_estado.definir_fila(caixas, self._arquivo)
        self._render_fila(caixas)
        self._update_stats(caixas)
        self._btn_ini.habilitar()
        n  = len(caixas)
        ns = sum(1 for c in caixas if c.tipo == TipoCaixa.SIMPLES.value)
        nm = sum(1 for c in caixas if c.tipo == TipoCaixa.MULTIPLA.value)
        self._lbl_sb.config(text=f"Fila: {n} caixas ({ns} simples, {nm} múltiplas)")
        self._append_log(f"Excel carregado: {n} caixas ({ns} simples, {nm} múltiplas)", "verde")
        for av in avisos:
            self._append_log(f"⚠ {av}", "amarelo")

    def _on_excel_erro(self, erros):
        self.root.after(0, lambda: self._mostrar_erro_excel(erros))

    def _mostrar_erro_excel(self, erros):
        self._btn_ini.habilitar()
        msg = "\n".join(erros)
        self._append_log(f"Erro Excel: {msg}", "vermelho")
        self._lbl_sb.config(text="Erro ao carregar Excel")
        messagebox.showerror("Erro ao carregar Excel", msg)

    def _cmd_iniciar(self):
        if motor.esta_rodando():
            self._append_log("Automação já em execução.", "amarelo")
            return
        if not self._caixas:
            self._append_log("Carregue um arquivo Excel primeiro.", "amarelo")
            messagebox.showwarning("Sem fila", "Carregue um Excel antes de iniciar.")
            return
        mt = self._modo_teste.get()
        self._append_log(f"Iniciando{'  [MODO TESTE]' if mt else ''}…", "azul")
        motor.iniciar(modo_teste=mt)

    def _cmd_parar(self):
        if motor.esta_rodando():
            motor.parar()

    def _cmd_pausar(self):
        if motor.esta_rodando() and not motor.esta_pausado():
            motor.pausar()

    def _cmd_continuar(self):
        if motor.esta_rodando() and motor.esta_pausado():
            motor.continuar()

    def _cmd_baan_fake(self):
        try:
            import subprocess, sys, os
            fake = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baan_fake.py")
            subprocess.Popen([sys.executable, fake])
            self._append_log("BAAN Fake aberto.", "azul")
        except Exception as e:
            self._append_log(f"Erro ao abrir BAAN Fake: {e}", "vermelho")

    def _cmd_limpar_fila(self):
        if motor.esta_rodando():
            self._append_log("Pare a automação antes de limpar a fila.", "amarelo")
            return
        self._caixas = []
        for w in self._fr_fila.winfo_children():
            w.destroy()
        self._widgets.clear()
        self._lbl_count.config(text="0 itens")
        gerenciador_estado.resetar()
        self._update_stats([])
        self._ph = tk.Label(self._fr_fila,
                            text="Carregue um arquivo Excel para iniciar",
                            bg=COR_BG_DARK, fg=COR_TEXTO_TERT,
                            font=("Segoe UI", 12))
        self._ph.pack(pady=80)
        self._append_log("Fila limpa.", "azul")

    def _cmd_limpar_logs(self):
        try:
            self._txt.configure(state="normal")
            self._txt.delete("1.0", "end")
            self._txt.configure(state="disabled")
        except tk.TclError:
            pass

    # ─────────────────────────────────────────
    #  SESSÃO ANTERIOR
    # ─────────────────────────────────────────
    def _verificar_sessao(self):
        if not gerenciador_estado.tem_sessao_anterior():
            return
        est = gerenciador_estado.estado
        if not messagebox.askyesno(
            "Sessão Anterior Encontrada",
            f"Sessão interrompida encontrada:\n\n"
            f"Arquivo: {est.arquivo_excel or 'desconhecido'}\n"
            f"Progresso: {est.concluidas} de {est.total} caixas\n"
            f"Posição: #{est.indice_atual + 1}\n\n"
            f"Deseja continuar de onde parou?"
        ):
            gerenciador_estado.resetar()
            return

        gerenciador_estado.carregar()
        fila = gerenciador_estado.get_fila()
        if not fila:
            return

        self._caixas = fila
        arq = gerenciador_estado.estado.arquivo_excel
        if arq:
            nome = arq.replace("\\", "/").split("/")[-1]
            self._lbl_arq.config(text=nome, fg=COR_TEXTO)
            self._lbl_sb_arq.config(text=arq)

        self._render_fila(fila)
        self._update_stats(fila)
        self._btn_ini.habilitar()

        for i, c in enumerate(fila):
            if c.status == StatusCaixa.CONCLUIDA.value:
                self._update_item(i, StatusCaixa.CONCLUIDA)

        est = gerenciador_estado.estado
        self._append_log(
            f"Sessão retomada: {est.concluidas} de {est.total} concluídas.", "verde")
        self._lbl_sb.config(text="Sessão anterior carregada — pronto para continuar.")

    # ─────────────────────────────────────────
    #  RELÓGIO
    # ─────────────────────────────────────────
    def _tick_clock(self):
        try:
            self._lbl_clock.config(text=datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))
            self.root.after(1000, self._tick_clock)
        except tk.TclError:
            pass

    # ─────────────────────────────────────────
    #  FECHAR
    # ─────────────────────────────────────────
    def _fechar(self):
        if motor.esta_rodando():
            if not messagebox.askyesno("Automação em Execução",
                                       "Automação ativa. Parar e sair?"):
                return
            motor.parar()
            time.sleep(0.5)
        gerenciador_estado.parar()
        self.root.destroy()

    # ─────────────────────────────────────────
    #  INICIAR
    # ─────────────────────────────────────────
    def iniciar(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = AutomatsuoApp()
    app.iniciar()
