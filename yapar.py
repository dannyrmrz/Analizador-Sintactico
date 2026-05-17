#!/usr/bin/env python3
"""CLI principal para YAPar."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parent
SYNTACTIC_DIR = ROOT / "Analizador Sintactico"
if str(SYNTACTIC_DIR) not in sys.path:
    sys.path.insert(0, str(SYNTACTIC_DIR))

from yapar_runtime import emit_parser_runner, run_yapar  # noqa: E402


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="yapar",
        description="Generador/ejecutor YAPar con LL(1), LR(0) y SLR(1).",
    )
    parser.add_argument("grammar_file", help="Archivo .yalp/.yapar")
    parser.add_argument("-l", "--lexer", dest="lexer_file", help="Archivo .yal/.yalex o lexer Python generado")
    parser.add_argument("-o", dest="out_parser", help="Parser runner a generar")
    parser.add_argument("--input", dest="input_file", help="Archivo de entrada a analizar")
    parser.add_argument(
        "--method",
        choices=["ll1", "lr0", "slr", "lalr"],
        default="slr",
        help="Metodo de analisis a usar",
    )
    parser.add_argument("--dot", dest="dot_file", help="Ruta para exportar el automata LR(0) DOT")
    parser.add_argument("--json", dest="json_file", help="Ruta para exportar estructuras JSON")
    parser.add_argument("--verbose", action="store_true", help="Muestra pasos del parser")
    args = parser.parse_args(argv)

    if args.out_parser and not args.lexer_file:
        print("Error: -o requiere -l/--lexer para generar un runner ejecutable.")
        return 1

    if args.out_parser:
        emit_parser_runner(
            output_file=args.out_parser,
            grammar_file=args.grammar_file,
            lexer_file=args.lexer_file,
            method=args.method,
        )
        print(f"Generated parser runner: {args.out_parser}")

    result = run_yapar(
        grammar_file=args.grammar_file,
        lexer_file=args.lexer_file,
        input_file=args.input_file,
        method=args.method,
        dot_file=args.dot_file,
        json_file=args.json_file,
        verbose=args.verbose,
    )
    print(result.message)
    return 0 if result.ok else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
