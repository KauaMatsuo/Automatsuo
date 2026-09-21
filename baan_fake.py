"""
baan_fake.py — AUTOMATSUO V3
Simulador fiel do BAAN para testes sem o sistema real.

Janelas replicadas (títulos exatos):
  tdpuro401m000 : Imprimir Etiquetas de Entrada [000]     ← tela principal
  tkcpdo400s000 : Selecionar Recebimentos Específicos [000] ← grid DTI
  tdinvs0001.o  : Imprimir Etiquetas de Entrada           ← popup confirmação

Correções desta versão (v3.0.1):
  ✔ Import de `Optional` que faltava — a janela de múltiplas DTIs
    (tkcpdo400s000) quebrava com NameError assim que "Recebimento
    Específico" ia para "Sim".
  ✔ Título da janela principal ganha um marcador temporário
    ("... Imprimindo ...") enquanto a impressão simulada está rodando,
    e volta ao título normal só quando o foco já voltou para
    "Recebimento Específico". A automação usa esse marcador para saber
    quando é seguro começar a próxima caixa — sem isso, a próxima DTI
    podia ser digitada cedo demais e cair no botão/campo errado.
  ✔ Popup "Recebimento Específico" = janela modal REAL com Sim/Não
    navegável por TAB, SHIFT+TAB, ENTER, ←/→, ESC
  ✔ Grid DTI: TAB em campo vazio → foco vai para botão Ok
  ✔ Grid DTI: ENTER = TAB (comportamento BAAN real)
  ✔ Foco inicial: campo "Recebimento Específico" ao abrir e após cada ciclo
  ✔ Autopreenchimento "Até" ao sair do campo "De" com TAB
  ✔ Spinbox responde a S/N além de Up/Down
  ✔ Simulação de impressão com mensagem no campo "Mensagem"
  ✔ grab_set/grab_release em todos os modais
"""

import tkinter as tk
from tkinter import ttk
import threading
import time
import logging
import sys
import os
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import TITULO_PRINCIPAL, TITULO_JANELA_DTI, TITULO_POPUP, TITULO_OCUPADO

log = logging.getLogger("AUTOMATSUO.baan_fake")

# ─────────────────────────────────────────────
#  VISUAL (Windows XP clássico = BAAN real)
# ─────────────────────────────────────────────
BG          = "#ECE9D8"
BG_CAMPO    = "#FFFFFF"
BG_BOTAO    = "#D4D0C8"
BG_TOOLBAR  = "#C8C8C8"
BORDA       = "#808080"
TXT         = "#000000"
TXT_LABEL   = "#000000"
TXT_INATIVO = "#707070"
COR_FOCO    = "#C5D9E8"
COR_AVISO   = "#FFD700"
BARRA_BG    = "#D4D0C8"
BARRA_TXT   = "#000080"

FM  = ("Courier New", 10)
FMS = ("Courier New", 9)
FMB = ("Courier New", 10, "bold")

ENUM_REC    = ["Não", "Sim"]
COLS_GRID   = 8
ROWS_GRID   = 16
N_CAMPOS    = COLS_GRID * ROWS_GRID       # 128

TITULO_PRONTO = TITULO_PRINCIPAL + " : Imprimir Etiquetas de Entrada [000]"


