"""
automacao.py — AUTOMATSUO V3
Motor de automação do BAAN com navegação determinística.

Correções desta versão (v3.0.1):
  ✔ _simples()/_multipla() não fazem mais um TAB "às cegas" no início.
    O foco já está garantido em "Recebimento Específico" ao final de
    cada ciclo (veja _aguardar_impressao). O TAB extra que existia antes
    empurrava o foco para o campo seguinte ANTES de definirmos Sim/Não,
    e é isso que fazia a DTI (ou o "n"/"s") cair em campo errado quando
    caixas simples e múltiplas se alternavam.
  ✔ Definir "Sim" no campo Recebimento Específico já abre a janela DTI
    sozinho (é o próprio BAAN Fake que faz isso ao detectar a tecla "S").
    Não é necessário official TAB/ENTER extra depois — e enviar esse
    extra atrapalhava o timing de abertura da janela.
  ✔ _aguardar_impressao() agora espera o marcador "Imprimindo" sumir do
    título da janela principal (não só o popup fechar). No BAAN Fake o
    popup fecha ANTES da impressão terminar de fato, então esperar só o
    popup sumir liberava a próxima caixa cedo demais — momento em que o
    foco ainda não tinha voltado para "Recebimento Específico".
"""

import threading
import time
from enum import Enum
from typing import Callable, List, Optional

from config import (
    TITULO_PRINCIPAL, TITULO_JANELA_DTI, TITULO_POPUP, TITULO_OCUPADO,
    DELAY_TECLA, DELAY_ACAO, DELAY_JANELA,
    DELAY_ENTRE_CAIXAS, TIMEOUT_JANELA, TIMEOUT_IMPRESSAO,
    MODO_TESTE, MAX_DTIS_GRID,
)
from estado import (
    Caixa, StatusCaixa, StatusGlobal, TipoCaixa,
    gerenciador_estado,
)
from logger import get_logger

log = get_logger("automacao")


# ─────────────────────────────────────────────
#  BACKEND DE AUTOMAÇÃO
# ─────────────────────────────────────────────
try:
    import pyautogui
    import pygetwindow as gw
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = DELAY_TECLA
    _REAL = True
    log.info("pyautogui/pygetwindow OK — modo REAL ativo")
except ImportError:
    _REAL = False
    log.warning("pyautogui/pygetwindow ausentes — modo SIMULAÇÃO ativo")


# ─────────────────────────────────────────────
#  EXCEÇÕES
# ─────────────────────────────────────────────
class InterrupcaoException(Exception):
    """Usuário pressionou PARAR."""


class JanelaException(Exception):
    """Janela esperada não encontrada no timeout."""


class NavegacaoException(Exception):
    """Falha na navegação de campos."""


# ─────────────────────────────────────────────
#  CONTEXTO DEBUG (compartilhado com interface)
# ─────────────────────────────────────────────
class DebugCtx:
    __slots__ = ("etapa", "janela", "campo", "proxima",
                 "ultimo_tab", "ultimo_enter", "_cb", "_lock")

    def __init__(self):
        self.etapa        = "—"
        self.janela       = "—"
        self.campo        = "—"
        self.proxima      = "—"
        self.ultimo_tab   = "—"
        self.ultimo_enter = "—"
        self._cb          = None
        self._lock        = threading.Lock()

    def set(self, **kw):
        with self._lock:
            for k, v in kw.items():
                if hasattr(self, k) and not k.startswith("_"):
                    setattr(self, k, v)
        if self._cb:
            try:
                self._cb(self.snapshot())
            except Exception:
                pass

    def snapshot(self) -> dict:
        with self._lock:
            return {s: getattr(self, s) for s in self.__slots__
                    if not s.startswith("_")}

    def registrar_callback(self, cb: Callable):
        self._cb = cb


debug = DebugCtx()


