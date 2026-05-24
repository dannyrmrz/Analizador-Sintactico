#!/usr/bin/env python3
"""Interfaz grafica tipo IDE para YAPar."""
from __future__ import annotations

import sys
import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent
SYNTACTIC_DIR = ROOT / "Analizador Sintactico"
if str(SYNTACTIC_DIR) not in sys.path:
    sys.path.insert(0, str(SYNTACTIC_DIR))

from semantic_tree import SemanticNode  # noqa: E402
from yapar_runtime import run_yapar  # noqa: E402


class YaparIDE(tk.Tk):
    """Pequeno IDE para editar gramaticas y ejecutar YAPar."""

    def __init__(self) -> None:
        super().__init__()
        self.title("YAPar IDE")
        self.geometry("1180x760")
        self.minsize(920, 560)

        self.grammar_path = tk.StringVar()
        self.lexer_path = tk.StringVar()
        self.input_path = tk.StringVar()
        self.dot_path = tk.StringVar()
        self.json_path = tk.StringVar()
        self.method = tk.StringVar(value="slr")
        self.verbose = tk.BooleanVar(value=False)
        self.recover = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Listo")
        self.current_tree: Optional[SemanticNode] = None

        self._build_ui()
        default_grammar = ROOT / "examples" / "calculator_parser.yalp"
        if default_grammar.exists():
            self._load_grammar(default_grammar)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)

        ttk.Button(toolbar, text="Abrir", command=self._browse_grammar).grid(row=0, column=0)
        ttk.Entry(toolbar, textvariable=self.grammar_path).grid(
            row=0, column=1, sticky="ew", padx=(8, 8)
        )
        ttk.Button(toolbar, text="Guardar", command=self._save_grammar).grid(row=0, column=2)
        ttk.Button(toolbar, text="Ejecutar", command=self._run).grid(row=0, column=3, padx=(8, 0))

        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.grid(row=1, column=0, sticky="nsew")

        editor_frame = ttk.Frame(body, padding=(10, 0, 5, 0))
        editor_frame.rowconfigure(1, weight=1)
        editor_frame.columnconfigure(0, weight=1)
        ttk.Label(editor_frame, text="Gramatica YAPar").grid(row=0, column=0, sticky="w")
        self.grammar_editor = tk.Text(
            editor_frame,
            wrap="none",
            undo=True,
            font=("Menlo", 12),
            borderwidth=1,
            relief="solid",
        )
        self.grammar_editor.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        editor_scroll_y = ttk.Scrollbar(editor_frame, orient="vertical", command=self.grammar_editor.yview)
        editor_scroll_y.grid(row=1, column=1, sticky="ns", pady=(6, 0))
        editor_scroll_x = ttk.Scrollbar(editor_frame, orient="horizontal", command=self.grammar_editor.xview)
        editor_scroll_x.grid(row=2, column=0, sticky="ew")
        self.grammar_editor.configure(
            yscrollcommand=editor_scroll_y.set,
            xscrollcommand=editor_scroll_x.set,
        )
        body.add(editor_frame, weight=1)

        output_frame = ttk.Frame(body, padding=(5, 0, 10, 0))
        output_frame.rowconfigure(1, weight=1)
        output_frame.columnconfigure(0, weight=1)
        ttk.Label(output_frame, text="Salida").grid(row=0, column=0, sticky="w")
        output_tabs = ttk.Notebook(output_frame)
        output_tabs.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.output = self._text_tab(output_tabs, "Reporte", wrap="word")
        self.tree_text = self._text_tab(output_tabs, "Arbol texto")
        self.tree_json_text = self._text_tab(output_tabs, "Arbol JSON")
        self.tree_dot_text = self._text_tab(output_tabs, "Arbol DOT")

        tree_frame = ttk.Frame(output_tabs)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree_view = ttk.Treeview(tree_frame, columns=("lexeme", "pos"), show="tree headings")
        self.tree_view.heading("#0", text="Simbolo")
        self.tree_view.heading("lexeme", text="Lexema")
        self.tree_view.heading("pos", text="Linea:Col")
        self.tree_view.column("#0", width=240)
        self.tree_view.column("lexeme", width=150)
        self.tree_view.column("pos", width=80)
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_view.yview)
        self.tree_view.configure(yscrollcommand=tree_scroll.set)
        self.tree_view.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns")
        output_tabs.add(tree_frame, text="Arbol visual")
        body.add(output_frame, weight=1)

        options = ttk.Frame(self, padding=(10, 8))
        options.grid(row=2, column=0, sticky="ew")
        options.columnconfigure(1, weight=1)
        options.columnconfigure(4, weight=1)

        self._path_row(options, 0, "Lexer", self.lexer_path, self._browse_lexer)
        self._path_row(options, 1, "Input", self.input_path, self._browse_input)
        self._path_row(options, 2, "DOT", self.dot_path, self._browse_dot)
        self._path_row(options, 3, "JSON", self.json_path, self._browse_json)

        ttk.Label(options, text="Metodo").grid(row=0, column=3, sticky="w", padx=(20, 6))
        ttk.Combobox(
            options,
            textvariable=self.method,
            values=("ll1", "lr0", "slr", "lalr"),
            state="readonly",
            width=8,
        ).grid(row=0, column=4, sticky="w")
        ttk.Checkbutton(options, text="Verbose", variable=self.verbose).grid(
            row=1, column=4, sticky="w"
        )
        ttk.Checkbutton(options, text="Recover", variable=self.recover).grid(
            row=2, column=4, sticky="w"
        )
        ttk.Button(options, text="Limpiar salida", command=lambda: self._set_output("")).grid(
            row=3, column=4, sticky="w"
        )
        ttk.Button(options, text="Exportar arbol JSON", command=self._export_tree_json).grid(
            row=1, column=5, sticky="w", padx=(10, 0)
        )
        ttk.Button(options, text="Exportar arbol DOT", command=self._export_tree_dot).grid(
            row=2, column=5, sticky="w", padx=(10, 0)
        )

        status_bar = ttk.Label(self, textvariable=self.status, anchor="w", padding=(10, 5))
        status_bar.grid(row=3, column=0, sticky="ew")

    def _path_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command: Callable[[], None],
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, sticky="ew", padx=(8, 8), pady=2
        )
        ttk.Button(parent, text="Buscar", command=command).grid(row=row, column=2, pady=2)

    def _browse_grammar(self) -> None:
        path = filedialog.askopenfilename(
            title="Abrir gramatica YAPar",
            filetypes=(("YAPar", "*.yalp *.yapar"), ("Todos", "*.*")),
        )
        if path:
            self._load_grammar(Path(path))

    def _browse_lexer(self) -> None:
        self._set_path_from_dialog(
            self.lexer_path,
            "Seleccionar lexer",
            (("YALex o Python", "*.yal *.yalex *.py"), ("Todos", "*.*")),
        )

    def _browse_input(self) -> None:
        self._set_path_from_dialog(
            self.input_path,
            "Seleccionar entrada",
            (("Texto", "*.txt"), ("Todos", "*.*")),
        )

    def _browse_dot(self) -> None:
        self._set_save_path_from_dialog(self.dot_path, "Guardar DOT", ".dot")

    def _browse_json(self) -> None:
        self._set_save_path_from_dialog(self.json_path, "Guardar JSON", ".json")

    def _set_path_from_dialog(
        self,
        variable: tk.StringVar,
        title: str,
        filetypes: tuple[tuple[str, str], ...],
    ) -> None:
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        if path:
            variable.set(path)

    def _set_save_path_from_dialog(
        self,
        variable: tk.StringVar,
        title: str,
        extension: str,
    ) -> None:
        path = filedialog.asksaveasfilename(
            title=title,
            defaultextension=extension,
            filetypes=((extension.upper().lstrip("."), f"*{extension}"), ("Todos", "*.*")),
        )
        if path:
            variable.set(path)

    def _load_grammar(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("YAPar IDE", f"No se pudo leer la gramatica:\n{exc}")
            return
        self.grammar_path.set(str(path))
        self.grammar_editor.delete("1.0", tk.END)
        self.grammar_editor.insert("1.0", text)
        self.grammar_editor.edit_modified(False)
        self.status.set(f"Gramatica cargada: {path.name}")

    def _save_grammar(self) -> Optional[Path]:
        raw_path = self.grammar_path.get().strip()
        if not raw_path:
            raw_path = filedialog.asksaveasfilename(
                title="Guardar gramatica",
                defaultextension=".yalp",
                filetypes=(("YAPar", "*.yalp *.yapar"), ("Todos", "*.*")),
            )
            if not raw_path:
                return None
            self.grammar_path.set(raw_path)

        path = Path(raw_path)
        try:
            path.write_text(self.grammar_editor.get("1.0", "end-1c"), encoding="utf-8", newline="\n")
        except OSError as exc:
            messagebox.showerror("YAPar IDE", f"No se pudo guardar la gramatica:\n{exc}")
            return None
        self.grammar_editor.edit_modified(False)
        self.status.set(f"Gramatica guardada: {path.name}")
        return path

    def _run(self) -> None:
        grammar = self._save_grammar()
        if grammar is None:
            self.status.set("Ejecucion cancelada: falta gramatica")
            return

        self.status.set("Ejecutando YAPar...")
        self.update_idletasks()

        result = run_yapar(
            grammar_file=str(grammar),
            lexer_file=_none_if_blank(self.lexer_path.get()),
            input_file=_none_if_blank(self.input_path.get()),
            method=self.method.get(),
            dot_file=_none_if_blank(self.dot_path.get()),
            json_file=_none_if_blank(self.json_path.get()),
            show_tree=True,
            verbose=self.verbose.get(),
            recover=self.recover.get(),
        )
        self._set_output(result.message)
        self._set_tree(result.tree if result.ok else None)
        self.status.set("OK" if result.ok else "Revisar salida")

    def _text_tab(self, notebook: ttk.Notebook, title: str, wrap: str = "none") -> tk.Text:
        frame = ttk.Frame(notebook)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        text = tk.Text(
            frame,
            wrap=wrap,
            font=("Menlo", 12),
            borderwidth=1,
            relief="solid",
            state="disabled",
        )
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        notebook.add(frame, text=title)
        return text

    def _set_output(self, text: str) -> None:
        self._set_text(self.output, text)

    def _set_text(self, widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        if text:
            widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _set_tree(self, tree: Optional[SemanticNode]) -> None:
        self.current_tree = tree
        self._set_text(self.tree_text, tree.pretty() if tree else "")
        self._set_text(
            self.tree_json_text,
            json.dumps(tree.to_dict(), indent=2, ensure_ascii=False) if tree else "",
        )
        self._set_text(self.tree_dot_text, tree.to_dot() if tree else "")
        self._clear_tree_view()
        if tree:
            self._insert_tree_node(tree)

    def _clear_tree_view(self) -> None:
        for item in self.tree_view.get_children():
            self.tree_view.delete(item)

    def _insert_tree_node(self, node: SemanticNode, parent: str = "") -> None:
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
            self._insert_tree_node(child, item)

    def _export_tree_json(self) -> None:
        if self.current_tree is None:
            messagebox.showinfo("YAPar IDE", "No hay arbol aceptado para exportar.")
            return
        path = filedialog.asksaveasfilename(
            title="Guardar arbol JSON",
            defaultextension=".json",
            filetypes=(("JSON", "*.json"), ("Todos", "*.*")),
        )
        if path:
            Path(path).write_text(
                json.dumps(self.current_tree.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
                newline="\n",
            )

    def _export_tree_dot(self) -> None:
        if self.current_tree is None:
            messagebox.showinfo("YAPar IDE", "No hay arbol aceptado para exportar.")
            return
        path = filedialog.asksaveasfilename(
            title="Guardar arbol DOT",
            defaultextension=".dot",
            filetypes=(("DOT", "*.dot"), ("Todos", "*.*")),
        )
        if path:
            Path(path).write_text(self.current_tree.to_dot(), encoding="utf-8", newline="\n")


def _none_if_blank(value: str) -> Optional[str]:
    value = value.strip()
    return value or None


def main() -> int:
    app = YaparIDE()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