# ═══════════════════════════════════════════════════════════════
#  TELA PRINCIPAL: tdpuro401m000
# ═══════════════════════════════════════════════════════════════
class BaanFake:

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(TITULO_PRONTO)
        self.root.geometry("780x600")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

        self._vars: dict           = {}
        self._campos: dict         = {}
        self._janela_dti           = None
        self._dtis_selecionadas    = []
        self._imprimindo           = False
        self._var_mensagem         = tk.StringVar(value="")
        self._bloqueio_enter       = False
        self._impressao_concluida  = threading.Event()

        self._build_menu()
        self._build_toolbar()
        self._build_form()
        self._build_statusbar()

        # Foco inicial: Recebimento Específico (comportamento BAAN real)
        self.root.after(150, lambda: self._campos["rec"].focus_set())

    # ─────────────────────────────────────────
    #  CONSTRUÇÃO
    # ─────────────────────────────────────────
    def _build_menu(self):
        mb = tk.Menu(self.root)
        for nome in ["File","Edit","Group","Workflow","Options","Order","Tools","Special","Help"]:
            mb.add_cascade(label=nome, menu=tk.Menu(mb, tearoff=0))
        self.root.config(menu=mb)

    def _build_toolbar(self):
        tb = tk.Frame(self.root, bg=BG_TOOLBAR, relief="raised", bd=1, height=36)
        tb.pack(fill="x")
        tb.pack_propagate(False)
        for ico in ["🖫","🖨","↩","⏮","◀","▶","⏭","⏮⏮","⏭⏭","T","?"]:
            tk.Button(tb, text=ico, bg=BG_BOTAO, relief="raised",
                      font=("Segoe UI Symbol", 9), width=2,
                      takefocus=False).pack(side="left", padx=1, pady=4)

    def _verificar_trava_rec_especifico(self, event=None):
        """Se Recebimento Específico for 'Sim', redireciona o foco para a janela DTI."""
        if self._vars["rec"].get() == "Sim":
            self._abrir_janela_dti()
            return "break"

    def _build_form(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True)

        form = tk.Frame(outer, bg=BG, padx=20, pady=12)
        form.pack(side="left", fill="both", expand=True)

        fr_btns = tk.Frame(outer, bg=BG, padx=10, pady=12)
        fr_btns.pack(side="right", anchor="ne")

        # ── Tipo de Etiqueta ──────────────────
        self._vars["tipo"] = tk.StringVar(value="Contagem e Laudo")
        self._label(form, 0, "Tipo de Etiqueta")
        fr_t = tk.Frame(form, bg=BG)
        fr_t.grid(row=0, column=1, sticky="w", pady=3)
        tk.Entry(fr_t, textvariable=self._vars["tipo"], bg=BG_CAMPO,
                 relief="sunken", bd=1, font=FM, width=20,
                 state="readonly", takefocus=False).pack(side="left")
        tk.Button(fr_t, text="▼", bg=BG_BOTAO, relief="raised",
                  width=2, font=FMS, takefocus=False).pack(side="left", padx=2)

        # ── Recebimento Específico ────────────
        self._vars["rec"] = tk.StringVar(value="Não")
        self._label(form, 1, "Recebimento Específico")
        fr_r = tk.Frame(form, bg=BG)
        fr_r.grid(row=1, column=1, sticky="w", pady=3)
        sb = tk.Spinbox(fr_r, values=ENUM_REC, textvariable=self._vars["rec"],
                        bg=BG_CAMPO, relief="sunken", bd=1, font=FM, width=5,
                        state="readonly", readonlybackground=BG_CAMPO)
        sb.pack(side="left")
        tk.Button(fr_r, text="▼", bg=BG_BOTAO, relief="raised",
                  width=2, font=FMS, takefocus=False).pack(side="left", padx=2)
        self._campos["rec"] = sb
        sb.bind("<FocusIn>", lambda e: self._hl(sb, True))
        sb.bind("<FocusOut>", lambda e: self._hl(sb, False))
        sb.bind("<Tab>", self._on_tab_rec)
        sb.bind("<Return>", self._on_tab_rec)
        sb.bind("<Up>", lambda e: self._ciclar(-1))
        sb.bind("<Down>", lambda e: self._ciclar(1))
        sb.bind("s", lambda e: (self._vars["rec"].set("Sim"), self._abrir_janela_dti(), "break")[2])
        sb.bind("S", lambda e: (self._vars["rec"].set("Sim"), self._abrir_janela_dti(), "break")[2])
        sb.bind("n", lambda e: (self._vars["rec"].set("Não"), "break")[1])
        sb.bind("N", lambda e: (self._vars["rec"].set("Não"), "break")[1])

        # ── Nro. Cópias ───────────────────────
        self._vars["copias"] = tk.StringVar(value="1")
        self._label(form, 2, "Nro. Cópias")
        e_cop = tk.Entry(form, textvariable=self._vars["copias"],
                         bg=BG_CAMPO, relief="sunken", bd=1, font=FM, width=6)
        e_cop.grid(row=2, column=1, sticky="w", pady=3)
        e_cop.bind("<FocusIn>", lambda e: self._verificar_trava_rec_especifico() or
                   (self._hl(e_cop, True), e_cop.select_range(0, "end")))
        e_cop.bind("<Button-1>", lambda e: self._verificar_trava_rec_especifico())
        e_cop.bind("<FocusOut>", lambda e: self._hl(e_cop, False))
        self._campos["copias"] = e_cop

        # ── Separador ─────────────────────────
        tk.Frame(form, bg=BORDA, height=1).grid(
            row=3, column=0, columnspan=5, sticky="ew", pady=10)

        # ── Cabeçalhos De / Até ───────────────
        tk.Label(form, text="", bg=BG, font=FM, width=22).grid(row=4, column=0)
        tk.Label(form, text="De", bg=BG, font=FMB).grid(row=4, column=1, sticky="w")
        tk.Label(form, text="Até", bg=BG, font=FMB).grid(row=4, column=3, sticky="w")

        # ── Campos filtro ─────────────────────
        filtros = [
            ("No Recebimento", "dti_de", "dti_ate", "0", "999999"),
            ("Fornecedor", "forn_de", "forn_ate", "", "ZZZZZZ"),
            ("Código do Item", "item_de", "item_ate", "", "ZZZZZZZZZZZZZZ"),
            ("Ordem de Compra", "oc_de", "oc_ate", "0", "999999"),
            ("Número da Posição", "pos_de", "pos_ate", "0", "9999"),
        ]
        for r, (lbl, k_de, k_ate, vd, va) in enumerate(filtros, start=5):
            self._label(form, r, lbl)

            # Campo DE
            vr_de = tk.StringVar(value=vd)
            self._vars[k_de] = vr_de
            e_de = tk.Entry(form, textvariable=vr_de, bg=BG_CAMPO,
                            relief="sunken", bd=1, font=FM, width=12, justify="right")
            e_de.grid(row=r, column=1, sticky="w", pady=3)

            if k_de == "dti_de":
                e_de.bind("<FocusIn>", lambda e, w=e_de: self._verificar_trava_rec_especifico() or (self._hl(w, True),
                                                                                                    w.select_range(0,
                                                                                                                   "end")))
                e_de.bind("<Button-1>", lambda e: self._verificar_trava_rec_especifico())
            else:
                e_de.bind("<FocusIn>", lambda e, w=e_de: (self._hl(w, True), w.select_range(0, "end")))

            e_de.bind("<FocusOut>", lambda e, w=e_de, ka=k_ate: (self._hl(w, False), self._auto_ate(ka)))
            self._campos[k_de] = e_de

            tk.Label(form, text="►", bg=BG, fg=TXT_INATIVO, font=FMS).grid(row=r, column=2, padx=3)

            # Campo ATÉ
            vr_ate = tk.StringVar(value=va)
            self._vars[k_ate] = vr_ate
            e_ate = tk.Entry(form, textvariable=vr_ate, bg=BG_CAMPO,
                             relief="sunken", bd=1, font=FM, width=16, justify="right")
            e_ate.grid(row=r, column=3, sticky="w", pady=3)

            if k_ate == "dti_ate":
                e_ate.bind("<FocusIn>", lambda e, w=e_ate: self._verificar_trava_rec_especifico() or (self._hl(w, True),
                                                                                                      w.select_range(0,
                                                                                                                     "end")))
                e_ate.bind("<Button-1>", lambda e: self._verificar_trava_rec_especifico())
                e_ate.bind("<FocusOut>", lambda e, w=e_ate: self._hl(w, False))
                # Ao apertar TAB no campo DTI Até, pula direto para o botão Continue
                e_ate.bind("<Tab>", lambda e: (self._btn_continue.focus_set(), "break")[1])
            else:
                e_ate.bind("<FocusIn>", lambda e, w=e_ate: (self._hl(w, True), w.select_range(0, "end")))
                e_ate.bind("<FocusOut>", lambda e, w=e_ate: self._hl(w, False))

            tk.Label(form, text="►", bg=BG, fg=TXT_INATIVO, font=FMS).grid(row=r, column=4, padx=3)
            self._campos[k_ate] = e_ate

        # ── Ordenado Por Item ─────────────────
        r_x = len(filtros) + 5
        self._vars["ord"] = tk.StringVar(value="Sim")
        self._label(form, r_x, "Ordenado    Por    Item")
        tk.Spinbox(form, values=["Sim", "Não"], textvariable=self._vars["ord"],
                   bg=BG_CAMPO, relief="sunken", bd=1, font=FM, width=5,
                   state="readonly", readonlybackground=BG_CAMPO,
                   takefocus=False).grid(row=r_x, column=1, sticky="w", pady=3)

        # ── Embarque ──────────────────────────
        r_x += 1
        self._label(form, r_x, "Embarque")
        tk.Entry(form, bg=BG_CAMPO, relief="sunken", bd=1, font=FM,
                 width=20, takefocus=False).grid(row=r_x, column=1, sticky="w", pady=3)

        # ── Impressora ────────────────────────
        r_x += 1
        self._vars["imp"] = tk.StringVar(value="PR_FIS82")
        self._label(form, r_x, "Impressora")
        fr_imp = tk.Frame(form, bg=BG)
        fr_imp.grid(row=r_x, column=1, sticky="w", pady=3)
        tk.Entry(fr_imp, textvariable=self._vars["imp"], bg=BG_CAMPO,
                 relief="sunken", bd=1, font=FM, width=14,
                 takefocus=False).pack(side="left")
        tk.Label(fr_imp, text="►", bg=BG, fg=TXT_INATIVO, font=FMS).pack(side="left", padx=2)

        # ── Mensagem ──────────────────────────
        r_x += 2
        self._label(form, r_x, "Mensagem")
        tk.Label(form, textvariable=self._var_mensagem,
                 bg=BG, fg=BARRA_TXT, font=FM, anchor="w", width=44
                 ).grid(row=r_x, column=1, columnspan=4, sticky="w")

        # ── Botões Continue / Cancel ──────────
        self._btn_continue = tk.Button(
            fr_btns, text="Continue",
            bg=BG_BOTAO, relief="raised", font=FM, width=10,
            command=self._cmd_continue, takefocus=True)
        self._btn_continue.pack(pady=(0, 6))

        self._btn_continue.bind("<Return>", lambda e: self._cmd_continue())
        self._btn_continue.bind("<space>", lambda e: self._cmd_continue())

        tk.Button(fr_btns, text="Cancel",
                  bg=BG_BOTAO, relief="raised", font=FM, width=10,
                  command=self.root.destroy, takefocus=False).pack()

        # ── HABILITA ENTER GLOBAL NO FORMULÁRIO ──
        self.root.bind_all("<Return>", self._ao_pressionar_enter_global)
        self.root.bind_all("<KP_Enter>", self._ao_pressionar_enter_global)

    def _build_statusbar(self):
        sf = tk.Frame(self.root, bg=BARRA_BG, relief="sunken", bd=1, height=22)
        sf.pack(fill="x", side="bottom")
        sf.pack_propagate(False)
        tk.Label(sf, text="Companhia 000  |  Empresa Teste Ltda.",
                 bg=BARRA_BG, fg=TXT_INATIVO, font=FMS).pack(side="left", padx=8)
        tk.Label(sf, text="enum", bg=BARRA_BG, fg=TXT_INATIVO,
                 font=FMS).pack(side="right", padx=8)

    # ─────────────────────────────────────────
    #  HELPERS
    # ─────────────────────────────────────────
    def _label(self, parent, row, texto):
        tk.Label(parent, text=texto, bg=BG, fg=TXT_LABEL,
                 font=FM, anchor="w", width=24
                 ).grid(row=row, column=0, sticky="w", pady=3)

    def _hl(self, w, ativo: bool):
        try:
            w.config(bg=COR_FOCO if ativo else BG_CAMPO)
        except Exception:
            pass

    def _ciclar(self, d: int):
        cur = self._vars["rec"].get()
        idx = ENUM_REC.index(cur) if cur in ENUM_REC else 0
        self._vars["rec"].set(ENUM_REC[(idx + d) % len(ENUM_REC)])

    def _auto_ate(self, chave_ate: str):
        """Copia DTI De → Até ao sair do campo De com TAB."""
        if chave_ate != "dti_ate":
            return
        v = self._vars["dti_de"].get().strip()
        if v and (v.isdigit() or v == "0"):
            self._vars["dti_ate"].set(v)

    # ─────────────────────────────────────────
    #  TAB NO CAMPO RECEBIMENTO ESPECÍFICO
    # ─────────────────────────────────────────
    def _on_tab_rec(self, event=None):
        """
        Comportamento BAAN real:
          Sim + TAB → abre modal "Selecionar Recebimentos Específicos"
          Não + TAB → vai para Nro. Cópias
        """
        v = self._vars["rec"].get()
        log.debug(f"[FAKE] TAB rec={v!r}")
        if v == "Sim":
            self.root.after(80, self._abrir_janela_dti)
        else:
            self._campos["copias"].focus_set()
        return "break"

    # ─────────────────────────────────────────
    #  JANELA DTI
    # ─────────────────────────────────────────
    def _abrir_janela_dti(self):
        if self._janela_dti and self._janela_dti.win.winfo_exists():
            self._janela_dti.win.lift()
            return
        log.info("[FAKE] Abrindo janela DTI")
        self._janela_dti = JanelaSelecaoDTI(
            parent=self.root,
            callback_ok=self._on_dti_ok)

    def _on_dti_ok(self, dtis: list):
        # 1. Ativa a trava para ignorar o Enter residual que veio da janela DTI
        self._bloqueio_enter = True

        self._janela_dti = None
        self._dtis_selecionadas = dtis
        log.info(f"[FAKE] DTIs recebidas: {dtis}")

        def _liberar_e_focar():
            self.root.focus_force()
            if hasattr(self, "_btn_continue") and self._btn_continue:
                self._btn_continue.focus_set()
            # 2. Libera a captura do Enter global na tela principal
            self._bloqueio_enter = False

        # Aguarda 250ms para que o Enter da DTI seja totalmente descartado
        self.root.after(250, _liberar_e_focar)

    # ─────────────────────────────────────────
    #  CONTINUE
    # ─────────────────────────────────────────
    def _cmd_continue(self):
        if self._imprimindo:
            return

        rec = self._vars["rec"].get()
        if rec == "Sim":
            if not self._dtis_selecionadas:
                self._set_msg("⚠ Selecione Recebimentos primeiro.")
                return
            dtis = self._dtis_selecionadas
        else:
            v = self._vars["dti_de"].get().strip()
            if not v or not (v.isdigit() or v == "0") or v == "0":
                # "0" é o valor padrão (não preenchido)
                if v == "0":
                    self._set_msg("⚠ Informe o No. Recebimento.")
                    return
            if not v.isdigit():
                self._set_msg("⚠ No. Recebimento inválido.")
                return
            dtis = [v]

        log.info(f"[FAKE] Continue → DTIs={dtis}")
        self._imprimindo = True
        self.root.after(100, lambda: self._popup_confirmacao(dtis))

    def _ao_pressionar_enter_global(self, event=None):
        # Se a trava temporária estiver ativa ou houver pop-up aberto, ignora o Enter
        if self._bloqueio_enter or self._janela_dti is not None or any(
                isinstance(w, tk.Toplevel) for w in self.root.winfo_children()):
            return

        log.info("[FAKE] Enter capturado no formulário → Chamando Continue")
        self._cmd_continue()
        return "break"

    # ─────────────────────────────────────────
    #  POPUP DE CONFIRMAÇÃO — tdinvs0001.o
    # ─────────────────────────────────────────
    def _popup_confirmacao(self, dtis: list):
        """
        Modal real com Sim/Não.
        Navegação: TAB ↔ SHIFT+TAB entre botões, ENTER aciona focado,
        ←/→ alternam, ESC = Não.
        Foco padrão: botão Não (usuário precisa usar a seta esquerda para ir ao Sim).
        """
        pop = tk.Toplevel(self.root)
        pop.title(TITULO_POPUP + " : Imprimir Etiquetas de Entrada")
        pop.geometry("400x175")
        pop.resizable(False, False)
        pop.configure(bg=BG)
        pop.transient(self.root)
        pop.grab_set()
        pop.protocol("WM_DELETE_WINDOW", lambda: self._popup_nao(pop))

        # Centralizar sobre a janela principal
        self.root.update_idletasks()
        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        pop.geometry(f"+{rx + (rw - 400) // 2}+{ry + (rh - 175) // 2}")

        # Ícone
        tk.Label(pop, text="⚠", bg=BG, font=("Segoe UI Symbol", 28),
                 fg=COR_AVISO).place(x=18, y=24)

        # Mensagem
        tk.Label(pop, text="Confirma Impressao das Etiquetas ?",
                 bg=BG, fg=TXT, font=FMB).place(x=66, y=44)
        n = len(dtis)
        tk.Label(pop, text=f"({n} DTI{'s' if n > 1 else ''}: {', '.join(dtis[:4])}{'...' if n > 4 else ''})",
                 bg=BG, fg=TXT_INATIVO, font=FMS).place(x=66, y=72)

        # Botões
        fr = tk.Frame(pop, bg=BG)
        fr.place(x=66, y=110)

        btn_sim = tk.Button(fr, text="Sim", bg=BG_BOTAO, relief="raised",
                            font=FM, width=8,
                            command=lambda: self._popup_sim(pop, dtis),
                            takefocus=True)
        btn_sim.pack(side="left", padx=(0, 20))

        btn_nao = tk.Button(fr, text="Não", bg=BG_BOTAO, relief="raised",
                            font=FM, width=8,
                            command=lambda: self._popup_nao(pop),
                            takefocus=True)
        btn_nao.pack(side="left")

        # Acionar botão atualmente em foco (Return / Space)
        def acionar_focado(event=None):
            foco = pop.focus_get()
            if foco == btn_sim:
                self._popup_sim(pop, dtis)
            else:
                self._popup_nao(pop)
            return "break"

        # Bindings de teclado
        pop.bind("<Return>", acionar_focado)
        pop.bind("<KP_Enter>", acionar_focado)
        pop.bind("<space>", acionar_focado)
        pop.bind("<Escape>", lambda e: (self._popup_nao(pop), "break")[1])

        # Alternar foco com as setas
        pop.bind("<Left>", lambda e: (btn_sim.focus_set(), "break")[1])
        pop.bind("<Right>", lambda e: (btn_nao.focus_set(), "break")[1])

        # ── FOCO PADRÃO DEFINIDO PARA O BOTÃO NÃO ──
        pop.after(60, btn_nao.focus_set)
        log.info("[FAKE] Popup confirmação aberto (foco inicial: Não)")

    def _popup_sim(self, pop, dtis):
        try:
            pop.grab_release()
            pop.destroy()
        except tk.TclError:
            pass
        # Devolve o foco de janela (nível OS) para a principal assim que o
        # modal fecha — sem isso, em alguns ambientes o foco pode ficar
        # "solto" depois que o Toplevel com grab_set é destruído.
        self.root.focus_force()
        log.info("[FAKE] Popup → Sim → iniciando impressão")
        self._impressao_concluida.clear()
        threading.Thread(target=self._simular_impressao, args=(dtis,), daemon=True).start()
        # Poll agendado NATIVAMENTE na thread principal do Tk (não é uma
        # chamada retransmitida de outra thread). O passo final — devolver
        # o foco para "Recebimento Específico" — precisa rodar assim; feito
        # via after(0, ...) chamado de dentro da thread de impressão, o
        # título/mensagem atualizavam certinho mas o foco não "colava".
        self.root.after(50, self._poll_impressao_concluida)

    def _popup_nao(self, pop):
        try:
            pop.grab_release()
            pop.destroy()
        except tk.TclError:
            pass
        self.root.focus_force()
        self._imprimindo = False
        log.info("[FAKE] Popup → Não → cancelado")

    # ─────────────────────────────────────────
    #  SIMULAÇÃO DE IMPRESSÃO
    # ─────────────────────────────────────────
    def _simular_impressao(self, dtis: list):
        # Marca a janela principal como "ocupada" — a automação espera esse
        # marcador sumir do título antes de começar a próxima caixa.
        self.root.after(0, self._marcar_ocupado)

        for dti in dtis:
            msg = f"Imprimindo Etiqueta : {dti}"
            log.info(f"[FAKE] {msg}")
            self.root.after(0, lambda m=msg: self._set_msg(m))
            time.sleep(0.7)

        self.root.after(0, lambda: self._set_msg("Concluído !"))
        time.sleep(1.2)
        # Apenas sinaliza (primitiva thread-safe) — quem efetivamente chama
        # _resetar() (e portanto devolve o foco) é a thread principal do Tk,
        # via _poll_impressao_concluida.
        self._impressao_concluida.set()

    def _poll_impressao_concluida(self):
        if self._impressao_concluida.is_set():
            self._impressao_concluida.clear()
            self._resetar()
        else:
            self.root.after(50, self._poll_impressao_concluida)

    def _marcar_ocupado(self):
        try:
            self.root.title(f"{TITULO_PRINCIPAL} : {TITULO_OCUPADO}...")
        except tk.TclError:
            pass

    def _resetar(self):
        self._imprimindo = False
        self._vars["dti_de"].set("0")
        self._vars["dti_ate"].set("999999")
        self._set_msg("")
        try:
            self.root.title(TITULO_PRONTO)
        except tk.TclError:
            pass
        # Mesmo reforço de foco usado depois da janela DTI (_liberar_e_focar):
        # garante que a janela principal tem o foco de verdade antes de
        # focar o campo "Recebimento Específico" para a próxima caixa.
        self.root.focus_force()
        self._campos["rec"].focus_set()
        log.info("[FAKE] Pronto para próxima operação.")

    def _set_msg(self, msg: str):
        try:
            self._var_mensagem.set(msg)
        except tk.TclError:
            pass

    # ─────────────────────────────────────────
    #  MAIN LOOP
    # ─────────────────────────────────────────
    def iniciar(self):
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════
#  JANELA DTI: tkcpdo400s000
# ═══════════════════════════════════════════════════════════════
class JanelaSelecaoDTI:
    """
    Grid de 8 colunas × 16 linhas = 128 campos de DTI.

    Navegação (BAAN real):
      TAB / ENTER em campo preenchido → próximo campo (navegação vertical)
      TAB em campo vazio → pula para botão Ok
      SHIFT+TAB volta
      ENTER no botão Ok → confirma
    """

    def _hl(self, widget, focado: bool):
        """Destaca o campo com foco."""
        try:
            cor = COR_FOCO if focado else BG_CAMPO
            widget.config(bg=cor)
        except Exception:
            pass

    def __init__(self, parent: tk.Tk, callback_ok=None):
        self.parent = parent
        self.callback_ok = callback_ok
        self._entries: list = []
        self._vars: list = []
        self._btn_ok: Optional[tk.Button] = None

        self.win = tk.Toplevel(parent)
        self._cfg()
        self._build_menu()
        self._build_toolbar()
        self._build_content()
        self.win.after(100, lambda: self._entries[0].focus_set() if self._entries else None)

    def _cfg(self):
        self.win.title(TITULO_JANELA_DTI + " : Selecionar Recebimentos Específicos [550]")
        self.win.geometry("840x580")
        self.win.resizable(False, False)
        self.win.configure(bg=BG)
        self.win.transient(self.parent)
        self.win.grab_set()
        self.win.protocol("WM_DELETE_WINDOW", self._cancelar)

        self.parent.update_idletasks()
        px, py = self.parent.winfo_x(), self.parent.winfo_y()
        pw, ph = self.parent.winfo_width(), self.parent.winfo_height()
        self.win.geometry(f"+{px + (pw - 840) // 2}+{py + (ph - 580) // 2}")

    def _build_menu(self):
        mb = tk.Menu(self.win)
        for n in ["File", "Edit", "Group", "Workflow", "Options", "Order", "Tools", "Special", "Help"]:
            mb.add_cascade(label=n, menu=tk.Menu(mb, tearoff=0))
        self.win.config(menu=mb)

    def _build_toolbar(self):
        tb = tk.Frame(self.win, bg=BG_TOOLBAR, relief="raised", bd=1, height=34)
        tb.pack(fill="x")
        tb.pack_propagate(False)
        for ico in ["🖫", "🖨", "↩", "⏮", "◀", "▶", "⏭", "T", "?"]:
            tk.Button(tb, text=ico, bg=BG_BOTAO, relief="raised",
                      font=("Segoe UI Symbol", 8), width=2,
                      takefocus=False).pack(side="left", padx=1, pady=3)

    def _build_content(self):
        tk.Label(self.win, text="Recebimento Físico", bg=BG, fg=TXT,
                 font=FMB, anchor="w").pack(anchor="w", padx=16, pady=(8, 4))

        main = tk.Frame(self.win, bg=BG)
        main.pack(fill="both", expand=True, padx=8, pady=4)

        # ── Grid de campos ─────────────────────
        fr_grid = tk.Frame(main, bg=BG)
        fr_grid.pack(side="left", fill="both", expand=True)

        # Matriz temporária para organizar a ordem de tabulação por colunas (0..127)
        matriz_entries = [[None for _ in range(COLS_GRID)] for _ in range(ROWS_GRID)]

        for row in range(ROWS_GRID):
            for col in range(COLS_GRID):
                var = tk.StringVar()
                self._vars.append(var)
                e = tk.Entry(fr_grid, textvariable=var,
                             bg=BG_CAMPO, relief="sunken", bd=1,
                             font=FMS, width=8, justify="right")
                e.grid(row=row, column=col * 2, padx=1, pady=1, sticky="w")

                if row == 0:
                    tk.Label(fr_grid, text="►", bg=BG, fg=TXT_INATIVO,
                             font=("Courier New", 7)
                             ).grid(row=row, column=col * 2 + 1, sticky="w")

                matriz_entries[row][col] = e

        # Achata a matriz na ordem VERTICAL (Coluna por Coluna)
        self._entries = []
        for col in range(COLS_GRID):
            for row in range(ROWS_GRID):
                self._entries.append(matriz_entries[row][col])

        # Binds de eventos na ordem lógica de navegação
        for idx, e in enumerate(self._entries):
            e.bind("<Tab>", lambda ev, i=idx: self._nav_vertical(i))
            e.bind("<Return>", lambda ev, i=idx: self._nav_vertical(i))
            e.bind("<FocusIn>", lambda ev, w=e: (self._hl(w, True), w.select_range(0, "end")))
            e.bind("<FocusOut>", lambda ev, w=e: self._hl(w, False))

        # ── Botões ─────────────────────────────
        fr_btn = tk.Frame(main, bg=BG, padx=14)
        fr_btn.pack(side="right", anchor="n", pady=8)

        self._btn_ok = tk.Button(
            fr_btn, text="Ok", bg=BG_BOTAO, relief="raised",
            font=FM, width=8, command=self._confirmar, takefocus=True)
        self._btn_ok.pack(pady=(0, 8))
        self._btn_ok.bind("<Return>", lambda e: self._confirmar())
        self._btn_ok.bind("<space>", lambda e: self._confirmar())
        self._btn_ok.bind("<FocusIn>", lambda e: self._btn_ok.config(relief="groove"))
        self._btn_ok.bind("<FocusOut>", lambda e: self._btn_ok.config(relief="raised"))

        btn_cancel = tk.Button(fr_btn, text="Cancel", bg=BG_BOTAO, relief="raised",
                               font=FM, width=8, command=self._cancelar, takefocus=False)
        btn_cancel.pack()

        self.win.bind("<Escape>", lambda e: self._cancelar())

    def _nav_vertical(self, idx_atual: int):
        val = self._entries[idx_atual].get().strip()

        # Se o campo atual estiver vazio ou for o último, move o foco para o botão Ok
        if not val or idx_atual == len(self._entries) - 1:
            if self._btn_ok:
                self._btn_ok.focus_set()
        else:
            # Avança para o próximo campo na ordem vertical
            self._entries[idx_atual + 1].focus_set()
        return "break"

    def _confirmar(self):
        dtis = [e.get().strip() for e in self._entries if e.get().strip()]
        if not dtis:
            log.info("[FAKE] JanelaSelecaoDTI VAZIA — Nenhuma DTI inserida")
            return

        log.info(f"[FAKE] JanelaSelecaoDTI OK → {len(dtis)} DTIs")
        cb = self.callback_ok
        try:
            self.win.grab_release()
            self.win.destroy()
        except tk.TclError:
            pass

        if cb:
            cb(dtis)

    def _cancelar(self):
        log.info("[FAKE] JanelaSelecaoDTI Cancelada")
        try:
            self.win.grab_release()
            self.win.destroy()
        except tk.TclError:
            pass


# ═══════════════════════════════════════════════════════════════
#  ENTRADA DIRETA
# ═══════════════════════════════════════════════════════════════
def iniciar():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s.%(msecs)03d  [%(levelname)s]  %(message)s",
        datefmt="%H:%M:%S",
    )
    BaanFake().iniciar()


if __name__ == "__main__":
    iniciar()
