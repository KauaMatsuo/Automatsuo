<p align="center">
  <img src="automatsuo.png" alt="Automatsuo" width="300"/>
</p>

# 🤖 Automatsuo (AutoERP-PrintLabel)

Sistema de automação inteligente (RPA) para processamento e emissão automatizada de etiquetas de entrada em ERPs industriais (compatível com interfaces Baan / Infor LN).

---

## 📸 Demonstração da Interface

| Painel Principal (Fila de Impressão) | Simulador ERP (Baan Fake) |
| :-<img width="780" height="650" alt="Captura de tela 2026-09-21 145014" src="https://github.com/user-attachments/assets/65c5b180-8b70-40fa-ac1f-5f11984c6b02" /><img width="780" height="650" alt="Captura de tela 2026-09-21 145055" src="https://github.com/user-attachments/assets/f4bb94bf-52d3-45c2-888c-5bf1dffc9b33" />

---

## 📌 Sobre o Projeto
O **Automatsuo** é uma solução desenvolvida para otimizar o fluxo operacional de recebimento físico e emissão de etiquetas. A solução lê dados de planilhas de entrada, valida a consistência das informações e interage diretamente com a interface do ERP, eliminando erros manuais de digitação e reduzindo significativamente o tempo de processamento por caixa.

Para garantir testes seguros, isolados e contínuos sem a necessidade de conexão direta com o ambiente de produção do ERP, foi desenvolvido um **simulador completo da interface (Mock Application)**.

---

## 🌟 Principais Destaques e Diferenciais
- **Simulador de ERP Integrado (`baan_fake.py`):** Interface Tkinter fiel às telas reais do ERP para testes end-to-end sem riscos operacionais.
- **Tratamento Avançado de Foco:** Controle rigoroso da caixa de diálogo e navegação por teclado (TAB, ENTER, Setas) via PyAutoGUI, evitando atropelo de comandos.
- **Validação e Tratamento de Dados:** Leitura e higienização automática de dados via Pandas.
- **Testes de Integração Automatizados:** Script de testes em loop de eventos (`teste_fluxo.py`) para validação de regressão na interface.
- **Arquitetura Modular:** Separação clara de responsabilidades entre regras de negócio, interface, logs e automação.

---

## 🛠️ Tecnologias Utilizadas
- **Linguagem:** Python 3.10+
- **Interface Gráfica (Mock):** Tkinter
- **Automação de Interface:** PyAutoGUI / PyGetWindow
- **Manipulação de Dados:** Pandas / OpenPyXL
- **Gerenciamento de Ambientes:** Virtualenv / `uv`

---

## 🚀 Como Executar o Projeto

### Pré-requisitos
- Python instalado (v3.10 ou superior)

### Passo a Passo

1. **Clonar o repositório:**
   ```bash
   git clone https://github.com/SEU-USUARIO/Automatsuo.git
   cd Automatsuo
   ```

2. **Criar e ativar o ambiente virtual:**
   ```bash
   python -m venv .venv
   # Windows (PowerShell):
   .\.venv\Scripts\Activate.ps1
   ```

3. **Instalar as dependências:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Rodar o Simulador do ERP (Baan Fake):**
   ```bash
   python baan_fake.py
   ```

5. **Executar a Automação:**
   ```bash
   python main.py
   ```

6. **Rodar os Testes de Integração da Interface:**
   ```bash
   python teste_fluxo.py
   ```

---

## 🛡️ Segurança e Privacidade
Este projeto foi desenvolvido utilizando dados anonimizados e um simulador próprio para demonstração pública de arquitetura de automação, em total conformidade com boas práticas de governança de dados.
