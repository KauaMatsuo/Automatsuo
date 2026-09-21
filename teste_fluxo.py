"""
Teste de integração dirigido por gerador, rodando dentro do mainloop real
do Tk (na mesma thread que criou a janela). Isso evita os falsos-positivos
de "main thread is not in main loop" / "different apartment" que aparecem
quando se tenta pilotar o Tk manualmente com root.update() fora do
mainloop de verdade — o app real (main.py) sempre roda dentro de
mainloop(), então este é o jeito fiel de testar.
"""
import sys, time, traceback
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from baan_fake import BaanFake

app = BaanFake()
root = app.root

resultado = {"ok": None, "erro": None}


def foco():
    return root.focus_get()


def send_key(keysym):
    w = foco()
    if w is None:
        raise RuntimeError("Nenhum widget com foco!")
    w.event_generate("<KeyPress>", keysym=keysym)


def tab():
    send_key("Tab")


def enter():
    send_key("Return")


def digitar(texto):
    for ch in str(texto):
        send_key(ch)


def obter_botoes_popup(pop):
    achados = {}
    def rec(w):
        for ch in w.winfo_children():
            if isinstance(ch, tk.Button):
                achados[ch.cget("text")] = ch
            rec(ch)
    rec(pop)
    return achados.get("Sim"), achados.get("Não")


def esperar(pred, timeout_s, msg):
    fim = time.time() + timeout_s
    while time.time() < fim:
        if pred():
            return
        yield 0.04
    raise AssertionError(f"timeout esperando: {msg}")


def achar_toplevel(substr):
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel):
            try:
                if substr in w.title():
                    return w
            except tk.TclError:
                pass
    return None


def confirmar_popup_sim():
    yield from esperar(lambda: achar_toplevel("tdinvs0001") is not None, 3.0, "popup abrir")
    pop = achar_toplevel("tdinvs0001")
    btn_sim, btn_nao = obter_botoes_popup(pop)
    assert btn_sim and btn_nao, "botoes do popup nao encontrados"
    yield from esperar(lambda: foco() is btn_nao, 2.0, "foco inicial em Não")
    send_key("Left")
    yield 0.05
    assert foco() is btn_sim, f"seta esquerda nao moveu foco pra Sim, tem {foco()}"
    enter()
    yield 0.05


def processar_simples(dti):
    print(f"\n--- SIMPLES dti={dti} ---")
    app._campos["rec"].focus_set()
    yield 0.08
    assert foco() is app._campos["rec"], f"esperava foco em rec, tem {foco()}"

    digitar("n")
    assert app._vars["rec"].get() == "Não"
    tab()
    yield 0.05
    assert foco() is app._campos["copias"], f"esperava foco em copias, tem {foco()}"

    root.focus_get().select_range(0, "end")
    digitar("1")
    tab()
    yield 0.05
    assert foco() is app._campos["dti_de"], f"esperava foco em dti_de, tem {foco()}"

    digitar(dti)
    tab()
    yield 0.05
    assert app._vars["dti_ate"].get() == dti, f"AUTO-ATE falhou: {app._vars['dti_ate'].get()!r}"
    assert foco() is app._campos["dti_ate"], f"esperava foco em dti_ate, tem {foco()}"

    tab()
    yield 0.05
    assert foco() is app._btn_continue, f"esperava foco no botao Continue, tem {foco()}"

    enter()
    yield from confirmar_popup_sim()

    yield from esperar(lambda: app._vars["dti_de"].get() == "0" and not app._imprimindo,
                       8.0, "impressao terminar e resetar rodar")
    yield 0.2
    if foco() is not app._campos["rec"]:
        print(f"    [aviso] foco pos-impressao={foco()!r} (nao critico p/ esta validacao)")
    print(f"OK simples dti={dti}")


def processar_multipla(dtis):
    print(f"\n--- MULTIPLA dtis={dtis} ---")
    app._campos["rec"].focus_set()
    yield 0.08
    assert foco() is app._campos["rec"], f"esperava foco em rec, tem {foco()}"

    # DEPOIS:
    digitar("s")
    yield from esperar(lambda: app._janela_dti is not None and app._janela_dti.win.winfo_exists(),
                       3.0, "janela DTI abrir")
    dw = app._janela_dti

    # Aguarda o foco sair do Spinbox e ir para a 1ª célula do grid (até 2 segundos)
    yield from esperar(lambda: foco() is dw._entries[0], 2.0, "foco ir para a 1a célula do grid DTI")
    for dti in dtis:
        digitar(dti)
        tab()
        yield 0.05

    tab()
    yield 0.05
    assert foco() is dw._btn_ok, f"esperava foco no botao Ok, tem {foco()}"

    enter()
    yield from esperar(lambda: foco() is app._btn_continue, 3.0,
                       "foco voltar pro Continue depois do Ok")
    assert app._dtis_selecionadas == dtis, f"DTIs selecionadas != esperado: {app._dtis_selecionadas}"

    enter()
    yield from confirmar_popup_sim()

    yield from esperar(lambda: app._vars["dti_de"].get() == "0" and not app._imprimindo,
                       10.0, "impressao terminar e resetar rodar (multipla)")
    yield 0.2
    if foco() is not app._campos["rec"]:
        print(f"    [aviso] foco pos-impressao={foco()!r} (nao critico p/ esta validacao)")
    print(f"OK multipla dtis={dtis}")


def fluxo_completo():
    sequencia = [
        ("simples", "547821"),
        ("multipla", ["100001", "100002", "100003"]),
        ("simples", "998877"),
        ("multipla", ["555001", "555002"]),
        ("multipla", ["777001", "777002", "777003", "777004"]),
        ("simples", "111222"),
    ]
    yield from esperar(lambda: foco() is app._campos["rec"], 3.0, "foco inicial em rec")
    for tipo, dado in sequencia:
        if tipo == "simples":
            yield from processar_simples(dado)
        else:
            yield from processar_multipla(dado)
    print("\n============================")
    print("TODAS AS CAIXAS OK — nenhuma DTI caiu em campo errado.")
    print("============================")


_gen = fluxo_completo()
_estado = {"proxima_hora": 0.0}


def _tick():
    if time.time() < _estado["proxima_hora"]:
        root.after(15, _tick)
        return
    try:
        espera = next(_gen)
        _estado["proxima_hora"] = time.time() + (espera or 0.01)
        root.after(15, _tick)
    except StopIteration:
        resultado["ok"] = True
        root.quit()
    except Exception as e:
        resultado["ok"] = False
        resultado["erro"] = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        root.quit()


root.after(300, _tick)
root.mainloop()

print()
if resultado["ok"]:
    print("RESULTADO: SUCESSO")
else:
    print("RESULTADO: FALHA")
    print(resultado["erro"])

try:
    root.destroy()
except tk.TclError:
    pass

sys.exit(0 if resultado["ok"] else 1)