# ═══════════════════════════════════════════════════════════════
#  MOTOR
# ═══════════════════════════════════════════════════════════════
class MotorAutomacao:

    def __init__(self):
        self._thread:    Optional[threading.Thread] = None
        self._pausado    = threading.Event()
        self._pausado.set()       # set = NÃO pausado
        self._parar      = threading.Event()
        self._modo_teste = MODO_TESTE

        # Callbacks → interface
        self.on_status:          Optional[Callable] = None
        self.on_caixa_iniciada:  Optional[Callable] = None
        self.on_caixa_concluida: Optional[Callable] = None
        self.on_caixa_erro:      Optional[Callable] = None
        self.on_progresso:       Optional[Callable] = None
        self.on_concluido:       Optional[Callable] = None

    # ── API pública ──────────────────────────
    def iniciar(self, modo_teste: bool = False) -> bool:
        if self._thread and self._thread.is_alive():
            log.warning("Motor já em execução.")
            return False
        self._modo_teste = modo_teste
        self._parar.clear()
        self._pausado.set()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="Motor")
        self._thread.start()
        log.info(f"Motor iniciado | teste={modo_teste} | real={_REAL}")
        return True

    def parar(self):
        log.info("PARAR solicitado.")
        self._parar.set()
        self._pausado.set()
        self._emit_status(StatusGlobal.PARADO, "Parado pelo usuário.")
        gerenciador_estado.atualizar_status(StatusGlobal.PARADO)

    def pausar(self):
        if self._pausado.is_set():
            log.info("PAUSAR solicitado.")
            self._pausado.clear()
            self._emit_status(StatusGlobal.PAUSADO, "Pausado.")
            gerenciador_estado.atualizar_status(StatusGlobal.PAUSADO)

    def continuar(self):
        if not self._pausado.is_set():
            log.info("CONTINUAR solicitado.")
            self._pausado.set()
            self._emit_status(StatusGlobal.IMPRIMINDO, "Retomado.")
            gerenciador_estado.atualizar_status(StatusGlobal.IMPRIMINDO)

    def esta_rodando(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def esta_pausado(self) -> bool:
        return not self._pausado.is_set()

    # ── Loop principal ───────────────────────
    def _loop(self):
        fila = gerenciador_estado.get_fila()
        est = gerenciador_estado.estado

        if not fila:
            self._emit_status(StatusGlobal.ERRO, "Fila vazia.")
            return

        total = len(fila)
        idx = est.indice_atual

        if idx >= total:
            idx = 0
            gerenciador_estado.estado.indice_atual = 0

        self._emit_status(StatusGlobal.IMPRIMINDO,
                          f"Iniciando — {total} caixas (a partir de #{idx + 1}).")
        gerenciador_estado.atualizar_status(StatusGlobal.IMPRIMINDO)

        while idx < total:
            self._chk()
            self._aguardar_pausado()
            self._chk()

            caixa = gerenciador_estado.get_caixa(idx)
            if not caixa:
                idx += 1
                continue

            gerenciador_estado.atualizar_status_caixa(idx, StatusCaixa.ATUAL)
            gerenciador_estado.atualizar_status(
                StatusGlobal.IMPRIMINDO, caixa=caixa.caixa)
            self._emit_caixa_iniciada(idx, caixa)
            self._emit_progresso(idx, total)

            try:
                quantidade_dtis = len([d for d in caixa.dtis if d and str(d).strip()])
                usar_multipla = (caixa.tipo == TipoCaixa.MULTIPLA.value or quantidade_dtis > 1)

                if usar_multipla:
                    log.info(f"[FILA] {caixa.caixa} → {quantidade_dtis} DTIs → MÚLTIPLA")
                    self._multipla(caixa)
                else:
                    log.info(f"[FILA] {caixa.caixa} → 1 DTI → SIMPLES")
                    self._simples(caixa)

                gerenciador_estado.atualizar_status_caixa(idx, StatusCaixa.CONCLUIDA)
                self._emit_caixa_concluida(idx, caixa)
                log.sucesso(f"✔ {caixa.caixa}")

            except InterrupcaoException:
                log.info(f"Interrompido em #{idx + 1} {caixa.caixa}.")
                gerenciador_estado.salvar()
                return

            except (JanelaException, NavegacaoException) as e:
                log.error(f"Erro navegação [{caixa.caixa}]: {e}")
                gerenciador_estado.atualizar_status_caixa(idx, StatusCaixa.ERRO)
                self._emit_caixa_erro(idx, caixa, str(e))

            except Exception as e:
                log.error(f"Erro inesperado [{caixa.caixa}]: {e}", exc_info=True)
                gerenciador_estado.atualizar_status_caixa(idx, StatusCaixa.ERRO)
                self._emit_caixa_erro(idx, caixa, str(e))

            idx += 1
            gerenciador_estado.avancar_indice()
            self._sleep(DELAY_ENTRE_CAIXAS)

        if not self._parar.is_set():
            gerenciador_estado.atualizar_status(StatusGlobal.CONCLUIDO)
            self._emit_status(StatusGlobal.CONCLUIDO, "Todas as caixas processadas!")
            log.sucesso("Automação concluída.")
            if self.on_concluido:
                self.on_concluido()
        else:
            gerenciador_estado.salvar()

    # ═══════════════════════════════════════
    #  FLUXO SIMPLES (1 DTI)
    # ═══════════════════════════════════════
    #
    # Pré-condição garantida antes de chamar este método: o foco no BAAN
    # (real ou fake) está em "Recebimento Específico" — isso é assegurado
    # pelo fim do ciclo anterior em _aguardar_impressao().
    #
    # Sequência:
    #   1. Rec.Específico: tecla "n" (fixa "Não", sem mover o foco)
    #   2. TAB            → Não => foco pula direto para "Nro. Cópias"
    #   3. Cópias: garante "1" e TAB → foco vai para "No Recebimento (De)"
    #   4. DTI De: digita a DTI, TAB → auto-preenche "Até" e move o foco pra lá
    #   5. DTI Até: TAB → pula direto para o botão Continue
    #   6. Continue (ENTER) → abre popup de confirmação
    #   7. Popup: seta ESQUERDA (Não → Sim) + ENTER → confirma impressão
    #
    def _simples(self, caixa: Caixa):
        dti = str(caixa.dtis[0]).strip()
        log.info(f"[SIMPLES] {caixa.caixa} → DTI={dti}")
        debug.set(etapa="SIMPLES", janela=TITULO_PRINCIPAL, campo="iniciando")

        if not _REAL:
            self._simular(1.0, caixa.caixa, ["focar", "Rec.Esp=Não", "Cópias=1",
                                              "DTI De/Até", "Continue", "Sim", "impressão"])
            return

        self._focar_principal()
        self._sleep(0.3)

        # 1-2. Recebimento Específico = Não → avança para Cópias
        debug.set(campo="Recebimento Específico", proxima="Definir NÃO")
        self._digitar("n", "Rec.Específico = Não")
        self._sleep(0.15)
        self._tab("Rec.Específico(Não) → Cópias")
        self._sleep(0.15)

        # 3. Nro. Cópias = 1 → avança para DTI De
        debug.set(campo="Nro. Cópias")
        self._selecionar_tudo()
        self._digitar("1", "Cópias = 1")
        self._sleep(0.15)
        self._tab("Cópias → No Recebimento (De)")
        self._sleep(0.15)

        # 4. DTI De → TAB copia automaticamente para "Até" e move o foco
        debug.set(campo="No Recebimento (De)")
        self._selecionar_tudo()
        self._digitar(dti, f"No Recebimento De = {dti}")
        self._sleep(0.15)
        self._tab("DTI De → DTI Até (auto-preenchido)")
        self._sleep(0.15)

        if self._modo_teste:
            log.info(f"[TESTE] Parado antes de Continue — {caixa.caixa}")
            return

        # 5. DTI Até já está preenchido — TAB pula direto para Continue
        debug.set(campo="No Recebimento (Até)")
        self._tab("DTI Até → Continue")
        self._sleep(0.2)

        # 6. Continue → abre popup de confirmação
        debug.set(campo="Continue", proxima="Confirmar impressão")
        self._enter("Continue")
        self._sleep(DELAY_JANELA)

        if not self._aguardar_janela(TITULO_POPUP):
            raise JanelaException(f"Popup não apareceu (timeout={TIMEOUT_JANELA}s)")

        # 7. Popup: Não → Sim (seta esquerda) + Enter confirma
        self._sleep(0.3)
        self._key("left", "popup: Não → Sim")
        self._sleep(0.2)
        self._enter("popup → confirmar Sim")

        self._aguardar_impressao(dti)
        log.sucesso(f"[SIMPLES] OK — DTI={dti}")

    # ═══════════════════════════════════════
    #  FLUXO MÚLTIPLA (2+ DTIs)
    # ═══════════════════════════════════════
    #
    # Mesma pré-condição: foco já está em "Recebimento Específico".
    #
    # Sequência:
    #   1. Rec.Específico: tecla "s" → já define "Sim" E abre a janela DTI
    #      sozinho (nenhum TAB/ENTER extra é necessário aqui)
    #   2. Para cada DTI: digita e TAB (grid navega verticalmente)
    #   3. Após a última DTI, o campo seguinte fica vazio → mais um TAB
    #      pula direto para o botão Ok
    #   4. Ok (ENTER) → fecha a janela e devolve o foco para Continue,
    #      na janela principal
    #   5. Continue (ENTER) → abre popup de confirmação
    #   6. Popup: seta ESQUERDA (Não → Sim) + ENTER → confirma impressão
    #
    def _multipla(self, caixa: Caixa):
        dtis = [str(d).strip() for d in caixa.dtis if str(d).strip()]
        n = len(dtis)
        log.info(f"[MÚLTIPLA] {caixa.caixa} → {n} DTIs: {dtis}")
        debug.set(etapa="MÚLTIPLA", janela=TITULO_PRINCIPAL, campo="iniciando")

        if n > MAX_DTIS_GRID:
            log.warning(f"[MÚLTIPLA] {caixa.caixa} tem {n} DTIs — grid só "
                        f"comporta {MAX_DTIS_GRID}. Truncando.")
            dtis = dtis[:MAX_DTIS_GRID]
            n = len(dtis)

        if not _REAL:
            self._simular(1.5, caixa.caixa,
                          ["focar", "Rec.Esp=Sim (abre janela DTI)",
                           f"inserir {n} DTIs", "Ok", "Continue", "Sim", "impressão"])
            return

        # 1. Focar a janela principal (foco já deve estar em Rec.Específico)
        self._focar_principal()
        self._sleep(0.3)

        # 2. Recebimento Específico = Sim → abre a janela DTI sozinho
        debug.set(campo="Recebimento Específico", proxima="Definir SIM (abre janela DTI)")
        self._digitar("s", "Rec.Específico = Sim (abre janela DTI)")
        self._sleep(DELAY_JANELA + 0.2)

        if not self._aguardar_janela(TITULO_JANELA_DTI):
            raise JanelaException(f"Janela DTI não abriu (timeout={TIMEOUT_JANELA}s)")

        self._sleep(0.3)
        debug.set(janela=TITULO_JANELA_DTI)

        # 3. Preencher os DTIs em ordem vertical (um TAB depois de cada)
        for i, dti in enumerate(dtis):
            self._chk()
            self._aguardar_pausado()
            debug.set(campo=f"DTI[{i + 1}]/{n}")
            self._digitar(dti, f"DTI[{i + 1}]={dti}")
            self._sleep(0.15)
            self._tab(f"DTI[{i + 1}] → próximo campo")
            self._sleep(0.15)

        # 4. Agora estamos parados num campo vazio (logo após a última DTI).
        #    Mais um TAB nesse campo vazio pula direto para o botão Ok.
        debug.set(campo="campo vazio → Ok")
        self._tab("campo vazio → botão Ok")
        self._sleep(0.2)

        if self._modo_teste:
            log.info(f"[TESTE] Parado antes de confirmar Ok/Continue — {caixa.caixa}")
            return

        self._enter("confirmar Ok (janela DTI)")
        # Aguarda a janela fechar e o foco voltar para o botão Continue
        # na janela principal (o BAAN Fake faz isso ~250ms depois do Ok).
        self._sleep(DELAY_JANELA + 0.35)

        # 5. Continue (foco já está nele) → abre popup de confirmação
        debug.set(janela=TITULO_PRINCIPAL, campo="Continue", proxima="Confirmar impressão")
        self._enter("Continue")
        self._sleep(DELAY_JANELA)

        if not self._aguardar_janela(TITULO_POPUP):
            raise JanelaException("Popup de confirmação não apareceu após inserção de DTIs")

        # 6. Popup: Não → Sim (seta esquerda) + Enter confirma
        self._sleep(0.3)
        self._key("left", "popup: Não → Sim")
        self._sleep(0.2)
        self._enter("popup → confirmar Sim")

        self._aguardar_impressao(caixa.caixa)
        log.sucesso(f"[MÚLTIPLA] OK — {caixa.caixa}")

    # ═══════════════════════════════════════
    #  FOCO DE JANELA ROBUSTO (FORÇA WINDOWS)
    # ═══════════════════════════════════════
    def _focar_principal(self, focar_rec_especifico: bool = False):
        """Traz a janela principal para o primeiro plano de forma forçada."""
        if not _REAL:
            return
        import pygetwindow as _gw
        debug.set(proxima="focar janela principal")

        deadline = time.time() + TIMEOUT_JANELA
        while time.time() < deadline:
            self._chk()
            try:
                wins = [w for w in _gw.getAllWindows()
                        if TITULO_PRINCIPAL in (w.title or "")]
                if wins:
                    w = wins[0]
                    if hasattr(w, 'isMinimized') and w.isMinimized:
                        w.restore()

                    try:
                        import win32gui
                        win32gui.SetForegroundWindow(w._hWnd)
                    except Exception:
                        w.activate()

                    self._sleep(0.2)
                    debug.set(janela=w.title)
                    return
            except Exception as e:
                log.debug(f"[FOCO] tentativa falhou: {e}")
            time.sleep(0.25)

        raise JanelaException(f"Janela principal não encontrada: {TITULO_PRINCIPAL!r}")

    def _aguardar_janela(self, titulo: str, focar_corpo: bool = False) -> bool:
        """Aguarda a janela surgir e ativa o foco pelo Windows."""
        if not _REAL:
            return True
        import pygetwindow as _gw
        deadline = time.time() + TIMEOUT_JANELA
        while time.time() < deadline:
            self._chk()
            try:
                for w in _gw.getAllWindows():
                    if titulo.lower() in (w.title or "").lower():
                        if hasattr(w, 'isMinimized') and w.isMinimized:
                            w.restore()
                        try:
                            import win32gui
                            win32gui.SetForegroundWindow(w._hWnd)
                        except Exception:
                            w.activate()

                        self._sleep(0.2)
                        debug.set(janela=w.title)
                        log.debug(f"[JANELA] Encontrada: {w.title!r}")
                        return True
            except Exception as e:
                log.debug(f"[JANELA] erro: {e}")
            time.sleep(0.18)
        log.warning(f"[JANELA] Timeout: {titulo!r}")
        return False

    def _aguardar_impressao(self, ident: str):
        """
        Espera a impressão realmente terminar E o foco já ter voltado
        para "Recebimento Específico" antes de liberar a próxima caixa.

        Dois estágios:
          1. Espera o popup de confirmação sumir (some assim que o "Sim"
             é clicado — não significa que a impressão já terminou).
          2. Espera o marcador de "ocupado" sumir do título da janela
             principal — esse marcador só some quando o BAAN Fake já
             terminou de "imprimir" e recolocou o foco em
             "Recebimento Específico" (ver _resetar em baan_fake.py).
        """
        if not _REAL:
            self._sleep(0.8)
            return

        import pygetwindow as _gw
        log.debug(f"[IMPRESSÃO] Aguardando: {ident}")
        deadline = time.time() + TIMEOUT_IMPRESSAO

        # Estágio 1 — popup sumir
        while time.time() < deadline:
            self._chk()
            self._aguardar_pausado()
            try:
                popup = any(TITULO_POPUP.lower() in (w.title or "").lower()
                            for w in _gw.getAllWindows())
                if not popup:
                    break
            except Exception:
                pass
            time.sleep(0.15)
        else:
            log.warning(f"[IMPRESSÃO] Timeout esperando popup fechar: {ident}")

        # Estágio 2 — marcador de ocupado sumir do título principal
        while time.time() < deadline:
            self._chk()
            self._aguardar_pausado()
            try:
                ocupado = any(
                    TITULO_PRINCIPAL in (w.title or "") and
                    TITULO_OCUPADO.lower() in (w.title or "").lower()
                    for w in _gw.getAllWindows()
                )
                if not ocupado:
                    log.debug("[IMPRESSÃO] Pronto — foco de volta em Rec.Específico.")
                    self._sleep(0.3)
                    return
            except Exception:
                pass
            time.sleep(0.15)

        log.warning(f"[IMPRESSÃO] Timeout aguardando pronto: {ident}")
        self._sleep(0.4)

    # ═══════════════════════════════════════
    #  PRIMITIVAS DE TECLADO
    # ═══════════════════════════════════════

    def _key(self, tecla: str, desc: str = ""):
        self._chk()
        if _REAL:
            if "+" in tecla:
                keys = [k.strip() for k in tecla.split("+")]
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(tecla)
        log.debug(f"[KEY:{tecla.upper()}] {desc}")
        time.sleep(DELAY_TECLA)

    def _tab(self, desc: str = ""):
        self._chk()
        if _REAL:
            pyautogui.press("tab")
        ts = time.strftime("%H:%M:%S")
        debug.set(ultimo_tab=f"{ts} {desc}")
        log.debug(f"[TAB] {desc}")
        time.sleep(DELAY_TECLA)

    def _enter(self, desc: str = ""):
        self._chk()
        if _REAL:
            pyautogui.press("enter")
        ts = time.strftime("%H:%M:%S")
        debug.set(ultimo_enter=f"{ts} {desc}")
        log.debug(f"[ENTER] {desc}")
        time.sleep(DELAY_TECLA)

    def _digitar(self, texto: str, desc: str = ""):
        self._chk()
        if _REAL:
            pyautogui.typewrite(str(texto), interval=DELAY_TECLA)
        log.debug(f"[TYPE] {desc or repr(texto)}")
        time.sleep(DELAY_TECLA)

    def _selecionar_tudo(self):
        """Ctrl+A defensivo antes de digitar — garante que o valor digitado
        substitui o que já estava no campo, em vez de ser concatenado."""
        self._chk()
        if _REAL:
            pyautogui.hotkey("ctrl", "a")
        log.debug("[SELECT] Ctrl+A")
        time.sleep(DELAY_TECLA)

    def _limpar(self):
        """Limpeza alternativa via Backspace (mantida por compatibilidade)."""
        self._chk()
        if _REAL:
            pyautogui.press("backspace", presses=15, interval=0.01)
        log.debug("[LIMPAR] Backspace x15")
        time.sleep(DELAY_TECLA)

    # ═══════════════════════════════════════
    #  SIMULAÇÃO (sem pyautogui)
    # ═══════════════════════════════════════

    def _simular(self, dur: float, nome: str, passos: List[str]):
        log.info(f"[SIM] {nome} ({dur:.1f}s)")
        fim = time.time() + dur
        for p in passos:
            if time.time() >= fim:
                break
            debug.set(proxima=p)
            self._sleep(dur / max(len(passos), 1))

    # ═══════════════════════════════════════
    #  CONTROLE INTERNO
    # ═══════════════════════════════════════

    def _sleep(self, s: float):
        if s <= 0:
            return
        fim = time.time() + s
        while time.time() < fim:
            self._chk()
            self._pausado.wait(timeout=0.05)
            restante = fim - time.time()
            if restante > 0:
                time.sleep(min(0.04, restante))

    def _chk(self):
        if self._parar.is_set():
            raise InterrupcaoException("Parado pelo usuário.")

    def _aguardar_pausado(self):
        while not self._pausado.is_set():
            if self._parar.is_set():
                raise InterrupcaoException("Parado durante pausa.")
            time.sleep(0.1)

    # ═══════════════════════════════════════
    #  CALLBACKS
    # ═══════════════════════════════════════

    def _emit_status(self, s: StatusGlobal, msg: str = ""):
        if self.on_status:
            try:
                self.on_status(s, msg)
            except Exception:
                pass

    def _emit_caixa_iniciada(self, idx: int, c: Caixa):
        if self.on_caixa_iniciada:
            try:
                self.on_caixa_iniciada(idx, c)
            except Exception:
                pass

    def _emit_caixa_concluida(self, idx: int, c: Caixa):
        if self.on_caixa_concluida:
            try:
                self.on_caixa_concluida(idx, c)
            except Exception:
                pass

    def _emit_caixa_erro(self, idx: int, c: Caixa, e: str):
        if self.on_caixa_erro:
            try:
                self.on_caixa_erro(idx, c, e)
            except Exception:
                pass

    def _emit_progresso(self, atual: int, total: int):
        if self.on_progresso:
            try:
                self.on_progresso(atual, total)
            except Exception:
                pass


# Singleton global
motor = MotorAutomacao()
