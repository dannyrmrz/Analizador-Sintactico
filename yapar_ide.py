#!/usr/bin/env python3
"""Interfaz grafica tipo IDE para YAPar."""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from tkinter import BooleanVar, StringVar, Text, Tk, filedialog, messagebox
from tkinter import ttk
from typing import Optional

ROOT = Path(__file__).resolve().parent
SYNTACTIC_DIR = ROOT / "Analizador Sintactico"
if str(SYNTACTIC_DIR) not in sys.path:
    sys.path.insert(0, str(SYNTACTIC_DIR))

from semantic_tree import SemanticNode  # noqa: E402
from yapar_runtime import run_yapar  # noqa: E402


class YaparIDE:
    """Pequena IDE local para editar, ejecutar y visualizar YAPar."""

    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("YAPar IDE")
        self.root.geometry("1180x760")

        self.grammar_path = StringVar(value=str(ROOT / "examples" / "calculator_parser.yalp"))
        self.lexer_path = StringVar(value=str(ROOT / "Analizador Lexico" / "examples" / "calculator.yal"))
        self.input_path = StringVar(value=str(ROOT / "examples" / "calculator_input_ok.txt"))
        self.method = StringVar(value="slr")
        self.verbose = BooleanVar(value=False)
        self.status = StringVar(value="Listo")
        self.current_tree: Optional[SemanticNode] = None

        self._build_layout()
        self._load_initial_files()

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)
        toolbar.columnconfigure(4, weight=1)
        toolbar.columnconfigure(7, weight=1)

        self._path_row(toolbar, 0, "Gramatica", self.grammar_path, self.open_grammar, 0)
        self._path_row(toolbar, 0, "Lexer", self.lexer_path, self.open_lexer, 3)
        self._path_row(toolbar, 0, "Entrada", self.input_path, self.open_input, 6)

        controls = ttk.Frame(toolbar)
        controls.grid(row=1, column=0, columnspan=9, sticky="ew", pady=(8, 0))

        ttk.Label(controls, text="Metodo").pack(side="left")
        ttk.Combobox(
            controls,
            textvariable=self.method,
            values=("ll1", "lr0", "slr", "lalr"),
            width=7,
            state="readonly",
        ).pack(side="left", padx=(6, 14))
        ttk.Checkbutton(controls, text="Pasos", variable=self.verbose).pack(side="left")
        ttk.Button(controls, text="Guardar", command=self.save_all).pack(side="left", padx=(14, 4))
        ttk.Button(controls, text="Ejecutar", command=self.run_analysis).pack(side="left", padx=4)
        ttk.Button(controls, text="Exportar JSON", command=self.export_tree_json).pack(side="left", padx=(18, 4))
        ttk.Button(controls, text="Exportar DOT", command=self.export_tree_dot).pack(side="left", padx=4)
        ttk.Label(controls, textvariable=self.status).pack(side="right")

        main = ttk.PanedWindow(self.root, orient="horizontal")
        main.grid(row=1, column=0, sticky="nsew")

        editors = ttk.Notebook(main)
        self.grammar_text = self._text_tab(editors, "Gramatica")
        self.input_text = self._text_tab(editors, "Entrada")
        main.add(editors, weight=2)

        outputs = ttk.Notebook(main)
        self.report_text = self._text_tab(outputs, "Reporte", readonly=True)
        self.tree_text = self._text_tab(outputs, "Arbol texto", readonly=True)
        self.tree_json_text = self._text_tab(outputs, "Arbol JSON", readonly=True)
        self.tree_dot_text = self._text_tab(outputs, "Arbol DOT", readonly=True)

        tree_frame = ttk.Frame(outputs)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree_view = ttk.Treeview(tree_frame, columns=("lexeme", "pos"), show="tree headings")
        self.tree_view.heading("#0", text="Simbolo")
        self.tree_view.heading("lexeme", text="Lexema")
        self.tree_view.heading("pos", text="Linea:Col")
        self.tree_view.column("#0", width=260)
        self.tree_view.column("lexeme", width=170)
        self.tree_view.column("pos", width=90)
        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_view.yview)
        self.tree_view.configure(yscrollcommand=yscroll.set)
        self.tree_view.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        outputs.add(tree_frame, text="Arbol visual")

        main.add(outputs, weight=3)

    def _path_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: StringVar,
        command: object,
        column: int,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 4))
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=column + 1, sticky="ew", padx=(0, 4))
        ttk.Button(parent, text="Abrir", command=command).grid(row=row, column=column + 2, sticky="ew")

    def _text_tab(self, notebook: ttk.Notebook, title: str, readonly: bool = False) -> Text:
        frame = ttk.Frame(notebook)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        text = Text(frame, wrap="none", undo=not readonly, font=("Consolas", 10))
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        if readonly:
            text.configure(state="disabled")
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        notebook.add(frame, text=title)
        return text

    def _load_initial_files(self) -> None:
        self._load_text(self.grammar_path.get(), self.grammar_text)
        self._load_text(self.input_path.get(), self.input_text)

    def open_grammar(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("YAPar", "*.yalp *.yapar"), ("Todos", "*.*")])
        if path:
            self.grammar_path.set(path)
            self._load_text(path, self.grammar_text)

    def open_lexer(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("YALex/Python", "*.yal *.yalex *.py"), ("Todos", "*.*")])
        if path:
            self.lexer_path.set(path)

    def open_input(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Texto", "*.txt"), ("Todos", "*.*")])
        if path:
            self.input_path.set(path)
            self._load_text(path, self.input_text)

    def save_all(self) -> None:
        try:
            self._save_text(self.grammar_path.get(), self.grammar_text)
            if self.input_path.get():
                self._save_text(self.input_path.get(), self.input_text)
        except OSError as exc:
            messagebox.showerror("YAPar IDE", f"No se pudo guardar: {exc}")
            return
        self.status.set("Archivos guardados")

    def run_analysis(self) -> None:
        self.save_all()
        self.status.set("Ejecutando...")
        self._set_text(self.report_text, "")
        self._set_text(self.tree_text, "")
        self._set_text(self.tree_json_text, "")
        self._set_text(self.tree_dot_text, "")
        self._clear_tree_view()

        thread = threading.Thread(target=self._run_analysis_worker, daemon=True)
        thread.start()

    def _run_analysis_worker(self) -> None:
        result = run_yapar(
            grammar_file=self.grammar_path.get(),
            lexer_file=self.lexer_path.get() or None,
            input_file=self.input_path.get() or None,
            method=self.method.get(),
            show_tree=True,
            verbose=self.verbose.get(),
        )
        self.root.after(0, lambda: self._show_result(result.ok, result.message, result.tree))

    def _show_result(self, ok: bool, message: str, tree: Optional[SemanticNode]) -> None:
        self.current_tree = tree if ok else None
        self._set_text(self.report_text, message)
        if self.current_tree is None:
            self.status.set("Rechazado o sin arbol")
            return

        self._set_text(self.tree_text, self.current_tree.pretty())
        self._set_text(self.tree_json_text, json.dumps(self.current_tree.to_dict(), indent=2, ensure_ascii=False))
        self._set_text(self.tree_dot_text, self.current_tree.to_dot())
        self._populate_tree_view(self.current_tree)
        self.status.set("Aceptado")

    def export_tree_json(self) -> None:
        if self.current_tree is None:
            messagebox.showinfo("YAPar IDE", "No hay arbol aceptado para exportar.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            Path(path).write_text(
                json.dumps(self.current_tree.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
                newline="\n",
            )
            self.status.set(f"JSON exportado: {path}")

    def export_tree_dot(self) -> None:
        if self.current_tree is None:
            messagebox.showinfo("YAPar IDE", "No hay arbol aceptado para exportar.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".dot", filetypes=[("DOT", "*.dot")])
        if path:
            Path(path).write_text(self.current_tree.to_dot(), encoding="utf-8", newline="\n")
            self.status.set(f"DOT exportado: {path}")

    def _load_text(self, path: str, widget: Text) -> None:
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError:
            content = ""
        widget.delete("1.0", "end")
        widget.insert("1.0", content)

    def _save_text(self, path: str, widget: Text) -> None:
        if not path:
            return
        Path(path).write_text(widget.get("1.0", "end-1c"), encoding="utf-8", newline="\n")

    def _set_text(self, widget: Text, content: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    def _clear_tree_view(self) -> None:
        for item in self.tree_view.get_children():
            self.tree_view.delete(item)

    def _populate_tree_view(self, root: SemanticNode) -> None:
        self._clear_tree_view()

        def insert(node: SemanticNode, parent: str = "") -> None:
            pos = ""
            if node.line is not None and node.column is not None:
                pos = f"{node.line}:{node.column}"
            item = self.tree_view.insert(
                parent,
                "end",
                text=node.symbol,
                values=(node.lexeme or "", pos),
                open=True,
            )
            for child in node.children:
                insert(child, item)

        insert(root)


def main() -> int:
    root = Tk()
    YaparIDE(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
