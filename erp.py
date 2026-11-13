"""
Gestão Comercial Local - Tkinter + SQLite
Requisitos:
    pip install reportlab

Execute:
    python gestao_comercial.py

O banco gestao_comercial.db será criado automaticamente na mesma pasta.
"""

import os
import sqlite3
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    )
    PDF_DISPONIVEL = True
except ImportError:
    PDF_DISPONIVEL = False


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "gestao_comercial.db"


def conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def inicializar_banco():
    with conectar() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS empresa (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            nome TEXT NOT NULL DEFAULT '',
            contato TEXT DEFAULT '',
            cnpj TEXT DEFAULT '',
            endereco TEXT DEFAULT '',
            representantes TEXT DEFAULT ''
        );

        INSERT OR IGNORE INTO empresa
            (id, nome, contato, cnpj, endereco, representantes)
        VALUES (1, 'Minha Empresa', '', '', '', '');

        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            documento TEXT DEFAULT '',
            telefone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            endereco TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS fornecedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            documento TEXT DEFAULT '',
            telefone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            endereco TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT DEFAULT '',
            descricao TEXT NOT NULL,
            unidade TEXT DEFAULT 'UN',
            preco_venda INTEGER NOT NULL DEFAULT 0,
            preco_compra INTEGER NOT NULL DEFAULT 0,
            estoque REAL NOT NULL DEFAULT 0,
            estoque_minimo REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            numero TEXT NOT NULL UNIQUE,
            data TEXT NOT NULL,
            pessoa_id INTEGER,
            pessoa_nome TEXT NOT NULL,
            observacoes TEXT DEFAULT '',
            total INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'ABERTO',
            criado_em TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS documento_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            documento_id INTEGER NOT NULL,
            produto_id INTEGER,
            codigo TEXT DEFAULT '',
            descricao TEXT NOT NULL,
            quantidade REAL NOT NULL,
            valor_unitario INTEGER NOT NULL,
            total_item INTEGER NOT NULL,
            FOREIGN KEY(documento_id) REFERENCES documentos(id) ON DELETE CASCADE,
            FOREIGN KEY(produto_id) REFERENCES produtos(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_documentos_tipo
            ON documentos(tipo);
        """)


def dinheiro_para_centavos(valor):
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if not texto:
        raise ValueError("Informe um valor.")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    numero = Decimal(texto)
    if not numero.is_finite():
        raise ValueError("Valor inválido.")
    return int((numero * 100).quantize(Decimal("1")))


def formatar_dinheiro(centavos):
    valor = Decimal(int(centavos or 0)) / 100
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_numero(numero):
    return f"{numero:,.3f}".rstrip("0").rstrip(".").replace(",", "X").replace(".", ",").replace("X", ".")


def proximo_numero(tipo):
    prefixos = {"PROPOSTA": "PROP", "VENDA": "PV", "COMPRA": "PC"}
    prefixo = prefixos[tipo]
    with conectar() as conn:
        linha = conn.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 AS proximo FROM documentos WHERE tipo=?",
            (tipo,)
        ).fetchone()
    return f"{prefixo}-{linha['proximo']:06d}"


def obter_empresa():
    with conectar() as conn:
        return conn.execute("SELECT * FROM empresa WHERE id=1").fetchone()


class GestaoComercial:
    def __init__(self, root):
        self.root = root
        self.root.title("Sistema de Gestão Comercial")
        self.root.geometry("1200x760")
        self.root.minsize(980, 620)
        self.criar_interface()
        self.atualizar_todas_listas()

    def criar_interface(self):
        topo = ttk.Frame(self.root, padding=(14, 10))
        topo.pack(fill="x")
        ttk.Label(topo, text="GESTÃO COMERCIAL", font=("Arial", 20, "bold")).pack(side="left")
        ttk.Label(
            topo, text="Python • Tkinter • SQLite",
            font=("Arial", 10)
        ).pack(side="right")

        self.abas = ttk.Notebook(self.root)
        self.abas.pack(fill="both", expand=True, padx=10, pady=8)

        self.aba_empresa = ttk.Frame(self.abas, padding=14)
        self.aba_clientes = ttk.Frame(self.abas, padding=10)
        self.aba_fornecedores = ttk.Frame(self.abas, padding=10)
        self.aba_produtos = ttk.Frame(self.abas, padding=10)
        self.aba_propostas = ttk.Frame(self.abas, padding=10)
        self.aba_vendas = ttk.Frame(self.abas, padding=10)
        self.aba_compras = ttk.Frame(self.abas, padding=10)

        for frame, titulo in [
            (self.aba_empresa, "Empresa"),
            (self.aba_clientes, "Clientes"),
            (self.aba_fornecedores, "Fornecedores"),
            (self.aba_produtos, "Produtos / Estoque"),
            (self.aba_propostas, "Propostas"),
            (self.aba_vendas, "Pedidos de venda"),
            (self.aba_compras, "Pedidos de compra")
        ]:
            self.abas.add(frame, text=titulo)

        self.criar_aba_empresa()
        self.criar_aba_cadastros(
            self.aba_clientes, "clientes",
            [("nome", "Nome"), ("documento", "CPF/CNPJ"),
             ("telefone", "Telefone"), ("email", "E-mail"),
             ("endereco", "Endereço")]
        )
        self.criar_aba_cadastros(
            self.aba_fornecedores, "fornecedores",
            [("nome", "Nome"), ("documento", "CNPJ/CPF"),
             ("telefone", "Telefone"), ("email", "E-mail"),
             ("endereco", "Endereço")]
        )
        self.criar_aba_produtos()
        self.criar_aba_documentos(self.aba_propostas, "PROPOSTA")
        self.criar_aba_documentos(self.aba_vendas, "VENDA")
        self.criar_aba_documentos(self.aba_compras, "COMPRA")

    def criar_aba_empresa(self):
        ttk.Label(
            self.aba_empresa, text="Dados da empresa",
            font=("Arial", 15, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        self.empresa_vars = {}
        campos = [
            ("nome", "Nome da empresa"),
            ("contato", "Contato (telefone / e-mail)"),
            ("cnpj", "CNPJ"),
            ("endereco", "Endereço"),
            ("representantes", "Representantes")
        ]
        dados = obter_empresa()
        for i, (chave, rotulo) in enumerate(campos, start=1):
            ttk.Label(self.aba_empresa, text=rotulo).grid(
                row=i, column=0, sticky="w", pady=7, padx=(0, 12)
            )
            var = tk.StringVar(value=dados[chave] or "")
            self.empresa_vars[chave] = var
            ttk.Entry(
                self.aba_empresa, textvariable=var, width=75
            ).grid(row=i, column=1, sticky="ew", pady=7)

        self.aba_empresa.columnconfigure(1, weight=1)
        ttk.Button(
            self.aba_empresa, text="Salvar dados da empresa",
            command=self.salvar_empresa
        ).grid(row=6, column=1, sticky="e", pady=15)

    def salvar_empresa(self):
        valores = {k: v.get().strip() for k, v in self.empresa_vars.items()}
        if not valores["nome"]:
            messagebox.showwarning("Validação", "Informe o nome da empresa.")
            return
        with conectar() as conn:
            conn.execute("""
                UPDATE empresa SET nome=?, contato=?, cnpj=?,
                    endereco=?, representantes=? WHERE id=1
            """, (
                valores["nome"], valores["contato"], valores["cnpj"],
                valores["endereco"], valores["representantes"]
            ))
        messagebox.showinfo("Empresa", "Dados da empresa salvos.")

    def criar_aba_cadastros(self, frame, tabela, campos):
        titulo = ttk.Label(
            frame, text=f"Gerenciamento de {tabela}",
            font=("Arial", 14, "bold")
        )
        titulo.pack(anchor="w", pady=(0, 10))

        colunas = [c[0] for c in campos]
        tree = ttk.Treeview(frame, columns=colunas, show="headings", height=18)
        for chave, rotulo in campos:
            tree.heading(chave, text=rotulo)
            tree.column(chave, width=170, anchor="w")
        tree.pack(fill="both", expand=True)
        setattr(self, f"tree_{tabela}", tree)

        botoes = ttk.Frame(frame)
        botoes.pack(fill="x", pady=10)
        ttk.Button(
            botoes, text="Novo cadastro",
            command=lambda: self.form_cadastro(tabela, campos, tree)
        ).pack(side="left", padx=4)
        ttk.Button(
            botoes, text="Editar selecionado",
            command=lambda: self.editar_cadastro(tabela, campos, tree)
        ).pack(side="left", padx=4)
        ttk.Button(
            botoes, text="Excluir selecionado",
            command=lambda: self.excluir_cadastro(tabela, tree)
        ).pack(side="left", padx=4)
        ttk.Button(
            botoes, text="Atualizar lista",
            command=lambda: self.atualizar_lista_cadastro(tabela, tree, campos)
        ).pack(side="left", padx=4)

    def atualizar_lista_cadastro(self, tabela, tree, campos):
        for iid in tree.get_children():
            tree.delete(iid)
        with conectar() as conn:
            registros = conn.execute(
                f"SELECT id, {','.join(c[0] for c in campos)} FROM {tabela} ORDER BY id DESC"
            ).fetchall()
        for reg in registros:
            tree.insert("", "end", iid=str(reg["id"]),
                        values=tuple(reg[c[0]] or "" for c in campos))

    def form_cadastro(self, tabela, campos, tree, registro=None):
        janela = tk.Toplevel(self.root)
        janela.title(("Editar " if registro else "Novo ") + tabela)
        janela.transient(self.root)
        janela.grab_set()
        janela.resizable(False, False)

        vars_campos = {}
        for i, (chave, rotulo) in enumerate(campos):
            ttk.Label(janela, text=rotulo).grid(
                row=i, column=0, padx=12, pady=6, sticky="w"
            )
            var = tk.StringVar(
                value=(registro[chave] or "") if registro else ""
            )
            vars_campos[chave] = var
            ttk.Entry(janela, textvariable=var, width=48).grid(
                row=i, column=1, padx=12, pady=6
            )

        def salvar():
            valores = [vars_campos[c[0]].get().strip() for c in campos]
            if not valores[0]:
                messagebox.showwarning("Validação", "O nome/descrição é obrigatório.")
                return
            with conectar() as conn:
                if registro:
                    atribuicoes = ", ".join(f"{c[0]}=?" for c in campos)
                    conn.execute(
                        f"UPDATE {tabela} SET {atribuicoes} WHERE id=?",
                        valores + [registro["id"]]
                    )
                else:
                    nomes = ", ".join(c[0] for c in campos)
                    marcas = ", ".join("?" for _ in campos)
                    conn.execute(
                        f"INSERT INTO {tabela} ({nomes}) VALUES ({marcas})",
                        valores
                    )
            janela.destroy()
            self.atualizar_lista_cadastro(tabela, tree, campos)
            self.atualizar_combos_documentos()

        ttk.Button(
            janela, text="Salvar", command=salvar
        ).grid(row=len(campos), column=1, padx=12, pady=12, sticky="e")

    def editar_cadastro(self, tabela, campos, tree):
        selecionado = tree.selection()
        if not selecionado:
            messagebox.showwarning("Atenção", "Selecione um registro.")
            return
        with conectar() as conn:
            registro = conn.execute(
                f"SELECT * FROM {tabela} WHERE id=?",
                (int(selecionado[0]),)
            ).fetchone()
        self.form_cadastro(tabela, campos, tree, registro)

    def excluir_cadastro(self, tabela, tree):
        selecionado = tree.selection()
        if not selecionado:
            messagebox.showwarning("Atenção", "Selecione um registro.")
            return
        if not messagebox.askyesno("Confirmar", "Deseja excluir o cadastro selecionado?"):
            return
        try:
            with conectar() as conn:
                conn.execute(f"DELETE FROM {tabela} WHERE id=?", (int(selecionado[0]),))
            campos = {
                "clientes": [("nome", "Nome"), ("documento", "CPF/CNPJ"),
                             ("telefone", "Telefone"), ("email", "E-mail"),
                             ("endereco", "Endereço")],
                "fornecedores": [("nome", "Nome"), ("documento", "CNPJ/CPF"),
                                 ("telefone", "Telefone"), ("email", "E-mail"),
                                 ("endereco", "Endereço")]
            }[tabela]
            self.atualizar_lista_cadastro(tabela, tree, campos)
            self.atualizar_combos_documentos()
        except sqlite3.IntegrityError:
            messagebox.showerror(
                "Cadastro em uso",
                "Este registro está relacionado a documentos e não pode ser excluído."
            )

    def criar_aba_produtos(self):
        frame = self.aba_produtos
        ttk.Label(
            frame, text="Produtos e controle de estoque",
            font=("Arial", 14, "bold")
        ).pack(anchor="w", pady=(0, 10))

        colunas = ("codigo", "descricao", "unidade", "venda", "compra", "estoque", "minimo")
        tree = ttk.Treeview(frame, columns=colunas, show="headings", height=18)
        titulos = {
            "codigo": "Código", "descricao": "Descrição", "unidade": "Unidade",
            "venda": "Preço venda", "compra": "Preço compra",
            "estoque": "Estoque", "minimo": "Estoque mínimo"
        }
        larguras = {"codigo": 90, "descricao": 280, "unidade": 75,
                    "venda": 120, "compra": 120, "estoque": 100, "minimo": 110}
        for c in colunas:
            tree.heading(c, text=titulos[c])
            tree.column(c, width=larguras[c], anchor="w")
        tree.pack(fill="both", expand=True)
        self.tree_produtos = tree

        botoes = ttk.Frame(frame)
        botoes.pack(fill="x", pady=10)
        ttk.Button(botoes, text="Novo produto",
                   command=lambda: self.form_produto()).pack(side="left", padx=4)
        ttk.Button(botoes, text="Editar produto",
                   command=self.editar_produto).pack(side="left", padx=4)
        ttk.Button(botoes, text="Excluir produto",
                   command=self.excluir_produto).pack(side="left", padx=4)
        ttk.Button(botoes, text="Movimentar estoque",
                   command=self.movimentar_estoque).pack(side="left", padx=4)
        ttk.Button(botoes, text="Atualizar",
                   command=self.atualizar_produtos).pack(side="left", padx=4)

    def atualizar_produtos(self):
        tree = self.tree_produtos
        for iid in tree.get_children():
            tree.delete(iid)
        with conectar() as conn:
            rows = conn.execute("SELECT * FROM produtos ORDER BY descricao").fetchall()
        for r in rows:
            tree.insert("", "end", iid=str(r["id"]), values=(
                r["codigo"], r["descricao"], r["unidade"],
                formatar_dinheiro(r["preco_venda"]),
                formatar_dinheiro(r["preco_compra"]),
                formatar_numero(r["estoque"]),
                formatar_numero(r["estoque_minimo"])
            ))

    def form_produto(self, registro=None):
        janela = tk.Toplevel(self.root)
        janela.title("Editar produto" if registro else "Novo produto")
        janela.transient(self.root)
        janela.grab_set()
        campos = [
            ("codigo", "Código"), ("descricao", "Descrição"),
            ("unidade", "Unidade (UN, CX...)"),
            ("preco_venda", "Preço de venda"),
            ("preco_compra", "Preço de compra"),
            ("estoque", "Estoque atual"),
            ("estoque_minimo", "Estoque mínimo")
        ]
        vars_ = {}
        for i, (chave, rotulo) in enumerate(campos):
            ttk.Label(janela, text=rotulo).grid(row=i, column=0, padx=10, pady=6, sticky="w")
            valor = registro[chave] if registro else (
                "UN" if chave == "unidade" else "0"
            )
            var = tk.StringVar(value=str(valor if valor is not None else ""))
            vars_[chave] = var
            ttk.Entry(janela, textvariable=var, width=38).grid(row=i, column=1, padx=10, pady=6)

        def salvar():
            try:
                if not vars_["descricao"].get().strip():
                    raise ValueError("Informe a descrição do produto.")
                venda = dinheiro_para_centavos(vars_["preco_venda"].get())
                compra = dinheiro_para_centavos(vars_["preco_compra"].get())
                estoque = float(vars_["estoque"].get().replace(",", "."))
                minimo = float(vars_["estoque_minimo"].get().replace(",", "."))
                if estoque < 0 or minimo < 0:
                    raise ValueError("Estoque não pode ser negativo.")
                valores = (
                    vars_["codigo"].get().strip(),
                    vars_["descricao"].get().strip(),
                    vars_["unidade"].get().strip() or "UN",
                    venda, compra, estoque, minimo
                )
                with conectar() as conn:
                    if registro:
                        conn.execute("""
                            UPDATE produtos SET codigo=?, descricao=?, unidade=?,
                                preco_venda=?, preco_compra=?, estoque=?, estoque_minimo=?
                            WHERE id=?
                        """, valores + (registro["id"],))
                    else:
                        conn.execute("""
                            INSERT INTO produtos
                            (codigo, descricao, unidade, preco_venda, preco_compra,
                             estoque, estoque_minimo)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, valores)
                janela.destroy()
                self.atualizar_produtos()
                self.atualizar_combos_documentos()
            except (ValueError, InvalidOperation) as erro:
                messagebox.showerror("Dados inválidos", str(erro))

        ttk.Button(janela, text="Salvar", command=salvar).grid(
            row=len(campos), column=1, padx=10, pady=12, sticky="e"
        )

    def editar_produto(self):
        sel = self.tree_produtos.selection()
        if not sel:
            messagebox.showwarning("Atenção", "Selecione um produto.")
            return
        with conectar() as conn:
            reg = conn.execute("SELECT * FROM produtos WHERE id=?", (int(sel[0]),)).fetchone()
        self.form_produto(reg)

    def excluir_produto(self):
        sel = self.tree_produtos.selection()
        if not sel:
            messagebox.showwarning("Atenção", "Selecione um produto.")
            return
        if not messagebox.askyesno("Confirmar", "Excluir o produto selecionado?"):
            return
        with conectar() as conn:
            conn.execute("DELETE FROM produtos WHERE id=?", (int(sel[0]),))
        self.atualizar_produtos()
        self.atualizar_combos_documentos()

    def movimentar_estoque(self):
        sel = self.tree_produtos.selection()
        if not sel:
            messagebox.showwarning("Atenção", "Selecione um produto.")
            return
        produto_id = int(sel[0])
        with conectar() as conn:
            produto = conn.execute("SELECT * FROM produtos WHERE id=?", (produto_id,)).fetchone()

        janela = tk.Toplevel(self.root)
        janela.title("Movimentação de estoque")
        janela.transient(self.root)
        janela.grab_set()
        ttk.Label(janela, text=produto["descricao"], font=("Arial", 11, "bold")).pack(padx=12, pady=10)
        ttk.Label(janela, text=f"Estoque atual: {formatar_numero(produto['estoque'])}").pack()
        tipo = tk.StringVar(value="ENTRADA")
        ttk.Radiobutton(janela, text="Entrada", variable=tipo, value="ENTRADA").pack(anchor="w", padx=15)
        ttk.Radiobutton(janela, text="Saída", variable=tipo, value="SAIDA").pack(anchor="w", padx=15)
        qtd = tk.StringVar()
        ttk.Label(janela, text="Quantidade:").pack(anchor="w", padx=12, pady=(8, 0))
        ttk.Entry(janela, textvariable=qtd).pack(padx=12, pady=5)

        def aplicar():
            try:
                quantidade = float(qtd.get().replace(",", "."))
                if quantidade <= 0:
                    raise ValueError("Informe uma quantidade maior que zero.")
                novo = produto["estoque"] + quantidade if tipo.get() == "ENTRADA" else produto["estoque"] - quantidade
                if novo < 0:
                    raise ValueError("Estoque insuficiente.")
                with conectar() as conn:
                    conn.execute("UPDATE produtos SET estoque=? WHERE id=?", (novo, produto_id))
                janela.destroy()
                self.atualizar_produtos()
            except ValueError as erro:
                messagebox.showerror("Movimentação inválida", str(erro))

        ttk.Button(janela, text="Confirmar movimentação", command=aplicar).pack(pady=12)

    def criar_aba_documentos(self, frame, tipo):
        nomes = {"PROPOSTA": "Propostas comerciais",
                 "VENDA": "Pedidos de venda",
                 "COMPRA": "Pedidos de compra"}
        ttk.Label(
            frame, text=nomes[tipo], font=("Arial", 14, "bold")
        ).pack(anchor="w", pady=(0, 10))

        colunas = ("numero", "data", "pessoa", "total", "status")
        tree = ttk.Treeview(frame, columns=colunas, show="headings", height=18)
        for c, titulo, largura in [
            ("numero", "Número", 130), ("data", "Data", 100),
            ("pessoa", "Cliente / Fornecedor", 330),
            ("total", "Valor total", 150), ("status", "Status", 120)
        ]:
            tree.heading(c, text=titulo)
            tree.column(c, width=largura, anchor="w")
        tree.pack(fill="both", expand=True)
        setattr(self, f"tree_{tipo.lower()}", tree)

        botoes = ttk.Frame(frame)
        botoes.pack(fill="x", pady=10)
        ttk.Button(
            botoes, text="Novo documento",
            command=lambda: self.novo_documento(tipo)
        ).pack(side="left", padx=4)
        ttk.Button(
            botoes, text="Visualizar detalhes",
            command=lambda: self.detalhes_documento(tipo)
        ).pack(side="left", padx=4)
        ttk.Button(
            botoes, text="Gerar PDF",
            command=lambda: self.pdf_documento_selecionado(tipo)
        ).pack(side="left", padx=4)
        ttk.Button(
            botoes, text="Imprimir",
            command=lambda: self.imprimir_documento_selecionado(tipo)
        ).pack(side="left", padx=4)

        if tipo in ("VENDA", "COMPRA"):
            acao = "Concluir venda / baixar estoque" if tipo == "VENDA" else "Receber compra / entrada no estoque"
            ttk.Button(
                botoes, text=acao,
                command=lambda: self.processar_documento(tipo)
            ).pack(side="left", padx=4)

        ttk.Button(
            botoes, text="Atualizar lista",
            command=lambda: self.atualizar_documentos(tipo)
        ).pack(side="left", padx=4)

    def atualizar_documentos(self, tipo):
        tree = getattr(self, f"tree_{tipo.lower()}")
        for iid in tree.get_children():
            tree.delete(iid)
        with conectar() as conn:
            rows = conn.execute(
                "SELECT * FROM documentos WHERE tipo=? ORDER BY id DESC",
                (tipo,)
            ).fetchall()
        for r in rows:
            tree.insert("", "end", iid=str(r["id"]), values=(
                r["numero"], r["data"], r["pessoa_nome"],
                formatar_dinheiro(r["total"]), r["status"]
            ))

    def atualizar_combos_documentos(self):
        # As listas são consultadas no momento em que o formulário abre.
        pass

    def novo_documento(self, tipo):
        if tipo == "COMPRA":
            tabela_pessoa = "fornecedores"
            rotulo_pessoa = "Fornecedor"
        else:
            tabela_pessoa = "clientes"
            rotulo_pessoa = "Cliente"

        with conectar() as conn:
            pessoas = conn.execute(
                f"SELECT id, nome FROM {tabela_pessoa} ORDER BY nome"
            ).fetchall()
            produtos = conn.execute(
                "SELECT * FROM produtos ORDER BY descricao"
            ).fetchall()

        if not pessoas:
            messagebox.showwarning(
                "Cadastro necessário",
                f"Cadastre pelo menos um(a) {rotulo_pessoa.lower()} antes de criar o documento."
            )
            return
        if not produtos:
            messagebox.showwarning(
                "Cadastro necessário",
                "Cadastre pelo menos um produto antes de criar o documento."
            )
            return

        janela = tk.Toplevel(self.root)
        janela.title(f"Novo documento - {tipo}")
        janela.geometry("940x650")
        janela.transient(self.root)
        janela.grab_set()

        ttk.Label(janela, text=f"Novo {tipo}", font=("Arial", 15, "bold")).pack(anchor="w", padx=12, pady=10)
        topo = ttk.Frame(janela, padding=10)
        topo.pack(fill="x")

        numero = proximo_numero(tipo)
        ttk.Label(topo, text=f"Número: {numero}").grid(row=0, column=0, padx=5, sticky="w")
        data_var = tk.StringVar(value=datetime.now().strftime("%d/%m/%Y"))
        ttk.Label(topo, text="Data:").grid(row=0, column=1, padx=5)
        ttk.Entry(topo, textvariable=data_var, width=14).grid(row=0, column=2, padx=5)

        pessoa_var = tk.StringVar()
        mapa_pessoas = {f"{p['id']} - {p['nome']}": p for p in pessoas}
        ttk.Label(topo, text=rotulo_pessoa + ":").grid(row=1, column=0, padx=5, pady=8, sticky="w")
        pessoa_combo = ttk.Combobox(
            topo, textvariable=pessoa_var, values=list(mapa_pessoas.keys()),
            state="readonly", width=48
        )
        pessoa_combo.grid(row=1, column=1, columnspan=2, sticky="w", padx=5)
        pessoa_combo.current(0)

        item_frame = ttk.LabelFrame(janela, text="Adicionar produtos", padding=10)
        item_frame.pack(fill="x", padx=12, pady=5)

        mapa_produtos = {
            f"{p['id']} - {p['descricao']} (Estoque: {formatar_numero(p['estoque'])})": p
            for p in produtos
        }
        produto_var = tk.StringVar()
        ttk.Label(item_frame, text="Produto:").grid(row=0, column=0, sticky="w")
        produto_combo = ttk.Combobox(
            item_frame, textvariable=produto_var,
            values=list(mapa_produtos.keys()), state="readonly", width=62
        )
        produto_combo.grid(row=0, column=1, padx=5, pady=5)
        produto_combo.current(0)

        qtd_var = tk.StringVar(value="1")
        ttk.Label(item_frame, text="Quantidade:").grid(row=0, column=2, padx=5)
        ttk.Entry(item_frame, textvariable=qtd_var, width=10).grid(row=0, column=3, padx=5)

        itens_tree = ttk.Treeview(
            janela, columns=("qtd", "descricao", "unitario", "total"),
            show="headings", height=12
        )
        for c, titulo, largura in [
            ("qtd", "Qtd.", 80), ("descricao", "Descrição", 440),
            ("unitario", "Valor unitário", 150), ("total", "Total item", 150)
        ]:
            itens_tree.heading(c, text=titulo)
            itens_tree.column(c, width=largura, anchor="w")
        itens_tree.pack(fill="both", expand=True, padx=12, pady=8)

        itens = []
        total_var = tk.StringVar(value="R$ 0,00")

        def atualizar_total():
            total_var.set(formatar_dinheiro(sum(i["total_item"] for i in itens)))

        def adicionar():
            try:
                produto = mapa_produtos[produto_var.get()]
                qtd = float(qtd_var.get().replace(",", "."))
                if qtd <= 0:
                    raise ValueError("A quantidade deve ser maior que zero.")
                if tipo == "VENDA" and qtd > produto["estoque"]:
                    raise ValueError(
                        f"Estoque disponível: {formatar_numero(produto['estoque'])}."
                    )
                valor = produto["preco_compra"] if tipo == "COMPRA" else produto["preco_venda"]
                total_item = int(round(qtd * valor))
                itens.append({
                    "produto_id": produto["id"],
                    "codigo": produto["codigo"] or "",
                    "descricao": produto["descricao"],
                    "quantidade": qtd,
                    "valor_unitario": valor,
                    "total_item": total_item
                })
                itens_tree.insert("", "end", values=(
                    formatar_numero(qtd), produto["descricao"],
                    formatar_dinheiro(valor), formatar_dinheiro(total_item)
                ))
                atualizar_total()
            except (ValueError, KeyError) as erro:
                messagebox.showerror("Item inválido", str(erro), parent=janela)

        def excluir_item():
            sel = itens_tree.selection()
            if not sel:
                messagebox.showwarning("Atenção", "Selecione um item.", parent=janela)
                return
            idx = itens_tree.index(sel[0])
            itens_tree.delete(sel[0])
            del itens[idx]
            atualizar_total()

        linha_botoes = ttk.Frame(item_frame)
        linha_botoes.grid(row=0, column=4, padx=5)
        ttk.Button(linha_botoes, text="Adicionar item", command=adicionar).pack(pady=2)
        ttk.Button(linha_botoes, text="Excluir item", command=excluir_item).pack(pady=2)

        rodape = ttk.Frame(janela, padding=12)
        rodape.pack(fill="x")
        ttk.Label(rodape, text="VALOR TOTAL:", font=("Arial", 12, "bold")).pack(side="right", padx=5)
        ttk.Label(rodape, textvariable=total_var, font=("Arial", 14, "bold")).pack(side="right", padx=8)

        obs_var = tk.StringVar()
        ttk.Label(janela, text="Observações:").pack(anchor="w", padx=12)
        ttk.Entry(janela, textvariable=obs_var).pack(fill="x", padx=12, pady=(0, 8))

        def salvar():
            if not itens:
                messagebox.showwarning("Documento vazio", "Adicione pelo menos um produto.", parent=janela)
                return
            pessoa = mapa_pessoas.get(pessoa_var.get())
            if not pessoa:
                messagebox.showwarning("Atenção", f"Selecione um(a) {rotulo_pessoa.lower()}.", parent=janela)
                return
            total = sum(i["total_item"] for i in itens)
            try:
                with conectar() as conn:
                    cur = conn.execute("""
                        INSERT INTO documentos
                        (tipo, numero, data, pessoa_id, pessoa_nome,
                         observacoes, total, status, criado_em)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'ABERTO', ?)
                    """, (
                        tipo, numero, data_var.get().strip(), pessoa["id"],
                        pessoa["nome"], obs_var.get().strip(), total,
                        datetime.now().isoformat(timespec="seconds")
                    ))
                    doc_id = cur.lastrowid
                    for item in itens:
                        conn.execute("""
                            INSERT INTO documento_itens
                            (documento_id, produto_id, codigo, descricao,
                             quantidade, valor_unitario, total_item)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            doc_id, item["produto_id"], item["codigo"],
                            item["descricao"], item["quantidade"],
                            item["valor_unitario"], item["total_item"]
                        ))
                janela.destroy()
                self.atualizar_documentos(tipo)
                if messagebox.askyesno(
                    "Documento salvo",
                    f"{numero} salvo com sucesso.\nDeseja gerar o PDF agora?"
                ):
                    self.gerar_pdf(doc_id)
            except sqlite3.Error as erro:
                messagebox.showerror("Erro no banco", str(erro), parent=janela)

        ttk.Button(rodape, text="Salvar documento", command=salvar).pack(side="left")
        ttk.Button(rodape, text="Cancelar", command=janela.destroy).pack(side="left", padx=6)

    def id_documento_selecionado(self, tipo):
        tree = getattr(self, f"tree_{tipo.lower()}")
        sel = tree.selection()
        if not sel:
            messagebox.showwarning("Atenção", "Selecione um documento.")
            return None
        return int(sel[0])

    def detalhes_documento(self, tipo):
        doc_id = self.id_documento_selecionado(tipo)
        if doc_id:
            self.mostrar_detalhes(doc_id)

    def mostrar_detalhes(self, doc_id):
        with conectar() as conn:
            doc = conn.execute("SELECT * FROM documentos WHERE id=?", (doc_id,)).fetchone()
            itens = conn.execute(
                "SELECT * FROM documento_itens WHERE documento_id=? ORDER BY id",
                (doc_id,)
            ).fetchall()
        if not doc:
            return
        janela = tk.Toplevel(self.root)
        janela.title(f"Detalhes - {doc['numero']}")
        janela.geometry("850x600")
        texto = tk.Text(janela, wrap="word", font=("Consolas", 10))
        texto.pack(fill="both", expand=True, padx=10, pady=10)
        empresa = obter_empresa()
        texto.insert("end", f"{empresa['nome']}\n")
        texto.insert("end", f"{empresa['contato']} | CNPJ: {empresa['cnpj']}\n")
        texto.insert("end", f"{empresa['endereco']}\n")
        texto.insert("end", f"Representantes: {empresa['representantes']}\n\n")
        texto.insert("end", f"{doc['tipo']} - {doc['numero']}\n")
        texto.insert("end", f"Data: {doc['data']}\n")
        texto.insert("end", f"Cliente/Fornecedor: {doc['pessoa_nome']}\n")
        texto.insert("end", f"Status: {doc['status']}\n\n")
        texto.insert("end", "QTD | DESCRIÇÃO | VALOR UNITÁRIO | TOTAL\n")
        texto.insert("end", "-" * 85 + "\n")
        for item in itens:
            texto.insert(
                "end",
                f"{formatar_numero(item['quantidade'])} | {item['descricao']} | "
                f"{formatar_dinheiro(item['valor_unitario'])} | "
                f"{formatar_dinheiro(item['total_item'])}\n"
            )
        texto.insert("end", f"\nVALOR TOTAL: {formatar_dinheiro(doc['total'])}\n")
        if doc["observacoes"]:
            texto.insert("end", f"\nObservações: {doc['observacoes']}\n")
        texto.config(state="disabled")
        botoes = ttk.Frame(janela)
        botoes.pack(pady=8)
        ttk.Button(botoes, text="Gerar PDF", command=lambda: self.gerar_pdf(doc_id)).pack(side="left", padx=5)
        ttk.Button(botoes, text="Imprimir", command=lambda: self.imprimir_pdf(doc_id)).pack(side="left", padx=5)
        ttk.Button(botoes, text="Fechar", command=janela.destroy).pack(side="left", padx=5)

    def pdf_documento_selecionado(self, tipo):
        doc_id = self.id_documento_selecionado(tipo)
        if doc_id:
            self.gerar_pdf(doc_id)

    def imprimir_documento_selecionado(self, tipo):
        doc_id = self.id_documento_selecionado(tipo)
        if doc_id:
            self.imprimir_pdf(doc_id)

    def gerar_pdf(self, doc_id, caminho=None):
        if not PDF_DISPONIVEL:
            messagebox.showerror(
                "Biblioteca ausente",
                "Para gerar PDF, instale a biblioteca:\npip install reportlab"
            )
            return None
        with conectar() as conn:
            doc = conn.execute("SELECT * FROM documentos WHERE id=?", (doc_id,)).fetchone()
            itens = conn.execute(
                "SELECT * FROM documento_itens WHERE documento_id=? ORDER BY id",
                (doc_id,)
            ).fetchall()
        if not doc:
            messagebox.showerror("Erro", "Documento não encontrado.")
            return None
        if caminho is None:
            caminho = filedialog.asksaveasfilename(
                title="Salvar documento em PDF",
                defaultextension=".pdf",
                initialfile=f"{doc['numero']}.pdf",
                filetypes=[("PDF", "*.pdf")]
            )
        if not caminho:
            return None

        empresa = obter_empresa()
        styles = getSampleStyleSheet()
        normal = ParagraphStyle("NormalCustom", parent=styles["Normal"], fontSize=9, leading=13)
        center = ParagraphStyle("CenterCustom", parent=normal, alignment=TA_CENTER)
        right = ParagraphStyle("RightCustom", parent=normal, alignment=TA_RIGHT)
        title = ParagraphStyle(
            "TitleCustom", parent=styles["Title"], fontSize=18,
            textColor=colors.HexColor("#183A5A"), alignment=TA_CENTER
        )
        story = [
            Paragraph(empresa["nome"] or "Empresa", title),
            Paragraph(
                f"{empresa['contato'] or ''} | CNPJ: {empresa['cnpj'] or ''}",
                center
            ),
            Paragraph(empresa["endereco"] or "", center),
            Paragraph(f"Representantes: {empresa['representantes'] or ''}", center),
            Spacer(1, 12),
            Paragraph(f"<b>{doc['tipo']} - {doc['numero']}</b>", normal),
            Paragraph(f"Data: {doc['data']}", normal),
            Paragraph(f"Cliente/Fornecedor: {doc['pessoa_nome']}", normal),
            Paragraph(f"Status: {doc['status']}", normal),
            Spacer(1, 12)
        ]
        dados = [["Qtd.", "Código", "Descrição", "Valor unitário", "Total"]]
        for item in itens:
            dados.append([
                formatar_numero(item["quantidade"]),
                item["codigo"] or "",
                Paragraph(str(item["descricao"]).replace("&", "&amp;"), normal),
                formatar_dinheiro(item["valor_unitario"]),
                formatar_dinheiro(item["total_item"])
            ])
        tabela = Table(
            dados,
            colWidths=[15*mm, 22*mm, 65*mm, 35*mm, 35*mm],
            repeatRows=1
        )
        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#183A5A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (3, 1), (4, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F1F4F7")]),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7)
        ]))
        story.extend([tabela, Spacer(1, 12)])
        story.append(Paragraph(
            f"<b>VALOR TOTAL: {formatar_dinheiro(doc['total'])}</b>",
            right
        ))
        if doc["observacoes"]:
            story.extend([
                Spacer(1, 12),
                Paragraph(f"<b>Observações:</b> {doc['observacoes']}", normal)
            ])
        story.extend([
            Spacer(1, 35),
            Paragraph(
                f"{empresa['representantes'] or ''}<br/>{empresa['contato'] or ''}",
                right
            )
        ])
        try:
            pdf = SimpleDocTemplate(
                caminho, pagesize=A4,
                rightMargin=15*mm, leftMargin=15*mm,
                topMargin=15*mm, bottomMargin=15*mm
            )
            pdf.build(story)
            messagebox.showinfo("PDF", f"PDF gerado:\n{caminho}")
            return caminho
        except Exception as erro:
            messagebox.showerror("Erro ao gerar PDF", str(erro))
            return None

    def imprimir_pdf(self, doc_id):
        if not PDF_DISPONIVEL:
            messagebox.showerror(
                "Biblioteca ausente", "Instale reportlab: pip install reportlab"
            )
            return
        with conectar() as conn:
            doc = conn.execute("SELECT numero FROM documentos WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            return
        caminho = str(Path(tempfile.gettempdir()) / f"{doc['numero']}.pdf")
        if not self.gerar_pdf(doc_id, caminho):
            return
        try:
            if sys.platform == "win32":
                os.startfile(caminho, "print")
            elif sys.platform == "darwin":
                subprocess.Popen(["open", caminho])
            else:
                subprocess.Popen(["xdg-open", caminho])
            messagebox.showinfo(
                "Impressão",
                "O documento foi encaminhado ao aplicativo de PDF. "
                "Se necessário, confirme a impressão no leitor."
            )
        except Exception as erro:
            messagebox.showerror(
                "Impressão", f"Não foi possível iniciar a impressão: {erro}\nPDF: {caminho}"
            )

    def processar_documento(self, tipo):
        doc_id = self.id_documento_selecionado(tipo)
        if not doc_id:
            return
        with conectar() as conn:
            doc = conn.execute("SELECT * FROM documentos WHERE id=?", (doc_id,)).fetchone()
            itens = conn.execute(
                "SELECT * FROM documento_itens WHERE documento_id=?",
                (doc_id,)
            ).fetchall()
            if doc["status"] != "ABERTO":
                messagebox.showinfo("Documento", "Este documento já foi processado.")
                return
            if tipo == "VENDA":
                for item in itens:
                    produto = conn.execute(
                        "SELECT estoque FROM produtos WHERE id=?",
                        (item["produto_id"],)
                    ).fetchone() if item["produto_id"] else None
                    if produto is None or produto["estoque"] < item["quantidade"]:
                        messagebox.showerror(
                            "Estoque insuficiente",
                            f"Não há estoque suficiente para {item['descricao']}."
                        )
                        return
                for item in itens:
                    conn.execute(
                        "UPDATE produtos SET estoque=estoque-? WHERE id=?",
                        (item["quantidade"], item["produto_id"])
                    )
                novo_status = "CONCLUIDO"
            else:
                for item in itens:
                    if item["produto_id"] is not None:
                        conn.execute(
                            "UPDATE produtos SET estoque=estoque+? WHERE id=?",
                            (item["quantidade"], item["produto_id"])
                        )
                novo_status = "RECEBIDO"
            conn.execute(
                "UPDATE documentos SET status=? WHERE id=?",
                (novo_status, doc_id)
            )
        self.atualizar_produtos()
        self.atualizar_documentos(tipo)
        messagebox.showinfo(
            "Processamento concluído",
            "Venda concluída e estoque baixado." if tipo == "VENDA"
            else "Compra recebida e estoque atualizado."
        )

    def atualizar_todas_listas(self):
        self.atualizar_lista_cadastro(
            "clientes", self.tree_clientes,
            [("nome", "Nome"), ("documento", "CPF/CNPJ"),
             ("telefone", "Telefone"), ("email", "E-mail"),
             ("endereco", "Endereço")]
        )
        self.atualizar_lista_cadastro(
            "fornecedores", self.tree_fornecedores,
            [("nome", "Nome"), ("documento", "CNPJ/CPF"),
             ("telefone", "Telefone"), ("email", "E-mail"),
             ("endereco", "Endereço")]
        )
        self.atualizar_produtos()
        for tipo in ("PROPOSTA", "VENDA", "COMPRA"):
            self.atualizar_documentos(tipo)


if __name__ == "__main__":
    inicializar_banco()
    root = tk.Tk()
    app = GestaoComercial(root)
    root.mainloop()
