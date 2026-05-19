#!/usr/bin/env python3
"""Interfaz grafica tipo IDE para YAPar."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent
SYNTACTIC_DIR = ROOT / "Analizador Sintactico"
if str(SYNTACTIC_DIR) not in sys.path:
    sys.path.insert(0, str(SYNTACTIC_DIR))

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
        self.output = tk.Text(
            output_frame,
            wrap="word",
            font=("Menlo", 12),
            borderwidth=1,
            relief="solid",
            state="disabled",
        )
        self.output.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        output_scroll = ttk.Scrollbar(output_frame, orient="vertical", command=self.output.yview)
        output_scroll.grid(row=1, column=1, sticky="ns", pady=(6, 0))
        self.output.configure(yscrollcommand=output_scroll.set)
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
            verbose=self.verbose.get(),
            recover=self.recover.get(),
        )
        self._set_output(result.message)
        self.status.set("OK" if result.ok else "Revisar salida")

    def _set_output(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", tk.END)
        if text:
            self.output.insert("1.0", text)
        self.output.configure(state="disabled")


def _none_if_blank(value: str) -> Optional[str]:
    value = value.strip()
    return value or None


def main() -> int:
    app = YaparIDE()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
